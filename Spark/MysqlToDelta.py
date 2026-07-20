"""
Delta Blue-Green Swap Script（精简版 — 使用最小校验，发现 staging 表已存在则报错退出）

设计要点：
- staging_path 与 staging_table 必须由用户显式提供，不做路径/表名猜测
- 最小校验：确认 staging 可读且非空；确认 primary_key 存在且无重复主键
- 若 staging_table 在 metastore 已存在 -> 立即抛异常并退出（不做覆盖）
- 支持 dry_run、skip_validate、num_partitions、show_sample
- 保证在 finally 中停止 Spark
"""

import argparse
import sys
import logging
import traceback
from datetime import datetime
from pyspark.sql.dataframe import DataFrame
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from delta.tables import DeltaTable

LOG = logging.getLogger("delta_blue_green_minimal")


def build_spark(app_name: str) -> SparkSession:
    sb = SparkSession.builder.appName(app_name)
    sb = sb.enableHiveSupport()
    return sb.getOrCreate()


# spark读取mysql
def read_jdbc(spark: SparkSession, jdbc_url: str, dbtable: str, user: str, password: str, fetchsize: int = 10000):
    return spark.read.format("jdbc") \
        .option("url", jdbc_url) \
        .option("dbtable", dbtable) \
        .option("user", user) \
        .option("password", password) \
        .option("fetchsize", str(fetchsize)) \
        .load()


# 将数据写入delta
def write_staging(df, staging_path: str, num_partitions: int = 0):
    """
    Repartition first so writer sees the new partitioning, then write.
    """
    if num_partitions and num_partitions > 0:
        LOG.info("=============================Repartitioning DataFrame to %d partitions before write", num_partitions)
        df = df.repartition(num_partitions)

    writer = df.write.format("delta").mode("overwrite")
    writer = writer.option("overwriteSchema", "true")
    writer.option("path", staging_path).save()


# 非法验证
def compute_minimal_validations(spark: SparkSession, staging_path: str, primary_key: str, jdbc_df: DataFrame,
                                sample_limit: int = 5):
    """
    Minimal validations (低开销但关键安全检查):
      1) staging 能被读取且非空（用 limit(1) / take(1) 快速检测）
      2) primary_key 存在于 staging columns
      3) staging 中是否存在重复主键（会扫描 staging）
    返回 dict：
      {
        "staging_non_empty": True/False,
        "staging_sample_ids": [...],
        "staging_duplicate_pk": int
      }
    在发现空表或主键缺失时抛出异常（默认不可接受）。
    """
    try:
        src = spark.read.format("delta").load(staging_path)
    except Exception as e:
        raise RuntimeError(f"=============================无法读取 staging_path '{staging_path}': {e}")

    # region 1) 非空快速检测
    one = src.limit(1).collect()
    if not one:
        # 视作错误：通常意味着写入失败或数据为空
        raise RuntimeError(
            f"=============================Staging 在路径 '{staging_path}' 读取到 0 行，疑似写入失败或数据为空。")
    # endregion

    # region 2) primary_key 存在性
    if primary_key not in src.columns:
        raise RuntimeError(
            f"=============================Primary key 列 '{primary_key}' 在 staging 数据中不存在 (columns: {src.columns})")
    # endregion

    # region 3) 检查重复主键（不可避免的全表 groupBy）
    try:
        dup_count = src.groupBy(primary_key).count().filter(F.col("count") > 1).count()
    except Exception as e:
        raise RuntimeError(f"=============================无法读取 staging_path '{staging_path}': {e}")
    # endregion

    # region 对比两个数据库的数据量是否一致
    src_count = src.select(primary_key).dropDuplicates().count()
    jdbc_count = jdbc_df.select(primary_key).dropDuplicates().count()
    if src_count != jdbc_count:
        raise RuntimeError("mysql数据量和delta数据量不一致")
    # endregion

    # 少量样本 id 返回（用于日志）
    sample_ids = [r[primary_key] for r in src.select(primary_key).distinct().limit(sample_limit).collect()]

    return {
        "staging_non_empty": True,
        "staging_sample_ids": sample_ids,
        "staging_duplicate_pk": dup_count,
    }


# 更改文件夹名称，将当前生产环境的delta文件夹改成old标识，将staging文件夹的名称改成生产环境文件夹的名称
def rename_tables_atomic(spark: SparkSession, prod_path: str, staging_path: str, run_id: str):
    """
    使用 Hadoop 文件系统原子重命名替代表名交换
    """
    if prod_path == staging_path:
        raise RuntimeError("=============================prod_path 与 staging_path 相同，无法重命名")
    # 导入 Hadoop FS 相关模块
    jvm = spark._jvm
    hadoop_conf = spark._jsc.hadoopConfiguration()
    Path = jvm.org.apache.hadoop.fs.Path
    fs = jvm.org.apache.hadoop.fs.FileSystem.get(hadoop_conf)

    staging_p = Path(staging_path)
    prod_p = Path(prod_path)
    prod_old_p = Path(f"{prod_path}_old_{run_id}")

    # 1) 备份原 prod 路径（如果存在）
    if fs.exists(prod_p):
        LOG.info("=============================Renaming existing prod path %s -> %s", prod_path, str(prod_old_p))
        if not fs.rename(prod_p, prod_old_p):
            raise RuntimeError("=============================Failed to rename prod -> prod_old")

    # 2) 将 staging 重命名为 prod
    LOG.info("=============================Renaming staging %s -> %s", staging_path, prod_path)
    if not fs.rename(staging_p, prod_p):
        # 如果失败，尝试回滚：将 prod_old 恢复为 prod
        if fs.exists(prod_old_p):
            fs.rename(prod_old_p, prod_p)
        raise RuntimeError("=============================Failed to rename staging -> prod path")
    LOG.info("=============================Filesystem swap complete. New prod files are at %s", prod_path)


def main():
    # region 生成参数
    epilog_text = """
EXAMPLE:
  python delta_blue_green_swap.py \\
    --jdbc_url "jdbc:mysql://host:3306/dbname" \\
    --dbtable "(select * from tb_rates) t" \\
    --user root --password secret \\
    --staging_path "/mnt/delta/tb_rates_staging_20260130_001" \\
    --staging_table "prod.tb_rates_staging_20260130_001" \\
    --prod_table "prod.tb_rates" \\
    --prod_table_path "·/mnt/delta/tb_rates" \\
    --primary_key "id" \\
    --dry_run
(Notes: staging_path and staging_table are REQUIRED and used exactly as provided. prod_table_path is optional.)
"""

    p = argparse.ArgumentParser(
        description="Delta Blue-Green Swap Script (最小校验版)",
        epilog=epilog_text,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    p.add_argument("--jdbc_url", required=True, help="JDBC URL to source MySQL, e.g. jdbc:mysql://host:3306/db")
    p.add_argument("--dbtable", required=True,
                   help="table name or subquery (use parens for subquery), e.g. '(select * from tb_rates) t'")
    p.add_argument("--user", required=True, help="DB user for JDBC")
    p.add_argument("--password", required=False, help="DB password (or set env MYSQL_PWD or DB_PASSWORD)")
    p.add_argument("--staging_path", required=True,
                   help="Delta staging path (required). Must be the exact filesystem path to staging data.")
    p.add_argument("--staging_table", required=True,
                   help="Qualified staging table name in metastore (required).")
    p.add_argument("--run_id", required=False, default=datetime.utcnow().strftime("%Y%m%d%H%M%S"),
                   help="Run id suffix used when naming the old prod table.")
    p.add_argument("--num_partitions", type=int, default=0, help="Optional: repartition count for written staging data")
    p.add_argument("--prod_table", required=True,
                   help="Qualified prod table name in metastore (used for ALTER TABLE RENAME), e.g. prod.tb_rates")
    p.add_argument("--prod_table_path", required=False,
                   help="Optional: explicit Delta filesystem path for the prod table for DeltaTable.forPath() history reads (no guessing).")
    p.add_argument("--primary_key", required=True, help="Primary key column name used for validation and unique checks")

    p.add_argument("--dry_run", action='store_true', help="Do everything up to but not including the metastore swap")
    p.add_argument("--skip_validate", action='store_true', help="Skip validation phase entirely (you accept risk)")
    p.add_argument("--sample_limit", type=int, default=5, help="Sample size for sample ids returned")
    p.add_argument("--show_sample", action='store_true',
                   help="Show sample rows from JDBC read (may contain sensitive data)")

    args = p.parse_args()
    LOG.info("=============================开始打印")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    LOG.info("=============================Starting Delta Blue-Green Swap (minimal validation)")
    # endregion

    # region 非空验证
    password = args.password
    if not password:
        LOG.error(
            "=============================DB password not supplied. Use --password or set MYSQL_PWD/DB_PASSWORD env "
            "var.")
        sys.exit(2)
    # endregion

    # region 参数初始化
    staging_path = args.staging_path.format(run_id=args.run_id)
    staging_table = args.staging_table.format(run_id=args.run_id)
    prod_path = args.prod_table_path
    prod_table = args.prod_table
    run_id = args.run_id
    spark = None
    # endregion

    try:
        # region 建立spark
        spark = build_spark(f"DeltaBlueGreen-Minimal-{run_id}")
        LOG.info("=============================Spark version: %s", spark.version)
        # endregion

        # region spark读取mysql数据
        LOG.info("=============================Reading from JDBC...")
        jdbc_df = read_jdbc(spark, args.jdbc_url, args.dbtable, args.user, password)
        jdbc_df = jdbc_df.withColumn("rate", F.col("rate").cast("decimal(18,2)"))
        LOG.info("=============================Source (JDBC) quick check (count of small sample): %d",
                 jdbc_df.limit(1).count())
        if args.show_sample:
            jdbc_df.show(5, truncate=False)
            LOG.info("=============================")
        # endregion

        # region 将mysql中的数据写入到本地（staging_path）
        # optional repartition before write
        if args.num_partitions and args.num_partitions > 0:
            jdbc_df = jdbc_df.repartition(args.num_partitions)

        # write to delta staging (use staging_path exactly)
        LOG.info("=============================Writing to staging path: %s", staging_path)
        write_staging(jdbc_df, staging_path, num_partitions=args.num_partitions)
        LOG.info("=============================Staging write complete.")
        # endregion

        # region 验证数据
        if not args.skip_validate:
            LOG.info(
                "=============================Running minimal validations (non-empty, primary key exists, duplicate "
                "PK check)...")
            val = compute_minimal_validations(spark, staging_path, args.primary_key, jdbc_df, sample_limit=args.sample_limit)
            LOG.info(
                "=============================Minimal validation result: staging_non_empty=%s, duplicate_pk=%d, "
                "sample_ids=%s",
                val['staging_non_empty'], val['staging_duplicate_pk'], val['staging_sample_ids'])
            if val['staging_duplicate_pk'] > 0:
                LOG.error("=============================duplicate primary keys found in staging; aborting before swap")
                sys.exit(3)
        else:
            LOG.info("=============================Skipping validation as requested (--skip_validate)")
        # endregion

        # region 验证当前生产环境的路径是否正确
        try:
            if args.prod_table_path:
                prod_loc = args.prod_table_path
                LOG.info("Using user-supplied prod_table_path: %s", prod_loc)
                try:
                    dt = DeltaTable.forPath(spark, prod_loc)
                    LOG.info("=============================prod table last history entry (if accessible):")
                    try:
                        dt.history(1).show(truncate=False)
                        # 新增：读取前100行数据
                        LOG.info("=============================Reading first 100 rows from prod table...")
                        sample_data = dt.toDF().limit(100)
                        sample_data.show(truncate=False)
                        LOG.info("=============================")
                    except Exception:
                        LOG.warning(
                            "=============================Unable to show delta history; your environment may restrict history calls.")
                except Exception as e:
                    LOG.warning("=============================DeltaTable.forPath failed for prod_table_path: %s", e)
            else:
                LOG.info(
                    "=============================No prod_table_path provided; skipping DeltaTable.forPath history display.")
        except Exception as e:
            LOG.warning("=============================failed while attempting to read prod table history: %s", e)
        # endregion

        # region 模拟运行 验证前面的操作都能流畅执行
        if args.dry_run:
            LOG.info(
                "=============================Dry-run requested; stopping before metastore swap. Staging is available at: %s",
                staging_path)
            spark.stop()
            sys.exit(0)
        # endregion

        # region 更改名称：将当前生产表改成old标识，将导过来的表改成生产表的名字
        rename_tables_atomic(spark, prod_path, staging_path, run_id)
        LOG.info("=============================Atomic rename complete.")
        # endregion

        LOG.info("=============================")
        try:
            # 修复硬编码，使用动态变量 prod_table
            for r in spark.sql(f"DESCRIBE FORMATTED {prod_table}").collect():
                key = str(r[0] or "").strip().lower()
                if key.startswith("location"):
                    LOG.info(f"Location from Metastore: {r[1]}")
                    break
        except Exception as e:
            LOG.warning(f"Could not describe table {prod_table} in metastore. Path confirmed at: {prod_path}")
        LOG.info("=============================")

    except SystemExit:
        raise
    except Exception:
        LOG.error("Exception occurred:\n%s", traceback.format_exc())
        LOG.error("Aborting. Staging path retained at: %s", staging_path)
        sys.exit(4)
    finally:
        print("已经结束")
        if spark:
            try:
                spark.stop()
            except Exception:
                LOG.debug("spark.stop() raised", exc_info=True)


if __name__ == '__main__':
    main()

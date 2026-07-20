from delta.tables import DeltaTable
from pyspark import StorageLevel
from pyspark.sql.functions import (
    col, from_json, coalesce, when, lit, struct, max as spark_max
)
from pyspark.sql.types import TimestampType
from confluent_kafka import Producer
import Model.Config
from Model.Message.Message import (
    ENVELOPE_USERINFO_SCHEMA, KEY_SCHEMA
)
from Until.SparkCommon import json_list_to_array_bytes

delta_path = Model.Config.SPARK_DELTA_USERINFO

def delivery_report(err, msg):
    if err is not None:
        print("Message delivery failed:", err)
    else:
        print(f"Delivered to {msg.topic()} [{msg.partition()}] @ offset {msg.offset()}")


def process(batch_df, batch_id, spark, kafka_bootstrap):
    # 注意：foreachBatch 在 driver 上执行，可以做 show / 写入外部系统等
    print("=== New batch:", batch_id, "=== for topic dbserver1.test.tb_userinfo")

    # region 如果批次为空，直接返回
    if len(batch_df.head(1)) == 0:
        print("Batch is empty")
        return
    # endregion

    # region 1) 打印基础信息与前 50 条原始消息（key/value 以字符串显示；value 可能为 NULL）
    # 我们把 key/value cast 为 string（NULL 仍然是 NULL），方便观察 tombstone
    raw_view = (batch_df
    .select(
        col("topic"),
        col("partition"),
        col("offset"),
        col("kafka_ts"),
        col("key").cast("string").alias("key_str"),
        col("value").cast("string").alias("value_str")
    ))
    print(">>> Raw messages (first 50 rows):")
    raw_view.show(50, truncate=False)
    # endregion

    # region 2) 尝试把 value 解析为 Debezium envelope（如果 value 为 NULL，则解析列为 NULL）
    # 从 envelope 中展开 after/before 字段（可能为 NULL）
    parsed_env = (batch_df
    .withColumn("value_str", col("value").cast("string"))
    .withColumn("envelope", from_json(col("value_str"), ENVELOPE_USERINFO_SCHEMA))
    .withColumn("after_id", col("envelope.after.id"))
    .withColumn("after_user_name", col("envelope.after.user_name"))
    .withColumn("after_real_name", col("envelope.after.real_name"))
    .withColumn("after_country_id", col("envelope.after.country_id"))
    .withColumn("after_updatetime", col("envelope.after.updatetime"))
    .withColumn("before_id", col("envelope.before.id"))
    .withColumn("before_user_name", col("envelope.before.user_name"))
    .withColumn("before_real_name", col("envelope.before.real_name"))
    .withColumn("before_country_id", col("envelope.before.country_id"))
    .withColumn("before_updatetime", col("envelope.before.updatetime"))
    .withColumn("op_from_envelope", col("envelope.op"))
    .withColumn("ts_ms", col("envelope.ts_ms"))
    .select(
        col("topic"),
        col("partition"),
        col("offset"),
        col("kafka_ts"),
        col("key").cast("string").alias("key_str"),
        col("value_str"),
        col("after_id"), col("after_user_name"), col("after_real_name"), col("after_country_id"), col("after_updatetime"),
        col("before_id"), col("before_user_name"), col("before_real_name"), col("before_country_id"), col("before_updatetime"),
        col("op_from_envelope"), col("ts_ms")
    ))

    print(">>> Parsed envelope attempts (first 50 rows):")
    parsed_env.show(50, truncate=False)
    # endregion

    # region 3) 从 key 尝试解析 id（支持 key 为 JSON {"id":"..."} 或直接字符串）
    key_parsed = parsed_env.withColumn("key_json", from_json(col("key_str"), KEY_SCHEMA)) \
        .withColumn("key_id", col("key_json.id"))
    # endregion

    # region 4) 归一化：优先使用 after，其次 before；如果 value 为 NULL（tombstone），则使用 key_id
    normalized = (key_parsed
                  .withColumn("id",
                              coalesce(col("after_id"), col("before_id"), col("key_id"), col("key_str")))
                  .withColumn("user_name",
                              coalesce(col("after_user_name"), col("before_user_name")))
                  .withColumn("real_name",
                              coalesce(col("after_real_name"), col("before_real_name")))
                  .withColumn("country_id",
                              coalesce(col("after_country_id"), col("before_country_id")))
                  .withColumn("updatetime",
                              coalesce(col("after_updatetime"), col("before_updatetime")))
                  .withColumn("op",
                              when(col("value_str").isNull(), lit("d")).otherwise(col("op_from_envelope")))
                  .withColumn("event_ts",
                              when(col("ts_ms").isNotNull(),
                                   (col("ts_ms") / 1000).cast(TimestampType())).otherwise(col("kafka_ts")))
                  .withColumn("is_tombstone", col("value_str").isNull())
                  .select("topic", "partition", "offset", "kafka_ts", "key_str",
                          "value_str", "id", "user_name", "real_name", "country_id", "updatetime", "op", "ts_ms", "event_ts", "is_tombstone")
                  )

    print(">>> Normalized view (first 50 rows):")
    # 可根据数据量决定存储级别
    normalized = normalized.persist(StorageLevel.MEMORY_AND_DISK)
    # 触发一次 action 来 materialize cache（如果你需要后续多次重用）
    # 使用 count() 会扫描全部 partition 并填满缓存；如果你只需要缓存被后续多次使用且要保证完整缓存，使用 count()
    normalized.count()  # materialize into cache; 代价 = 一次完整计算
    normalized.show(50, truncate=False)
    # endregion

    # region 5) 选每个 id 的“最新”行：用 groupBy + max(struct(...))
    # struct 的字段顺序即比较顺序：先 event_ts，再 partition，再 offset
    cmp_struct = struct(
        col("event_ts").cast("long").alias("event_ts_unix"),
        col("partition"),
        col("offset"),
        col("user_name"),
        col("real_name"),
        col("country_id"),
        col("updatetime"),
        col("op"),
        col("value_str")
    )

    best_per_id = (
        normalized
        .where(col("id").isNotNull())
        .groupBy("id")
        .agg(spark_max(cmp_struct).alias("best"))
    )

    latest_per_id = best_per_id.select(
        col("id"),
        col("best.user_name").alias("user_name"),
        col("best.real_name").alias("real_name"),
        col("best.country_id").alias("country_id"),
        col("best.updatetime").alias("updatetime"),
        col("best.op").alias("op"),
        col("best.event_ts_unix").cast(TimestampType()).alias("event_ts")
    )
    # endregion

    # region 6) 构造 upsert_df（只包含 op != 'd' 的最新行）
    upsert_df = latest_per_id.filter((col("op") != "d") & col("id").isNotNull())

    print(">>> upsert_df view (first 50 rows):")
    upsert_df.show(50, truncate=False)
    # endregion

    # region 7) deletes（仍然取最新一条里标记为 delete 的 id）
    deletes_df = latest_per_id.filter((col("op") == "d") & col("id").isNotNull()).select("id").dropDuplicates(["id"])
    print(">>> deletes_df view (first 50 rows):")
    deletes_df.show(50, truncate=False)
    # endregion

    # region 8) 持久化到 Delta（支持首次创建表）
    # 如果 upsert_df 非空：进行 merge upsert（当表不存在则创建）
    table_exists = False
    delta_tbl = None
    try:
        delta_tbl = DeltaTable.forPath(spark, delta_path)
        table_exists = True
        print("存在")
    except Exception as e:
        # 表不存在或路径不可访问
        table_exists = False
        print("不存在")
        print(e)

    if len(upsert_df.head(1)) > 0:
        if not table_exists:
            # 如果表不存在，用 upsert_df 初始化 Delta 表（append 会创建目录）
            print("Delta table not found. Creating new Delta table at:", delta_path)
            upsert_df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").save(delta_path)
            table_exists = True
        else:
            # 使用 merge 更新/插入所有列
            delta_tbl.alias("t").merge(
                source=upsert_df.alias("s"),
                condition="t.id = s.id"
            ).whenMatchedUpdate(
                condition="s.event_ts > t.event_ts OR t.event_ts IS NULL",
                set={
                    "id": "s.id",
                    "user_name": "s.user_name",
                    "real_name": "s.real_name",
                    "country_id": "s.country_id",
                    "updatetime": "s.updatetime",
                    "event_ts": "s.event_ts"
                }
            ).whenNotMatchedInsertAll().execute()
            print("Merged upserted rows into Delta.")
    # endregion

    # region 9) 处理删除：对存在的 Delta 表执行删除（用 merge ... whenMatchedDelete）
    if table_exists and len(deletes_df.head(1)) > 0:
        # merge deletes_df to delete matching rows
        delta_tbl.alias("t").merge(
            source=deletes_df.alias("s"),
            condition="t.id = s.id"
        ).whenMatchedDelete().execute()

        print("Applied deletes (tombstones / op=='d') to Delta.")
    # endregion

    # region 10) 批次后查询并打印 Delta 中受影响的记录（以本批次 id 作为过滤） 验证***************
    # 收集本批次的 id 到 driver（限量以防爆内存）
    batch_ids = (normalized.select("id")
                 .where(col("id").isNotNull())
                 .distinct()
                 .limit(1000)  # 限制到前 1000 个 id 做回显
                 .rdd.map(lambda r: r[0])
                 .collect())

    if len(batch_ids) == 0:
        print("No ids parsed in this batch to query from Delta.")
    else:
        print(f"Querying Delta for up to {len(batch_ids)} ids from this batch (showing up to 50 rows):")
        delta_df = spark.read.format("delta").load(delta_path)
        delta_df.filter(col("id").isin(batch_ids)).show(50, truncate=False)
        delta_df.show(50, truncate=False)
    # endregion

    # region 统计信息 验证****************
    total = batch_df.count()
    tombstones = batch_df.filter(col("value").isNull()).count()
    parsed_success = normalized.filter(col("id").isNotNull()).count()
    print(
        f"Batch {batch_id} total rows: {total}, tombstones (value is NULL): {tombstones}, rows with id parsed (after ensure): {parsed_success}")

    # endregion

    # region 11）给dask发送消息重新加载数据
    # 释放内测
    normalized.unpersist()
    latest_version = DeltaTable.forPath(spark, delta_path).history(1).select("version").collect()[0][0]
    print("latest version:", latest_version)
    # 创建测试生产者实例
    # TOPIC = "test-topic"
    #
    # conf = {
    #     "bootstrap.servers": kafka_bootstrap,
    #     # 如果使用 SASL/SSL，打开下面示例并填写
    #     # "security.protocol": "SASL_PLAINTEXT",
    #     # "sasl.mechanisms": "SCRAM-SHA-512",
    #     # "sasl.username": "your-user",
    #     # "sasl.password": "your-pass",
    #     # "socket.timeout.ms": 10000,
    # }
    # p = Producer(conf)
    #
    # key = "change"
    # value = str(latest_version)
    # try:
    #     p.produce(TOPIC, key=key.encode("utf-8"), value=value.encode("utf-8"), callback=delivery_report)
    # except BufferError as e:
    #     print("Local producer queue is full ({}) — waiting...".format(e))
    #     p.flush()
    #     p.produce(TOPIC, key=key.encode("utf-8"), value=value.encode("utf-8"), callback=delivery_report)

    json_rows = latest_per_id.toJSON().collect()
    if json_rows:
        TOPIC = "change-userinfo"

        conf = {
            "bootstrap.servers": kafka_bootstrap,
            # 如果使用 SASL/SSL，打开下面示例并填写
            # "security.protocol": "SASL_PLAINTEXT",
            # "sasl.mechanisms": "SCRAM-SHA-512",
            # "sasl.username": "your-user",
            # "sasl.password": "your-pass",
            # "socket.timeout.ms": 10000,
        }
        p = Producer(conf)

        key = str(latest_version)
        value = json_list_to_array_bytes(json_rows)
        try:
            p.produce(TOPIC, key=key.encode("utf-8"), value=value, callback=delivery_report)
        except BufferError as e:
            print("Local producer queue is full ({}) — waiting...".format(e))
            p.flush()
            p.produce(TOPIC, key=key.encode("utf-8"), value=value, callback=delivery_report)
        p.poll(0)
        print("Flushing...")
        p.flush(10)
    # endregion

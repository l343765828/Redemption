from pyspark.sql import SparkSession
from pyspark.sql.functions import col
import importlib
from pathlib import Path

# region # ------------ 配置 ------------
kafka_bootstrap = "my-cluster-kafka-bootstrap.kafka-prod.svc.cluster.local:9092"
topic = "dbserver1.test.tb_user,dbserver1.test.tb_rates,dbserver1.test.tb_userinfo"
checkpoint_location = "/mnt/delta/checkpoints/debezium_to_delta_inspect"
# endregion

# region # ------------ Spark 会话 ------------
spark = SparkSession.builder \
    .appName("kafka_inspect_app") \
    .getOrCreate()

spark.sparkContext.setLogLevel("WARN")
# endregion

# region # ------------ 读取 Kafka 流 ------------
raw_df = (spark.readStream
          .format("kafka")
          .option("kafka.bootstrap.servers", kafka_bootstrap)
          .option("subscribe", topic)
          .option("startingOffsets", "earliest")
          .option("failOnDataLoss", "false")
          .load())

# 我们只关心这些列：保留原始二进制 key/value 以便检查 tombstone（value == NULL）
selected = raw_df.select(
    col("topic"),
    col("partition"),
    col("offset"),
    col("timestamp").alias("kafka_ts"),
    col("key"),
    col("value")
)


# endregion


# region ------------ 每个批次的处理函数 ------------
def add_path(p):
    import sys
    if p not in sys.path:
        sys.path.insert(0, p)
        return True
    return False


def process_message(batch_df, batch_id):
    # region 将当前路径添加到sys.path中，避免读取不到
    here = Path(__file__).resolve().parent
    project_root = str(here.parent)
    add_path(project_root)
    # endregion

    # 获取 topic 信息
    topics = batch_df.select("topic").distinct().collect()
    for topic in topics:
        topic_name = topic[0]
        print(f"Processing topic: {topic_name}")

        try:
            # region 处理user
            if topic_name == "dbserver1.test.tb_user":
                # 动态导入 test1.py 并调用
                userConsumerSpark = importlib.import_module("MessageConsumer.UserConsumerSpark")
                userConsumerSpark.process(batch_df, batch_id, spark, kafka_bootstrap)
            # endregion

            # region 处理rates
            elif topic_name == "dbserver1.test.tb_rates":
                # 动态导入 test2.py 并调用
                test2 = importlib.import_module("MessageConsumer.RatesConsumerSpark")
                test2.process(batch_df, batch_id, spark, kafka_bootstrap)
            # endregion

            elif topic_name == "dbserver1.test.tb_userinfo":
                userInfoConsumerSpark = importlib.import_module("MessageConsumer.UserInfoConsumerSpark")
                userInfoConsumerSpark.process(batch_df, batch_id, spark, kafka_bootstrap)

            # region 处理其他异常消息
            else:
                print(f"Unknown topic: {topic_name}")
            # endregion
        except Exception as e:
            # 记录并继续处理其他 topic（不要抛出），以免终止整个 query
            print(f"Error processing {topic_name} in batch {batch_id}: {e}")


# endregion


# region # ------------ 启动流并打印 ------------
query = (selected.writeStream
         .foreachBatch(process_message)
         .option("checkpointLocation", checkpoint_location)
         .start())

query.awaitTermination()
# endregion

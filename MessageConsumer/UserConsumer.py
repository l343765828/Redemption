import json
from confluent_kafka import Consumer, KafkaException
import signal
from dask.distributed import Client
from pydantic import TypeAdapter, ValidationError
from Model.User.ChangeUserMsg import ChangeUserMsg

# region kafka配置
BOOTSTRAP = "my-cluster-kafka-bootstrap.kafka-prod.svc.cluster.local:9092"  # 改成你的地址
# "test-topic" dbserver1.test.tb_user
# TOPIC = "test-topic"
TOPIC = "change-user"
GROUP_ID = "py-consumer-group"

conf = {
    "bootstrap.servers": BOOTSTRAP,
    "group.id": GROUP_ID,
    "auto.offset.reset": "earliest",  # earliest 或 latest
    # 如果使用 SASL/SSL，添加相应配置
}

consumer = Consumer(conf)
run = True
# endregion

SCHEDULE_ADDRESS = "tcp://127.0.0.1:8786"


# region 停止服务
def shutdown(signalnum, frame):
    global run
    run = False
    print("Shutting down consumer...")


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)


# endregion


def consume_loop():
    client = Client(SCHEDULE_ADDRESS)

    # region 创建 actor（一次） 订阅消息
    actor_future = client.get_dataset("graph_actor")
    actor = actor_future.result()
    consumer.subscribe([TOPIC])
    # endregion

    try:
        while run:

            # region 处理消息
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                # 处理可恢复/不可恢复的错误
                print("Consumer error:", msg.error())
                continue
            key = msg.key().decode("utf-8") if msg.key() else None
            value = msg.value().decode("utf-8") if msg.value() else None
            adapter = TypeAdapter(list[ChangeUserMsg])
            try:
                # s 是 JSON 字符串（比如 val.decode("utf-8")）
                models = adapter.validate_json(value)  # 直接从 JSON 字符串解析
            except ValidationError as e:
                print("validation error:", e)
                models = []
            print(
                f"Received message: topic={msg.topic()} partition={msg.partition()} offset={msg.offset()} key={key}")
            print(models)
            print("结束")
            # endregion

            # region 构建图（只在版本升级时建）
            remote_future = actor.run_update(int(key), changList=models, npartitions=1, renumber_disable=False)
            res = remote_future.result()
            # endregion

            print("build res:", res)
            # endregion

            # 如果需要手动提交：
            # consumer.commit(message=msg)
    except KafkaException as ke:
        print("Kafka exception:", ke)
    finally:
        # region 1) 先优雅让 actor 释放资源（在 actor 所在 worker 执行）
        try:
            if actor is not None:
                # actor 是一个 ActorProxy；调用 cleanup() 会在 actor 所在 worker 执行 cleanup() 逻辑
                actor.cleanup_cluster().result(timeout=30)
        except Exception as e:
            print("Warning: failed to cleanup actor:", e)
        # endregion

        # region 2) 关闭 consumer
        consumer.close()
        print("Consumer closed.")
        # endregion

        # region 3) 关闭 Dask client（如果你在此进程创建了 client）
        try:
            client.close()
        except Exception:
            pass
        # endregion


if __name__ == "__main__":
    consume_loop()

from confluent_kafka import Consumer, KafkaException
import signal
from dask.distributed import Client
from pathlib import Path
from Model.Config import RATES_CACHE, RATE_TOPIC


# region 停止服务
def shutdown(signalnum, frame):
    global run
    run = False
    print("Shutting down consumer...")


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)
# endregion

# region kafka配置
BOOTSTRAP = "my-cluster-kafka-bootstrap.kafka-prod.svc.cluster.local:9092"  # 改成你的地址
GROUP_ID = "py-consumer-group"
SCHEDULE_ADDRESS = "tcp://127.0.0.1:8786"

conf = {
    "bootstrap.servers": BOOTSTRAP,
    "group.id": GROUP_ID,
    "auto.offset.reset": "earliest",  # earliest 或 latest
    # 如果使用 SASL/SSL，添加相应配置
}

consumer = Consumer(conf)
run = True


# endregion

def add_path(p):
    import sys
    if p not in sys.path:
        sys.path.insert(0, p)
        return True
    return False


def consume_loop():
    client = Client(SCHEDULE_ADDRESS)

    # region 将项目路径添加到sys.path，并测试是否能读取模块
    here = Path(__file__).resolve().parent
    project_root = str(here.parent)
    client.run(add_path, project_root)  # workers
    client.run_on_scheduler(add_path, project_root)  # scheduler（非常关键）
    print("路径添加完成")
    # endregion

    consumer.subscribe([RATE_TOPIC])

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
            print(
                f"Received message: topic={msg.topic()} partition={msg.partition()} offset={msg.offset()} key={key} value={value}")
            # endregion

            # region 清空缓存，让程序重新加载
            try:
                # 尝试显式取消已有 dataset（若不存在会抛异常）
                client.unpublish_dataset(RATES_CACHE)
                print(f"Unpublished existing dataset: {RATES_CACHE}")
            except Exception:
                # 忽略找不到或其它小错误
                pass
            # endregion

    except KafkaException as ke:
        print("Kafka exception:", ke)
    finally:

        # region 1) 关闭 consumer
        consumer.close()
        print("Consumer closed.")
        # endregion

        # region 2) 关闭 Dask client（如果你在此进程创建了 client）
        try:
            client.close()
        except Exception:
            pass
        # endregion


if __name__ == "__main__":
    consume_loop()

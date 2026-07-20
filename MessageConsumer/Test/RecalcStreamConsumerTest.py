import os
import json
import redis

# 1. 启动前，通过写入环境变量强制覆盖常量配置 (仅对本进程生效)
os.environ["RECALC_RECLAIM_MIN_IDLE_MS"] = "3000"  # 3 秒即视为滞留
os.environ["RECALC_RECLAIM_EVERY_SEC"] = "1"  # 每 1 秒扫描一次 PEL
os.environ["RECALC_MAX_RETRIES"] = "2"  # 重试 2 次即判定为毒丸

# 环境变量设置完毕后，再 import 真实的消费者类
from MessageConsumer.RecalcStreamConsumer import RecalcStreamConsumer


class RecalcStreamConsumerTest(RecalcStreamConsumer):
    """
    故障注入测试子类。
    利用父类暴露的 _dispatch_business 接缝，我们仅需覆写业务行为，
    即可完整测试外层的捕获、判定和落库(DLQ)逻辑。
    """

    def _dispatch_business(self, et: str, event: dict) -> None:
        if et == "POISON_TEST":
            print("[故障注入] 捕获到测试毒丸，即将主动抛出业务崩溃...")
            raise ValueError("test-only injected business failure")

        # 正常类型的事件直接交由真实实现处理
        return super()._dispatch_business(et, event)


def inject_test_data():
    """自动化打入测试数据"""
    r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
    STREAM_KEY = "system:recalc_outbox_stream"

    print("\n--- 正在向 Redis 发送坏数据 ---")

    # 立即进入 DLQ 的事件 (JSON 解析级异常)
    r.xadd(STREAM_KEY, {"payload": "{this_is_not_valid_json: 123, ]"})

    # 触发重试机制并最终进入 DLQ 的事件 (业务级异常)
    r.xadd(STREAM_KEY, {"payload": json.dumps({"event_type": "POISON_TEST", "user_id": "999"})})


if __name__ == "__main__":
    import threading

    # 为了方便一次性完成验证，单开一个线程在 2 秒后自动注入坏数据
    threading.Timer(2.0, inject_test_data).start()

    print("启动测试版消费者，等待数据注入...")
    # 启动魔改后的消费者
    RecalcStreamConsumerTest(host="127.0.0.1", port=6379, db=0).start_consuming()
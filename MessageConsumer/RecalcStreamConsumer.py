import os
import socket
import redis
import json
import time
import logging
import signal
import sys

# ==========================================
# 生产环境配置区 (支持通过环境变量覆盖)
# ==========================================
# region Redis Stream 配置
STREAM_KEY = "system:recalc_outbox_stream"
GROUP_NAME = "recalc_audit_group"
DLQ_STREAM_KEY = "system:recalc_outbox_dlq"
# endregion

# 稳定的消费者名称 (重启后能接回自己的 PEL)
CONSUMER_NAME = os.getenv("CONSUMER_NAME", socket.gethostname())

# region 配置外置：优先读取环境变量，若无则使用生产默认值
# 滞留消息回收配置：必须大于最坏情况下的单条消息处理耗时，生产默认设为 5 分钟
RECLAIM_MIN_IDLE_MS = int(os.getenv("RECALC_RECLAIM_MIN_IDLE_MS", "300000"))
RECLAIM_EVERY_SEC = int(os.getenv("RECALC_RECLAIM_EVERY_SEC", "30"))
MAX_RETRIES = int(os.getenv("RECALC_MAX_RETRIES", "5"))  # 业务失败最大重试次数
# endregion

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(process)d] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


class RecalcStreamConsumer:
    def __init__(self, host="127.0.0.1", port=6379, db=0, password=None):
        self.r = redis.Redis(host=host, port=port, db=db, password=password, decode_responses=True)
        self.running = True
        self._last_reclaim = 0.0
        self._setup_signal_handlers()
        self._ensure_consumer_group()

    def _setup_signal_handlers(self):
        signal.signal(signal.SIGINT, self._graceful_shutdown)
        signal.signal(signal.SIGTERM, self._graceful_shutdown)

    def _graceful_shutdown(self, signum, frame):
        logger.info(f"收到停止信号 ({signum})，准备优雅停机...")
        self.running = False

    def _ensure_consumer_group(self):
        try:
            self.r.xgroup_create(STREAM_KEY, GROUP_NAME, id="0-0", mkstream=True)
            logger.info(f"消费者组 '{GROUP_NAME}' 创建/验证成功。")
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP Consumer Group name already exists" not in str(e):
                raise

    def _is_poison_pill(self, message_id: str) -> bool:
        """检查消息投递次数，判断是否为无限报错的毒丸"""
        try:
            # XPENDING 获取单条消息的状态
            pending_info = self.r.xpending_range(
                STREAM_KEY, GROUP_NAME, min=message_id, max=message_id, count=1
            )
            if pending_info and len(pending_info) > 0:
                deliveries = pending_info[0].get('times_delivered', 0)
                if deliveries >= MAX_RETRIES:
                    return True
        except Exception as e:
            logger.error(f"检查消息投递次数失败: {e}")
        return False

    def _reclaim_stale(self):
        """扫描并认领长时间未 ACK 的滞留消息"""
        cursor = "0-0"
        reclaimed_count = 0

        while True:
            # region 读取大于设定时间（默认5分钟）没被处理的数据
            res = self.r.xautoclaim(
                name=STREAM_KEY,
                groupname=GROUP_NAME,
                consumername=CONSUMER_NAME,
                min_idle_time=RECLAIM_MIN_IDLE_MS,
                start_id=cursor,
                count=100
            )
            # endregion

            next_cursor, claimed = res[0], res[1]
            ack_ids = []

            for message_id, fields in claimed:
                # region 幽灵消息 消息如果在原 Stream 中被删了，但还在 PEL 里，清掉占位
                if not fields:
                    ack_ids.append(message_id)
                    continue
                # endregion

                # 重新处理，如果成功则准备 ACK
                if self.process_event(message_id, fields.get("payload")):
                    ack_ids.append(message_id)

            # region 处理ack消息
            if ack_ids:
                self.r.xack(STREAM_KEY, GROUP_NAME, *ack_ids)
                reclaimed_count += len(ack_ids)
            # endregion

            cursor = next_cursor

            # region 严格依据 cursor 归零来判断是否扫完了整个 PEL，redis读完PEL会将cursor清0
            if cursor in ("0-0", "0"):
                break
            # endregion

        if reclaimed_count > 0:
            logger.info(f"成功回收并处理了 {reclaimed_count} 条滞留消息。")

    def process_event(self, message_id: str, payload_str: str) -> bool:
        """
        处理事件（纯容错与流程控制）。
        真正的业务分发已剥离到 _dispatch_business 中。
        """
        # region 验证
        if not payload_str:
            return True
        # endregion

        # region 处理消息 如有异常 加入死信队列 (格式级别毒丸)
        try:
            e = json.loads(payload_str)
        except json.JSONDecodeError as err:
            logger.error(f"解析 JSON 失败: {err}, 扔进死信队列 (DLQ)")
            self.r.xadd(DLQ_STREAM_KEY, {"original_id": message_id, "raw_payload": payload_str, "error": str(err),
                                         "type": "JSON_ERROR"})
            return True
        # endregion

        et = e.get("event_type")

        try:
            # region 调用业务分发接缝 (Seam)
            self._dispatch_business(et, e)
            return True
            # endregion

        except Exception as ex:
            logger.error(f"业务处理异常 (Message ID: {message_id}): {ex}")

            # 检查重试次数，兜底业务失败，防止无限重试拖垮系统 (业务级别毒丸)
            if self._is_poison_pill(message_id):
                logger.warning(f"消息 {message_id} 超过最大重试次数 ({MAX_RETRIES})，转入 DLQ")
                self.r.xadd(DLQ_STREAM_KEY, {
                    "original_id": message_id,
                    "raw_payload": payload_str,
                    "error": f"Max retries reached: {str(ex)}",
                    "type": "BUSINESS_ERROR"
                })
                # 返回 True，将其 ACK 掉，不再阻塞 PEL
                return True

            # 返回 False，不执行 ACK，等待 xautoclaim 下次捡回
            return False

    def _dispatch_business(self, et: str, event: dict) -> None:
        """
        纯业务逻辑分发。
        不包含任何异常捕获、重试逻辑或状态确认。
        """
        # region 【业务逻辑处理区】(注意：此处代码必须保持幂等性)
        if et in ("RECALC_STATE_DRIFT", "RECALC_NODE_MATERIALIZED"):
            print("进入了 RECALC_STATE_DRIFT RECALC_NODE_MATERIALIZED")
            pass  # 发送至下游处理状态变更

        elif et == "HIGHEST_RANK_UPDATED":
            print("进入了 HIGHEST_RANK_UPDATED")
            pass  # 补齐了晋衔事件的处理分支

        elif et == "SETTLEMENT_PERIOD_DONE":
            print("进入了 SETTLEMENT_PERIOD_DONE")
            pass  # 整个结算周期结束的哨兵
        # endregion

    def start_consuming(self):
        logger.info(f"消费者 '{CONSUMER_NAME}' 启动，监听 Stream (Group={GROUP_NAME})...")

        while self.running:
            # region 周期性（默认30秒）扫描 PEL 寻找消费并且未ACK的消息
            if time.time() - self._last_reclaim > RECLAIM_EVERY_SEC:
                try:
                    self._reclaim_stale()
                except Exception as e:
                    logger.error(f"回收滞留消息失败: {e}")
                self._last_reclaim = time.time()
            # endregion

            try:
                # region 接受最新消息 如果没有消息 阻塞2秒
                streams = self.r.xreadgroup(
                    GROUP_NAME,
                    CONSUMER_NAME,
                    {STREAM_KEY: ">"},
                    count=100,
                    block=2000
                )
                # endregion

                # region 验证
                if not streams:
                    continue
                # endregion

                # region 处理消息
                for _, messages in streams:
                    ack_ids = []
                    for message_id, fields in messages:
                        payload_str = fields.get("payload")
                        if self.process_event(message_id, payload_str):
                            ack_ids.append(message_id)

                    # region 将处理过的消息加入到ack中
                    if ack_ids:
                        self.r.xack(STREAM_KEY, GROUP_NAME, *ack_ids)
                    # endregion
                # endregion

            except redis.exceptions.ConnectionError as e:
                logger.error(f"Redis 连接中断: {e}，5秒后重试...")
                time.sleep(5)
            except Exception as e:
                logger.error(f"主消费循环发生异常: {e}")
                time.sleep(1)


if __name__ == "__main__":
    consumer = RecalcStreamConsumer(host="127.0.0.1", port=6379, db=0)
    consumer.start_consuming()
from decimal import Decimal
from Until.Common import read_delta_snapshot_files
import logging
from typing import Dict
from Model.Config import DELTA_RATES, RATES_CACHE
from dask.distributed import Lock

logger = logging.getLogger(__name__)


class RatesService:

    # 从delta获取数据
    @staticmethod
    def _read_rates_from_delta_strict(cols=None, npartitions: int = 1) -> (
            Dict[int, Decimal], int):
        """
        严格地从 delta 读取费率表并返回 (level->rate, version)
        若读取失败或表为空则抛出 RuntimeError。
        期望 delta 表包含至少两列: level, rate
        """
        # region 读取delta
        try:
            ddf_rates, ver = read_delta_snapshot_files(DELTA_RATES, cols=cols or ["level", "rate"],
                                                       npartitions=npartitions)
        except Exception as e:
            logger.exception("Failed to list/read delta snapshot files from %s", DELTA_RATES)
            raise RuntimeError(f"Failed to read rates from delta at {DELTA_RATES}: {e}") from e
        # endregion

        # region 获取pandas
        try:
            pdf = ddf_rates.compute()
        except Exception as e:
            logger.exception("Failed to compute ddf_rates from delta at %s", DELTA_RATES)
            raise RuntimeError(f"Failed to compute rates DataFrame from delta at {DELTA_RATES}: {e}") from e

        # 把 cudf/pandas 等统一成 pandas DataFrame，便于后续处理
        try:
            pdf = pdf.to_pandas()
        except Exception:
            # 如果已经是 pandas，会抛异常，忽略
            pass

        if pdf is None or len(pdf) == 0:
            logger.error("Rates table from delta at %s is empty.", DELTA_RATES)
            raise RuntimeError(f"Rates table from delta at {DELTA_RATES} is empty.")
        # endregion

        # region 将pandas转为字典
        rates = {}
        for _, row in pdf.iterrows():
            try:
                lvl = int(row["level"])
                rate_value = Decimal(str(row["rate"]))
            except Exception as e:
                logger.warning("Skipping invalid row when parsing rates: %s (%s)",
                               row.to_dict() if hasattr(row, "to_dict") else str(row), e)
                continue
            rates[lvl] = rate_value

        if not rates:
            logger.error("After parsing, no valid rate rows found in delta at %s.", DELTA_RATES)
            raise RuntimeError(f"No valid rate rows found in delta at {DELTA_RATES}.")
        # endregion

        return rates, int(ver)

    # 从缓存获取汇率，缓存不存在时从delta获取
    @classmethod
    def get_rates_ppm_cached_strict(cls, client, cache_name: str = RATES_CACHE,
                                    lock_timeout: int = 30) -> Dict[int, int]:
        """
        严格的缓存获取逻辑（生产级）：
        1) 优先尝试从 scheduler 的 dataset 读取缓存（期望结构为 { 'ppm': {level:int_ppm,...}, 'version': ver }）
        2) 若缓存不存在，则通过带锁的 double-check 读取 delta 并 publish 到 scheduler（若失败直接抛出 RuntimeError）
        返回： level -> ppm(int) 字典
        """

        # region 1) 快速尝试从 scheduler 读取
        try:
            cached = client.get_dataset(cache_name)
            if isinstance(cached, dict) and "ppm" in cached and isinstance(cached["ppm"], dict):
                logger.info("Using rates cache from scheduler (cache_name=%s, version=%s).", cache_name,
                            cached.get("version"))
                return {int(k): int(v) for k, v in cached["ppm"].items()}
            else:
                logger.debug("Scheduler dataset %s exists but has unexpected format, will reload from delta.",
                             cache_name)
        except Exception:
            # 未找到缓存或读取失败：继续走后续流程
            logger.debug("Scheduler dataset %s not found or unreadable; will load from delta.", cache_name)
        # endregion

        # 2) 获取锁，double-check 模式防止并发冲刺
        lock = Lock(f"rates_reload_lock", client=client)
        got = lock.acquire(timeout=lock_timeout)

        # region 获取锁失败：直接抛错
        if not got:
            logger.error("Failed to acquire lock 'rates_reload_lock' within %d seconds", lock_timeout)
            raise RuntimeError(
                "Failed to acquire rates reload lock; concurrent reload in progress or scheduler unresponsive.")
        # endregion

        try:

            # region second check：double-check cache inside lock
            try:
                cached = client.get_dataset(cache_name)
                if isinstance(cached, dict) and "ppm" in cached and isinstance(cached["ppm"], dict):
                    logger.info("Using rates cache from scheduler (post-lock) (cache_name=%s, version=%s).", cache_name,
                                cached.get("version"))
                    return {int(k): int(v) for k, v in cached["ppm"].items()}
            except Exception:
                logger.debug("No usable scheduler cache found inside lock; proceeding to read delta.")
            # endregion

            # 3) 从 delta 读取（严格，不使用任何默认值）
            rates_decimal, ver = cls._read_rates_from_delta_strict(cols=["level", "rate"])
            print("读取物理磁盘的delta了")

            # region 4) 转换为 ppm（parts-per-million）整数
            try:
                rate_ppm = {int(level): int(round(rate * Decimal(str("1_000_000")))) for level, rate in
                            rates_decimal.items()}
            except Exception as e:
                logger.exception("Failed to convert rates to ppm: %s", e)
                raise RuntimeError(f"Failed to convert rates to ppm: {e}") from e
            # endregion

            # region 5) publish 到 scheduler（先尝试 unpublish，保证覆盖）
            try:
                try:
                    client.unpublish_dataset(cache_name)
                except Exception:
                    # 无需对不存在的 dataset 报错，继续 publish
                    pass
                # publish 包含 version 便于外部检查
                client.publish_dataset(**{cache_name: {"ppm": rate_ppm, "version": int(ver)}})
                logger.info("Published rates cache to scheduler (cache_name=%s, version=%s).", cache_name, int(ver))
            except Exception as e:
                logger.exception("Failed to publish rates cache to scheduler: %s", e)
                # publish 失败不代表我们不能使用内存中的 rate_ppm；但根据你的要求“读取 delta 失败需返回错误”，此处 publish 失败不是 delta 读取失败，我们认为只是缓存发布失败，仍返回 rate_ppm 并记录警告
                # 若你希望在 publish 失败时也抛错，可在此处 raise
                logger.warning(
                    "publish_dataset failed but returning computed rate_ppm. If you require publish success, configure to raise here.")
            # endregion

            return rate_ppm
        finally:
            try:
                lock.release()
            except Exception:
                logger.exception("Failed to release rates_reload_lock (ignored)")

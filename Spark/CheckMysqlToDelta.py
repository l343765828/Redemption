import logging

from deltalake import DeltaTable

from Model.Config import DELTA_RATES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
LOG = logging.getLogger("delta_blue_green_minimal")


def main():
    try:
        dt = DeltaTable(DELTA_RATES)
        try:

            # dt.history(1).show(truncate=False)
            # 新增：读取前100行数据
            LOG.info("=============================Reading first 100 rows from new prod table...")
            sample_data = dt.to_pandas().head(100)
            LOG.info(sample_data)
            LOG.info("=============================")
        except Exception as e:
            # print(
            #     "=============================Unable to show delta history; your environment may restrict history calls.")
            # print("报错：", e)
            LOG.warning(
                "=============================Unable to show delta history; your environment may restrict history calls.")
            LOG.error("报错：", e)
    except Exception as e:
        # print("=============================failed to read new prod table after swap: %s", e)
        LOG.error("=============================failed to read new prod table after swap: %s", e)


if __name__ == '__main__':
    main()

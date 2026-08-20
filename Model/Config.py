import os


DELTA_USER = "/mnt/tables/tb_user"
DELTA_RATES = "/mnt/tables/tb_rates"
DELTA_UNSERINFO = "/mnt/tables/tb_userinfo"

DELTA_USER_LOCAL = "/mnt/d/Redemption/Redemption/Tables/tb_user"
DELTA_RATES_LOCAL = "/mnt/d/Redemption/Redemption/Tables/tb_rates"

SPARK_DELTA_USER = "/mnt/delta/tables/tb_user"
SPARK_DELTA_USERINFO = "/mnt/delta/tables/tb_userinfo"

RATES_CACHE = "rates_cache"

RATE_TOPIC = "rate-topic"

SCHEDULE_ADDRESS = os.getenv("PVAM_DASK_SCHEDULER", "tcp://192.168.18.149:38786")
REDIS_HOST = os.getenv("PVAM_REDIS_HOST", "192.168.18.149")
REDIS_PORT = int(os.getenv("PVAM_REDIS_PORT", "36378"))
REDIS_DB = int(os.getenv("PVAM_REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("PVAM_REDIS_PASSWORD", "123456")

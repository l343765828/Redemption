from redis_om import JsonModel, get_redis_connection
from Model.Config import REDIS_DB, REDIS_HOST, REDIS_PASSWORD, REDIS_PORT

redis_conn = get_redis_connection(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    password=REDIS_PASSWORD,
    decode_responses=True
)


class BaseRedisModel(JsonModel):
    """
    所有 Redis 模型的公共基类。
    主要作用：统一绑定数据库连接，避免子类重复编写。
    """

    class Meta:
        # 统一绑定连接池
        database = redis_conn

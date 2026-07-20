from redis_om import JsonModel, get_redis_connection

redis_conn = get_redis_connection(
    host="192.168.18.149",
    port=36378,
    db=0,
    password="123456",
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

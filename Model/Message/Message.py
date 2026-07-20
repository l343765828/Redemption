from pyspark.sql.types import StructType, StructField, StringType, LongType
from Model.User.User import USER_SCHEMA
from Model.Rates.Rates import RATES_SCHEMA
from Model.User.UserInfo import USERINFO_SCHEMA

ENVELOPE_USER_SCHEMA = StructType([
    StructField("before", USER_SCHEMA, True),
    StructField("after", USER_SCHEMA, True),
    StructField("op", StringType(), True),
    StructField("ts_ms", LongType(), True)
])

ENVELOPE_USERINFO_SCHEMA = StructType([
    StructField("before", USERINFO_SCHEMA, True),
    StructField("after", USERINFO_SCHEMA, True),
    StructField("op", StringType(), True),
    StructField("ts_ms", LongType(), True)
])

ENVELOPE_RATES_SCHEMA = StructType([
    StructField("before", RATES_SCHEMA, True),
    StructField("after", RATES_SCHEMA, True),
    StructField("op", StringType(), True),
    StructField("ts_ms", LongType(), True)
])

KEY_SCHEMA = StructType([StructField("id", StringType(), True)])

from pyspark.sql.types import StructType, StructField, StringType, LongType, IntegerType

USERINFO_SCHEMA = StructType([
    StructField("id", StringType(), True),
    StructField("user_name", StringType(), True),
    StructField("real_name", StringType(), True),
    StructField("country_id", IntegerType(), True),
    StructField("updatetime", LongType(), True)
])
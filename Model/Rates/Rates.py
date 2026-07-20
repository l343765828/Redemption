from pyspark.sql.types import StructType, StructField, StringType, LongType

RATES_SCHEMA = StructType([
    StructField("id", StringType(), True),
    StructField("rate", StringType(), True),
    StructField("level", StringType(), True),
    StructField("updatetime", LongType(), True)
])

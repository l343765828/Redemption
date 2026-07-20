from pyspark.sql.types import StructType, StructField, StringType, LongType, IntegerType

USER_SCHEMA = StructType([
    StructField("id", StringType(), True),
    StructField("user", StringType(), True),
    StructField("parent", StringType(), True),
    StructField("placementId", StringType(), True),
    StructField("placementLeg", IntegerType(), True),
    StructField("updatetime", LongType(), True)
])

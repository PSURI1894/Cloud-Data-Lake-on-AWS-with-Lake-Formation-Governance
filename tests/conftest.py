import pytest
import os

# Set dummy AWS Credentials to support module-level boto3 client initializations in Lambdas
os.environ["AWS_ACCESS_KEY_ID"] = "mock_key"
os.environ["AWS_SECRET_ACCESS_KEY"] = "mock_secret"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

from pyspark.sql import SparkSession

@pytest.fixture(scope="session")
def spark_session():
    """
    Initializes a localized test Spark session with fully functional
    Hadoop-backed Iceberg configuration, automatically fetching target packages.
    """
    warehouse_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../local_dev/mock_data/test_warehouse"))
    
    spark = SparkSession.builder \
        .master("local[*]") \
        .appName("data-lake-unit-tests") \
        .config("spark.jars.packages", "org.apache.iceberg:iceberg-spark-runtime-3.4_2.12:1.3.1,org.apache.hadoop:hadoop-aws:3.3.4") \
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions") \
        .config("spark.sql.catalog.testcatalog", "org.apache.iceberg.spark.SparkCatalog") \
        .config("spark.sql.catalog.testcatalog.type", "hadoop") \
        .config("spark.sql.catalog.testcatalog.warehouse", f"file://{warehouse_path}") \
        .config("spark.sql.catalog.testcatalog.io-impl", "org.apache.iceberg.hadoop.HadoopFileIO") \
        .getOrCreate()
        
    yield spark
    spark.stop()
    """

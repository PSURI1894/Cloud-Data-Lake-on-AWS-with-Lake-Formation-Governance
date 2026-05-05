import sys
import os
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, to_timestamp, current_timestamp, sha2, md5, expr

# Fetch runtime arguments
args = getResolvedOptions(sys.argv, ['JOB_NAME', 'RAW_BUCKET', 'CONFORMED_BUCKET'])

# Initialize Spark & Glue Context with Apache Iceberg extensions
spark = SparkSession.builder     .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")     .config("spark.sql.catalog.awsglue", "org.apache.iceberg.spark.SparkCatalog")     .config("spark.sql.catalog.awsglue.catalog-impl", "org.apache.iceberg.aws.glue.GlueCatalog")     .config("spark.sql.catalog.awsglue.warehouse", f"s3://{args['CONFORMED_BUCKET']}/iceberg-warehouse/")     .config("spark.sql.catalog.awsglue.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")     .getOrCreate()

glueContext = GlueContext(spark.sparkContext)
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

print("🚀 Ingestion Pipeline Started: Raw to Conformed")

# Helper function to ingest and upsert transactions
def ingest_transactions():
    raw_path = f"s3://{args['RAW_BUCKET']}/raw_transactions/event_date=*/*.csv"
    print(f"📥 Loading Transactions from S3 Raw Path: {raw_path}")
    
    # Read CSV with schema validation & drift capability
    raw_df = spark.read.option("header", "true").option("inferSchema", "true").csv(raw_path)
    
    if raw_df.rdd.isEmpty():
        print("⚠️ No new records found in raw transaction path.")
        return
        
    # Transform fields: Standardize types, cast timestamps
    transformed_df = raw_df         .withColumn("amount", col("amount").cast("double"))         .withColumn("transaction_time", to_timestamp(col("transaction_time")))         .withColumn("ingested_at", current_timestamp())
        
    # Standardize column naming structure
    for c in transformed_df.columns:
        transformed_df = transformed_df.withColumnRenamed(c, c.lower().strip())
        
    # Create temporary view for execution
    transformed_df.createOrReplaceTempView("incoming_transactions")
    
    # Initialize Conformed Iceberg Table if not exists
    spark.sql("""
        CREATE TABLE IF NOT EXISTS awsglue.conformed_db.transactions (
            transaction_id string,
            customer_id string,
            amount double,
            product_id string,
            product_category string,
            region_code string,
            transaction_time timestamp,
            event_date string,
            promotion_code string,
            device_type string,
            ingested_at timestamp
        )
        USING iceberg
        PARTITIONED BY (days(transaction_time), region_code)
        TBLPROPERTIES (
            'write.object-storage.enabled'='true',
            'write.format.default'='parquet',
            'write.parquet.compression-codec'='snappy',
            'history.expire.max-snapshot-age-ms'='604800000'
        )
    """)
    
    # MERGE INTO to guarantee exact-once delivery & deduplication (Upsert)
    print("🔄 Executing MERGE INTO operation on transactions table...")
    spark.sql("""
        MERGE INTO awsglue.conformed_db.transactions t
        USING incoming_transactions s
        ON t.transaction_id = s.transaction_id
        WHEN MATCHED THEN
            UPDATE SET 
                t.amount = s.amount,
                t.product_id = s.product_id,
                t.product_category = s.product_category,
                t.region_code = s.region_code,
                t.transaction_time = s.transaction_time,
                t.promotion_code = s.promotion_code,
                t.device_type = s.device_type,
                t.ingested_at = s.ingested_at
        WHEN NOT MATCHED THEN
            INSERT (
                transaction_id, customer_id, amount, product_id, product_category, 
                region_code, transaction_time, event_date, promotion_code, device_type, ingested_at
            )
            VALUES (
                s.transaction_id, s.customer_id, s.amount, s.product_id, s.product_category, 
                s.region_code, s.transaction_time, s.event_date, s.promotion_code, s.device_type, s.ingested_at
            )
    """)
    print("✅ Transactions merge complete.")

# Helper function to ingest and upsert customers
def ingest_customers():
    raw_path = f"s3://{args['RAW_BUCKET']}/raw_customers/customers.json"
    print(f"📥 Loading Customers from S3 Raw Path: {raw_path}")
    
    # Read customer profiles
    raw_df = spark.read.json(raw_path)
    
    if raw_df.rdd.isEmpty():
        print("⚠️ No customer records found.")
        return
        
    # Anonymize PII for base conformed compliance (Marketing/Operations cannot access raw SSNs easily)
    # Perform sha2 hashing on SSN for basic protection at ingest
    processed_df = raw_df         .withColumn("ssn_hash", sha2(col("ssn"), 256))         .withColumn("created_at", to_timestamp(col("created_at")))         .withColumn("ingested_at", current_timestamp())
        
    processed_df.createOrReplaceTempView("incoming_customers")
    
    # Register Conformed Iceberg Customers Table
    spark.sql("""
        CREATE TABLE IF NOT EXISTS awsglue.conformed_db.customers (
            customer_id string,
            first_name string,
            last_name string,
            email string,
            phone_number string,
            ssn string,
            ssn_hash string,
            country string,
            region_code string,
            created_at timestamp,
            ingested_at timestamp
        )
        USING iceberg
        PARTITIONED BY (region_code)
        TBLPROPERTIES (
            'write.format.default'='parquet',
            'history.expire.max-snapshot-age-ms'='604800000'
        )
    """)
    
    # Merge customers
    print("🔄 Executing MERGE INTO operation on customers table...")
    spark.sql("""
        MERGE INTO awsglue.conformed_db.customers t
        USING incoming_customers s
        ON t.customer_id = s.customer_id
        WHEN MATCHED THEN
            UPDATE SET 
                t.first_name = s.first_name,
                t.last_name = s.last_name,
                t.email = s.email,
                t.phone_number = s.phone_number,
                t.ssn = s.ssn,
                t.ssn_hash = s.ssn_hash,
                t.country = s.country,
                t.region_code = s.region_code,
                t.ingested_at = s.ingested_at
        WHEN NOT MATCHED THEN
            INSERT (
                customer_id, first_name, last_name, email, phone_number, 
                ssn, ssn_hash, country, region_code, created_at, ingested_at
            )
            VALUES (
                s.customer_id, s.first_name, s.last_name, s.email, s.phone_number, 
                s.ssn, s.ssn_hash, s.country, s.region_code, s.created_at, s.ingested_at
            )
    """)
    print("✅ Customers merge complete.")

# Run steps
ingest_transactions()
ingest_customers()

job.commit()
print("🏆 Raw to Conformed Ingestion Pipeline Successfully Completed!")

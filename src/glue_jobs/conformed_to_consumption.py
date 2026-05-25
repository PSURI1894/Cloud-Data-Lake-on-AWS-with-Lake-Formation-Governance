import sys
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, current_timestamp, lit, to_date

# Resolve arguments
args = getResolvedOptions(sys.argv, ['JOB_NAME', 'CONFORMED_BUCKET', 'CONSUMPTION_BUCKET'])

# Spark context with Iceberg integration
spark = SparkSession.builder     .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")     .config("spark.sql.catalog.awsglue", "org.apache.iceberg.spark.SparkCatalog")     .config("spark.sql.catalog.awsglue.catalog-impl", "org.apache.iceberg.aws.glue.GlueCatalog")     .config("spark.sql.catalog.awsglue.warehouse", f"s3://{args['CONSUMPTION_BUCKET']}/iceberg-warehouse/")     .config("spark.sql.catalog.awsglue.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")     .getOrCreate()

glueContext = GlueContext(spark.sparkContext)
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

print("🚀 Consumption Star Schema Builder Started")

# Ensure target consumption database exists
spark.sql("CREATE DATABASE IF NOT EXISTS awsglue.consumption_db")

def build_dim_customers_scd2():
    """
    Implements SCD Type 2 (Slowly Changing Dimensions) logic for Customers
    using Iceberg SQL capability.
    """
    print("👤 Rebuilding/Updating dim_customers SCD-2...")
    
    # Check if target dim_customers table exists
    spark.sql("""
        CREATE TABLE IF NOT EXISTS awsglue.consumption_db.dim_customers (
            customer_key string, -- generated unique key
            customer_id string,
            first_name string,
            last_name string,
            email string,
            phone_number string,
            ssn string,
            ssn_hash string,
            country string,
            region_code string,
            start_date timestamp,
            end_date timestamp,
            is_current boolean,
            ingested_at timestamp
        )
        USING iceberg
        PARTITIONED BY (is_current, region_code)
    """)
    
    # Read fresh conformed customer records
    conformed_cust = spark.sql("SELECT * FROM awsglue.conformed_db.customers")
    conformed_cust.createOrReplaceTempView("fresh_customers")
    
    # Perform Type-2 matching to detect changes
    # Identify customers with differences in email, phone, or region
    changed_records = spark.sql("""
        SELECT 
            f.customer_id, f.first_name, f.last_name, f.email, f.phone_number, 
            f.ssn, f.ssn_hash, f.country, f.region_code
        FROM fresh_customers f
        LEFT JOIN awsglue.consumption_db.dim_customers d
          ON f.customer_id = d.customer_id AND d.is_current = true
        WHERE d.customer_id IS NULL -- New customer
           OR f.email != d.email 
           OR f.phone_number != d.phone_number 
           OR f.region_code != d.region_code -- Value changed
    """)
    
    if changed_records.rdd.isEmpty():
        print("ℹ️ No customer record updates detected for SCD-2.")
        return
        
    changed_records.createOrReplaceTempView("updates")
    
    # 1. Close out existing active records that had changes
    print("🔄 Expiring old SCD-2 rows...")
    spark.sql("""
        MERGE INTO awsglue.consumption_db.dim_customers d
        USING updates u
        ON d.customer_id = u.customer_id AND d.is_current = true
        WHEN MATCHED THEN
            UPDATE SET d.is_current = false, d.end_date = current_timestamp()
    """)
    
    # 2. Insert new current records
    print("📥 Inserting new active SCD-2 rows...")
    spark.sql("""
        INSERT INTO awsglue.consumption_db.dim_customers
        SELECT 
            uuid() as customer_key,
            customer_id,
            first_name,
            last_name,
            email,
            phone_number,
            ssn,
            ssn_hash,
            country,
            region_code,
            current_timestamp() as start_date,
            cast(null as timestamp) as end_date,
            true as is_current,
            current_timestamp() as ingested_at
        FROM updates
    """)
    print("✅ dim_customers SCD-2 reconciliation completed.")

def build_fact_transactions():
    """
    Builds the fact_transactions table joining conformed transaction data
    to customer dimension records using the active customer keys.
    """
    print("💳 Building fact_transactions...")
    
    spark.sql("""
        CREATE TABLE IF NOT EXISTS awsglue.consumption_db.fact_transactions (
            transaction_id string,
            customer_key string,
            customer_id string,
            amount double,
            product_id string,
            product_category string,
            region_code string,
            transaction_time timestamp,
            event_date string,
            promotion_code string,
            ingested_at timestamp
        )
        USING iceberg
        PARTITIONED BY (days(transaction_time), product_category)
    """)
    
    # Read and join
    fresh_txns = spark.sql("SELECT * FROM awsglue.conformed_db.transactions")
    fresh_txns.createOrReplaceTempView("txns")
    
    # Fetch active customer keys to link fact rows to dimension rows
    fact_rows = spark.sql("""
        SELECT 
            t.transaction_id,
            coalesce(c.customer_key, 'UNKNOWN') as customer_key,
            t.customer_id,
            t.amount,
            t.product_id,
            t.product_category,
            t.region_code,
            t.transaction_time,
            t.event_date,
            t.promotion_code,
            current_timestamp() as ingested_at
        FROM txns t
        LEFT JOIN awsglue.consumption_db.dim_customers c
          ON t.customer_id = c.customer_id AND c.is_current = true
    """)
    
    fact_rows.createOrReplaceTempView("incoming_facts")
    
    # Perform upsert on fact table
    spark.sql("""
        MERGE INTO awsglue.consumption_db.fact_transactions f
        USING incoming_facts s
        ON f.transaction_id = s.transaction_id
        WHEN MATCHED THEN
            UPDATE SET 
                f.customer_key = s.customer_key,
                f.amount = s.amount,
                f.product_id = s.product_id,
                f.product_category = s.product_category,
                f.region_code = s.region_code,
                f.transaction_time = s.transaction_time,
                f.promotion_code = s.promotion_code,
                f.ingested_at = s.ingested_at
        WHEN NOT MATCHED THEN
            INSERT (
                transaction_id, customer_key, customer_id, amount, product_id,
                product_category, region_code, transaction_time, event_date, promotion_code, ingested_at
            )
            VALUES (
                s.transaction_id, s.customer_key, s.customer_id, s.amount, s.product_id,
                s.product_category, s.region_code, s.transaction_time, s.event_date, s.promotion_code, s.ingested_at
            )
    """)
    print("✅ fact_transactions merge completed.")

# Run builds
build_dim_customers_scd2()
build_fact_transactions()

job.commit()
print("🏆 Star Schema Consumption Build Successful!")

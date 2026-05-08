import sys
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import SparkSession
from datetime import datetime, timedelta

# Resolve arguments
args = getResolvedOptions(sys.argv, ['JOB_NAME', 'TARGET_TABLES', 'RETENTION_DAYS'])

# Initialize Iceberg Spark Session
spark = SparkSession.builder     .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")     .config("spark.sql.catalog.awsglue", "org.apache.iceberg.spark.SparkCatalog")     .config("spark.sql.catalog.awsglue.catalog-impl", "org.apache.iceberg.aws.glue.GlueCatalog")     .config("spark.sql.catalog.awsglue.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")     .getOrCreate()

glueContext = GlueContext(spark.sparkContext)
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

print(f"🧹 Starting Iceberg Table Maintenance Pipeline...")
tables = args['TARGET_TABLES'].split(",")
retention_days = int(args['RETENTION_DAYS'])

# Compute older-than timestamp
older_than_ts = (datetime.now() - timedelta(days=retention_days)).strftime("%Y-%m-%d %H:%M:%S.000")

for t in tables:
    t = t.strip()
    catalog_t = f"awsglue.{t}"
    print(f"\n⚡ Processing Table: {catalog_t}")
    
    try:
        # 1. Compaction: Rewrite Small Data Files to ~128MB - 512MB sizes
        print(f"   📦 Compacting small files on {catalog_t}...")
        compaction_res = spark.sql(f"""
            CALL awsglue.system.rewrite_data_files(
                table => '{catalog_t}',
                options => map('max-file-size-bytes', '536870912', 'min-input-files', '5')
            )
        """)
        compaction_res.show(truncate=False)
        
        # 2. Expire Snapshots older than threshold (pruning historical metadata/data)
        print(f"   ⏱️ Expiring snapshots older than {older_than_ts}...")
        expire_res = spark.sql(f"""
            CALL awsglue.system.expire_snapshots(
                table => '{catalog_t}',
                older_than => TIMESTAMP '{older_than_ts}',
                retain_last => 3
            )
        """)
        expire_res.show(truncate=False)
        
        # 3. Clean up Orphan Files (deleted transaction remnants)
        print(f"   🗑️ Cleaning up orphan files (3+ days old)...")
        orphan_res = spark.sql(f"""
            CALL awsglue.system.remove_orphan_files(
                table => '{catalog_t}',
                older_than => TIMESTAMP '{older_than_ts}'
            )
        """)
        orphan_res.show(truncate=False)
        
        # 4. Reorganize Manifest Files to speed up Athena planners
        print(f"   🗂️ Rewriting manifest files...")
        manifest_res = spark.sql(f"""
            CALL awsglue.system.rewrite_manifests(
                table => '{catalog_t}'
            )
        """)
        manifest_res.show(truncate=False)
        
        print(f"✅ Maintenance completed successfully for {catalog_t}")
        
    except Exception as e:
        print(f"❌ Error maintaining table {catalog_t}: {str(e)}")

job.commit()
print("\n🏆 Iceberg Maintenance Pipeline Successfully Completed!")

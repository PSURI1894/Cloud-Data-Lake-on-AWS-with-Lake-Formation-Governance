import subprocess
import os
import sys

def run_spark_job(job_name, args=[]):
    """
    Submits a PySpark job to the spark-iceberg container or runs it locally.
    """
    print(f"🚀 Running PySpark Job: {job_name}")
    
    # Path settings
    workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src_dir = os.path.join(workspace_dir, "src")
    local_dev_dir = os.path.join(workspace_dir, "local_dev")
    
    # Spark packages & configuration (matches AWS Glue 4.0 runtime)
    packages = [
        "org.apache.iceberg:iceberg-spark-runtime-3.4_2.12:1.3.1",
        "org.apache.hadoop:hadoop-aws:3.3.4",
        "software.amazon.awssdk:bundle:2.18.41",
        "software.amazon.awssdk:url-connection-client:2.18.41"
    ]
    
    cmd = [
        "spark-submit",
        f"--packages={','.join(packages)}",
        "--conf", "spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        "--conf", "spark.sql.catalog.local=org.apache.iceberg.spark.SparkCatalog",
        "--conf", "spark.sql.catalog.local.type=hadoop",
        "--conf", "spark.sql.catalog.local.warehouse=mock_data/warehouse",
        os.path.join(src_dir, "glue_jobs", f"{job_name}.py")
    ] + args

    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            print(line, end="")
        process.wait()
        if process.returncode != 0:
            print(f"❌ Spark job failed with exit code {process.returncode}")
            sys.exit(process.returncode)
        else:
            print("✅ Spark job completed successfully!")
    except FileNotFoundError:
        print("❌ 'spark-submit' not found in path! Please ensure Apache Spark is installed locally or run this inside the 'spark-iceberg' container.")
        print("💡 Alternatively, use docker-compose: docker compose exec spark-iceberg spark-submit /opt/spark/src/glue_jobs/" + job_name + ".py")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_local_spark.py <job_name> [args...]")
        print("Available jobs: raw_to_conformed_pyspark, conformed_to_consumption, iceberg_maintenance")
        sys.exit(1)
        
    run_spark_job(sys.argv[1], sys.argv[2:])

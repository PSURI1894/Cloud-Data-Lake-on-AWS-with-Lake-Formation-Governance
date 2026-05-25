# Glue Data Catalog Databases
resource "aws_glue_catalog_database" "raw" {
  name        = "raw_db"
  description = "Glue database housing Raw landing datasets"
}

resource "aws_glue_catalog_database" "conformed" {
  name        = "conformed_db"
  description = "Glue database housing clean Conformed datasets in Apache Iceberg format"

  parameters = {
    "classification" = "iceberg"
  }
}

resource "aws_glue_catalog_database" "consumption" {
  name        = "consumption_db"
  description = "Glue database housing Business Unit consumption data products"

  parameters = {
    "classification" = "iceberg"
  }
}

# 1. Glue Job: Raw to Conformed (Ingestion)
resource "aws_glue_job" "raw_to_conformed" {
  name              = "raw_to_conformed_ingestion"
  role_arn          = aws_iam_role.glue_job_role.arn
  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 10
  timeout           = 120

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.utility.id}/scripts/raw_to_conformed_pyspark.py"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.utility.id}/temp/"
    "--enable-metrics"                   = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-glue-datacatalog"          = "true"
    "--datalake-formats"                 = "iceberg"

    # User-defined runtime variables
    "--RAW_BUCKET"       = aws_s3_bucket.raw.id
    "--CONFORMED_BUCKET" = aws_s3_bucket.conformed.id
    "--catalog"          = "awsglue"
  }
}

# 2. Glue Job: Conformed to Consumption (Mart Aggregates)
resource "aws_glue_job" "conformed_to_consumption" {
  name              = "conformed_to_consumption_marts"
  role_arn          = aws_iam_role.glue_job_role.arn
  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 10
  timeout           = 120

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.utility.id}/scripts/conformed_to_consumption.py"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.utility.id}/temp/"
    "--enable-metrics"                   = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-glue-datacatalog"          = "true"
    "--datalake-formats"                 = "iceberg"

    # User-defined runtime variables
    "--CONFORMED_BUCKET"   = aws_s3_bucket.conformed.id
    "--CONSUMPTION_BUCKET" = aws_s3_bucket.consumption.id
  }
}

# 3. Glue Job: Iceberg Table Maintenance (Compaction & Pruning)
resource "aws_glue_job" "iceberg_maintenance" {
  name              = "iceberg_table_maintenance"
  role_arn          = aws_iam_role.glue_job_role.arn
  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 5
  timeout           = 60

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.utility.id}/scripts/iceberg_maintenance.py"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.utility.id}/temp/"
    "--enable-metrics"                   = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-glue-datacatalog"          = "true"
    "--datalake-formats"                 = "iceberg"

    # User-defined runtime variables
    "--TARGET_TABLES"  = "conformed_db.transactions,conformed_db.customers,consumption_db.dim_customers,consumption_db.fact_transactions"
    "--RETENTION_DAYS" = "7"
  }
}

# Glue Crawler for Raw Landing Zone
resource "aws_glue_crawler" "raw_crawler" {
  database_name = aws_glue_catalog_database.raw.name
  name          = "raw_data_crawler"
  role          = aws_iam_role.glue_job_role.arn

  s3_target {
    path = "s3://${aws_s3_bucket.raw.id}/raw_transactions/"
  }

  configuration = jsonencode({
    Version = 1.0
    CrawlerOutput = {
      Partitions = { AddOrUpdateBehavior = "InheritFromTable" }
      Tables     = { TableThreshold = 1 }
    }
    VersionId = "v1"
  })
}

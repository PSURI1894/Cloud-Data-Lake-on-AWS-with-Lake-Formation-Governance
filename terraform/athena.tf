# 1. Athena Workgroup: Marketing BU (Cost-Isolated with scan limits)
resource "aws_athena_workgroup" "marketing" {
  name = "marketing_workgroup"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location = "s3://${aws_s3_bucket.utility.id}/athena_results/marketing/"
      
      encryption_configuration {
        encryption_option = "SSE_KMS"
        kms_key_arn       = aws_kms_key.lake_key.arn
      }
    }

    # Restrict ad-hoc queries to scan max 10 GB per query to protect budget
    bytes_scanned_cutoff_per_query = 10737418240 
  }
}

# 2. Athena Workgroup: Finance BU
resource "aws_athena_workgroup" "finance" {
  name = "finance_workgroup"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location = "s3://${aws_s3_bucket.utility.id}/athena_results/finance/"
      
      encryption_configuration {
        encryption_option = "SSE_KMS"
        kms_key_arn       = aws_kms_key.lake_key.arn
      }
    }

    # Restrict queries to scan max 100 GB per query
    bytes_scanned_cutoff_per_query = 107374182400
  }
}

# Standard Governance Query: Stale Tables Audit
resource "aws_athena_named_query" "stale_tables_audit" {
  name      = "stale_tables_audit"
  workgroup = aws_athena_workgroup.finance.id
  database  = aws_glue_catalog_database.conformed.name
  query     = <<EOF
-- Identify tables that have not had active writes/compaction in 90+ days
SELECT table_name, last_updated_time 
FROM information_schema.tables 
WHERE last_updated_time < current_date - interval '90' day;
EOF
}

# Standard Governance Query: Top Expensive Queries Audit
resource "aws_athena_named_query" "expensive_queries" {
  name      = "expensive_queries_audit"
  workgroup = aws_athena_workgroup.finance.id
  database  = aws_glue_catalog_database.conformed.name
  query     = <<EOF
-- Search CloudTrail logs to identify top data-scanners
SELECT 
  user_identity.arn as user_arn, 
  event_time, 
  request_parameters.query as sql_text,
  cast(json_extract_scalar(additional_event_data, '$.bytesScanned') as double) / 1e9 as scanned_gb
FROM cloudtrail_logs
WHERE event_name = 'StartQueryExecution'
  AND cast(json_extract_scalar(additional_event_data, '$.bytesScanned') as double) > 1e11 -- > 100 GB
ORDER BY scanned_gb DESC
LIMIT 50;
EOF
}

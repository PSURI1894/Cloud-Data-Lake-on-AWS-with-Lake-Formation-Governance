# CloudTrail Bucket
resource "aws_s3_bucket" "cloudtrail" {
  bucket        = "${var.project_name}-cloudtrail-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_policy" "cloudtrail" {
  bucket = aws_s3_bucket.cloudtrail.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AWSCloudTrailAclCheck"
        Effect = "Allow"
        Principal = {
          Service = "cloudtrail.amazonaws.com"
        }
        Action   = "s3:GetBucketAcl"
        Resource = aws_s3_bucket.cloudtrail.arn
      },
      {
        Sid    = "AWSCloudTrailWrite"
        Effect = "Allow"
        Principal = {
          Service = "cloudtrail.amazonaws.com"
        }
        Action   = "s3:PutObject"
        Resource = "${aws_s3_bucket.cloudtrail.arn}/AWSLogs/${data.aws_caller_identity.current.account_id}/*"
        Condition = {
          StringEquals = {
            "s3:x-amz-acl" = "bucket-owner-full-control"
          }
        }
      }
    ]
  })
}

# 1. AWS CloudTrail to track all Athena/S3 access audits
resource "aws_cloudtrail" "data_lake" {
  name                          = "data-lake-governance-audit-trail"
  s3_bucket_name                = aws_s3_bucket.cloudtrail.id
  include_global_service_events = true
  is_multi_region_trail         = true
  enable_log_file_validation    = true

  # Audit S3 Data Events (Get/Put/Delete) on data lake zones
  event_selector {
    read_write_type           = "All"
    include_management_events = true

    data_resource {
      type   = "AWS::S3::Object"
      values = [
        "${aws_s3_bucket.raw.arn}/",
        "${aws_s3_bucket.conformed.arn}/",
        "${aws_s3_bucket.consumption.arn}/"
      ]
    }
  }

  depends_on = [aws_s3_bucket_policy.cloudtrail]
}

# 2. S3 Storage Lens configuration
resource "aws_s3control_storage_lens_configuration" "lake_lens" {
  config_id = "data-lake-storage-lens"

  storage_lens_configuration {
    enabled = true

    account_level {
      activity_metrics {
        enabled = true
      }
      bucket_level {
        activity_metrics {
          enabled = true
        }
        prefix_level {
          storage_metrics {
            enabled = true
            selection_criteria {
              max_depth = 5
            }
          }
        }
      }
    }

    data_export {
      s3_bucket_destination {
        account_id = data.aws_caller_identity.current.account_id
        arn        = aws_s3_bucket.utility.arn
        format     = "CSV"
        output_schema_version = "V_1"
        prefix     = "storage_lens_exports"
      }
    }
  }
}

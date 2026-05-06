# Central KMS Key for Data Lake Encryption
resource "aws_kms_key" "lake_key" {
  description             = "KMS Key for AWS Data Lake Encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.kms_policy.json
}

data "aws_iam_policy_document" "kms_policy" {
  statement {
    sid    = "Enable IAM User Permissions"
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
    actions   = ["kms:*"]
    resources = ["*"]
  }

  statement {
    sid    = "Allow S3 to use the key"
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }
    actions = [
      "kms:Decrypt",
      "kms:GenerateDataKey*"
    ]
    resources = ["*"]
  }

  statement {
    sid    = "Allow Glue and EMR to use the key"
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com", "elasticmapreduce.amazonaws.com"]
    }
    actions = [
      "kms:Decrypt",
      "kms:Encrypt",
      "kms:GenerateDataKey*",
      "kms:ReEncrypt*",
      "kms:DescribeKey"
    ]
    resources = ["*"]
  }
}

# Access Logs Bucket
resource "aws_s3_bucket" "access_logs" {
  bucket        = "${var.project_name}-access-logs-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "access_logs" {
  bucket                  = aws_s3_bucket.access_logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# 1. Raw Zone Bucket
resource "aws_s3_bucket" "raw" {
  bucket        = "${var.project_name}-raw-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id
  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.lake_key.arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id
  rule {
    id     = "archive-raw-data"
    status = "Enabled"
    filter {}

    transition {
      days          = 30
      storage_class = "GLACIER"
    }

    expiration {
      days = 365
    }
  }
}

# 2. Conformed Zone Bucket (Iceberg Layer)
resource "aws_s3_bucket" "conformed" {
  bucket        = "${var.project_name}-conformed-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "conformed" {
  bucket = aws_s3_bucket.conformed.id
  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.lake_key.arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "conformed" {
  bucket = aws_s3_bucket.conformed.id
  rule {
    id     = "intelligent-tiering-conformed"
    status = "Enabled"
    filter {}

    transition {
      days          = 0
      storage_class = "INTELLIGENT_TIERING"
    }
  }
}

# 3. Consumption Zone Bucket (Analytics Marts)
resource "aws_s3_bucket" "consumption" {
  bucket        = "${var.project_name}-consumption-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "consumption" {
  bucket = aws_s3_bucket.consumption.id
  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.lake_key.arn
      sse_algorithm     = "aws:kms"
    }
  }
}

# 4. Utility / Assets Bucket (Spark scripts, Metadata)
resource "aws_s3_bucket" "utility" {
  bucket        = "${var.project_name}-utility-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}

# Enforce secure transport (HTTPS) on all buckets
data "aws_iam_policy_document" "bucket_policy" {
  statement {
    sid     = "EnforceTLS"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      "arn:aws:s3:::${var.project_name}-raw-${data.aws_caller_identity.current.account_id}",
      "arn:aws:s3:::${var.project_name}-raw-${data.aws_caller_identity.current.account_id}/*",
      "arn:aws:s3:::${var.project_name}-conformed-${data.aws_caller_identity.current.account_id}",
      "arn:aws:s3:::${var.project_name}-conformed-${data.aws_caller_identity.current.account_id}/*",
      "arn:aws:s3:::${var.project_name}-consumption-${data.aws_caller_identity.current.account_id}",
      "arn:aws:s3:::${var.project_name}-consumption-${data.aws_caller_identity.current.account_id}/*"
    ]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

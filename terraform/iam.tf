# 1. Glue Job Execution Role
resource "aws_iam_role" "glue_job_role" {
  name = "data-lake-glue-job-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "glue.amazonaws.com"
        }
      }
    ]
  })
}

# Attach standard AWS policy for Glue Service
resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue_job_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

# Inline Custom Policy for S3 + Lake Formation + KMS
resource "aws_iam_role_policy" "glue_lake_access" {
  name = "glue-lake-access-policy"
  role = aws_iam_role.glue_job_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.raw.arn,
          "${aws_s3_bucket.raw.arn}/*",
          aws_s3_bucket.conformed.arn,
          "${aws_s3_bucket.conformed.arn}/*",
          aws_s3_bucket.consumption.arn,
          "${aws_s3_bucket.consumption.arn}/*",
          aws_s3_bucket.utility.arn,
          "${aws_s3_bucket.utility.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "lakeformation:GetDataAccess",
          "lakeformation:GetResourceLFTags",
          "lakeformation:ListLFTags",
          "lakeformation:SearchTablesByLFTags",
          "lakeformation:SearchDatabasesByLFTags"
        ]
        Resource = ["*"]
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:Encrypt",
          "kms:GenerateDataKey"
        ]
        Resource = [aws_kms_key.lake_key.arn]
      }
    ]
  })
}

# 2. Multi-Tenant Analyst Roles
# A. Finance Analyst Role
resource "aws_iam_role" "finance_analyst_role" {
  name = "finance-analyst-data-lake-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
      }
    ]
  })
}

# B. APAC Analyst Role (restricted rows)
resource "aws_iam_role" "apac_analyst_role" {
  name = "apac-analyst-data-lake-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
      }
    ]
  })
}

# C. Marketing Analyst Role (restricted columns)
resource "aws_iam_role" "marketing_analyst_role" {
  name = "marketing-analyst-data-lake-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
      }
    ]
  })
}

# Apply base Athena execution rights to Analysts
resource "aws_iam_policy" "athena_analyst_access" {
  name        = "athena-analyst-access-policy"
  description = "Base access policy for executing Athena queries"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "athena:StartQueryExecution",
          "athena:StopQueryExecution",
          "athena:GetQueryExecution",
          "athena:GetQueryResults",
          "athena:ListQueryExecutions",
          "athena:GetWorkGroup"
        ]
        Resource = ["*"]
      },
      {
        Effect = "Allow"
        Action = [
          "glue:GetDatabase",
          "glue:GetTable",
          "glue:GetPartitions",
          "glue:GetTables"
        ]
        Resource = ["*"]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "finance_athena" {
  role       = aws_iam_role.finance_analyst_role.name
  policy_arn = aws_iam_policy.athena_analyst_access.arn
}

resource "aws_iam_role_policy_attachment" "apac_athena" {
  role       = aws_iam_role.apac_analyst_role.name
  policy_arn = aws_iam_policy.athena_analyst_access.arn
}

resource "aws_iam_role_policy_attachment" "marketing_athena" {
  role       = aws_iam_role.marketing_analyst_role.name
  policy_arn = aws_iam_policy.athena_analyst_access.arn
}

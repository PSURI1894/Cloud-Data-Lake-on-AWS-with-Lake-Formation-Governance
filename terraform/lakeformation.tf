# Register S3 Buckets in Lake Formation
resource "aws_lakeformation_resource" "raw" {
  arn = aws_s3_bucket.raw.arn
}

resource "aws_lakeformation_resource" "conformed" {
  arn = aws_s3_bucket.conformed.arn
}

resource "aws_lakeformation_resource" "consumption" {
  arn = aws_s3_bucket.consumption.arn
}

# 1. LF Tags Definition
resource "aws_lakeformation_lf_tag" "bu" {
  key    = "BU"
  values = var.business_units
}

resource "aws_lakeformation_lf_tag" "sensitivity" {
  key    = "Sensitivity"
  values = var.sensitivity_levels
}

resource "aws_lakeformation_lf_tag" "pii" {
  key    = "PII"
  values = var.pii_categories
}

# 2. Grant permissions based on Tag-Based Access Control (LF-TBAC)
# Grant 'finance-analyst' role read permission on databases/tables tagged BU=finance and Sensitivity IN (public, internal)
resource "aws_lakeformation_permissions" "finance_analyst_tbac" {
  principal = aws_iam_role.finance_analyst_role.arn

  lf_tag_policy {
    resource_type = "TABLE"

    expression {
      key    = aws_lakeformation_lf_tag.bu.key
      values = ["finance"]
    }
    expression {
      key    = aws_lakeformation_lf_tag.sensitivity.key
      values = ["public", "internal"]
    }
  }

  permissions = ["SELECT", "DESCRIBE"]
}

# Row-Level Security: APAC Data filter on conformed transactions
resource "aws_lakeformation_data_cells_filter" "apac_transactions_filter" {
  table_data {
    name             = "apac_transactions_filter"
    database_name    = aws_glue_catalog_database.conformed.name
    table_name       = "transactions"
    table_catalog_id = data.aws_caller_identity.current.account_id

    row_filter {
      filter_expression = "region_code = 'APAC'"
    }
  }
}

# Grant the APAC Analyst access via the Row-level filter
resource "aws_lakeformation_permissions" "apac_analyst_filtered_access" {
  principal   = aws_iam_role.apac_analyst_role.arn
  permissions = ["SELECT", "DESCRIBE"]

  data_cells_filter {
    database_name    = aws_glue_catalog_database.conformed.name
    table_name       = "transactions"
    name             = aws_lakeformation_data_cells_filter.apac_transactions_filter.name
    table_catalog_id = data.aws_caller_identity.current.account_id
  }
}

# Column Masking Filter: Nullify SSN for marketing analysts
resource "aws_lakeformation_data_cells_filter" "marketing_customer_filter" {
  table_data {
    name                = "marketing_customer_filter"
    database_name       = aws_glue_catalog_database.consumption.name
    table_name          = "dim_customers"
    table_catalog_id = data.aws_caller_identity.current.account_id

    column_wildcard {
      excluded_column_names = ["ssn", "phone_number"]
    }

    row_filter {
      filter_expression = "TRUE" # All rows, but columns SSN & Phone are excluded
    }
  }
}

resource "aws_lakeformation_permissions" "marketing_analyst_filtered_access" {
  principal   = aws_iam_role.marketing_analyst_role.arn
  permissions = ["SELECT", "DESCRIBE"]

  data_cells_filter {
    database_name    = aws_glue_catalog_database.consumption.name
    table_name       = "dim_customers"
    name             = aws_lakeformation_data_cells_filter.marketing_customer_filter.name
    table_catalog_id = data.aws_caller_identity.current.account_id
  }
}

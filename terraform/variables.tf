variable "aws_region" {
  type        = string
  description = "The target AWS Region for all core data lake resources"
  default     = "us-east-1"
}

variable "dr_aws_region" {
  type        = string
  description = "The disaster recovery AWS Region for replication"
  default     = "us-west-2"
}

variable "environment" {
  type        = string
  description = "Application deployment environment (e.g. dev, staging, prod)"
  default     = "prod"
}

variable "project_name" {
  type        = string
  description = "Name of the global data lake project"
  default     = "enterprise-datalake"
}

variable "business_units" {
  type        = list(string)
  description = "List of business units utilizing the multi-tenant lakehouse"
  default     = ["marketing", "finance", "compliance", "analytics", "operations"]
}

variable "sensitivity_levels" {
  type        = list(string)
  description = "Security classifications used for Lake Formation data classification"
  default     = ["public", "internal", "confidential", "restricted"]
}

variable "pii_categories" {
  type        = list(string)
  description = "PII identification classes for granular column profiling"
  default     = ["none", "quasi", "direct"]
}

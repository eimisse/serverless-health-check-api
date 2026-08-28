variable "environment" {
  description = "Deployment environment prefix."
  type        = string
}

variable "aws_account_id" {
  description = "Owning AWS account ID used by the key policy conditions."
  type        = string
}

variable "aws_partition" {
  description = "AWS partition used to construct the account root ARN."
  type        = string
}

variable "aws_region" {
  description = "AWS Region used by the DynamoDB via-service condition."
  type        = string
}

variable "table_name" {
  description = "Exact DynamoDB table name bound into the encryption-context condition."
  type        = string
}

variable "runtime_role_arn" {
  description = "Lambda runtime role that may decrypt through DynamoDB only."
  type        = string
}

variable "deployment_role_arn" {
  description = "Environment deployment role that administers the key and provisions the encrypted table."
  type        = string
}

variable "deletion_window_days" {
  description = "KMS scheduled deletion recovery window."
  type        = number
}

variable "rotation_period_days" {
  description = "Automatic rotation interval in days."
  type        = number
}

variable "tags" {
  description = "Tags applied to the key."
  type        = map(string)
}

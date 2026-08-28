variable "environment" {
  description = "Deployment environment prefix."
  type        = string
}

variable "table_arn" {
  description = "Exact DynamoDB table ARN allowed by the runtime role."
  type        = string
}

variable "aws_account_id" {
  description = "AWS account ID used in deterministic resource ARNs."
  type        = string
}

variable "aws_partition" {
  description = "AWS partition used in deterministic resource ARNs."
  type        = string
}

variable "aws_region" {
  description = "AWS Region used in deterministic resource ARNs."
  type        = string
}

variable "permissions_boundary_arn" {
  description = "Optional IAM permissions boundary for the runtime role."
  type        = string
  default     = null
  nullable    = true
}

variable "tags" {
  description = "Tags applied to the runtime role."
  type        = map(string)
}

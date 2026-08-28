variable "environment" {
  description = "Deployment environment prefix and REST API stage name."
  type        = string
}

variable "aws_region" {
  description = "AWS Region used in the Lambda integration URI."
  type        = string
}

variable "aws_partition" {
  description = "AWS partition used in the Lambda integration URI."
  type        = string
}

variable "aws_account_id" {
  description = "AWS account ID used to construct the exact access-log group ARN."
  type        = string
}

variable "lambda_function_name" {
  description = "Lambda function invoked by GET and POST /health."
  type        = string
}

variable "lambda_qualifier" {
  description = "Environment-scoped Lambda alias qualifier invoked by API Gateway."
  type        = string
}

variable "lambda_invoke_arn" {
  description = "Alias-qualified Lambda invoke ARN used by both AWS_PROXY integrations."
  type        = string
}

variable "max_payload_length" {
  description = "Maximum POST payload string length enforced before Lambda invocation."
  type        = number
}

variable "log_retention_days" {
  description = "Finite API access-log retention."
  type        = number
}

variable "stage_throttle_rate_limit" {
  description = "Stage steady-state rate limit for GET and POST /health."
  type        = number
}

variable "stage_throttle_burst_limit" {
  description = "Stage burst limit for GET and POST /health."
  type        = number
}

variable "usage_plan_rate_limit" {
  description = "Per-key usage-plan steady-state rate limit."
  type        = number
}

variable "usage_plan_burst_limit" {
  description = "Per-key usage-plan burst limit."
  type        = number
}

variable "tags" {
  description = "Tags applied to taggable API resources."
  type        = map(string)
}

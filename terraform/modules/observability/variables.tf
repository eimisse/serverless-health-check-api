variable "environment" {
  description = "Deployment environment prefix."
  type        = string
}

variable "aws_region" {
  description = "AWS Region displayed by the dashboard widgets."
  type        = string
}

variable "lambda_function_name" {
  description = "Lambda function monitored by error and throttle alarms."
  type        = string
}

variable "api_name" {
  description = "REST API name monitored by service alarms."
  type        = string
}

variable "api_stage_name" {
  description = "REST API stage monitored by service alarms."
  type        = string
}

variable "api_latency_threshold_ms" {
  description = "p95 API latency alarm threshold in milliseconds."
  type        = number
}

variable "tags" {
  description = "Tags applied to CloudWatch alarms."
  type        = map(string)
}

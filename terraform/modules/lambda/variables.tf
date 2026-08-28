variable "environment" {
  description = "Deployment environment prefix."
  type        = string
}

variable "table_name" {
  description = "DynamoDB request table name exposed to the handler."
  type        = string
}

variable "subnet_ids" {
  description = "Two private subnet IDs used by the Lambda VPC configuration."
  type        = list(string)

  validation {
    condition     = length(var.subnet_ids) == 2
    error_message = "The Lambda function requires exactly two private subnets."
  }
}

variable "security_group_id" {
  description = "Restricted Lambda security group ID."
  type        = string
}

variable "package_path" {
  description = "Absolute path to the deterministic Lambda ZIP built before terraform plan."
  type        = string
}

variable "role_arn" {
  description = "Pre-created least-privilege Lambda runtime role ARN."
  type        = string
}

variable "application_version" {
  description = "Git commit SHA supplied to the handler and function description."
  type        = string
}

variable "memory_size" {
  description = "Lambda memory in MiB."
  type        = number
}

variable "timeout_seconds" {
  description = "Lambda timeout in seconds."
  type        = number
}

variable "reserved_concurrency" {
  description = "Reserved concurrency cap."
  type        = number
}

variable "request_ttl_days" {
  description = "Request retention interval exposed to the handler."
  type        = number
}

variable "max_payload_length" {
  description = "Maximum payload length exposed to the handler."
  type        = number
}

variable "log_retention_days" {
  description = "Finite Lambda log retention."
  type        = number
}

variable "tags" {
  description = "Tags applied to taggable Lambda resources."
  type        = map(string)
}

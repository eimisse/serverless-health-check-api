variable "environment" {
  description = "Deployment environment. Only the reviewed staging and prod configurations are supported."
  type        = string

  validation {
    condition     = contains(["staging", "prod"], var.environment)
    error_message = "environment must be either staging or prod."
  }
}

variable "aws_region" {
  description = "AWS Region in which the application stack is deployed."
  type        = string
  default     = "eu-west-1"

  validation {
    condition     = can(regex("^[a-z]{2}(-gov)?-[a-z]+-[0-9]+$", var.aws_region))
    error_message = "aws_region must be a valid AWS Region name."
  }
}

variable "vpc_cidr" {
  description = "IPv4 CIDR for the isolated application VPC."
  type        = string

  validation {
    condition     = can(cidrnetmask(var.vpc_cidr))
    error_message = "vpc_cidr must be a valid IPv4 CIDR."
  }
}

variable "private_subnet_cidrs" {
  description = "Exactly two distinct private subnet CIDRs. The reviewed environment tfvars keep both ranges inside the VPC and non-overlapping."
  type        = list(string)

  validation {
    condition = (
      length(var.private_subnet_cidrs) == 2 &&
      length(toset(var.private_subnet_cidrs)) == 2 &&
      alltrue([for cidr in var.private_subnet_cidrs : can(cidrnetmask(cidr))])
    )
    error_message = "private_subnet_cidrs must contain exactly two distinct valid IPv4 CIDRs."
  }
}

variable "availability_zones" {
  description = "Two distinct Availability Zones used by the private subnets."
  type        = list(string)

  validation {
    condition = (
      length(var.availability_zones) == 2 &&
      length(toset(var.availability_zones)) == 2
    )
    error_message = "availability_zones must contain exactly two distinct Availability Zones."
  }
}

variable "lambda_package_path" {
  description = "Path, relative to terraform/, to the deterministic Lambda release ZIP built once before planning."
  type        = string
  default     = "../build/lambda.zip"
}

variable "application_version" {
  description = "Release commit SHA exposed to the function as APP_VERSION. CI supplies the immutable Git commit SHA."
  type        = string
  default     = "local"

  validation {
    condition     = var.application_version == "local" || can(regex("^[0-9a-f]{7,40}$", var.application_version))
    error_message = "application_version must be local or a lowercase 7-40 character Git commit SHA."
  }
}

variable "lambda_memory_size" {
  description = "Lambda memory allocation in MiB."
  type        = number
  default     = 128

  validation {
    condition     = var.lambda_memory_size >= 128 && var.lambda_memory_size <= 10240
    error_message = "lambda_memory_size must be between 128 and 10240 MiB."
  }
}

variable "lambda_timeout_seconds" {
  description = "Lambda execution timeout."
  type        = number
  default     = 5

  validation {
    condition     = var.lambda_timeout_seconds >= 1 && var.lambda_timeout_seconds <= 30
    error_message = "lambda_timeout_seconds must be between 1 and 30 seconds."
  }
}

variable "lambda_reserved_concurrency" {
  description = "Reserved concurrency cap used as a cost and abuse control."
  type        = number

  validation {
    condition     = var.lambda_reserved_concurrency >= 1 && floor(var.lambda_reserved_concurrency) == var.lambda_reserved_concurrency
    error_message = "lambda_reserved_concurrency must be a positive integer."
  }
}

variable "log_retention_days" {
  description = "Finite retention for application and API access logs."
  type        = number

  validation {
    condition = contains([
      1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096,
      1827, 2192, 2557, 2922, 3288, 3653
    ], var.log_retention_days)
    error_message = "log_retention_days must be a CloudWatch Logs supported retention value."
  }
}

variable "request_ttl_days" {
  description = "Number of days before DynamoDB expires request records."
  type        = number
  default     = 30

  validation {
    condition     = var.request_ttl_days >= 1 && var.request_ttl_days <= 365 && floor(var.request_ttl_days) == var.request_ttl_days
    error_message = "request_ttl_days must be an integer from 1 through 365."
  }
}

variable "max_payload_length" {
  description = "Maximum accepted payload length, enforced by API Gateway and Lambda."
  type        = number
  default     = 4096

  validation {
    condition     = var.max_payload_length >= 1 && var.max_payload_length <= 16384 && floor(var.max_payload_length) == var.max_payload_length
    error_message = "max_payload_length must be an integer from 1 through 16384."
  }
}

variable "dynamodb_point_in_time_recovery_enabled" {
  description = "Enable DynamoDB point-in-time recovery."
  type        = bool
  default     = true
}

variable "dynamodb_deletion_protection_enabled" {
  description = "Protect the DynamoDB table from accidental deletion. Enabled for prod."
  type        = bool
}

variable "kms_deletion_window_days" {
  description = "Recovery window before a scheduled KMS key deletion completes."
  type        = number

  validation {
    condition     = var.kms_deletion_window_days >= 7 && var.kms_deletion_window_days <= 30
    error_message = "kms_deletion_window_days must be between 7 and 30."
  }
}

variable "kms_rotation_period_days" {
  description = "Automatic KMS rotation interval."
  type        = number
  default     = 365

  validation {
    condition     = var.kms_rotation_period_days >= 90 && var.kms_rotation_period_days <= 2560
    error_message = "kms_rotation_period_days must be between 90 and 2560."
  }
}

variable "stage_throttle_rate_limit" {
  description = "Per-method API Gateway stage steady-state request rate."
  type        = number

  validation {
    condition     = var.stage_throttle_rate_limit > 0
    error_message = "stage_throttle_rate_limit must be greater than zero."
  }
}

variable "stage_throttle_burst_limit" {
  description = "Per-method API Gateway stage burst capacity."
  type        = number

  validation {
    condition     = var.stage_throttle_burst_limit >= 1 && floor(var.stage_throttle_burst_limit) == var.stage_throttle_burst_limit
    error_message = "stage_throttle_burst_limit must be a positive integer."
  }
}

variable "usage_plan_rate_limit" {
  description = "Per-API-key steady-state request rate."
  type        = number

  validation {
    condition     = var.usage_plan_rate_limit > 0
    error_message = "usage_plan_rate_limit must be greater than zero."
  }
}

variable "usage_plan_burst_limit" {
  description = "Per-API-key burst capacity."
  type        = number

  validation {
    condition     = var.usage_plan_burst_limit >= 1 && floor(var.usage_plan_burst_limit) == var.usage_plan_burst_limit
    error_message = "usage_plan_burst_limit must be a positive integer."
  }
}

variable "api_latency_alarm_threshold_ms" {
  description = "p95 API Gateway latency threshold for the non-paging service alarm."
  type        = number

  validation {
    condition     = var.api_latency_alarm_threshold_ms >= 100
    error_message = "api_latency_alarm_threshold_ms must be at least 100 milliseconds."
  }
}

variable "additional_tags" {
  description = "Additional non-secret tags merged into every taggable resource."
  type        = map(string)
  default     = {}
}

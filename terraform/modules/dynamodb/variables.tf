variable "environment" {
  description = "Deployment environment prefix."
  type        = string
}

variable "kms_key_arn" {
  description = "Customer-managed KMS key used for table encryption."
  type        = string
}

variable "point_in_time_recovery" {
  description = "Whether point-in-time recovery is enabled."
  type        = bool
}

variable "deletion_protection_enabled" {
  description = "Whether DynamoDB deletion protection is enabled."
  type        = bool
}

variable "tags" {
  description = "Tags applied to the table."
  type        = map(string)
}

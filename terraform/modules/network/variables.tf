variable "environment" {
  description = "Deployment environment prefix."
  type        = string
}

variable "aws_region" {
  description = "AWS Region used to construct the DynamoDB service endpoint name."
  type        = string
}

variable "vpc_cidr" {
  description = "Application VPC CIDR."
  type        = string
}

variable "private_subnet_cidrs" {
  description = "Two private subnet CIDRs."
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_cidrs) == 2
    error_message = "Exactly two private subnet CIDRs are required."
  }
}

variable "availability_zones" {
  description = "Two distinct Availability Zones."
  type        = list(string)

  validation {
    condition     = length(var.availability_zones) == 2 && length(toset(var.availability_zones)) == 2
    error_message = "Exactly two distinct Availability Zones are required."
  }
}

variable "dynamodb_prefix_list_id" {
  description = "AWS-managed DynamoDB prefix list used to restrict Lambda egress."
  type        = string
}

variable "dynamodb_table_arn" {
  description = "Exact application table ARN allowed by the gateway endpoint policy."
  type        = string
}

variable "lambda_runtime_role_arn" {
  description = "Exact runtime role allowed through the DynamoDB gateway endpoint."
  type        = string
}

variable "tags" {
  description = "Tags applied to taggable network resources."
  type        = map(string)
}

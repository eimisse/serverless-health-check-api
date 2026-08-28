variable "aws_region" {
  description = "AWS region that will contain the shared state bucket and both environment stacks."
  type        = string
  default     = "eu-west-1"

  validation {
    condition     = can(regex("^[a-z]{2}(-[a-z]+)+-[0-9]+$", var.aws_region))
    error_message = "aws_region must be a valid AWS region name."
  }
}

variable "github_repository" {
  description = "Repository allowed to exchange GitHub OIDC tokens for deployment sessions. Deliberately fixed for this project."
  type        = string
  default     = "eimisse/serverless-health-check-api"

  validation {
    condition     = var.github_repository == "eimisse/serverless-health-check-api"
    error_message = "github_repository is intentionally restricted to eimisse/serverless-health-check-api."
  }
}

variable "create_github_oidc_provider" {
  description = "Create the account-wide GitHub Actions OIDC provider. Set false when the provider already exists in this AWS account."
  type        = bool
  default     = true
}

variable "existing_github_oidc_provider_arn" {
  description = "Existing token.actions.githubusercontent.com provider ARN, required when create_github_oidc_provider is false."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition = (
      var.existing_github_oidc_provider_arn == null ||
      can(regex("^arn:(aws|aws-us-gov|aws-cn):iam::[0-9]{12}:oidc-provider/token\\.actions\\.githubusercontent\\.com$", var.existing_github_oidc_provider_arn))
    )
    error_message = "existing_github_oidc_provider_arn must identify token.actions.githubusercontent.com."
  }
}

variable "state_bucket_name" {
  description = "Optional globally unique state bucket name. The default includes the AWS account ID and region."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition = (
      var.state_bucket_name == null || (
        length(var.state_bucket_name) >= 3 &&
        length(var.state_bucket_name) <= 63 &&
        can(regex("^[a-z0-9][a-z0-9.-]*[a-z0-9]$", var.state_bucket_name)) &&
        !can(regex("\\.\\.", var.state_bucket_name))
      )
    )
    error_message = "state_bucket_name must meet the S3 bucket naming rules used by this module."
  }
}

variable "deployment_role_max_session_duration" {
  description = "Maximum GitHub Actions deployment-role session duration in seconds."
  type        = number
  default     = 3600

  validation {
    condition = (
      var.deployment_role_max_session_duration >= 3600 &&
      var.deployment_role_max_session_duration <= 43200
    )
    error_message = "deployment_role_max_session_duration must be between 3600 and 43200 seconds."
  }
}

variable "permissions_boundary_arn" {
  description = "Optional pre-existing IAM permissions boundary to attach to both deployment roles."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition = (
      var.permissions_boundary_arn == null ||
      can(regex("^arn:(aws|aws-us-gov|aws-cn):iam::[0-9]{12}:policy/[A-Za-z0-9+=,.@_/-]+$", var.permissions_boundary_arn))
    )
    error_message = "permissions_boundary_arn must be an IAM managed-policy ARN."
  }
}

variable "additional_tags" {
  description = "Additional non-secret tags for bootstrap resources. Required governance tags cannot be overridden."
  type        = map(string)
  default     = {}
}

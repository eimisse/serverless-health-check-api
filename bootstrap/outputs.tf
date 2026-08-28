output "state_bucket_name" {
  description = "S3 bucket used by both application Terraform backends."
  value       = aws_s3_bucket.state.id
}

output "state_kms_key_arn" {
  description = "Customer-managed KMS key used to encrypt Terraform state."
  value       = aws_kms_key.state.arn
}

output "state_kms_alias" {
  description = "Stable alias for the Terraform state KMS key."
  value       = aws_kms_alias.state.name
}

output "github_oidc_provider_arn" {
  description = "GitHub Actions OIDC provider created or reused by this bootstrap."
  value       = local.oidc_provider_arn
}

output "deployment_role_arns" {
  description = "Environment-specific GitHub Actions deployment role ARNs."
  value = {
    for environment, role in aws_iam_role.deployment : environment => role.arn
  }
}

output "api_gateway_cloudwatch_role_arn" {
  description = "Shared regional role used by API Gateway for staging and prod access logs."
  value       = aws_iam_role.api_gateway_cloudwatch.arn
}

output "backend_configuration" {
  description = "Values to copy into each environment backend HCL file. use_lockfile enables native S3 locking; no DynamoDB lock table is required."
  value = {
    for environment in local.environments : environment => {
      bucket       = aws_s3_bucket.state.id
      key          = local.state_key_by_environment[environment]
      region       = var.aws_region
      encrypt      = true
      kms_key_id   = aws_kms_key.state.arn
      use_lockfile = true
    }
  }
}

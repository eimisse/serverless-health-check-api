output "api_url" {
  description = "Base invoke URL. Append /health and supply the generated key in x-api-key."
  value       = module.api_gateway.invoke_url
}

output "api_id" {
  description = "REST API identifier used by live control-plane verification."
  value       = module.api_gateway.api_id
}

output "api_stage_name" {
  description = "Environment-prefixed REST API stage name."
  value       = module.api_gateway.stage_name
}

output "api_usage_plan_id" {
  description = "Usage plan identifier used by live throttle verification."
  value       = module.api_gateway.usage_plan_id
}

output "api_key_id" {
  description = "Identifier of the AWS-generated API key. Retrieve the value explicitly for smoke tests; Terraform never stores a configured value."
  value       = module.api_gateway.api_key_id
}

output "stage_throttle_rate_limit" {
  description = "Expected per-method stage steady-state throttle rate."
  value       = var.stage_throttle_rate_limit
}

output "stage_throttle_burst_limit" {
  description = "Expected per-method stage burst throttle."
  value       = var.stage_throttle_burst_limit
}

output "usage_plan_rate_limit" {
  description = "Expected per-key usage-plan steady-state throttle rate."
  value       = var.usage_plan_rate_limit
}

output "usage_plan_burst_limit" {
  description = "Expected per-key usage-plan burst throttle."
  value       = var.usage_plan_burst_limit
}

output "lambda_function_name" {
  description = "Deployed Lambda function name."
  value       = module.lambda.function_name
}

output "lambda_release_alias_name" {
  description = "Environment release alias used by API Gateway instead of unqualified $LATEST."
  value       = module.lambda.release_alias_name
}

output "lambda_release_alias_arn" {
  description = "Alias-qualified Lambda ARN for the current environment release."
  value       = module.lambda.release_alias_arn
}

output "lambda_release_version" {
  description = "Published immutable Lambda version currently targeted by the release alias."
  value       = module.lambda.release_version
}

output "lambda_log_group_name" {
  description = "Environment-prefixed CloudWatch log group used by Lambda."
  value       = module.lambda.log_group_name
}

output "lambda_runtime_role_arn" {
  description = "Least-privilege Lambda execution role ARN."
  value       = module.runtime_iam.role_arn
}

output "dynamodb_table_name" {
  description = "Request table name."
  value       = module.dynamodb.table_name
}

output "dynamodb_table_arn" {
  description = "Request table ARN."
  value       = module.dynamodb.table_arn
}

output "kms_key_arn" {
  description = "Customer-managed KMS key used for DynamoDB SSE."
  value       = module.kms.key_arn
}

output "vpc_id" {
  description = "Isolated Lambda VPC ID."
  value       = module.network.vpc_id
}

output "private_subnet_ids" {
  description = "Two private subnet IDs in distinct Availability Zones."
  value       = module.network.private_subnet_ids
}

output "dynamodb_vpc_endpoint_id" {
  description = "DynamoDB gateway endpoint used by the Lambda subnets."
  value       = module.network.dynamodb_vpc_endpoint_id
}

output "dashboard_name" {
  description = "Focused CloudWatch service dashboard."
  value       = module.observability.dashboard_name
}

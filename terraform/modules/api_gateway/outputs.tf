output "api_id" {
  description = "REST API ID."
  value       = aws_api_gateway_rest_api.health.id
}

output "api_name" {
  description = "Environment-prefixed REST API name."
  value       = aws_api_gateway_rest_api.health.name
}

output "stage_name" {
  description = "Environment-prefixed REST API stage name."
  value       = aws_api_gateway_stage.this.stage_name
}

output "invoke_url" {
  description = "REST API stage invoke URL."
  value       = aws_api_gateway_stage.this.invoke_url
}

output "execution_arn" {
  description = "REST API execution ARN."
  value       = aws_api_gateway_rest_api.health.execution_arn
}

output "api_key_id" {
  description = "ID of the generated API key; the secret value is intentionally not output."
  value       = aws_api_gateway_api_key.health.id
}

output "usage_plan_id" {
  description = "ID of the environment usage plan used for live throttle verification."
  value       = aws_api_gateway_usage_plan.health.id
}

output "access_log_group_name" {
  description = "Explicit environment-prefixed API access-log group name."
  value       = aws_cloudwatch_log_group.access.name
}

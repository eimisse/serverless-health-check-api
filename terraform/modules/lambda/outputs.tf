output "function_name" {
  description = "Lambda function name."
  value       = aws_lambda_function.health.function_name
}

output "function_arn" {
  description = "Unqualified Lambda function ARN."
  value       = aws_lambda_function.health.arn
}

output "invoke_arn" {
  description = "Lambda invocation ARN used by API Gateway."
  value       = aws_lambda_function.health.invoke_arn
}

output "qualified_arn" {
  description = "Published immutable Lambda version ARN."
  value       = aws_lambda_function.health.qualified_arn
}

output "log_group_name" {
  description = "Explicit Lambda log group name."
  value       = aws_cloudwatch_log_group.lambda.name
}

output "log_group_arn" {
  description = "Explicit Lambda log group ARN."
  value       = aws_cloudwatch_log_group.lambda.arn
}

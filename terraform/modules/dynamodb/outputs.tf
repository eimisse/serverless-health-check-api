output "table_name" {
  description = "Request table name."
  value       = aws_dynamodb_table.requests.name
}

output "table_arn" {
  description = "Request table ARN."
  value       = aws_dynamodb_table.requests.arn
}

output "table_id" {
  description = "Request table ID."
  value       = aws_dynamodb_table.requests.id
}

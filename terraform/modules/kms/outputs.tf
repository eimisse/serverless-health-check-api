output "key_arn" {
  description = "DynamoDB customer-managed KMS key ARN."
  value       = aws_kms_key.dynamodb.arn
}

output "key_id" {
  description = "DynamoDB customer-managed KMS key ID."
  value       = aws_kms_key.dynamodb.key_id
}

output "alias_name" {
  description = "Environment-prefixed KMS alias."
  value       = aws_kms_alias.dynamodb.name
}

output "vpc_id" {
  description = "Application VPC ID."
  value       = aws_vpc.this.id
}

output "vpc_arn" {
  description = "Application VPC ARN."
  value       = aws_vpc.this.arn
}

output "private_subnet_ids" {
  description = "Private subnet IDs in two Availability Zones."
  value       = aws_subnet.private[*].id
}

output "lambda_security_group_id" {
  description = "Lambda security group ID."
  value       = aws_security_group.lambda.id
}

output "dynamodb_vpc_endpoint_id" {
  description = "DynamoDB gateway VPC endpoint ID."
  value       = aws_vpc_endpoint.dynamodb.id
}

output "private_route_table_id" {
  description = "Private route table associated with both Lambda subnets."
  value       = aws_route_table.private.id
}

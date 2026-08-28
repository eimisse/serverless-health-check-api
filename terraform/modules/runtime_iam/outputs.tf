output "role_arn" {
  description = "Lambda runtime role ARN."
  value       = aws_iam_role.runtime.arn
}

output "role_name" {
  description = "Lambda runtime role name."
  value       = aws_iam_role.runtime.name
}

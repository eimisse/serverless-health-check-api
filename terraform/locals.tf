locals {
  project_name = "serverless-health-check-api"
  name_prefix  = "${var.environment}-health-check"
  table_name   = "${var.environment}-requests-db"

  runtime_role_name    = "${local.name_prefix}-function-role"
  deployment_role_name = "${local.name_prefix}-deployment-role"

  runtime_role_arn    = "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:role/${local.runtime_role_name}"
  deployment_role_arn = "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:role/${local.deployment_role_name}"
  table_arn           = "arn:${data.aws_partition.current.partition}:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${local.table_name}"

  lambda_package_path = abspath("${path.root}/${var.lambda_package_path}")

  common_tags = merge(
    {
      Environment = var.environment
      ManagedBy   = "Terraform"
      Project     = local.project_name
      Repository  = "eimisse/serverless-health-check-api"
    },
    var.additional_tags,
  )
}

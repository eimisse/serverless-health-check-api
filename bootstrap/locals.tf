data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  project_name = "serverless-health-check-api"
  environments = toset(["staging", "prod"])

  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition

  common_tags = merge(var.additional_tags, {
    Project     = local.project_name
    Environment = "shared"
    ManagedBy   = "Terraform"
    Component   = "bootstrap"
  })

  state_bucket_name = coalesce(
    var.state_bucket_name,
    "shared-health-check-tfstate-${local.account_id}-${var.aws_region}"
  )
  state_bucket_arn = "arn:${local.partition}:s3:::${local.state_bucket_name}"

  state_key_by_environment = {
    for environment in local.environments :
    environment => "env/${environment}/terraform.tfstate"
  }

  oidc_provider_arn = var.create_github_oidc_provider ? "arn:${local.partition}:iam::${local.account_id}:oidc-provider/token.actions.githubusercontent.com" : var.existing_github_oidc_provider_arn

  resource_arns = {
    for environment in local.environments : environment => {
      function = "arn:${local.partition}:lambda:${var.aws_region}:${local.account_id}:function:${environment}-health-check-function"
      table    = "arn:${local.partition}:dynamodb:${var.aws_region}:${local.account_id}:table/${environment}-requests-db"

      runtime_role = "arn:${local.partition}:iam::${local.account_id}:role/${environment}-health-check-function-role"

      application_key       = "arn:${local.partition}:kms:${var.aws_region}:${local.account_id}:key/*"
      application_key_alias = "arn:${local.partition}:kms:${var.aws_region}:${local.account_id}:alias/${environment}-requests-db-key"

      lambda_log_group     = "arn:${local.partition}:logs:${var.aws_region}:${local.account_id}:log-group:/aws/lambda/${environment}-health-check-function"
      api_access_log_group = "arn:${local.partition}:logs:${var.aws_region}:${local.account_id}:log-group:/aws/apigateway/${environment}-health-check-api-access"
      log_groups = [
        "arn:${local.partition}:logs:${var.aws_region}:${local.account_id}:log-group:/aws/lambda/${environment}-health-check-function",
        "arn:${local.partition}:logs:${var.aws_region}:${local.account_id}:log-group:/aws/lambda/${environment}-health-check-function:*",
        "arn:${local.partition}:logs:${var.aws_region}:${local.account_id}:log-group:/aws/apigateway/${environment}-health-check-api-access",
        "arn:${local.partition}:logs:${var.aws_region}:${local.account_id}:log-group:/aws/apigateway/${environment}-health-check-api-access:*"
      ]

      alarms = [
        "arn:${local.partition}:cloudwatch:${var.aws_region}:${local.account_id}:alarm:${environment}-health-check-function-errors",
        "arn:${local.partition}:cloudwatch:${var.aws_region}:${local.account_id}:alarm:${environment}-health-check-function-throttles",
        "arn:${local.partition}:cloudwatch:${var.aws_region}:${local.account_id}:alarm:${environment}-health-check-api-5xx",
        "arn:${local.partition}:cloudwatch:${var.aws_region}:${local.account_id}:alarm:${environment}-health-check-api-latency"
      ]
      dashboard = "arn:${local.partition}:cloudwatch::${local.account_id}:dashboard/${environment}-health-check-dashboard"

      api_gateway = [
        "arn:${local.partition}:apigateway:${var.aws_region}::/restapis",
        "arn:${local.partition}:apigateway:${var.aws_region}::/restapis/*",
        "arn:${local.partition}:apigateway:${var.aws_region}::/apikeys",
        "arn:${local.partition}:apigateway:${var.aws_region}::/apikeys/*",
        "arn:${local.partition}:apigateway:${var.aws_region}::/usageplans",
        "arn:${local.partition}:apigateway:${var.aws_region}::/usageplans/*",
        "arn:${local.partition}:apigateway:${var.aws_region}::/tags/*"
      ]
      ec2_vpcs           = "arn:${local.partition}:ec2:${var.aws_region}:${local.account_id}:vpc/*"
      ec2_subnets        = "arn:${local.partition}:ec2:${var.aws_region}:${local.account_id}:subnet/*"
      ec2_route_tables   = "arn:${local.partition}:ec2:${var.aws_region}:${local.account_id}:route-table/*"
      ec2_security_group = "arn:${local.partition}:ec2:${var.aws_region}:${local.account_id}:security-group/*"
      ec2_vpc_endpoint   = "arn:${local.partition}:ec2:${var.aws_region}:${local.account_id}:vpc-endpoint/*"
    }
  }
}

data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

data "aws_prefix_list" "dynamodb" {
  name = "com.amazonaws.${var.aws_region}.dynamodb"
}

module "runtime_iam" {
  source = "./modules/runtime_iam"

  environment              = var.environment
  table_arn                = local.table_arn
  aws_account_id           = data.aws_caller_identity.current.account_id
  aws_partition            = data.aws_partition.current.partition
  aws_region               = var.aws_region
  permissions_boundary_arn = null
  tags                     = local.common_tags
}

module "lambda" {
  source = "./modules/lambda"

  environment          = var.environment
  table_name           = local.table_name
  subnet_ids           = module.network.private_subnet_ids
  security_group_id    = module.network.lambda_security_group_id
  package_path         = local.lambda_package_path
  role_arn             = module.runtime_iam.role_arn
  application_version  = var.application_version
  memory_size          = var.lambda_memory_size
  timeout_seconds      = var.lambda_timeout_seconds
  reserved_concurrency = var.lambda_reserved_concurrency
  request_ttl_days     = var.request_ttl_days
  max_payload_length   = var.max_payload_length
  log_retention_days   = var.log_retention_days
  tags                 = local.common_tags

  depends_on = [
    module.dynamodb,
    module.network,
  ]
}

module "kms" {
  source = "./modules/kms"

  environment          = var.environment
  aws_account_id       = data.aws_caller_identity.current.account_id
  aws_partition        = data.aws_partition.current.partition
  aws_region           = var.aws_region
  table_name           = local.table_name
  runtime_role_arn     = local.runtime_role_arn
  deployment_role_arn  = local.deployment_role_arn
  deletion_window_days = var.kms_deletion_window_days
  rotation_period_days = var.kms_rotation_period_days
  tags                 = local.common_tags

  depends_on = [module.runtime_iam]
}

module "dynamodb" {
  source = "./modules/dynamodb"

  environment                 = var.environment
  kms_key_arn                 = module.kms.key_arn
  point_in_time_recovery      = var.dynamodb_point_in_time_recovery_enabled
  deletion_protection_enabled = var.dynamodb_deletion_protection_enabled
  tags                        = local.common_tags
}

module "network" {
  source = "./modules/network"

  environment             = var.environment
  aws_region              = var.aws_region
  vpc_cidr                = var.vpc_cidr
  private_subnet_cidrs    = var.private_subnet_cidrs
  availability_zones      = var.availability_zones
  dynamodb_prefix_list_id = data.aws_prefix_list.dynamodb.id
  dynamodb_table_arn      = local.table_arn
  lambda_runtime_role_arn = local.runtime_role_arn
  tags                    = local.common_tags
}

module "api_gateway" {
  source = "./modules/api_gateway"

  environment                = var.environment
  aws_region                 = var.aws_region
  aws_partition              = data.aws_partition.current.partition
  aws_account_id             = data.aws_caller_identity.current.account_id
  lambda_function_name       = module.lambda.function_name
  lambda_qualifier           = module.lambda.release_alias_name
  lambda_invoke_arn          = module.lambda.release_alias_invoke_arn
  max_payload_length         = var.max_payload_length
  log_retention_days         = var.log_retention_days
  stage_throttle_rate_limit  = var.stage_throttle_rate_limit
  stage_throttle_burst_limit = var.stage_throttle_burst_limit
  usage_plan_rate_limit      = var.usage_plan_rate_limit
  usage_plan_burst_limit     = var.usage_plan_burst_limit
  tags                       = local.common_tags
}

module "observability" {
  source = "./modules/observability"

  environment              = var.environment
  aws_region               = var.aws_region
  lambda_function_name     = module.lambda.function_name
  api_name                 = module.api_gateway.api_name
  api_stage_name           = module.api_gateway.stage_name
  api_latency_threshold_ms = var.api_latency_alarm_threshold_ms
  tags                     = local.common_tags
}

check "usage_plan_is_not_weaker_than_stage" {
  assert {
    condition = (
      var.usage_plan_rate_limit <= var.stage_throttle_rate_limit &&
      var.usage_plan_burst_limit <= var.stage_throttle_burst_limit
    )
    error_message = "The per-key usage plan must be at least as restrictive as the stage throttle."
  }
}

check "availability_zones_match_region" {
  assert {
    condition = alltrue([
      for availability_zone in var.availability_zones :
      startswith(availability_zone, var.aws_region)
    ])
    error_message = "Every configured Availability Zone must belong to aws_region."
  }
}

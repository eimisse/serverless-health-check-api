mock_provider "aws" {
  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::123456789012:role/mock-role"
      id  = "mock-role"
    }
  }

  mock_resource "aws_cloudwatch_log_group" {
    defaults = {
      arn  = "arn:aws:logs:eu-west-1:123456789012:log-group:mock-log-group"
      name = "mock-log-group"
    }
  }

  mock_resource "aws_api_gateway_rest_api" {
    defaults = {
      execution_arn    = "arn:aws:execute-api:eu-west-1:123456789012:api1234567"
      id               = "api1234567"
      root_resource_id = "root1234567"
    }
  }
}

run "network_is_private_and_dynamodb_only" {
  command = plan

  module {
    source = "./modules/network"
  }

  variables {
    environment             = "staging"
    aws_region              = "eu-west-1"
    vpc_cidr                = "10.10.0.0/24"
    private_subnet_cidrs    = ["10.10.0.0/26", "10.10.0.64/26"]
    availability_zones      = ["eu-west-1a", "eu-west-1b"]
    dynamodb_prefix_list_id = "pl-12345678"
    dynamodb_table_arn      = "arn:aws:dynamodb:eu-west-1:123456789012:table/staging-requests-db"
    lambda_runtime_role_arn = "arn:aws:iam::123456789012:role/staging-health-check-function-role"
    tags = {
      Environment = "staging"
      ManagedBy   = "Terraform"
      Project     = "serverless-health-check-api"
      Repository  = "eimisse/serverless-health-check-api"
    }
  }

  assert {
    condition     = aws_vpc.this.enable_dns_support && aws_vpc.this.enable_dns_hostnames
    error_message = "VPC DNS support and hostnames must be enabled."
  }

  assert {
    condition = (
      length(aws_subnet.private) == 2 &&
      aws_subnet.private[0].availability_zone != aws_subnet.private[1].availability_zone &&
      alltrue([for subnet in aws_subnet.private : subnet.map_public_ip_on_launch == false])
    )
    error_message = "Lambda requires two private subnets in distinct Availability Zones."
  }

  assert {
    condition = (
      !strcontains(file("${path.module}/main.tf"), "resource \"aws_nat_gateway\"") &&
      !strcontains(file("${path.module}/main.tf"), "resource \"aws_internet_gateway\"")
    )
    error_message = "The network module must not create NAT or Internet gateways."
  }

  assert {
    condition = (
      aws_vpc_security_group_egress_rule.dynamodb_https.prefix_list_id == "pl-12345678" &&
      aws_vpc_security_group_egress_rule.dynamodb_https.from_port == 443 &&
      aws_vpc_security_group_egress_rule.dynamodb_https.to_port == 443
    )
    error_message = "Lambda egress must be HTTPS to the DynamoDB prefix list only."
  }

  assert {
    condition = (
      aws_vpc_endpoint.dynamodb.vpc_endpoint_type == "Gateway" &&
      jsondecode(aws_vpc_endpoint.dynamodb.policy).Statement[0].Action == "dynamodb:PutItem" &&
      jsondecode(aws_vpc_endpoint.dynamodb.policy).Statement[0].Resource == "arn:aws:dynamodb:eu-west-1:123456789012:table/staging-requests-db"
    )
    error_message = "The DynamoDB gateway endpoint must allow only PutItem to the exact table."
  }
}

run "kms_rotation_and_scope" {
  command = plan

  module {
    source = "./modules/kms"
  }

  variables {
    environment          = "staging"
    aws_account_id       = "123456789012"
    aws_partition        = "aws"
    aws_region           = "eu-west-1"
    table_name           = "staging-requests-db"
    runtime_role_arn     = "arn:aws:iam::123456789012:role/staging-health-check-function-role"
    deployment_role_arn  = "arn:aws:iam::123456789012:role/staging-health-check-deployment-role"
    deletion_window_days = 7
    rotation_period_days = 365
    tags = {
      Environment = "staging"
      ManagedBy   = "Terraform"
      Project     = "serverless-health-check-api"
      Repository  = "eimisse/serverless-health-check-api"
    }
  }

  assert {
    condition = (
      aws_kms_key.dynamodb.enable_key_rotation &&
      aws_kms_key.dynamodb.rotation_period_in_days == 365 &&
      aws_kms_key.dynamodb.customer_master_key_spec == "SYMMETRIC_DEFAULT"
    )
    error_message = "The DynamoDB CMK must be symmetric and automatically rotated."
  }

  assert {
    condition     = aws_kms_alias.dynamodb.name == "alias/staging-requests-db-key"
    error_message = "The KMS alias must use the environment prefix."
  }

  assert {
    condition     = !strcontains(aws_kms_key.dynamodb.policy, "kms:*")
    error_message = "The KMS key policy must never use a wildcard action."
  }

  assert {
    condition = alltrue([
      for statement in jsondecode(aws_kms_key.dynamodb.policy).Statement :
      contains(statement.Action, "kms:UpdateAlias")
      if contains(["AccountRootBreakGlassAdministration", "DeploymentRoleKeyAdministration"], statement.Sid)
    ])
    error_message = "Both break-glass and deployment administrators need key-side UpdateAlias permission for safe key replacement."
  }

  assert {
    condition = one([
      for statement in jsondecode(aws_kms_key.dynamodb.policy).Statement : statement.Principal.AWS
      if statement.Sid == "AccountRootBreakGlassAdministration"
    ]) == "arn:aws:iam::123456789012:root"
    error_message = "Break-glass KMS administration must belong to the account root principal, never the Lambda runtime role."
  }

  assert {
    condition = one([
      for statement in jsondecode(aws_kms_key.dynamodb.policy).Statement : statement.Principal.AWS
      if statement.Sid == "RuntimeRoleDynamoDBCryptoUse"
    ]) == "arn:aws:iam::123456789012:role/staging-health-check-function-role"
    error_message = "Runtime DynamoDB KMS use must be granted directly to the exact Lambda role."
  }

  assert {
    condition = alltrue([
      for required_action in [
        "kms:Decrypt",
        "kms:DescribeKey",
        "kms:Encrypt",
        "kms:GenerateDataKey",
        "kms:GenerateDataKeyWithoutPlaintext",
        "kms:ReEncryptFrom",
        "kms:ReEncryptTo",
        ] : contains(
        one([
          for statement in jsondecode(aws_kms_key.dynamodb.policy).Statement : statement.Action
          if statement.Sid == "RuntimeRoleDynamoDBCryptoUse"
        ]),
        required_action,
      )
    ])
    error_message = "Runtime DynamoDB KMS use must include only the cryptographic operations DynamoDB needs on the caller's behalf."
  }

  assert {
    condition = (
      one([
        for statement in jsondecode(aws_kms_key.dynamodb.policy).Statement : statement.Condition.StringEquals["kms:ViaService"]
        if statement.Sid == "RuntimeRoleDynamoDBCryptoUse"
      ]) == "dynamodb.eu-west-1.amazonaws.com" &&
      one([
        for statement in jsondecode(aws_kms_key.dynamodb.policy).Statement : statement.Condition.StringEquals["kms:EncryptionContext:aws:dynamodb:tableName"]
        if statement.Sid == "RuntimeRoleDynamoDBCryptoUse"
      ]) == "staging-requests-db"
    )
    error_message = "Runtime KMS use must be constrained to DynamoDB and the exact table encryption context."
  }
}

run "dynamodb_is_encrypted_and_recoverable" {
  command = plan

  module {
    source = "./modules/dynamodb"
  }

  variables {
    environment                 = "prod"
    kms_key_arn                 = "arn:aws:kms:eu-west-1:123456789012:key/11111111-2222-3333-4444-555555555555"
    point_in_time_recovery      = true
    deletion_protection_enabled = true
    tags = {
      Environment = "prod"
      ManagedBy   = "Terraform"
      Project     = "serverless-health-check-api"
      Repository  = "eimisse/serverless-health-check-api"
    }
  }

  assert {
    condition = (
      aws_dynamodb_table.requests.name == "prod-requests-db" &&
      aws_dynamodb_table.requests.billing_mode == "PAY_PER_REQUEST" &&
      aws_dynamodb_table.requests.hash_key == "request_id"
    )
    error_message = "The request table must use the exact name, PAY_PER_REQUEST, and request_id partition key."
  }

  assert {
    condition = (
      aws_dynamodb_table.requests.server_side_encryption[0].enabled &&
      aws_dynamodb_table.requests.server_side_encryption[0].kms_key_arn == "arn:aws:kms:eu-west-1:123456789012:key/11111111-2222-3333-4444-555555555555"
    )
    error_message = "DynamoDB SSE must use the supplied customer-managed KMS key."
  }

  assert {
    condition = (
      aws_dynamodb_table.requests.point_in_time_recovery[0].enabled &&
      aws_dynamodb_table.requests.ttl[0].enabled &&
      aws_dynamodb_table.requests.ttl[0].attribute_name == "expires_at" &&
      aws_dynamodb_table.requests.deletion_protection_enabled
    )
    error_message = "Prod data protection requires PITR, TTL, and deletion protection."
  }
}

run "runtime_role_is_least_privilege" {
  command = plan

  module {
    source = "./modules/runtime_iam"
  }

  variables {
    environment    = "staging"
    table_arn      = "arn:aws:dynamodb:eu-west-1:123456789012:table/staging-requests-db"
    aws_account_id = "123456789012"
    aws_partition  = "aws"
    aws_region     = "eu-west-1"
    tags = {
      Environment = "staging"
      ManagedBy   = "Terraform"
      Project     = "serverless-health-check-api"
      Repository  = "eimisse/serverless-health-check-api"
    }
  }

  assert {
    condition = (
      aws_iam_role.runtime.name == "staging-health-check-function-role" &&
      jsondecode(aws_iam_role.runtime.assume_role_policy).Statement[0].Principal.Service == "lambda.amazonaws.com"
    )
    error_message = "The runtime role must use the exact environment name and trust only Lambda."
  }

  assert {
    condition = (
      strcontains(aws_iam_role_policy.runtime.policy, "dynamodb:PutItem") &&
      !strcontains(aws_iam_role_policy.runtime.policy, "dynamodb:Scan") &&
      !strcontains(aws_iam_role_policy.runtime.policy, "dynamodb:DeleteItem") &&
      !strcontains(aws_iam_role_policy.runtime.policy, "kms:") &&
      !strcontains(aws_iam_role_policy.runtime.policy, "iam:") &&
      !strcontains(aws_iam_role_policy.runtime.policy, "s3:")
    )
    error_message = "The runtime IAM identity policy must contain only persistence, logging, and exact VPC lifecycle permissions; KMS authorization is constrained in the key policy."
  }
}

run "lambda_has_bounded_private_runtime" {
  command = apply

  module {
    source = "./modules/lambda"
  }

  variables {
    environment          = "staging"
    table_name           = "staging-requests-db"
    subnet_ids           = ["subnet-11111111", "subnet-22222222"]
    security_group_id    = "sg-11111111"
    package_path         = "../build/lambda.zip"
    role_arn             = "arn:aws:iam::123456789012:role/staging-health-check-function-role"
    application_version  = "0123456789abcdef0123456789abcdef01234567"
    memory_size          = 128
    timeout_seconds      = 5
    reserved_concurrency = 2
    request_ttl_days     = 30
    max_payload_length   = 4096
    log_retention_days   = 14
    tags = {
      Environment = "staging"
      ManagedBy   = "Terraform"
      Project     = "serverless-health-check-api"
      Repository  = "eimisse/serverless-health-check-api"
    }
  }

  assert {
    condition = (
      aws_lambda_function.health.function_name == "staging-health-check-function" &&
      aws_lambda_function.health.runtime == "python3.14" &&
      aws_lambda_function.health.reserved_concurrent_executions == 2 &&
      length(aws_lambda_function.health.vpc_config[0].subnet_ids) == 2
    )
    error_message = "Lambda must use Python 3.14, reserved concurrency, and both private subnets."
  }

  assert {
    condition = (
      aws_cloudwatch_log_group.lambda.retention_in_days == 14 &&
      aws_lambda_function.health.source_code_hash == filebase64sha256("../build/lambda.zip")
    )
    error_message = "Lambda must have finite log retention and track the deterministic package hash."
  }
}

run "rest_api_validates_and_throttles" {
  command = apply

  module {
    source = "./modules/api_gateway"
  }

  variables {
    environment                = "staging"
    aws_region                 = "eu-west-1"
    aws_partition              = "aws"
    aws_account_id             = "123456789012"
    lambda_function_name       = "staging-health-check-function"
    lambda_invoke_arn          = "arn:aws:lambda:eu-west-1:123456789012:function:staging-health-check-function"
    max_payload_length         = 4096
    log_retention_days         = 14
    stage_throttle_rate_limit  = 5
    stage_throttle_burst_limit = 10
    usage_plan_rate_limit      = 2
    usage_plan_burst_limit     = 4
    tags = {
      Environment = "staging"
      ManagedBy   = "Terraform"
      Project     = "serverless-health-check-api"
      Repository  = "eimisse/serverless-health-check-api"
    }
  }

  assert {
    condition = (
      aws_api_gateway_method.post.api_key_required &&
      aws_api_gateway_request_validator.body.validate_request_body &&
      jsondecode(aws_api_gateway_model.request.schema).required[0] == "payload" &&
      jsondecode(aws_api_gateway_model.request.schema).properties.payload.maxLength == 4096
    )
    error_message = "POST /health must require an API key and validate the strict payload schema before Lambda."
  }

  assert {
    condition = (
      aws_api_gateway_method_settings.post.settings[0].throttling_rate_limit == 5 &&
      aws_api_gateway_method_settings.post.settings[0].throttling_burst_limit == 10 &&
      aws_api_gateway_usage_plan.health.throttle_settings[0].rate_limit == 2 &&
      aws_api_gateway_usage_plan.health.throttle_settings[0].burst_limit == 4
    )
    error_message = "Both stage and per-key usage-plan throttling must be configured."
  }

  assert {
    condition = (
      aws_cloudwatch_log_group.access.retention_in_days == 14 &&
      aws_lambda_permission.api_gateway.source_arn == "${aws_api_gateway_rest_api.health.execution_arn}/staging/POST/health"
    )
    error_message = "API logs require finite retention and Lambda invocation must be scoped to the exact method path and stage."
  }
}

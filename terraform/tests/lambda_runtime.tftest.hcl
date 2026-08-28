mock_provider "aws" {}

run "lambda_has_quota_compatible_private_runtime" {
  command = plan

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
    reserved_concurrency = -1
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
      aws_lambda_function.health.architectures[0] == "arm64" &&
      aws_lambda_function.health.reserved_concurrent_executions == -1 &&
      aws_lambda_function.health.timeout == 5 &&
      aws_lambda_function.health.memory_size == 128 &&
      length(aws_lambda_function.health.vpc_config[0].subnet_ids) == 2
    )
    error_message = "Staging Lambda must remain a small Python 3.14 ARM64 runtime in both private subnets and use the account shared concurrency pool when quota cannot support a reservation."
  }

  assert {
    condition = (
      aws_cloudwatch_log_group.lambda.name == "staging-health-check-function-logs" &&
      aws_cloudwatch_log_group.lambda.retention_in_days == 14 &&
      aws_lambda_function.health.logging_config[0].log_group == "staging-health-check-function-logs"
    )
    error_message = "Lambda must use the explicit environment-prefixed log group with finite retention."
  }

  assert {
    condition = (
      aws_lambda_function.health.environment[0].variables.TABLE_NAME == "staging-requests-db" &&
      aws_lambda_function.health.environment[0].variables.APP_VERSION == "0123456789abcdef0123456789abcdef01234567" &&
      aws_lambda_function.health.environment[0].variables.MAX_PAYLOAD_LENGTH == "4096" &&
      aws_lambda_function.health.environment[0].variables.REQUEST_TTL_DAYS == "30"
    )
    error_message = "Lambda runtime configuration must point at the exact table and immutable release/validation settings."
  }

  # The published version number is computed by AWS and is intentionally unknown
  # during a plan-only mock. Plan/live verification separately rejects $LATEST.
  assert {
    condition = (
      aws_lambda_function.health.publish &&
      aws_lambda_function.health.source_code_hash == filebase64sha256("../build/lambda.zip") &&
      aws_lambda_alias.release.name == "staging-release" &&
      aws_lambda_alias.release.function_name == "staging-health-check-function"
    )
    error_message = "The deterministic package must publish an immutable Lambda version behind the environment release alias."
  }
}

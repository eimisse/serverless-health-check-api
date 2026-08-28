mock_provider "aws" {}

run "lambda_names_are_environment_prefixed" {
  command = plan

  module {
    source = "./modules/lambda"
  }

  variables {
    environment          = "prod"
    table_name           = "prod-requests-db"
    subnet_ids           = ["subnet-11111111", "subnet-22222222"]
    security_group_id    = "sg-11111111"
    package_path         = "../build/lambda.zip"
    role_arn             = "arn:aws:iam::123456789012:role/prod-health-check-function-role"
    application_version  = "0123456789abcdef0123456789abcdef01234567"
    memory_size          = 128
    timeout_seconds      = 5
    reserved_concurrency = 5
    request_ttl_days     = 30
    max_payload_length   = 4096
    log_retention_days   = 30
    tags = {
      Environment = "prod"
      ManagedBy   = "Terraform"
      Project     = "serverless-health-check-api"
      Repository  = "eimisse/serverless-health-check-api"
    }
  }

  assert {
    condition     = aws_lambda_function.health.function_name == "prod-health-check-function"
    error_message = "Lambda function naming must start with the environment prefix."
  }

  assert {
    condition     = aws_cloudwatch_log_group.lambda.name == "prod-health-check-function-logs"
    error_message = "The explicit Lambda log group must start with the environment prefix."
  }

  assert {
    condition     = aws_lambda_function.health.logging_config[0].log_group == aws_cloudwatch_log_group.lambda.name
    error_message = "Lambda must write to the explicit environment-prefixed log group."
  }
}
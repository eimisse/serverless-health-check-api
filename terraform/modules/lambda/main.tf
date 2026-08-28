locals {
  function_name      = "${var.environment}-health-check-function"
  log_group_name     = "${var.environment}-health-check-function-logs"
  release_alias_name = "${var.environment}-release"
}

#trivy:ignore:AVD-AWS-0017
resource "aws_cloudwatch_log_group" "lambda" {
  #checkov:skip=CKV_AWS_158:Application logs are redacted and contain no secrets; AWS-managed CloudWatch encryption avoids an additional CMK and policy surface.
  name              = local.log_group_name
  retention_in_days = var.log_retention_days
  skip_destroy      = false

  tags = merge(var.tags, {
    Name = local.log_group_name
  })
}

#trivy:ignore:AVD-AWS-0066
resource "aws_lambda_function" "health" {
  #checkov:skip=CKV_AWS_272:Deterministic SHA-pinned packaging and protected CI are proportionate here; AWS Signer would add cost and release infrastructure.
  #checkov:skip=CKV_AWS_116:DLQs apply to asynchronous invocation; API Gateway invokes this function synchronously and receives controlled errors.
  #checkov:skip=CKV_AWS_173:Environment values are non-secret identifiers/limits and already use Lambda service-managed encryption at rest.
  function_name = local.function_name
  description   = "Validated health request processor; release ${var.application_version}"
  role          = var.role_arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.14"
  architectures = ["arm64"]

  filename         = var.package_path
  source_code_hash = filebase64sha256(var.package_path)
  publish          = true

  memory_size                    = var.memory_size
  timeout                        = var.timeout_seconds
  reserved_concurrent_executions = var.reserved_concurrency

  environment {
    variables = {
      APP_VERSION        = var.application_version
      LOG_LEVEL          = "INFO"
      MAX_PAYLOAD_LENGTH = tostring(var.max_payload_length)
      REQUEST_TTL_DAYS   = tostring(var.request_ttl_days)
      TABLE_NAME         = var.table_name
    }
  }

  ephemeral_storage {
    size = 512
  }

  logging_config {
    application_log_level = "INFO"
    log_format            = "JSON"
    log_group             = aws_cloudwatch_log_group.lambda.name
    system_log_level      = "WARN"
  }

  tracing_config {
    mode = "PassThrough"
  }

  vpc_config {
    security_group_ids = [var.security_group_id]
    subnet_ids         = var.subnet_ids
  }

  tags = merge(var.tags, {
    Name = local.function_name
  })

  depends_on = [
    aws_cloudwatch_log_group.lambda,
  ]
}

resource "aws_lambda_alias" "release" {
  name             = local.release_alias_name
  description      = "Current immutable ${var.environment} release; source ${var.application_version}"
  function_name    = aws_lambda_function.health.function_name
  function_version = aws_lambda_function.health.version
}

locals {
  api_name              = "${var.environment}-health-check-api"
  access_log_group_name = "/aws/apigateway/${var.environment}-health-check-api-access"
  access_log_group_arn  = "arn:${var.aws_partition}:logs:${var.aws_region}:${var.aws_account_id}:log-group:${local.access_log_group_name}"

  request_schema = jsonencode({
    "$schema"            = "http://json-schema.org/draft-04/schema#"
    title                = "${title(var.environment)}HealthCheckRequest"
    type                 = "object"
    additionalProperties = false
    required             = ["payload"]
    properties = {
      payload = {
        type      = "string"
        minLength = 1
        maxLength = var.max_payload_length
        pattern   = ".*\\S.*"
      }
    }
  })

  access_log_format = jsonencode({
    requestId          = "$context.requestId"
    extendedRequestId  = "$context.extendedRequestId"
    sourceIp           = "$context.identity.sourceIp"
    requestTime        = "$context.requestTime"
    httpMethod         = "$context.httpMethod"
    resourcePath       = "$context.resourcePath"
    status             = "$context.status"
    protocol           = "$context.protocol"
    responseLength     = "$context.responseLength"
    integrationStatus  = "$context.integration.status"
    integrationLatency = "$context.integration.latency"
    responseLatency    = "$context.responseLatency"
  })
}

#trivy:ignore:AVD-AWS-0017
resource "aws_cloudwatch_log_group" "access" {
  #checkov:skip=CKV_AWS_158:Access logs contain no headers or payload; AWS-managed CloudWatch encryption avoids another CMK and policy surface.
  name              = local.access_log_group_name
  retention_in_days = var.log_retention_days
  skip_destroy      = false

  tags = merge(var.tags, {
    Name = "${var.environment}-health-check-api-access-logs"
  })
}

resource "aws_api_gateway_rest_api" "health" {
  name            = local.api_name
  description     = "API-key protected health request ingestion endpoint"
  security_policy = "TLS_1_2"

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = merge(var.tags, {
    Name = local.api_name
  })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_resource" "health" {
  rest_api_id = aws_api_gateway_rest_api.health.id
  parent_id   = aws_api_gateway_rest_api.health.root_resource_id
  path_part   = "health"
}

resource "aws_api_gateway_model" "request" {
  rest_api_id  = aws_api_gateway_rest_api.health.id
  name         = "${title(var.environment)}HealthCheckRequest"
  description  = "Strict POST /health JSON request body"
  content_type = "application/json"
  schema       = local.request_schema
}

resource "aws_api_gateway_request_validator" "body" {
  rest_api_id                 = aws_api_gateway_rest_api.health.id
  name                        = "${var.environment}-health-check-request-validator"
  validate_request_body       = true
  validate_request_parameters = false
}

resource "aws_api_gateway_method" "post" {
  rest_api_id      = aws_api_gateway_rest_api.health.id
  resource_id      = aws_api_gateway_resource.health.id
  http_method      = "POST"
  authorization    = "NONE"
  api_key_required = true

  request_models = {
    "application/json" = aws_api_gateway_model.request.name
  }

  request_validator_id = aws_api_gateway_request_validator.body.id
}

resource "aws_api_gateway_integration" "lambda" {
  rest_api_id             = aws_api_gateway_rest_api.health.id
  resource_id             = aws_api_gateway_resource.health.id
  http_method             = aws_api_gateway_method.post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.lambda_invoke_arn
  timeout_milliseconds    = 5000
}

resource "aws_api_gateway_gateway_response" "bad_request_body" {
  rest_api_id   = aws_api_gateway_rest_api.health.id
  response_type = "BAD_REQUEST_BODY"
  status_code   = "400"

  response_parameters = {
    "gatewayresponse.header.Cache-Control" = "'no-store'"
    "gatewayresponse.header.Content-Type"  = "'application/json'"
  }

  response_templates = {
    "application/json" = jsonencode({
      status  = "error"
      message = "Request body failed validation."
    })
  }
}

resource "aws_api_gateway_gateway_response" "bad_request_parameters" {
  rest_api_id   = aws_api_gateway_rest_api.health.id
  response_type = "BAD_REQUEST_PARAMETERS"
  status_code   = "400"

  response_parameters = {
    "gatewayresponse.header.Cache-Control" = "'no-store'"
    "gatewayresponse.header.Content-Type"  = "'application/json'"
  }

  response_templates = {
    "application/json" = jsonencode({
      status  = "error"
      message = "Request parameters failed validation."
    })
  }
}

resource "aws_api_gateway_deployment" "health" {
  rest_api_id = aws_api_gateway_rest_api.health.id

  triggers = {
    redeployment = sha1(jsonencode({
      resource_id                     = aws_api_gateway_resource.health.id
      method_id                       = aws_api_gateway_method.post.id
      integration_id                  = aws_api_gateway_integration.lambda.id
      request_schema                  = local.request_schema
      request_validator_id            = aws_api_gateway_request_validator.body.id
      bad_request_body_template       = aws_api_gateway_gateway_response.bad_request_body.response_templates
      bad_request_parameters_template = aws_api_gateway_gateway_response.bad_request_parameters.response_templates
    }))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_gateway_response.bad_request_body,
    aws_api_gateway_gateway_response.bad_request_parameters,
    aws_api_gateway_integration.lambda,
  ]
}

#trivy:ignore:AVD-AWS-0003
resource "aws_api_gateway_stage" "this" {
  #checkov:skip=CKV_AWS_120:POST requests persist unique records and must never be served from a cache.
  #checkov:skip=CKV_AWS_73:X-Ray would add wildcard runtime permissions and cost; structured access logs and metrics cover this small synchronous path.
  #checkov:skip=CKV2_AWS_51:Client certificates authenticate API Gateway to a private backend, not callers of this Lambda proxy API.
  #checkov:skip=CKV2_AWS_4:Structured access logging is enabled; execution/data tracing stays off to avoid recording request content.
  #checkov:skip=CKV2_AWS_29:WAF cost and complexity are not justified for this bounded homework API with API keys and three throttling layers.
  rest_api_id   = aws_api_gateway_rest_api.health.id
  deployment_id = aws_api_gateway_deployment.health.id
  stage_name    = var.environment

  access_log_settings {
    destination_arn = local.access_log_group_arn
    format          = local.access_log_format
  }

  cache_cluster_enabled = false
  xray_tracing_enabled  = false

  tags = merge(var.tags, {
    Name = "${var.environment}-health-check-api-stage"
  })

  depends_on = [aws_cloudwatch_log_group.access]
}

#trivy:ignore:AVD-AWS-0190
resource "aws_api_gateway_method_settings" "post" {
  #checkov:skip=CKV_AWS_225:POST requests have side effects and must not be cached.
  rest_api_id = aws_api_gateway_rest_api.health.id
  stage_name  = aws_api_gateway_stage.this.stage_name
  method_path = "health/POST"

  settings {
    cache_data_encrypted                       = false
    cache_ttl_in_seconds                       = 0
    caching_enabled                            = false
    data_trace_enabled                         = false
    logging_level                              = "OFF"
    metrics_enabled                            = true
    throttling_burst_limit                     = var.stage_throttle_burst_limit
    throttling_rate_limit                      = var.stage_throttle_rate_limit
    unauthorized_cache_control_header_strategy = "FAIL_WITH_403"
  }
}

resource "aws_api_gateway_api_key" "health" {
  name        = "${var.environment}-health-check-api-key"
  description = "AWS-generated key for the ${var.environment} health-check usage plan"
  enabled     = true

  tags = merge(var.tags, {
    Name = "${var.environment}-health-check-api-key"
  })
}

resource "aws_api_gateway_usage_plan" "health" {
  name        = "${var.environment}-health-check-usage-plan"
  description = "Per-key throttling for POST /health"

  api_stages {
    api_id = aws_api_gateway_rest_api.health.id
    stage  = aws_api_gateway_stage.this.stage_name
  }

  throttle_settings {
    burst_limit = var.usage_plan_burst_limit
    rate_limit  = var.usage_plan_rate_limit
  }

  tags = merge(var.tags, {
    Name = "${var.environment}-health-check-usage-plan"
  })

  depends_on = [aws_api_gateway_method_settings.post]
}

resource "aws_api_gateway_usage_plan_key" "health" {
  key_id        = aws_api_gateway_api_key.health.id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.health.id
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "${title(var.environment)}AllowApiGatewayHealthPost"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.health.execution_arn}/${aws_api_gateway_stage.this.stage_name}/POST/health"
}

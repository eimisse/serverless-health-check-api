mock_provider "aws" {
  mock_resource "aws_api_gateway_rest_api" {
    defaults = {
      execution_arn    = "arn:aws:execute-api:eu-west-1:123456789012:api1234567"
      id               = "api1234567"
      root_resource_id = "root1234567"
    }
  }

  mock_resource "aws_api_gateway_stage" {
    defaults = {
      stage_name = "staging-health-check-stage"
      invoke_url = "https://api1234567.execute-api.eu-west-1.amazonaws.com/staging-health-check-stage"
    }
  }
}

run "health_api_security_contract" {
  command = plan

  module {
    source = "./modules/api_gateway"
  }

  variables {
    environment                = "staging"
    aws_region                 = "eu-west-1"
    aws_partition              = "aws"
    aws_account_id             = "123456789012"
    lambda_function_name       = "staging-health-check-function"
    lambda_qualifier           = "staging-release"
    lambda_invoke_arn          = "arn:aws:apigateway:eu-west-1:lambda:path/2015-03-31/functions/arn:aws:lambda:eu-west-1:123456789012:function:staging-health-check-function:staging-release/invocations"
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
      aws_api_gateway_rest_api.health.name == "staging-health-check-api" &&
      aws_api_gateway_stage.this.stage_name == "staging-health-check-stage" &&
      aws_cloudwatch_log_group.access.name == "staging-health-check-api-access-logs" &&
      aws_api_gateway_api_key.health.name == "staging-health-check-api-key" &&
      aws_api_gateway_usage_plan.health.name == "staging-health-check-usage-plan"
    )
    error_message = "Customer-named API resources must retain the staging- prefix."
  }

  assert {
    condition = (
      aws_api_gateway_rest_api.health.security_policy == "SecurityPolicy_TLS13_1_2_2021_06" &&
      aws_api_gateway_rest_api.health.endpoint_access_mode == "BASIC" &&
      aws_api_gateway_rest_api.health.endpoint_configuration[0].types[0] == "REGIONAL"
    )
    error_message = "REST API must retain the live-compatible TLS 1.2/1.3 security policy, BASIC access mode, and REGIONAL endpoint."
  }

  assert {
    condition     = aws_api_gateway_model.request.name == "stagingHealthCheckRequest"
    error_message = "The API model must keep the environment prefix while respecting API Gateway's alphanumeric-only model-name syntax."
  }

  assert {
    condition = (
      aws_api_gateway_method.get.http_method == "GET" &&
      aws_api_gateway_method.get.api_key_required &&
      aws_api_gateway_method.post.http_method == "POST" &&
      aws_api_gateway_method.post.api_key_required
    )
    error_message = "Both exposed health methods must remain API-key protected."
  }

  assert {
    condition = (
      aws_api_gateway_request_validator.body.validate_request_body &&
      !aws_api_gateway_request_validator.body.validate_request_parameters
    )
    error_message = "The POST body validator must remain enabled."
  }

  assert {
    condition = (
      aws_api_gateway_method.post.request_models["$default"] == aws_api_gateway_model.request.name &&
      aws_api_gateway_method.post.request_models["application/json"] == aws_api_gateway_model.request.name
    )
    error_message = "The strict model must apply to application/json and $default so Content-Type cannot bypass validation."
  }

  assert {
    condition = (
      jsondecode(aws_api_gateway_model.request.schema).type == "object" &&
      jsondecode(aws_api_gateway_model.request.schema).additionalProperties == false &&
      contains(jsondecode(aws_api_gateway_model.request.schema).required, "payload") &&
      jsondecode(aws_api_gateway_model.request.schema).properties.payload.type == "string" &&
      jsondecode(aws_api_gateway_model.request.schema).properties.payload.minLength == 1 &&
      jsondecode(aws_api_gateway_model.request.schema).properties.payload.maxLength == 4096
    )
    error_message = "The request schema must keep a strict, bounded string payload contract."
  }

  assert {
    condition = (
      aws_api_gateway_integration.lambda_get.uri == var.lambda_invoke_arn &&
      aws_api_gateway_integration.lambda.uri == var.lambda_invoke_arn
    )
    error_message = "GET and POST must invoke the immutable environment release alias, never unqualified $LATEST."
  }

  assert {
    condition = (
      aws_api_gateway_method_settings.get.settings[0].throttling_rate_limit == 5 &&
      aws_api_gateway_method_settings.get.settings[0].throttling_burst_limit == 10 &&
      aws_api_gateway_method_settings.post.settings[0].throttling_rate_limit == 5 &&
      aws_api_gateway_method_settings.post.settings[0].throttling_burst_limit == 10 &&
      aws_api_gateway_usage_plan.health.throttle_settings[0].rate_limit == 2 &&
      aws_api_gateway_usage_plan.health.throttle_settings[0].burst_limit == 4
    )
    error_message = "Stage and per-key throttling must remain configured."
  }

  assert {
    condition = (
      aws_api_gateway_method_settings.get.settings[0].data_trace_enabled == false &&
      aws_api_gateway_method_settings.post.settings[0].data_trace_enabled == false &&
      aws_api_gateway_stage.this.cache_cluster_enabled == false
    )
    error_message = "Request-body tracing and API caching must remain disabled for this write path."
  }

  # execution_arn/source_arn values are provider-computed during a plan-only mock.
  # Exact stage/method/path scoping is enforced by the saved-plan guard and live verifier.
  assert {
    condition = (
      aws_lambda_permission.api_gateway_get.action == "lambda:InvokeFunction" &&
      aws_lambda_permission.api_gateway_get.qualifier == "staging-release" &&
      aws_lambda_permission.api_gateway_get.principal == "apigateway.amazonaws.com" &&
      aws_lambda_permission.api_gateway.action == "lambda:InvokeFunction" &&
      aws_lambda_permission.api_gateway.qualifier == "staging-release" &&
      aws_lambda_permission.api_gateway.principal == "apigateway.amazonaws.com"
    )
    error_message = "API Gateway invoke permission must stay alias-qualified and trust only API Gateway."
  }
}

locals {
  name_prefix = "${var.environment}-health-check"

  lambda_dimensions = {
    FunctionName = var.lambda_function_name
  }

  api_dimensions = {
    ApiName = var.api_name
    Stage   = var.api_stage_name
  }
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  #checkov:skip=CKV_AWS_319:This homework has no real paging destination; the alarm remains visible without sending meaningless notifications.
  alarm_name          = "${local.name_prefix}-function-errors"
  alarm_description   = "At least one Lambda error occurred in five minutes; no paging action is configured for this homework."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = local.lambda_dimensions
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  datapoints_to_alarm = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  actions_enabled     = false

  tags = merge(var.tags, {
    Name = "${local.name_prefix}-function-errors"
  })
}

resource "aws_cloudwatch_metric_alarm" "lambda_throttles" {
  #checkov:skip=CKV_AWS_319:This homework has no real paging destination; the alarm remains visible without sending meaningless notifications.
  alarm_name          = "${local.name_prefix}-function-throttles"
  alarm_description   = "At least one Lambda throttle occurred in five minutes; inspect concurrency and request rate."
  namespace           = "AWS/Lambda"
  metric_name         = "Throttles"
  dimensions          = local.lambda_dimensions
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  datapoints_to_alarm = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  actions_enabled     = false

  tags = merge(var.tags, {
    Name = "${local.name_prefix}-function-throttles"
  })
}

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  #checkov:skip=CKV_AWS_319:This homework has no real paging destination; the alarm remains visible without sending meaningless notifications.
  alarm_name          = "${local.name_prefix}-api-5xx"
  alarm_description   = "At least one REST API server error occurred in five minutes."
  namespace           = "AWS/ApiGateway"
  metric_name         = "5XXError"
  dimensions          = local.api_dimensions
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  datapoints_to_alarm = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  actions_enabled     = false

  tags = merge(var.tags, {
    Name = "${local.name_prefix}-api-5xx"
  })
}

resource "aws_cloudwatch_metric_alarm" "api_latency" {
  #checkov:skip=CKV_AWS_319:This homework has no real paging destination; the alarm remains visible without sending meaningless notifications.
  alarm_name          = "${local.name_prefix}-api-latency"
  alarm_description   = "REST API p95 latency exceeded the environment threshold for two consecutive periods."
  namespace           = "AWS/ApiGateway"
  metric_name         = "Latency"
  dimensions          = local.api_dimensions
  extended_statistic  = "p95"
  period              = 300
  evaluation_periods  = 2
  datapoints_to_alarm = 2
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.api_latency_threshold_ms
  treat_missing_data  = "notBreaching"
  actions_enabled     = false

  tags = merge(var.tags, {
    Name = "${local.name_prefix}-api-latency"
  })
}

resource "aws_cloudwatch_dashboard" "service" {
  dashboard_name = "${local.name_prefix}-dashboard"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "text"
        x      = 0
        y      = 0
        width  = 24
        height = 2
        properties = {
          markdown = "# ${title(var.environment)} serverless health-check API\nFocused request, error, throttle, and latency signals."
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 2
        width  = 12
        height = 6
        properties = {
          title  = "Lambda requests and failures"
          region = var.aws_region
          view   = "timeSeries"
          stat   = "Sum"
          period = 300
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", var.lambda_function_name],
            [".", "Errors", ".", "."],
            [".", "Throttles", ".", "."],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 2
        width  = 12
        height = 6
        properties = {
          title  = "REST API responses"
          region = var.aws_region
          view   = "timeSeries"
          stat   = "Sum"
          period = 300
          metrics = [
            ["AWS/ApiGateway", "Count", "ApiName", var.api_name, "Stage", var.api_stage_name],
            [".", "4XXError", ".", ".", ".", "."],
            [".", "5XXError", ".", ".", ".", "."],
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 8
        width  = 24
        height = 6
        properties = {
          title  = "REST API p95 latency"
          region = var.aws_region
          view   = "timeSeries"
          stat   = "p95"
          period = 300
          metrics = [
            ["AWS/ApiGateway", "Latency", "ApiName", var.api_name, "Stage", var.api_stage_name],
            [".", "IntegrationLatency", ".", ".", ".", "."],
          ]
        }
      },
    ]
  })
}

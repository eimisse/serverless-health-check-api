locals {
  api_gateway_log_group_arns = [
    for environment in local.environments :
    local.resource_arns[environment].api_access_log_group
  ]

  api_gateway_log_stream_arns = [
    for log_group_arn in local.api_gateway_log_group_arns : "${log_group_arn}:*"
  ]
}

resource "aws_iam_role" "api_gateway_cloudwatch" {
  name                 = "shared-health-check-api-logs-role"
  description          = "Regional API Gateway role restricted to health-check access logs"
  max_session_duration = 3600

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ApiGatewayServiceAssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "apigateway.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "shared-health-check-api-logs-role"
  })
}

resource "aws_iam_role_policy" "api_gateway_cloudwatch" {
  name = "shared-health-check-api-logs-policy"
  role = aws_iam_role.api_gateway_cloudwatch.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "DiscoverRegionalLogGroups"
        Effect   = "Allow"
        Action   = "logs:DescribeLogGroups"
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:RequestedRegion" = var.aws_region
          }
        }
      },
      {
        Sid      = "DescribeOnlyHealthCheckLogStreams"
        Effect   = "Allow"
        Action   = "logs:DescribeLogStreams"
        Resource = local.api_gateway_log_group_arns
      },
      {
        Sid    = "WriteOnlyHealthCheckLogStreams"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = local.api_gateway_log_stream_arns
      },
    ]
  })
}

# API Gateway exposes one CloudWatch role setting per AWS account and Region.
# Bootstrap owns it once so independent staging/prod state cannot fight over it.
resource "aws_api_gateway_account" "regional" {
  cloudwatch_role_arn = aws_iam_role.api_gateway_cloudwatch.arn

  depends_on = [aws_iam_role_policy.api_gateway_cloudwatch]
}

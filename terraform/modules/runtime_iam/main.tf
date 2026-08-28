locals {
  function_name  = "${var.environment}-health-check-function"
  role_name      = "${var.environment}-health-check-function-role"
  log_group_name = "${var.environment}-health-check-function-logs"
  function_arn   = "arn:${var.aws_partition}:lambda:${var.aws_region}:${var.aws_account_id}:function:${local.function_name}"
  log_group_arn  = "arn:${var.aws_partition}:logs:${var.aws_region}:${var.aws_account_id}:log-group:${local.log_group_name}"

  vpc_eni_actions = [
    "ec2:AssignPrivateIpAddresses",
    "ec2:CreateNetworkInterface",
    "ec2:DeleteNetworkInterface",
    "ec2:DescribeNetworkInterfaces",
    "ec2:DescribeSubnets",
    "ec2:UnassignPrivateIpAddresses",
  ]
}

resource "aws_iam_role" "runtime" {
  name                 = local.role_name
  description          = "Least-privilege runtime role for ${local.function_name}"
  max_session_duration = 3600
  permissions_boundary = var.permissions_boundary_arn

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "LambdaServiceAssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(var.tags, {
    Name = local.role_name
  })
}

resource "aws_iam_role_policy" "runtime" {
  name = "${var.environment}-health-check-function-policy"
  role = aws_iam_role.runtime.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "PersistRequestOnly"
        Effect   = "Allow"
        Action   = "dynamodb:PutItem"
        Resource = var.table_arn
      },
      {
        Sid    = "WriteOnlyApplicationLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "${local.log_group_arn}:*"
      },
      {
        Sid    = "LambdaVpcEniLifecycle"
        Effect = "Allow"
        Action = local.vpc_eni_actions
        # Lambda's VPC control plane cannot scope this lifecycle to ENI ARNs
        # that do not exist yet. The exact actions are machine-audited.
        Resource = "*"
      },
      {
        Sid      = "DenyFunctionCodeVpcEniCalls"
        Effect   = "Deny"
        Action   = local.vpc_eni_actions
        Resource = "*"
        Condition = {
          ArnEquals = {
            "lambda:SourceFunctionArn" = local.function_arn
          }
        }
      },
    ]
  })
}
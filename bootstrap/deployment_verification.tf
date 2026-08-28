locals {
  deployment_verification_policy_name = {
    for environment in local.environments :
    environment => "${environment}-health-check-deployment-verification"
  }
}

data "aws_iam_policy_document" "deployment_verification" {
  for_each = local.environments

  statement {
    sid       = "ReadSmokeTestItem"
    effect    = "Allow"
    actions   = ["dynamodb:GetItem"]
    resources = [local.resource_arns[each.key].table]
  }

  statement {
    sid       = "VerifyLambdaApplicationLogs"
    effect    = "Allow"
    actions   = ["logs:FilterLogEvents"]
    resources = ["${local.resource_arns[each.key].lambda_log_group}:*"]
  }

  # These read-only EC2 APIs are required to prove that the deployed Lambda VPC
  # has no Internet Gateway or NAT Gateway. They do not support resource-level
  # authorization, so the statement is constrained to the deployment Region.
  statement {
    sid    = "VerifyNetworkIsolationReadOnly"
    effect = "Allow"
    actions = [
      "ec2:DescribeInternetGateways",
      "ec2:DescribeNatGateways",
    ]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }
  }
}

resource "aws_iam_role_policy" "deployment_verification" {
  for_each = local.environments

  name   = local.deployment_verification_policy_name[each.key]
  role   = aws_iam_role.deployment[each.key].id
  policy = data.aws_iam_policy_document.deployment_verification[each.key].json
}

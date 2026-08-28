data "aws_iam_policy_document" "deployment_state_runtime" {
  for_each = local.environments

  statement {
    sid    = "ReadOwnStateBucket"
    effect = "Allow"
    actions = [
      "s3:GetBucketLocation",
      "s3:GetBucketVersioning",
    ]
    resources = [local.state_bucket_arn]
  }

  statement {
    sid       = "ListOwnStatePrefix"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [local.state_bucket_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        local.state_key_by_environment[each.key],
        "${local.state_key_by_environment[each.key]}.tflock",
      ]
    }
  }

  statement {
    sid    = "ManageOwnStateObjects"
    effect = "Allow"
    actions = [
      "s3:DeleteObject",
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = [
      "${local.state_bucket_arn}/${local.state_key_by_environment[each.key]}",
      "${local.state_bucket_arn}/${local.state_key_by_environment[each.key]}.tflock",
    ]
  }

  statement {
    sid    = "UseStateEncryptionKey"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:DescribeKey",
      "kms:Encrypt",
      "kms:GenerateDataKey",
    ]
    resources = [aws_kms_key.state.arn]
  }

  statement {
    sid    = "ManageExactRuntimeRole"
    effect = "Allow"
    actions = [
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:GetRole",
      "iam:ListRolePolicies",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:UpdateAssumeRolePolicy",
    ]
    resources = [local.resource_arns[each.key].runtime_role]
  }

  statement {
    sid    = "ManageExactRuntimeInlinePolicy"
    effect = "Allow"
    actions = [
      "iam:DeleteRolePolicy",
      "iam:GetRolePolicy",
      "iam:PutRolePolicy",
    ]
    resources = [local.resource_arns[each.key].runtime_role]
  }

  statement {
    sid       = "PassRuntimeRoleOnlyToLambda"
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = [local.resource_arns[each.key].runtime_role]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "deployment_application" {
  for_each = local.environments

  statement {
    sid    = "ManageExactLambda"
    effect = "Allow"
    actions = [
      "lambda:AddPermission",
      "lambda:CreateFunction",
      "lambda:DeleteFunction",
      "lambda:DeleteFunctionConcurrency",
      "lambda:GetFunction",
      "lambda:GetFunctionCodeSigningConfig",
      "lambda:GetFunctionConcurrency",
      "lambda:GetFunctionConfiguration",
      "lambda:GetPolicy",
      "lambda:ListTags",
      "lambda:ListVersionsByFunction",
      "lambda:PublishVersion",
      "lambda:PutFunctionConcurrency",
      "lambda:RemovePermission",
      "lambda:TagResource",
      "lambda:UntagResource",
      "lambda:UpdateFunctionCode",
      "lambda:UpdateFunctionConfiguration",
    ]
    resources = [local.resource_arns[each.key].function]
  }

  statement {
    sid    = "ManageExactDynamoDBTable"
    effect = "Allow"
    actions = [
      "dynamodb:CreateTable",
      "dynamodb:DeleteTable",
      "dynamodb:DescribeContinuousBackups",
      "dynamodb:DescribeTable",
      "dynamodb:DescribeTimeToLive",
      "dynamodb:ListTagsOfResource",
      "dynamodb:TagResource",
      "dynamodb:UntagResource",
      "dynamodb:UpdateContinuousBackups",
      "dynamodb:UpdateTable",
      "dynamodb:UpdateTimeToLive",
    ]
    resources = [local.resource_arns[each.key].table]
  }
}

data "aws_iam_policy_document" "deployment_kms" {
  for_each = local.environments

  statement {
    sid       = "CreateOnlyApplicationEncryptionKey"
    effect    = "Allow"
    actions   = ["kms:CreateKey"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "kms:KeySpec"
      values   = ["SYMMETRIC_DEFAULT"]
    }

    condition {
      test     = "StringEquals"
      variable = "kms:KeyUsage"
      values   = ["ENCRYPT_DECRYPT"]
    }

    condition {
      test     = "Bool"
      variable = "kms:MultiRegion"
      values   = ["false"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/Environment"
      values   = [each.key]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/Project"
      values   = [local.project_name]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }
  }

  statement {
    sid       = "TagApplicationEncryptionKeyDuringCreate"
    effect    = "Allow"
    actions   = ["kms:TagResource"]
    resources = [local.resource_arns[each.key].application_key]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/Environment"
      values   = [each.key]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/Project"
      values   = [local.project_name]
    }
  }

  statement {
    sid    = "ManageTaggedApplicationEncryptionKey"
    effect = "Allow"
    actions = [
      "kms:DescribeKey",
      "kms:DisableKey",
      "kms:DisableKeyRotation",
      "kms:EnableKey",
      "kms:EnableKeyRotation",
      "kms:GetKeyPolicy",
      "kms:GetKeyRotationStatus",
      "kms:ListResourceTags",
      "kms:PutKeyPolicy",
      "kms:ScheduleKeyDeletion",
      "kms:TagResource",
      "kms:UntagResource",
      "kms:UpdateKeyDescription",
    ]
    resources = [local.resource_arns[each.key].application_key]

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/Environment"
      values   = [each.key]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/Project"
      values   = [local.project_name]
    }
  }

  statement {
    sid    = "ManageExactApplicationKeyAlias"
    effect = "Allow"
    actions = [
      "kms:CreateAlias",
      "kms:DeleteAlias",
      "kms:UpdateAlias",
    ]
    resources = [
      local.resource_arns[each.key].application_key_alias,
      local.resource_arns[each.key].application_key,
    ]
  }

  statement {
    sid       = "DiscoverKmsAliases"
    effect    = "Allow"
    actions   = ["kms:ListAliases"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }
  }
}

data "aws_iam_policy_document" "deployment_network" {
  for_each = local.environments

  statement {
    sid    = "DescribeRegionalEc2ControlPlane"
    effect = "Allow"
    actions = [
      "ec2:DescribeAvailabilityZones",
      "ec2:DescribeManagedPrefixLists",
      "ec2:DescribeNetworkInterfaces",
      "ec2:DescribePrefixLists",
      "ec2:DescribeRouteTables",
      "ec2:DescribeSecurityGroupRules",
      "ec2:DescribeSecurityGroups",
      "ec2:DescribeSubnets",
      "ec2:DescribeTags",
      "ec2:DescribeVpcAttribute",
      "ec2:DescribeVpcEndpoints",
      "ec2:DescribeVpcs",
    ]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }
  }

  statement {
    sid    = "CreateTaggedApplicationNetwork"
    effect = "Allow"
    actions = [
      "ec2:CreateRouteTable",
      "ec2:CreateSecurityGroup",
      "ec2:CreateSubnet",
      "ec2:CreateVpc",
      "ec2:CreateVpcEndpoint",
    ]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/Environment"
      values   = [each.key]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/Project"
      values   = [local.project_name]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }
  }

  statement {
    sid     = "TagOnlyDuringApplicationNetworkCreation"
    effect  = "Allow"
    actions = ["ec2:CreateTags"]
    resources = [
      local.resource_arns[each.key].ec2_vpcs,
      local.resource_arns[each.key].ec2_subnets,
      local.resource_arns[each.key].ec2_route_tables,
      local.resource_arns[each.key].ec2_security_group,
      local.resource_arns[each.key].ec2_vpc_endpoint,
    ]

    condition {
      test     = "StringEquals"
      variable = "ec2:CreateAction"
      values = [
        "CreateRouteTable",
        "CreateSecurityGroup",
        "CreateSubnet",
        "CreateVpc",
        "CreateVpcEndpoint",
      ]
    }
  }

  statement {
    sid    = "ManageTaggedApplicationNetwork"
    effect = "Allow"
    actions = [
      "ec2:AssociateRouteTable",
      "ec2:AuthorizeSecurityGroupEgress",
      "ec2:CreateTags",
      "ec2:DeleteRouteTable",
      "ec2:DeleteSecurityGroup",
      "ec2:DeleteSubnet",
      "ec2:DeleteTags",
      "ec2:DeleteVpc",
      "ec2:DeleteVpcEndpoints",
      "ec2:DisassociateRouteTable",
      "ec2:ModifyVpcAttribute",
      "ec2:ModifyVpcEndpoint",
      "ec2:RevokeSecurityGroupEgress",
    ]
    resources = [
      local.resource_arns[each.key].ec2_vpcs,
      local.resource_arns[each.key].ec2_subnets,
      local.resource_arns[each.key].ec2_route_tables,
      local.resource_arns[each.key].ec2_security_group,
      local.resource_arns[each.key].ec2_vpc_endpoint,
    ]

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/Environment"
      values   = [each.key]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/Project"
      values   = [local.project_name]
    }
  }
}

data "aws_iam_policy_document" "deployment_observability" {
  for_each = local.environments

  statement {
    sid    = "ManageHealthCheckApiGateway"
    effect = "Allow"
    actions = [
      "apigateway:DELETE",
      "apigateway:GET",
      "apigateway:PATCH",
      "apigateway:POST",
      "apigateway:PUT",
    ]
    resources = local.resource_arns[each.key].api_gateway
  }

  statement {
    sid    = "ManageApplicationLogGroups"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:DeleteLogGroup",
      "logs:DeleteRetentionPolicy",
      "logs:ListTagsForResource",
      "logs:PutRetentionPolicy",
      "logs:TagResource",
      "logs:UntagResource",
    ]
    resources = local.resource_arns[each.key].log_groups
  }

  statement {
    sid       = "DiscoverRegionalLogGroups"
    effect    = "Allow"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }
  }

  statement {
    sid    = "ManageExactCloudWatchAlarms"
    effect = "Allow"
    actions = [
      "cloudwatch:DeleteAlarms",
      "cloudwatch:DescribeAlarms",
      "cloudwatch:ListTagsForResource",
      "cloudwatch:PutMetricAlarm",
      "cloudwatch:TagResource",
      "cloudwatch:UntagResource",
    ]
    resources = local.resource_arns[each.key].alarms
  }

  statement {
    sid    = "ManageExactCloudWatchDashboard"
    effect = "Allow"
    actions = [
      "cloudwatch:DeleteDashboards",
      "cloudwatch:GetDashboard",
      "cloudwatch:PutDashboard",
    ]
    resources = [local.resource_arns[each.key].dashboard]
  }
}

locals {
  deployment_managed_policy_documents = {
    state-runtime = data.aws_iam_policy_document.deployment_state_runtime
    application   = data.aws_iam_policy_document.deployment_application
    kms           = data.aws_iam_policy_document.deployment_kms
    network       = data.aws_iam_policy_document.deployment_network
    observability = data.aws_iam_policy_document.deployment_observability
  }

  deployment_managed_policy_pairs = {
    for pair in flatten([
      for policy_key, documents in local.deployment_managed_policy_documents : [
        for environment in local.environments : {
          key         = "${environment}-${policy_key}"
          environment = environment
          policy_key  = policy_key
          document    = documents[environment].json
        }
      ]
    ]) : pair.key => pair
  }
}

resource "aws_iam_policy" "deployment" {
  for_each = local.deployment_managed_policy_pairs

  name        = "${each.value.environment}-health-check-${each.value.policy_key}"
  description = "Scoped ${each.value.policy_key} deployment permissions for ${each.value.environment}"
  policy      = each.value.document

  tags = merge(local.common_tags, {
    Name        = "${each.value.environment}-health-check-${each.value.policy_key}"
    Environment = each.value.environment
    Component   = "deployment"
  })
}

resource "aws_iam_role_policy_attachment" "deployment" {
  for_each = local.deployment_managed_policy_pairs

  role       = aws_iam_role.deployment[each.value.environment].name
  policy_arn = aws_iam_policy.deployment[each.key].arn
}

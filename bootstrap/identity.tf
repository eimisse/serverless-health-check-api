resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_github_oidc_provider ? 1 : 0

  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]

  tags = merge(local.common_tags, {
    Name = "github-actions-oidc"
  })
}

data "aws_iam_policy_document" "deployment_trust" {
  for_each = local.environments

  statement {
    sid     = "GitHubEnvironmentOnly"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:environment:${each.key}"]
    }
  }
}

resource "aws_iam_role" "deployment" {
  for_each = local.environments

  name                 = "${each.key}-health-check-deployment-role"
  description          = "GitHub OIDC deployment role for the ${each.key} health-check stack"
  assume_role_policy   = data.aws_iam_policy_document.deployment_trust[each.key].json
  max_session_duration = var.deployment_role_max_session_duration
  permissions_boundary = var.permissions_boundary_arn

  tags = merge(local.common_tags, {
    Name        = "${each.key}-health-check-deployment-role"
    Environment = each.key
    Component   = "deployment"
  })

  lifecycle {
    precondition {
      condition = (
        var.create_github_oidc_provider ||
        var.existing_github_oidc_provider_arn != null
      )
      error_message = "existing_github_oidc_provider_arn is required when create_github_oidc_provider is false."
    }
  }

  depends_on = [aws_iam_openid_connect_provider.github]
}

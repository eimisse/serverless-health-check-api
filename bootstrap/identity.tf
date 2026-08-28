locals {
  github_repository_owner = split("/", var.github_repository)[0]
  github_repository_name  = split("/", var.github_repository)[1]

  # Repositories created after 2026-07-15 use GitHub's immutable default OIDC
  # subject format. Names remain readable while owner/repository IDs prevent a
  # future rename, transfer, or namespace reuse from inheriting this AWS trust.
  github_immutable_repository = "${local.github_repository_owner}@${var.github_repository_owner_id}/${local.github_repository_name}@${var.github_repository_id}"
}

resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_github_oidc_provider ? 1 : 0

  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]

  tags = merge(local.common_tags, {
    Name = "github-actions-oidc"
  })
}

data "aws_iam_policy_document" "deployment_trust" {
  #checkov:skip=CKV_AWS_358:Checkov 3.3.15 does not yet recognize GitHub's immutable owner@ID/repository@ID subject syntax (upstream bridgecrewio/checkov#7610); this trust pins the exact immutable repository, environment, audience, repository/owner IDs and main ref.
  for_each = local.environments

  statement {
    sid     = "GitHubEnvironmentMainOnly"
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
      values   = ["repo:${local.github_immutable_repository}:environment:${each.key}"]
    }

    # These immutable/explicit claims provide defense in depth around the subject.
    # AWS exposes GitHub's repository, owner, environment and ref JWT claims as
    # OIDC condition context keys.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:repository_id"
      values   = [var.github_repository_id]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:repository_owner_id"
      values   = [var.github_repository_owner_id]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:environment"
      values   = [each.key]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:ref"
      values   = [var.github_deployment_ref]
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

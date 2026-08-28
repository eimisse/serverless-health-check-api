# Terraform refreshes an IAM role by listing both inline and attached policies.
# The application runtime role intentionally uses inline policies today, but the
# AWS provider still calls ListAttachedRolePolicies during refresh. Scope that
# read permission to the exact environment runtime role.

data "aws_iam_policy_document" "deployment_runtime_role_refresh" {
  for_each = local.environments

  statement {
    sid       = "RefreshExactRuntimeRoleAttachments"
    effect    = "Allow"
    actions   = ["iam:ListAttachedRolePolicies"]
    resources = [local.resource_arns[each.key].runtime_role]
  }
}

resource "aws_iam_role_policy" "deployment_runtime_role_refresh" {
  for_each = local.environments

  name   = "${each.key}-health-check-runtime-role-refresh"
  role   = aws_iam_role.deployment[each.key].id
  policy = data.aws_iam_policy_document.deployment_runtime_role_refresh[each.key].json
}

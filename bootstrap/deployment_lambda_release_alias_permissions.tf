data "aws_iam_policy_document" "deployment_lambda_release_alias" {
  for_each = local.environments

  statement {
    sid    = "ManageExactLambdaReleaseAlias"
    effect = "Allow"
    actions = [
      "lambda:AddPermission",
      "lambda:CreateAlias",
      "lambda:DeleteAlias",
      "lambda:GetAlias",
      "lambda:GetFunctionConfiguration",
      "lambda:GetPolicy",
      "lambda:RemovePermission",
      "lambda:UpdateAlias",
    ]
    resources = [
      local.resource_arns[each.key].function,
      local.resource_arns[each.key].function_alias,
    ]
  }
}

resource "aws_iam_policy" "deployment_lambda_release_alias" {
  for_each = local.environments

  name        = "${each.key}-health-check-release-alias"
  description = "Scoped Lambda release alias deployment permissions for ${each.key}"
  policy      = data.aws_iam_policy_document.deployment_lambda_release_alias[each.key].json

  tags = merge(local.common_tags, {
    Name        = "${each.key}-health-check-release-alias"
    Environment = each.key
    Component   = "deployment"
  })
}

resource "aws_iam_role_policy_attachment" "deployment_lambda_release_alias" {
  for_each = local.environments

  role       = aws_iam_role.deployment[each.key].name
  policy_arn = aws_iam_policy.deployment_lambda_release_alias[each.key].arn
}

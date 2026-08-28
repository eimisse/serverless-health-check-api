# Terraform's AWS provider polls a newly published Lambda version by its
# qualified ARN (function:<name>:<version>). Keep this read permission separate
# from the unqualified function management policy so mutating actions do not
# gain access to aliases or published versions.
data "aws_iam_policy_document" "deployment_lambda_published_version_read" {
  for_each = local.environments

  statement {
    sid     = "ReadPublishedLambdaVersionConfiguration"
    effect  = "Allow"
    actions = ["lambda:GetFunctionConfiguration"]
    resources = [
      "${local.resource_arns[each.key].function}:*",
    ]
  }
}

resource "aws_iam_role_policy" "deployment_lambda_published_version_read" {
  for_each = local.environments

  name   = "${each.key}-health-check-lambda-published-version-read"
  role   = aws_iam_role.deployment[each.key].name
  policy = data.aws_iam_policy_document.deployment_lambda_published_version_read[each.key].json
}

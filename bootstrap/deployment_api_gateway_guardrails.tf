# API Gateway uses AWS-generated identifiers for REST APIs, API keys, stages,
# deployments, models, validators and usage plans. The allow policy therefore
# names only the regional resource families Terraform needs. These explicit
# denies turn those generated-ID families into an environment/project boundary
# that the deployment role cannot remove from itself.

data "aws_iam_policy_document" "deployment_api_gateway_guardrails" {
  for_each = local.environments

  # Existing REST API resources and descendants inherit the RestApi tags for IAM
  # authorization. Reject any operation outside this environment/project.
  statement {
    sid    = "DenyOtherEnvironmentRestApiTree"
    effect = "Deny"
    actions = [
      "apigateway:DELETE",
      "apigateway:GET",
      "apigateway:PATCH",
      "apigateway:POST",
      "apigateway:PUT",
    ]
    resources = [local.resource_arns[each.key].api_gateway_restapi_tree]

    condition {
      test     = "StringNotEquals"
      variable = "aws:ResourceTag/Environment"
      values   = [each.key]
    }
  }

  statement {
    sid    = "DenyOtherProjectRestApiTree"
    effect = "Deny"
    actions = [
      "apigateway:DELETE",
      "apigateway:GET",
      "apigateway:PATCH",
      "apigateway:POST",
      "apigateway:PUT",
    ]
    resources = [local.resource_arns[each.key].api_gateway_restapi_tree]

    condition {
      test     = "StringNotEquals"
      variable = "aws:ResourceTag/Project"
      values   = [local.project_name]
    }
  }

  # API keys and usage plans are independently taggable and receive the common
  # Terraform tags in their create calls.
  statement {
    sid    = "DenyOtherEnvironmentApiKeys"
    effect = "Deny"
    actions = [
      "apigateway:DELETE",
      "apigateway:GET",
      "apigateway:PATCH",
    ]
    resources = [local.resource_arns[each.key].api_gateway_apikey_tree]

    condition {
      test     = "StringNotEquals"
      variable = "aws:ResourceTag/Environment"
      values   = [each.key]
    }
  }

  statement {
    sid    = "DenyOtherProjectApiKeys"
    effect = "Deny"
    actions = [
      "apigateway:DELETE",
      "apigateway:GET",
      "apigateway:PATCH",
    ]
    resources = [local.resource_arns[each.key].api_gateway_apikey_tree]

    condition {
      test     = "StringNotEquals"
      variable = "aws:ResourceTag/Project"
      values   = [local.project_name]
    }
  }

  statement {
    sid    = "DenyOtherEnvironmentUsagePlans"
    effect = "Deny"
    actions = [
      "apigateway:DELETE",
      "apigateway:GET",
      "apigateway:PATCH",
      "apigateway:POST",
    ]
    resources = [local.resource_arns[each.key].api_gateway_usageplan_tree]

    condition {
      test     = "StringNotEquals"
      variable = "aws:ResourceTag/Environment"
      values   = [each.key]
    }
  }

  statement {
    sid    = "DenyOtherProjectUsagePlans"
    effect = "Deny"
    actions = [
      "apigateway:DELETE",
      "apigateway:GET",
      "apigateway:PATCH",
      "apigateway:POST",
    ]
    resources = [local.resource_arns[each.key].api_gateway_usageplan_tree]

    condition {
      test     = "StringNotEquals"
      variable = "aws:ResourceTag/Project"
      values   = [local.project_name]
    }
  }

  # Collections do not have an existing resource tag. Require the tags present
  # in Terraform's create request; RestApi creation also has an API-name condition.
  statement {
    sid       = "DenyRestApiCreateWithoutEnvironmentTag"
    effect    = "Deny"
    actions   = ["apigateway:POST"]
    resources = [local.resource_arns[each.key].api_gateway_restapis]

    condition {
      test     = "StringNotEquals"
      variable = "aws:RequestTag/Environment"
      values   = [each.key]
    }
  }

  statement {
    sid       = "DenyRestApiCreateWithoutProjectTag"
    effect    = "Deny"
    actions   = ["apigateway:POST"]
    resources = [local.resource_arns[each.key].api_gateway_restapis]

    condition {
      test     = "StringNotEquals"
      variable = "aws:RequestTag/Project"
      values   = [local.project_name]
    }
  }

  statement {
    sid       = "DenyUnexpectedRestApiName"
    effect    = "Deny"
    actions   = ["apigateway:POST"]
    resources = [local.resource_arns[each.key].api_gateway_restapis]

    condition {
      test     = "StringNotEquals"
      variable = "apigateway:Request/ApiName"
      values   = [local.resource_arns[each.key].api_name]
    }
  }

  statement {
    sid       = "DenyApiKeyCreateWithoutEnvironmentTag"
    effect    = "Deny"
    actions   = ["apigateway:POST"]
    resources = [local.resource_arns[each.key].api_gateway_apikeys]

    condition {
      test     = "StringNotEquals"
      variable = "aws:RequestTag/Environment"
      values   = [each.key]
    }
  }

  statement {
    sid       = "DenyApiKeyCreateWithoutProjectTag"
    effect    = "Deny"
    actions   = ["apigateway:POST"]
    resources = [local.resource_arns[each.key].api_gateway_apikeys]

    condition {
      test     = "StringNotEquals"
      variable = "aws:RequestTag/Project"
      values   = [local.project_name]
    }
  }

  statement {
    sid       = "DenyUsagePlanCreateWithoutEnvironmentTag"
    effect    = "Deny"
    actions   = ["apigateway:POST"]
    resources = [local.resource_arns[each.key].api_gateway_usageplans]

    condition {
      test     = "StringNotEquals"
      variable = "aws:RequestTag/Environment"
      values   = [each.key]
    }
  }

  statement {
    sid       = "DenyUsagePlanCreateWithoutProjectTag"
    effect    = "Deny"
    actions   = ["apigateway:POST"]
    resources = [local.resource_arns[each.key].api_gateway_usageplans]

    condition {
      test     = "StringNotEquals"
      variable = "aws:RequestTag/Project"
      values   = [local.project_name]
    }
  }

  # RestApi, Stage, API key and UsagePlan create APIs all accept tags inline.
  # Generic TagResource could otherwise be used to tag an unrelated API resource
  # into the allowed ResourceTag boundary. Forbid post-create API Gateway tag
  # mutation entirely; Terraform may still read tags.
  statement {
    sid    = "DenyApiGatewayTagMutation"
    effect = "Deny"
    actions = [
      "apigateway:DELETE",
      "apigateway:PATCH",
      "apigateway:POST",
      "apigateway:PUT",
    ]
    resources = [local.resource_arns[each.key].api_gateway_tags]
  }
}

resource "aws_iam_role_policy" "deployment_api_gateway_guardrails" {
  for_each = local.environments

  name   = "${each.key}-health-check-api-gateway-guardrails"
  role   = aws_iam_role.deployment[each.key].id
  policy = data.aws_iam_policy_document.deployment_api_gateway_guardrails[each.key].json
}

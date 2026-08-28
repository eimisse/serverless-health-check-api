# API Gateway uses AWS-generated identifiers for REST APIs, API keys, stages,
# deployments, models, validators and usage plans. The allow policy therefore
# names only the regional resource families Terraform needs. Explicit denies
# keep existing resources inside their environment/project boundary while still
# allowing AWS API Gateway's tag-on-create authorization flow.

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

  # API Gateway authorizes inline create tags through PUT on /tags/<encoded ARN>.
  # The API Gateway Service Authorization Reference exposes aws:RequestTag and
  # aws:TagKeys for this Tags pseudo-resource, but not aws:ResourceTag. Do not
  # pretend the target resource can be scoped here with an unsupported condition.
  # Instead, constrain the tag request itself; the actual RestApi/ApiKey/UsagePlan
  # resource trees above enforce Environment/Project ResourceTag boundaries on
  # subsequent management operations.
  statement {
    sid    = "DenyUnexpectedApiGatewayTagKeys"
    effect = "Deny"
    actions = [
      "apigateway:DELETE",
      "apigateway:PUT",
    ]
    resources = [local.resource_arns[each.key].api_gateway_tags]

    condition {
      test     = "ForAnyValue:StringNotEquals"
      variable = "aws:TagKeys"
      values = [
        "Environment",
        "ManagedBy",
        "Name",
        "Project",
        "Repository",
        "Workload",
      ]
    }
  }

  # If a request explicitly changes a security-relevant tag, only the reviewed
  # value is accepted. Null=false deliberately ignores unrelated tag updates and
  # preserves Terraform provider compatibility after create.
  statement {
    sid       = "DenyWrongEnvironmentBoundaryTag"
    effect    = "Deny"
    actions   = ["apigateway:PUT"]
    resources = [local.resource_arns[each.key].api_gateway_tags]

    condition {
      test     = "Null"
      variable = "aws:RequestTag/Environment"
      values   = ["false"]
    }

    condition {
      test     = "StringNotEquals"
      variable = "aws:RequestTag/Environment"
      values   = [each.key]
    }
  }

  statement {
    sid       = "DenyWrongProjectBoundaryTag"
    effect    = "Deny"
    actions   = ["apigateway:PUT"]
    resources = [local.resource_arns[each.key].api_gateway_tags]

    condition {
      test     = "Null"
      variable = "aws:RequestTag/Project"
      values   = ["false"]
    }

    condition {
      test     = "StringNotEquals"
      variable = "aws:RequestTag/Project"
      values   = [local.project_name]
    }
  }

  statement {
    sid       = "DenyWrongManagedByTag"
    effect    = "Deny"
    actions   = ["apigateway:PUT"]
    resources = [local.resource_arns[each.key].api_gateway_tags]

    condition {
      test     = "Null"
      variable = "aws:RequestTag/ManagedBy"
      values   = ["false"]
    }

    condition {
      test     = "StringNotEquals"
      variable = "aws:RequestTag/ManagedBy"
      values   = ["Terraform"]
    }
  }

  statement {
    sid       = "DenyWrongRepositoryTag"
    effect    = "Deny"
    actions   = ["apigateway:PUT"]
    resources = [local.resource_arns[each.key].api_gateway_tags]

    condition {
      test     = "Null"
      variable = "aws:RequestTag/Repository"
      values   = ["false"]
    }

    condition {
      test     = "StringNotEquals"
      variable = "aws:RequestTag/Repository"
      values   = [var.github_repository]
    }
  }

  # Once the Environment/Project ownership boundary exists, the deployment role
  # must not remove those tag keys through UntagResource.
  statement {
    sid       = "DenyRemovingApiGatewayBoundaryTags"
    effect    = "Deny"
    actions   = ["apigateway:DELETE"]
    resources = [local.resource_arns[each.key].api_gateway_tags]

    condition {
      test     = "ForAnyValue:StringEquals"
      variable = "aws:TagKeys"
      values = [
        "Environment",
        "Project",
      ]
    }
  }
}

resource "aws_iam_role_policy" "deployment_api_gateway_guardrails" {
  for_each = local.environments

  name   = "${each.key}-health-check-api-gateway-guardrails"
  role   = aws_iam_role.deployment[each.key].id
  policy = data.aws_iam_policy_document.deployment_api_gateway_guardrails[each.key].json
}

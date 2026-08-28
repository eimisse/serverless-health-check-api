# Several EC2 create APIs authorize both the newly generated resource and the
# already-existing parent resource. `CreateTaggedApplicationNetwork` in the main
# deployment policy covers the new resource using RequestTag conditions. These
# statements cover only the exact tagged parent resources required by AWS.

data "aws_iam_policy_document" "deployment_network_parents" {
  for_each = local.environments

  statement {
    sid    = "CreateChildrenOnlyInOwnVpc"
    effect = "Allow"
    actions = [
      "ec2:CreateRouteTable",
      "ec2:CreateSecurityGroup",
      "ec2:CreateSubnet",
      "ec2:CreateVpcEndpoint",
    ]
    resources = [local.resource_arns[each.key].ec2_vpcs]

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

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }
  }

  # The DynamoDB Gateway endpoint is attached to the stack's private route
  # table during creation. No subnet or security-group resource is supplied for
  # this endpoint type.
  statement {
    sid       = "CreateEndpointOnlyOnOwnRouteTable"
    effect    = "Allow"
    actions   = ["ec2:CreateVpcEndpoint"]
    resources = [local.resource_arns[each.key].ec2_route_tables]

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

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }
  }
}

resource "aws_iam_role_policy" "deployment_network_parents" {
  for_each = local.environments

  name   = "${each.key}-health-check-network-parents"
  role   = aws_iam_role.deployment[each.key].id
  policy = data.aws_iam_policy_document.deployment_network_parents[each.key].json
}

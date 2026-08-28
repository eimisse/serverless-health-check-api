# Terraform can replace a route-table association if its target route table
# changes. AWS authorizes ReplaceRouteTableAssociation against the route table
# (required) and subnet involved in the association. Both resources are created
# by this stack and carry the exact project/environment tags below.

data "aws_iam_policy_document" "deployment_route_table_association" {
  for_each = local.environments

  statement {
    sid     = "ReplaceOwnRouteTableAssociation"
    effect  = "Allow"
    actions = ["ec2:ReplaceRouteTableAssociation"]
    resources = [
      local.resource_arns[each.key].ec2_route_tables,
      local.resource_arns[each.key].ec2_subnets,
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

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }
  }
}

resource "aws_iam_role_policy" "deployment_route_table_association" {
  for_each = local.environments

  name   = "${each.key}-health-check-route-table-association"
  role   = aws_iam_role.deployment[each.key].id
  policy = data.aws_iam_policy_document.deployment_route_table_association[each.key].json
}

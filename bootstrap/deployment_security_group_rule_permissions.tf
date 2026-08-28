# aws_vpc_security_group_egress_rule uses AuthorizeSecurityGroupEgress with
# TagSpecifications for the newly generated security-group-rule ID. The parent
# security group is authorized by the main deployment policy; these statements
# cover only the generated rule resource and its tags.

data "aws_iam_policy_document" "deployment_security_group_rule" {
  for_each = local.environments

  statement {
    sid       = "CreateTaggedSecurityGroupRule"
    effect    = "Allow"
    actions   = ["ec2:AuthorizeSecurityGroupEgress"]
    resources = [local.resource_arns[each.key].ec2_security_group_rule]

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

  # EC2 performs a separate CreateTags authorization when the rule is created
  # with TagSpecifications. ec2:CreateAction prevents use on arbitrary existing
  # security-group rules.
  statement {
    sid       = "TagSecurityGroupRuleOnlyDuringCreate"
    effect    = "Allow"
    actions   = ["ec2:CreateTags"]
    resources = [local.resource_arns[each.key].ec2_security_group_rule]

    condition {
      test     = "StringEquals"
      variable = "ec2:CreateAction"
      values   = ["AuthorizeSecurityGroupEgress"]
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
  }

  statement {
    sid    = "MaintainTaggedSecurityGroupRuleTags"
    effect = "Allow"
    actions = [
      "ec2:CreateTags",
      "ec2:DeleteTags",
    ]
    resources = [local.resource_arns[each.key].ec2_security_group_rule]

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

resource "aws_iam_role_policy" "deployment_security_group_rule" {
  for_each = local.environments

  name   = "${each.key}-health-check-security-group-rule"
  role   = aws_iam_role.deployment[each.key].id
  policy = data.aws_iam_policy_document.deployment_security_group_rule[each.key].json
}

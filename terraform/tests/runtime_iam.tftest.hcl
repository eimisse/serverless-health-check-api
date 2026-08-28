mock_provider "aws" {
  override_during = plan
}

run "runtime_role_is_least_privilege" {
  command = plan

  module {
    source = "./modules/runtime_iam"
  }

  variables {
    environment    = "staging"
    table_arn      = "arn:aws:dynamodb:eu-west-1:123456789012:table/staging-requests-db"
    aws_account_id = "123456789012"
    aws_partition  = "aws"
    aws_region     = "eu-west-1"
    tags = {
      Environment = "staging"
      ManagedBy   = "Terraform"
      Project     = "serverless-health-check-api"
      Repository  = "eimisse/serverless-health-check-api"
    }
  }

  assert {
    condition = (
      aws_iam_role.runtime.name == "staging-health-check-function-role" &&
      jsondecode(aws_iam_role.runtime.assume_role_policy).Statement[0].Principal.Service == "lambda.amazonaws.com"
    )
    error_message = "The runtime role must use the exact environment name and trust only Lambda."
  }

  assert {
    condition = (
      strcontains(aws_iam_role_policy.runtime.policy, "dynamodb:PutItem") &&
      !strcontains(aws_iam_role_policy.runtime.policy, "dynamodb:GetItem") &&
      !strcontains(aws_iam_role_policy.runtime.policy, "dynamodb:Scan") &&
      !strcontains(aws_iam_role_policy.runtime.policy, "dynamodb:DeleteItem") &&
      !strcontains(aws_iam_role_policy.runtime.policy, "dynamodb:DeleteTable") &&
      !strcontains(aws_iam_role_policy.runtime.policy, "kms:") &&
      !strcontains(aws_iam_role_policy.runtime.policy, "iam:") &&
      !strcontains(aws_iam_role_policy.runtime.policy, "s3:")
    )
    error_message = "The runtime identity policy must contain only persistence, logging, and mandatory VPC lifecycle permissions."
  }

  assert {
    condition = one([
      for statement in jsondecode(aws_iam_role_policy.runtime.policy).Statement : statement.Resource
      if statement.Sid == "PersistRequestOnly"
    ]) == "arn:aws:dynamodb:eu-west-1:123456789012:table/staging-requests-db"
    error_message = "DynamoDB PutItem must be scoped to the exact staging table ARN."
  }

  assert {
    condition = one([
      for statement in jsondecode(aws_iam_role_policy.runtime.policy).Statement : statement.Resource
      if statement.Sid == "WriteOnlyApplicationLogs"
    ]) == "arn:aws:logs:eu-west-1:123456789012:log-group:staging-health-check-function-logs:*"
    error_message = "Runtime logging must be scoped to the exact environment-prefixed log group streams."
  }

  assert {
    condition = (
      one([
        for statement in jsondecode(aws_iam_role_policy.runtime.policy).Statement : statement.Effect
        if statement.Sid == "DenyFunctionCodeVpcEniCalls"
      ]) == "Deny" &&
      one([
        for statement in jsondecode(aws_iam_role_policy.runtime.policy).Statement : statement.Condition.ArnEquals["lambda:SourceFunctionArn"]
        if statement.Sid == "DenyFunctionCodeVpcEniCalls"
      ]) == "arn:aws:lambda:eu-west-1:123456789012:function:staging-health-check-function"
    )
    error_message = "Function code must be explicitly denied from reusing its control-plane ENI permissions."
  }
}

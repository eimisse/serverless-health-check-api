mock_provider "aws" {
  override_during = plan
}

run "deployment_key_admin_excludes_grant_administration" {
  command = plan

  module {
    source = "./modules/kms"
  }

  variables {
    environment          = "staging"
    aws_account_id       = "123456789012"
    aws_partition        = "aws"
    aws_region           = "eu-west-1"
    table_name           = "staging-requests-db"
    runtime_role_arn     = "arn:aws:iam::123456789012:role/staging-health-check-function-role"
    deployment_role_arn  = "arn:aws:iam::123456789012:role/staging-health-check-deployment-role"
    deletion_window_days = 7
    rotation_period_days = 365
    tags = {
      Environment = "staging"
      ManagedBy   = "Terraform"
      Project     = "serverless-health-check-api"
      Repository  = "eimisse/serverless-health-check-api"
    }
  }

  assert {
    condition = (
      contains(
        one([
          for statement in jsondecode(aws_kms_key.dynamodb.policy).Statement : statement.Action
          if statement.Sid == "DeploymentRoleKeyAdministration"
        ]),
        "kms:DescribeKey",
      ) &&
      !contains(
        one([
          for statement in jsondecode(aws_kms_key.dynamodb.policy).Statement : statement.Action
          if statement.Sid == "DeploymentRoleKeyAdministration"
        ]),
        "kms:ListGrants",
      ) &&
      !contains(
        one([
          for statement in jsondecode(aws_kms_key.dynamodb.policy).Statement : statement.Action
          if statement.Sid == "DeploymentRoleKeyAdministration"
        ]),
        "kms:RevokeGrant",
      )
    )
    error_message = "Terraform key administration needs DescribeKey but must not include broad KMS grant administration."
  }

  assert {
    condition = length([
      for statement in jsondecode(aws_kms_key.dynamodb.policy).Statement : statement
      if statement.Sid == "DeploymentRoleDynamoDBDescribeKey"
    ]) == 0
    error_message = "Deployment DescribeKey must not be duplicated in a second DynamoDB statement."
  }

  assert {
    condition = (
      one([
        for statement in jsondecode(aws_kms_key.dynamodb.policy).Statement : statement.Action
        if statement.Sid == "DeploymentRoleDynamoDBGrant"
      ]) == "kms:CreateGrant" &&
      one([
        for statement in jsondecode(aws_kms_key.dynamodb.policy).Statement : statement.Condition.Bool["kms:GrantIsForAWSResource"]
        if statement.Sid == "DeploymentRoleDynamoDBGrant"
      ]) == "true" &&
      one([
        for statement in jsondecode(aws_kms_key.dynamodb.policy).Statement : statement.Condition.StringEquals["kms:ViaService"]
        if statement.Sid == "DeploymentRoleDynamoDBGrant"
      ]) == "dynamodb.eu-west-1.amazonaws.com"
    )
    error_message = "DynamoDB CreateGrant must remain isolated to the deployment role and AWS-resource service path."
  }

  assert {
    condition = (
      length([
        for statement in jsondecode(aws_kms_key.dynamodb.policy).Statement : statement
        if statement.Sid == "RuntimeRoleDynamoDBGrant"
      ]) == 0 &&
      !contains(
        one([
          for statement in jsondecode(aws_kms_key.dynamodb.policy).Statement : statement.Action
          if statement.Sid == "RuntimeRoleDynamoDBCryptoUse"
        ]),
        "kms:CreateGrant",
      )
    )
    error_message = "The Lambda runtime role must never receive kms:CreateGrant; table/grant lifecycle belongs to the deployment role."
  }

  assert {
    condition = (
      one([
        for statement in jsondecode(aws_kms_key.dynamodb.policy).Statement : statement.Condition.StringEquals["kms:EncryptionContext:aws:dynamodb:tableName"]
        if statement.Sid == "DeploymentRoleDynamoDBKeyUse"
      ]) == "staging-requests-db" &&
      one([
        for statement in jsondecode(aws_kms_key.dynamodb.policy).Statement : statement.Condition.StringEquals["kms:EncryptionContext:aws:dynamodb:subscriberId"]
        if statement.Sid == "DeploymentRoleDynamoDBKeyUse"
      ]) == "123456789012"
    )
    error_message = "Deployment-role cryptographic use must remain bound to the exact DynamoDB table context."
  }
}

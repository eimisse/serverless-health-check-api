mock_provider "aws" {
  override_during = plan
}

run "kms_rotation_and_runtime_scope" {
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
      aws_kms_key.dynamodb.enable_key_rotation &&
      aws_kms_key.dynamodb.rotation_period_in_days == 365 &&
      aws_kms_key.dynamodb.customer_master_key_spec == "SYMMETRIC_DEFAULT" &&
      !aws_kms_key.dynamodb.multi_region
    )
    error_message = "The DynamoDB CMK must be single-Region, symmetric, and automatically rotated."
  }

  assert {
    condition     = aws_kms_alias.dynamodb.name == "alias/staging-requests-db-key"
    error_message = "The KMS alias body must retain the staging- prefix."
  }

  assert {
    condition     = !strcontains(aws_kms_key.dynamodb.policy, "kms:*")
    error_message = "The KMS key policy must never use a wildcard action."
  }

  assert {
    condition = one([
      for statement in jsondecode(aws_kms_key.dynamodb.policy).Statement : statement.Principal.AWS
      if statement.Sid == "AccountRootBreakGlassAdministration"
    ]) == "arn:aws:iam::123456789012:root"
    error_message = "Break-glass key administration must belong to the AWS account root principal."
  }

  assert {
    condition = one([
      for statement in jsondecode(aws_kms_key.dynamodb.policy).Statement : statement.Principal.AWS
      if statement.Sid == "RuntimeRoleDynamoDBCryptoUse"
    ]) == "arn:aws:iam::123456789012:role/staging-health-check-function-role"
    error_message = "Runtime KMS use must be granted only to the exact Lambda role."
  }

  assert {
    condition = alltrue([
      for required_action in [
        "kms:Decrypt",
        "kms:Encrypt",
        "kms:GenerateDataKey",
        "kms:GenerateDataKeyWithoutPlaintext",
        "kms:ReEncryptFrom",
        "kms:ReEncryptTo",
        ] : contains(
        one([
          for statement in jsondecode(aws_kms_key.dynamodb.policy).Statement : statement.Action
          if statement.Sid == "RuntimeRoleDynamoDBCryptoUse"
        ]),
        required_action,
      )
    ])
    error_message = "Runtime DynamoDB KMS use must contain the intended cryptographic actions."
  }

  assert {
    condition = !contains(
      one([
        for statement in jsondecode(aws_kms_key.dynamodb.policy).Statement : statement.Action
        if statement.Sid == "RuntimeRoleDynamoDBCryptoUse"
      ]),
      "kms:DescribeKey",
    )
    error_message = "DescribeKey must stay outside the encryption-context constrained cryptographic statement."
  }

  assert {
    condition = (
      one([
        for statement in jsondecode(aws_kms_key.dynamodb.policy).Statement : statement.Action
        if statement.Sid == "RuntimeRoleDynamoDBDescribeKey"
      ]) == "kms:DescribeKey" &&
      one([
        for statement in jsondecode(aws_kms_key.dynamodb.policy).Statement : statement.Condition.StringEquals["kms:ViaService"]
        if statement.Sid == "RuntimeRoleDynamoDBDescribeKey"
      ]) == "dynamodb.eu-west-1.amazonaws.com"
    )
    error_message = "Runtime DescribeKey must be isolated and constrained to DynamoDB ViaService."
  }

  assert {
    condition = (
      one([
        for statement in jsondecode(aws_kms_key.dynamodb.policy).Statement : statement.Condition.StringEquals["kms:ViaService"]
        if statement.Sid == "RuntimeRoleDynamoDBCryptoUse"
      ]) == "dynamodb.eu-west-1.amazonaws.com" &&
      one([
        for statement in jsondecode(aws_kms_key.dynamodb.policy).Statement : statement.Condition.StringEquals["kms:EncryptionContext:aws:dynamodb:tableName"]
        if statement.Sid == "RuntimeRoleDynamoDBCryptoUse"
      ]) == "staging-requests-db" &&
      one([
        for statement in jsondecode(aws_kms_key.dynamodb.policy).Statement : statement.Condition.StringEquals["kms:EncryptionContext:aws:dynamodb:subscriberId"]
        if statement.Sid == "RuntimeRoleDynamoDBCryptoUse"
      ]) == "123456789012"
    )
    error_message = "Runtime cryptographic use must be constrained to DynamoDB and the exact table/account encryption context."
  }
}

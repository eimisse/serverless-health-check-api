locals {
  key_name         = "${var.environment}-requests-db-key"
  account_root_arn = "arn:${var.aws_partition}:iam::${var.aws_account_id}:root"

  # Break-glass administration remains explicit rather than using kms:*.
  root_key_administration_actions = [
    "kms:CancelKeyDeletion",
    "kms:CreateAlias",
    "kms:DeleteAlias",
    "kms:DescribeKey",
    "kms:DisableKey",
    "kms:DisableKeyRotation",
    "kms:EnableKey",
    "kms:EnableKeyRotation",
    "kms:GetKeyPolicy",
    "kms:GetKeyRotationStatus",
    "kms:ListGrants",
    "kms:ListResourceTags",
    "kms:PutKeyPolicy",
    "kms:RevokeGrant",
    "kms:ScheduleKeyDeletion",
    "kms:TagResource",
    "kms:UntagResource",
    "kms:UpdateAlias",
    "kms:UpdateKeyDescription",
  ]

  # The deployment role receives only operations exercised by the Terraform KMS
  # key/alias lifecycle. Grant administration is deliberately not included here;
  # DynamoDB CreateGrant has its own service-constrained statement below.
  deployment_key_administration_actions = [
    "kms:CreateAlias",
    "kms:DeleteAlias",
    "kms:DescribeKey",
    "kms:DisableKey",
    "kms:DisableKeyRotation",
    "kms:EnableKey",
    "kms:EnableKeyRotation",
    "kms:GetKeyPolicy",
    "kms:GetKeyRotationStatus",
    "kms:ListResourceTags",
    "kms:PutKeyPolicy",
    "kms:ScheduleKeyDeletion",
    "kms:TagResource",
    "kms:UntagResource",
    "kms:UpdateAlias",
    "kms:UpdateKeyDescription",
  ]

  # Keep DescribeKey separate for the runtime role: KMS encryption-context
  # condition keys apply to cryptographic operations (and CreateGrant), not DescribeKey.
  dynamodb_crypto_actions = [
    "kms:Decrypt",
    "kms:Encrypt",
    "kms:GenerateDataKey",
    "kms:GenerateDataKeyWithoutPlaintext",
    "kms:ReEncryptFrom",
    "kms:ReEncryptTo",
  ]
}

resource "aws_kms_key" "dynamodb" {
  description              = "Customer-managed encryption key for ${var.table_name}"
  key_usage                = "ENCRYPT_DECRYPT"
  customer_master_key_spec = "SYMMETRIC_DEFAULT"
  enable_key_rotation      = true
  rotation_period_in_days  = var.rotation_period_days
  deletion_window_in_days  = var.deletion_window_days
  multi_region             = false

  # KMS key policies require Resource "*" to denote the key to which the policy
  # is attached. Every principal, action, service path, account, and encryption
  # context is still explicit; see security/iam-wildcard-exceptions*.json.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AccountRootBreakGlassAdministration"
        Effect    = "Allow"
        Principal = { AWS = local.account_root_arn }
        Action    = local.root_key_administration_actions
        Resource  = "*"
      },
      {
        Sid       = "DeploymentRoleKeyAdministration"
        Effect    = "Allow"
        Principal = { AWS = var.deployment_role_arn }
        Action    = local.deployment_key_administration_actions
        Resource  = "*"
      },
      {
        Sid       = "DeploymentRoleDynamoDBKeyUse"
        Effect    = "Allow"
        Principal = { AWS = var.deployment_role_arn }
        Action    = local.dynamodb_crypto_actions
        Resource  = "*"
        Condition = {
          StringEquals = {
            "kms:CallerAccount"                               = var.aws_account_id
            "kms:ViaService"                                  = "dynamodb.${var.aws_region}.amazonaws.com"
            "kms:EncryptionContext:aws:dynamodb:subscriberId" = var.aws_account_id
            "kms:EncryptionContext:aws:dynamodb:tableName"    = var.table_name
          }
        }
      },
      {
        Sid       = "DeploymentRoleDynamoDBGrant"
        Effect    = "Allow"
        Principal = { AWS = var.deployment_role_arn }
        Action    = "kms:CreateGrant"
        Resource  = "*"
        Condition = {
          Bool = {
            "kms:GrantIsForAWSResource" = "true"
          }
          StringEquals = {
            "kms:CallerAccount" = var.aws_account_id
            "kms:ViaService"    = "dynamodb.${var.aws_region}.amazonaws.com"
          }
        }
      },
      {
        Sid       = "RuntimeRoleDynamoDBDescribeKey"
        Effect    = "Allow"
        Principal = { AWS = var.runtime_role_arn }
        Action    = "kms:DescribeKey"
        Resource  = "*"
        Condition = {
          StringEquals = {
            "kms:CallerAccount" = var.aws_account_id
            "kms:ViaService"    = "dynamodb.${var.aws_region}.amazonaws.com"
          }
        }
      },
      {
        Sid       = "RuntimeRoleDynamoDBCryptoUse"
        Effect    = "Allow"
        Principal = { AWS = var.runtime_role_arn }
        Action    = local.dynamodb_crypto_actions
        Resource  = "*"
        Condition = {
          StringEquals = {
            "kms:CallerAccount"                               = var.aws_account_id
            "kms:ViaService"                                  = "dynamodb.${var.aws_region}.amazonaws.com"
            "kms:EncryptionContext:aws:dynamodb:subscriberId" = var.aws_account_id
            "kms:EncryptionContext:aws:dynamodb:tableName"    = var.table_name
          }
        }
      },
      {
        Sid       = "RuntimeRoleDynamoDBGrant"
        Effect    = "Allow"
        Principal = { AWS = var.runtime_role_arn }
        Action    = "kms:CreateGrant"
        Resource  = "*"
        Condition = {
          Bool = {
            "kms:GrantIsForAWSResource" = "true"
          }
          StringEquals = {
            "kms:CallerAccount" = var.aws_account_id
            "kms:ViaService"    = "dynamodb.${var.aws_region}.amazonaws.com"
          }
        }
      },
    ]
  })

  tags = merge(var.tags, {
    Name = local.key_name
  })
}

resource "aws_kms_alias" "dynamodb" {
  # KMS requires the service prefix `alias/`; the customer-controlled alias body
  # still follows the requested environment-prefixed naming convention.
  name          = "alias/${local.key_name}"
  target_key_id = aws_kms_key.dynamodb.key_id
}
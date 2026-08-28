mock_provider "aws" {
  override_during = plan
}

run "dynamodb_is_encrypted_and_recoverable" {
  command = plan

  module {
    source = "./modules/dynamodb"
  }

  variables {
    environment                 = "prod"
    kms_key_arn                 = "arn:aws:kms:eu-west-1:123456789012:key/11111111-2222-3333-4444-555555555555"
    point_in_time_recovery      = true
    deletion_protection_enabled = true
    tags = {
      Environment = "prod"
      ManagedBy   = "Terraform"
      Project     = "serverless-health-check-api"
      Repository  = "eimisse/serverless-health-check-api"
    }
  }

  assert {
    condition = (
      aws_dynamodb_table.requests.name == "prod-requests-db" &&
      aws_dynamodb_table.requests.billing_mode == "PAY_PER_REQUEST" &&
      aws_dynamodb_table.requests.hash_key == "request_id"
    )
    error_message = "The request table must use the exact prod name, PAY_PER_REQUEST, and request_id partition key."
  }

  assert {
    condition = (
      aws_dynamodb_table.requests.server_side_encryption[0].enabled &&
      aws_dynamodb_table.requests.server_side_encryption[0].kms_key_arn == "arn:aws:kms:eu-west-1:123456789012:key/11111111-2222-3333-4444-555555555555"
    )
    error_message = "DynamoDB SSE must use the supplied customer-managed KMS key."
  }

  assert {
    condition = (
      aws_dynamodb_table.requests.point_in_time_recovery[0].enabled &&
      aws_dynamodb_table.requests.ttl[0].enabled &&
      aws_dynamodb_table.requests.ttl[0].attribute_name == "expires_at" &&
      aws_dynamodb_table.requests.deletion_protection_enabled
    )
    error_message = "Prod data protection requires PITR, TTL, and deletion protection."
  }

  assert {
    condition = (
      aws_dynamodb_table.requests.tags.Environment == "prod" &&
      aws_dynamodb_table.requests.tags.Project == "serverless-health-check-api" &&
      aws_dynamodb_table.requests.tags.Name == "prod-requests-db"
    )
    error_message = "The table must retain environment/project ownership tags and the prod name."
  }
}

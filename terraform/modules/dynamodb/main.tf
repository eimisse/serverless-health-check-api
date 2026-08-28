resource "aws_dynamodb_table" "requests" {
  name         = "${var.environment}-requests-db"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "request_id"
  table_class  = "STANDARD"

  deletion_protection_enabled = var.deletion_protection_enabled

  attribute {
    name = "request_id"
    type = "S"
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }

  point_in_time_recovery {
    enabled = var.point_in_time_recovery
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  tags = merge(var.tags, {
    Name = "${var.environment}-requests-db"
  })
}

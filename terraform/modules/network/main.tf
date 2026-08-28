locals {
  name_prefix     = "${var.environment}-health-check"
  subnet_suffixes = ["a", "b"]
}

#trivy:ignore:AVD-AWS-0178
resource "aws_vpc" "this" {
  #checkov:skip=CKV2_AWS_11:The VPC has no ingress, Internet gateway, or NAT; flow logs add cost and IAM/log infrastructure without useful signal for one DynamoDB endpoint path.
  #checkov:skip=CKV2_AWS_12:The unused default security group is never referenced; Lambda uses a dedicated no-ingress, prefix-list-only egress group.
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(var.tags, {
    Name = "${local.name_prefix}-vpc"
  })
}

resource "aws_subnet" "private" {
  count = 2

  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.private_subnet_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = false

  tags = merge(var.tags, {
    Name    = "${local.name_prefix}-private-${local.subnet_suffixes[count.index]}"
    Network = "private"
  })
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.tags, {
    Name = "${local.name_prefix}-private-routes"
  })
}

resource "aws_route_table_association" "private" {
  count = 2

  route_table_id = aws_route_table.private.id
  subnet_id      = aws_subnet.private[count.index].id
}

resource "aws_security_group" "lambda" {
  #checkov:skip=CKV2_AWS_5:The group is attached by aws_lambda_function.vpc_config; Checkov does not resolve this cross-module reference.
  name        = "${local.name_prefix}-function-sg"
  description = "No ingress; HTTPS egress only to the regional DynamoDB prefix list"
  vpc_id      = aws_vpc.this.id

  # Do not configure ingress/egress inline here. Rules are managed only by the
  # dedicated aws_vpc_security_group_*_rule resources below. Mixing both models
  # can make aws_security_group remove a separately managed rule during refresh/apply.
  tags = merge(var.tags, {
    Name = "${local.name_prefix}-function-sg"
  })
}

resource "aws_vpc_security_group_egress_rule" "dynamodb_https" {
  security_group_id = aws_security_group.lambda.id
  description       = "HTTPS to the AWS-managed DynamoDB prefix list only"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  prefix_list_id    = var.dynamodb_prefix_list_id

  tags = merge(var.tags, {
    Name = "${local.name_prefix}-dynamodb-https-egress"
  })
}

resource "aws_vpc_endpoint" "dynamodb" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${var.aws_region}.dynamodb"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowOnlyRuntimePutItemToApplicationTable"
        Effect    = "Allow"
        Principal = "*"
        Action    = "dynamodb:PutItem"
        Resource  = var.dynamodb_table_arn
        Condition = {
          ArnEquals = {
            "aws:PrincipalArn" = var.lambda_runtime_role_arn
          }
        }
      }
    ]
  })

  tags = merge(var.tags, {
    Name = "${local.name_prefix}-dynamodb-endpoint"
  })
}

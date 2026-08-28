mock_provider "aws" {
  override_during = plan
}

run "network_is_private_and_dynamodb_only" {
  command = plan

  module {
    source = "./modules/network"
  }

  variables {
    environment             = "staging"
    aws_region              = "eu-west-1"
    vpc_cidr                = "10.10.0.0/24"
    private_subnet_cidrs    = ["10.10.0.0/26", "10.10.0.64/26"]
    availability_zones      = ["eu-west-1a", "eu-west-1b"]
    dynamodb_prefix_list_id = "pl-12345678"
    dynamodb_table_arn      = "arn:aws:dynamodb:eu-west-1:123456789012:table/staging-requests-db"
    lambda_runtime_role_arn = "arn:aws:iam::123456789012:role/staging-health-check-function-role"
    tags = {
      Environment = "staging"
      ManagedBy   = "Terraform"
      Project     = "serverless-health-check-api"
      Repository  = "eimisse/serverless-health-check-api"
    }
  }

  assert {
    condition     = aws_vpc.this.enable_dns_support && aws_vpc.this.enable_dns_hostnames
    error_message = "VPC DNS support and hostnames must be enabled."
  }

  assert {
    condition = (
      length(aws_subnet.private) == 2 &&
      aws_subnet.private[0].availability_zone != aws_subnet.private[1].availability_zone &&
      alltrue([for subnet in aws_subnet.private : subnet.map_public_ip_on_launch == false])
    )
    error_message = "Lambda requires two private subnets in distinct Availability Zones with public IP assignment disabled."
  }

  assert {
    condition = (
      aws_vpc.this.tags.Name == "staging-health-check-vpc" &&
      aws_subnet.private[0].tags.Name == "staging-health-check-private-a" &&
      aws_subnet.private[1].tags.Name == "staging-health-check-private-b" &&
      aws_route_table.private.tags.Name == "staging-health-check-private-routes" &&
      aws_security_group.lambda.name == "staging-health-check-function-sg"
    )
    error_message = "Customer-named network resources must retain the staging- prefix."
  }

  assert {
    condition = (
      !strcontains(file("${path.module}/main.tf"), "resource \"aws_nat_gateway\"") &&
      !strcontains(file("${path.module}/main.tf"), "resource \"aws_internet_gateway\"")
    )
    error_message = "The network module must not create NAT or Internet gateways."
  }

  assert {
    condition = (
      !strcontains(file("${path.module}/main.tf"), "ingress = [") &&
      !strcontains(file("${path.module}/main.tf"), "egress  = [") &&
      !strcontains(file("${path.module}/main.tf"), "egress = [")
    )
    error_message = "Security group rules must be owned only by dedicated aws_vpc_security_group_*_rule resources; inline rule management can overwrite them."
  }

  assert {
    condition = (
      aws_vpc_security_group_egress_rule.dynamodb_https.prefix_list_id == "pl-12345678" &&
      aws_vpc_security_group_egress_rule.dynamodb_https.from_port == 443 &&
      aws_vpc_security_group_egress_rule.dynamodb_https.to_port == 443 &&
      aws_vpc_security_group_egress_rule.dynamodb_https.ip_protocol == "tcp"
    )
    error_message = "Lambda egress must be TCP/443 to the DynamoDB prefix list only."
  }

  assert {
    condition = (
      aws_vpc_endpoint.dynamodb.vpc_endpoint_type == "Gateway" &&
      jsondecode(aws_vpc_endpoint.dynamodb.policy).Statement[0].Action == "dynamodb:PutItem" &&
      jsondecode(aws_vpc_endpoint.dynamodb.policy).Statement[0].Resource == "arn:aws:dynamodb:eu-west-1:123456789012:table/staging-requests-db" &&
      jsondecode(aws_vpc_endpoint.dynamodb.policy).Statement[0].Condition.ArnEquals["aws:PrincipalArn"] == "arn:aws:iam::123456789012:role/staging-health-check-function-role"
    )
    error_message = "The DynamoDB endpoint must permit only runtime-role PutItem to the exact table."
  }
}

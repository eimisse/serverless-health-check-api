mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "123456789012"
      arn        = "arn:aws:iam::123456789012:role/terraform-test"
      user_id    = "AROATEST"
    }
  }

  mock_data "aws_partition" {
    defaults = {
      partition  = "aws"
      dns_suffix = "amazonaws.com"
    }
  }

  mock_data "aws_prefix_list" {
    defaults = {
      id   = "pl-12345678"
      name = "com.amazonaws.eu-west-1.dynamodb"
    }
  }
}

variables {
  environment                          = "staging"
  aws_region                           = "eu-west-1"
  vpc_cidr                             = "10.10.0.0/24"
  private_subnet_cidrs                 = ["10.10.0.0/26", "10.10.0.64/26"]
  availability_zones                   = ["eu-west-1a", "eu-west-1b"]
  lambda_reserved_concurrency          = -1
  log_retention_days                   = 14
  dynamodb_deletion_protection_enabled = false
  kms_deletion_window_days             = 7
  stage_throttle_rate_limit            = 5
  stage_throttle_burst_limit           = 10
  usage_plan_rate_limit                = 2
  usage_plan_burst_limit               = 4
  api_latency_alarm_threshold_ms       = 2000
}

run "staging_names_and_topology" {
  command = plan

  assert {
    condition     = output.lambda_function_name == "staging-health-check-function"
    error_message = "The staging Lambda name must use the environment prefix."
  }

  assert {
    condition     = output.dynamodb_table_name == "staging-requests-db"
    error_message = "The staging DynamoDB table must use the required exact name."
  }

  assert {
    condition     = length(output.private_subnet_ids) == 2
    error_message = "The application must create exactly two private subnets."
  }
}

run "prod_is_distinct_and_protected" {
  command = plan

  variables {
    environment                          = "prod"
    vpc_cidr                             = "10.20.0.0/24"
    private_subnet_cidrs                 = ["10.20.0.0/26", "10.20.0.64/26"]
    lambda_reserved_concurrency          = 10
    log_retention_days                   = 30
    dynamodb_deletion_protection_enabled = true
    kms_deletion_window_days             = 30
    stage_throttle_rate_limit            = 50
    stage_throttle_burst_limit           = 100
    usage_plan_rate_limit                = 25
    usage_plan_burst_limit               = 50
    api_latency_alarm_threshold_ms       = 1500
  }

  assert {
    condition     = output.lambda_function_name == "prod-health-check-function"
    error_message = "The prod Lambda name must use the environment prefix."
  }

  assert {
    condition     = output.dynamodb_table_name == "prod-requests-db"
    error_message = "The prod DynamoDB table must use the required exact name."
  }

  assert {
    condition     = output.lambda_function_name != run.staging_names_and_topology.lambda_function_name
    error_message = "Staging and prod names must be distinct."
  }
}

run "reject_zero_reserved_concurrency" {
  command = plan

  variables {
    lambda_reserved_concurrency = 0
  }

  expect_failures = [var.lambda_reserved_concurrency]
}

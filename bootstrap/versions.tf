terraform {
  required_version = "~> 1.16.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  # data.aws_caller_identity.current performs the explicit identity check. Avoid
  # the provider's duplicate STS/account probes so offline mock plans remain useful.
  skip_credentials_validation = true
  skip_requesting_account_id  = true

  default_tags {
    tags = local.common_tags
  }
}

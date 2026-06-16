# =============================================================================
# FloCI - dev environment
# =============================================================================
# Development environment with minimal resources.
# Suitable for local testing and development work.
# =============================================================================

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

module "platform" {
  source = "../../modules/platform"

  environment = "dev"
  region      = "us-east-1"

  tags = {
    Environment = "dev"
    CostCenter  = "engineering-dev"
  }
}

# Dev-specific outputs
output "dev_bucket_names" {
  value       = module.platform.bucket_names
  description = "S3 bucket names for the dev environment"
}

# =============================================================================
# FloCI - test environment
# =============================================================================
# Test environment for integration testing and validation.
# Reflects production configuration at reduced scale.
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

  environment = "test"
  region      = "us-east-1"

  tags = {
    Environment = "test"
    CostCenter  = "engineering-test"
  }
}

# Test-specific outputs
output "test_bucket_names" {
  value       = module.platform.bucket_names
  description = "S3 bucket names for the test environment"
}

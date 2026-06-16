# =============================================================================
# FloCI - prod environment
# =============================================================================
# Production environment with full security and compliance controls.
# Includes encryption, versioning, and extended monitoring.
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

  environment = "prod"
  region      = "us-east-1"

  tags = {
    Environment = "prod"
    CostCenter  = "operations-prod"
    Compliance  = "soc2"
  }
}

# Prod-specific outputs
output "prod_bucket_names" {
  value       = module.platform.bucket_names
  description = "S3 bucket names for the prod environment"
}

# Prod-specific: additional monitoring alert
resource "aws_s3_bucket_intelligent_tiering_configuration" "prod_metrics" {
  bucket = module.platform.bucket_names["metrics"]
  name   = "entire-bucket"

  tiering {
    access_tier = "DEEP_ARCHIVE_ACCESS"
    days        = 180
  }
}

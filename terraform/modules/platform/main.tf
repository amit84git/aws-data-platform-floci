# =============================================================================
# FloCI Platform Module
# =============================================================================
# This module defines the infrastructure resources for the data ingestion
# platform. It is designed to be instantiated per environment (dev/test/prod).
# For local development, resources map to Docker-based equivalents.
#
# Design decisions:
# - S3 buckets are environment-aware via `environment` variable
# - IAM roles are scoped per environment for isolation
# - Network boundary: private buckets with no public access
# =============================================================================

# S3 Buckets for ingestion pipeline (maps to MinIO buckets locally)
resource "aws_s3_bucket" "raw" {
  bucket = "floci-${var.environment}-ingestion-raw"

  tags = {
    Name        = "FloCI ${var.environment} Raw Ingestion"
    Environment = var.environment
    Service     = "floci-ingestion"
  }
}

resource "aws_s3_bucket" "valid" {
  bucket = "floci-${var.environment}-ingestion-valid"

  tags = {
    Name        = "FloCI ${var.environment} Valid Files"
    Environment = var.environment
    Service     = "floci-ingestion"
  }
}

resource "aws_s3_bucket" "quarantine" {
  bucket = "floci-${var.environment}-ingestion-quarantine"

  tags = {
    Name        = "FloCI ${var.environment} Quarantine"
    Environment = var.environment
    Service     = "floci-ingestion"
  }
}

resource "aws_s3_bucket" "processed" {
  bucket = "floci-${var.environment}-ingestion-processed"

  tags = {
    Name        = "FloCI ${var.environment} Processed Output"
    Environment = var.environment
    Service     = "floci-ingestion"
  }
}

resource "aws_s3_bucket" "metrics" {
  bucket = "floci-${var.environment}-ingestion-metrics"

  tags = {
    Name        = "FloCI ${var.environment} Metrics"
    Environment = var.environment
    Service     = "floci-ingestion"
  }
}

# S3 bucket public access blocks for security (network boundary)
resource "aws_s3_bucket_public_access_block" "raw" {
  bucket = aws_s3_bucket.raw.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "valid" {
  bucket = aws_s3_bucket.valid.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "quarantine" {
  bucket = aws_s3_bucket.quarantine.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "processed" {
  bucket = aws_s3_bucket.processed.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "metrics" {
  bucket = aws_s3_bucket.metrics.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# S3 bucket versioning for data protection
resource "aws_s3_bucket_versioning" "raw" {
  bucket = aws_s3_bucket.raw.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_versioning" "quarantine" {
  bucket = aws_s3_bucket.quarantine.id
  versioning_configuration {
    status = "Enabled"
  }
}

# S3 lifecycle policy: expire quarantined files after 30 days
resource "aws_s3_bucket_lifecycle_configuration" "quarantine" {
  bucket = aws_s3_bucket.quarantine.id

  rule {
    id     = "expire-quarantined"
    status = "Enabled"

    expiration {
      days = 30
    }
  }
}

# Lambda IAM role
resource "aws_iam_role" "lambda" {
  name = "floci-${var.environment}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Environment = var.environment
    Service     = "floci-ingestion"
  }
}

# Lambda IAM policy for S3 access
resource "aws_iam_role_policy" "lambda_s3" {
  name = "floci-${var.environment}-lambda-s3-policy"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
          "s3:CopyObject",
        ]
        Resource = [
          aws_s3_bucket.raw.arn,
          "${aws_s3_bucket.raw.arn}/*",
          aws_s3_bucket.valid.arn,
          "${aws_s3_bucket.valid.arn}/*",
          aws_s3_bucket.quarantine.arn,
          "${aws_s3_bucket.quarantine.arn}/*",
          aws_s3_bucket.processed.arn,
          "${aws_s3_bucket.processed.arn}/*",
        ]
      },
    ]
  })
}

# Outputs for use by environment configurations
output "bucket_names" {
  value = {
    raw        = aws_s3_bucket.raw.id
    valid      = aws_s3_bucket.valid.id
    quarantine = aws_s3_bucket.quarantine.id
    processed  = aws_s3_bucket.processed.id
    metrics    = aws_s3_bucket.metrics.id
  }
}

output "lambda_role_arn" {
  value = aws_iam_role.lambda.arn
}

########################################
# S3 bucket for application assets, exports, and telemetry/document
# artifacts (backend.app.agent document ingestion, robot data exports).
# Private by default — nothing here is served directly to end users.
########################################

resource "aws_s3_bucket" "main" {
  bucket        = var.bucket_name
  force_destroy = var.force_destroy

  tags = var.tags
}

resource "aws_s3_bucket_versioning" "main" {
  bucket = aws_s3_bucket.main.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "main" {
  bucket = aws_s3_bucket.main.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "main" {
  bucket = aws_s3_bucket.main.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "main" {
  bucket = aws_s3_bucket.main.id

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"
    filter {} # applies to every object in the bucket

    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_expiration_days
    }
  }

  rule {
    id     = "abort-incomplete-multipart-uploads"
    status = "Enabled"
    filter {} # applies to every object in the bucket

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

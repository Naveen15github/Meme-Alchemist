# ---------------------------------------------------------------------------
# Three buckets, all private. Nothing is ever made public via bucket policy;
# CloudFront reaches the two it serves through Origin Access Control (OAC).
# ---------------------------------------------------------------------------

# --- Uploads: raw user images, written by the browser via presigned PUT ------
resource "aws_s3_bucket" "uploads" {
  bucket        = local.upload_bucket_name
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "uploads" {
  bucket                  = aws_s3_bucket.uploads.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# The browser PUTs directly to S3, so the bucket itself needs CORS.
resource "aws_s3_bucket_cors_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  cors_rule {
    allowed_methods = ["PUT"]
    allowed_origins = ["*"]
    allowed_headers = ["content-type"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

# Originals are only needed for the few seconds Rekognition and Pillow use them.
resource "aws_s3_bucket_lifecycle_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  rule {
    id     = "expire-originals"
    status = "Enabled"
    filter {}
    expiration {
      days = var.upload_expiry_days
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

# --- Processed: finished memes, served through CloudFront at /memes/* --------
resource "aws_s3_bucket" "processed" {
  bucket        = local.processed_bucket_name
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "processed" {
  bucket                  = aws_s3_bucket.processed.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "processed" {
  bucket = aws_s3_bucket.processed.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# --- Site: the built React app, served through CloudFront at / ---------------
resource "aws_s3_bucket" "site" {
  bucket        = local.site_bucket_name
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket                  = aws_s3_bucket.site.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "site" {
  bucket = aws_s3_bucket.site.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# --- OAC bucket policies: only this CloudFront distribution may read ---------
data "aws_iam_policy_document" "site_oac" {
  statement {
    sid       = "AllowCloudFrontRead"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.site.arn}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.cdn.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "site" {
  bucket     = aws_s3_bucket.site.id
  policy     = data.aws_iam_policy_document.site_oac.json
  depends_on = [aws_s3_bucket_public_access_block.site]
}

data "aws_iam_policy_document" "processed_oac" {
  statement {
    sid       = "AllowCloudFrontRead"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.processed.arn}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.cdn.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "processed" {
  bucket     = aws_s3_bucket.processed.id
  policy     = data.aws_iam_policy_document.processed_oac.json
  depends_on = [aws_s3_bucket_public_access_block.processed]
}

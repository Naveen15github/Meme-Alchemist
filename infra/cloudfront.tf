# One distribution serves both the React app (/) and the finished memes
# (/memes/*). Same-origin image URLs mean the gallery, downloads and
# share links never touch CORS.

resource "aws_cloudfront_origin_access_control" "site" {
  name                              = "${local.name}-site-oac-${local.suffix}"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_origin_access_control" "processed" {
  name                              = "${local.name}-memes-oac-${local.suffix}"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# AWS managed policies: CachingOptimized for immutable memes, CachingDisabled
# for the HTML shell so redeploys are visible immediately.
data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_cache_policy" "disabled" {
  name = "Managed-CachingDisabled"
}

resource "aws_cloudfront_distribution" "cdn" {
  enabled             = true
  comment             = "${local.name} app + memes"
  default_root_object = "index.html"
  price_class         = "PriceClass_100" # NA + EU: cheapest tier that still feels fast

  origin {
    origin_id                = "site"
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }

  origin {
    origin_id                = "memes"
    domain_name              = aws_s3_bucket.processed.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.processed.id
  }

  default_cache_behavior {
    target_origin_id       = "site"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = data.aws_cloudfront_cache_policy.disabled.id
  }

  # Hashed Vite assets are safe to cache hard.
  ordered_cache_behavior {
    path_pattern           = "/assets/*"
    target_origin_id       = "site"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = data.aws_cloudfront_cache_policy.optimized.id
  }

  ordered_cache_behavior {
    path_pattern           = "/memes/*"
    target_origin_id       = "memes"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = false # already-compressed JPEG
    cache_policy_id        = data.aws_cloudfront_cache_policy.optimized.id
  }

  # S3 with OAC answers 403 for keys that do not exist; send both to the app
  # shell so a stray URL shows the app rather than an XML error page.
  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

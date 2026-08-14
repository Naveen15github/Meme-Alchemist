output "app_url" {
  description = "Public URL of the deployed app."
  value       = "https://${aws_cloudfront_distribution.cdn.domain_name}"
}

output "api_base_url" {
  description = "Base URL of the HTTP API."
  value       = aws_apigatewayv2_api.api.api_endpoint
}

output "cloudfront_distribution_id" {
  description = "Used by deploy.sh to invalidate the cache after a frontend upload."
  value       = aws_cloudfront_distribution.cdn.id
}

output "site_bucket" {
  description = "Bucket the built frontend is synced into."
  value       = aws_s3_bucket.site.id
}

output "uploads_bucket" {
  value = aws_s3_bucket.uploads.id
}

output "processed_bucket" {
  value = aws_s3_bucket.processed.id
}

output "table_name" {
  value = aws_dynamodb_table.memes.name
}

output "bedrock_model_id" {
  value = var.bedrock_model_id
}

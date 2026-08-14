data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Bucket names are globally unique, so suffix them with a stable random id.
resource "random_id" "suffix" {
  byte_length = 4
}

locals {
  name   = var.project_name
  suffix = random_id.suffix.hex

  upload_bucket_name    = "${local.name}-uploads-${local.suffix}"
  processed_bucket_name = "${local.name}-memes-${local.suffix}"
  site_bucket_name      = "${local.name}-site-${local.suffix}"

  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name
}

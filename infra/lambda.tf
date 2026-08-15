# One source zip shared by all three functions - they differ only by handler.
data "archive_file" "src" {
  type        = "zip"
  source_dir  = "${path.module}/../backend/src"
  output_path = "${path.module}/.build/src.zip"
  excludes    = ["**/__pycache__/**", "**/*.pyc"]
}

data "archive_file" "pillow_layer" {
  type        = "zip"
  source_dir  = "${path.module}/../backend/layer/build"
  output_path = "${path.module}/.build/pillow-layer.zip"
  excludes    = ["**/__pycache__/**", "**/*.pyc"]
}

resource "aws_lambda_layer_version" "pillow" {
  layer_name          = "${local.name}-pillow"
  description         = "Pillow for meme rendering (manylinux2014_x86_64, cp312)"
  filename            = data.archive_file.pillow_layer.output_path
  source_code_hash    = data.archive_file.pillow_layer.output_base64sha256
  compatible_runtimes = ["python3.12"]

  compatible_architectures = ["x86_64"]
}

locals {
  common_env = {
    UPLOAD_BUCKET    = aws_s3_bucket.uploads.id
    PROCESSED_BUCKET = aws_s3_bucket.processed.id
    TABLE_NAME       = aws_dynamodb_table.memes.name
    MAX_UPLOAD_BYTES = tostring(var.max_upload_bytes)
    LOG_LEVEL        = "INFO"
  }
}

# --- presign ----------------------------------------------------------------
resource "aws_cloudwatch_log_group" "presign" {
  name              = "/aws/lambda/${local.name}-presign"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "presign" {
  function_name    = "${local.name}-presign"
  role             = aws_iam_role.presign.arn
  handler          = "presign.handler.handler"
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  filename         = data.archive_file.src.output_path
  source_code_hash = data.archive_file.src.output_base64sha256
  timeout          = 10
  memory_size      = 256

  environment {
    variables = local.common_env
  }

  depends_on = [aws_cloudwatch_log_group.presign]
}

# --- generate ---------------------------------------------------------------
resource "aws_cloudwatch_log_group" "generate" {
  name              = "/aws/lambda/${local.name}-generate"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "generate" {
  function_name    = "${local.name}-generate"
  role             = aws_iam_role.generate.arn
  handler          = "generate.handler.handler"
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  filename         = data.archive_file.src.output_path
  source_code_hash = data.archive_file.src.output_base64sha256
  layers           = [aws_lambda_layer_version.pillow.arn]

  # Generous enough to absorb Bedrock retries plus rendering, well under the
  # 29s API Gateway limit for the common path.
  timeout     = 28
  memory_size = 1536 # more memory also means more CPU for Pillow

  environment {
    variables = merge(local.common_env, {
      PUBLIC_BASE_URL  = "https://${aws_cloudfront_distribution.cdn.domain_name}"
      BEDROCK_MODEL_ID = var.bedrock_model_id
      BEDROCK_REGION   = var.aws_region
      OUTPUT_MAX_EDGE  = "1080"
    })
  }

  depends_on = [aws_cloudwatch_log_group.generate]
}

# --- gallery ----------------------------------------------------------------
resource "aws_cloudwatch_log_group" "gallery" {
  name              = "/aws/lambda/${local.name}-gallery"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "gallery" {
  function_name    = "${local.name}-gallery"
  role             = aws_iam_role.gallery.arn
  handler          = "gallery.handler.handler"
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  filename         = data.archive_file.src.output_path
  source_code_hash = data.archive_file.src.output_base64sha256
  timeout          = 10
  memory_size      = 256

  environment {
    variables = local.common_env
  }

  depends_on = [aws_cloudwatch_log_group.gallery]
}

# --- delete -----------------------------------------------------------------
resource "aws_cloudwatch_log_group" "delete" {
  name              = "/aws/lambda/${local.name}-delete"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "delete" {
  function_name    = "${local.name}-delete"
  role             = aws_iam_role.delete.arn
  handler          = "delete.handler.handler"
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  filename         = data.archive_file.src.output_path
  source_code_hash = data.archive_file.src.output_base64sha256
  timeout          = 10
  memory_size      = 256

  environment {
    variables = local.common_env
  }

  depends_on = [aws_cloudwatch_log_group.delete]
}

# ---------------------------------------------------------------------------
# One role per function, each scoped to exactly the calls that function makes.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

locals {
  # Nova is reachable both as a plain foundation model and, for some variants,
  # only through a cross-region inference profile. Allow both shapes so
  # switching bedrock_model_id never requires an IAM edit.
  bedrock_model_arns = [
    "arn:aws:bedrock:${local.region}::foundation-model/*",
    "arn:aws:bedrock:${local.region}:${local.account_id}:inference-profile/*",
    "arn:aws:bedrock:*::foundation-model/*",
  ]
}

# --- presign ----------------------------------------------------------------
resource "aws_iam_role" "presign" {
  name               = "${local.name}-presign-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "presign" {
  statement {
    sid       = "WriteUploads"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.uploads.arn}/uploads/*"]
  }
}

resource "aws_iam_role_policy" "presign" {
  name   = "${local.name}-presign-policy"
  role   = aws_iam_role.presign.id
  policy = data.aws_iam_policy_document.presign.json
}

resource "aws_iam_role_policy_attachment" "presign_logs" {
  role       = aws_iam_role.presign.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# --- generate ---------------------------------------------------------------
resource "aws_iam_role" "generate" {
  name               = "${local.name}-generate-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "generate" {
  statement {
    sid       = "ReadUpload"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.uploads.arn}/uploads/*"]
  }

  statement {
    sid       = "WriteMeme"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.processed.arn}/memes/*"]
  }

  # Rekognition DetectLabels has no resource-level scoping; the S3 read above
  # is what actually bounds which images can be analysed.
  statement {
    sid       = "DetectLabels"
    actions   = ["rekognition:DetectLabels"]
    resources = ["*"]
  }

  statement {
    sid       = "InvokeCaptionModel"
    actions   = ["bedrock:InvokeModel"]
    resources = local.bedrock_model_arns
  }

  statement {
    sid       = "RecordMeme"
    actions   = ["dynamodb:PutItem"]
    resources = [aws_dynamodb_table.memes.arn]
  }
}

resource "aws_iam_role_policy" "generate" {
  name   = "${local.name}-generate-policy"
  role   = aws_iam_role.generate.id
  policy = data.aws_iam_policy_document.generate.json
}

resource "aws_iam_role_policy_attachment" "generate_logs" {
  role       = aws_iam_role.generate.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# --- gallery ----------------------------------------------------------------
resource "aws_iam_role" "gallery" {
  name               = "${local.name}-gallery-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "gallery" {
  statement {
    sid       = "ReadMemes"
    actions   = ["dynamodb:Query"]
    resources = [aws_dynamodb_table.memes.arn, "${aws_dynamodb_table.memes.arn}/index/*"]
  }
}

resource "aws_iam_role_policy" "gallery" {
  name   = "${local.name}-gallery-policy"
  role   = aws_iam_role.gallery.id
  policy = data.aws_iam_policy_document.gallery.json
}

resource "aws_iam_role_policy_attachment" "gallery_logs" {
  role       = aws_iam_role.gallery.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# --- delete -----------------------------------------------------------------
resource "aws_iam_role" "delete" {
  name               = "${local.name}-delete-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "delete" {
  # GetItem is needed to read the stored token hash before authorising.
  statement {
    sid       = "ReadAndRemoveRecord"
    actions   = ["dynamodb:GetItem", "dynamodb:DeleteItem"]
    resources = [aws_dynamodb_table.memes.arn]
  }

  statement {
    sid       = "RemoveMemeObject"
    actions   = ["s3:DeleteObject"]
    resources = ["${aws_s3_bucket.processed.arn}/memes/*"]
  }
}

resource "aws_iam_role_policy" "delete" {
  name   = "${local.name}-delete-policy"
  role   = aws_iam_role.delete.id
  policy = data.aws_iam_policy_document.delete.json
}

resource "aws_iam_role_policy_attachment" "delete_logs" {
  role       = aws_iam_role.delete.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

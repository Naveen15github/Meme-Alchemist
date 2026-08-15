resource "aws_apigatewayv2_api" "api" {
  name          = "${local.name}-api"
  protocol_type = "HTTP"
  description   = "Meme Alchemist public API"

  cors_configuration {
    allow_origins  = ["*"]
    allow_methods  = ["GET", "POST", "DELETE", "OPTIONS"]
    allow_headers  = ["content-type", "x-delete-token"]
    max_age        = 3600
    expose_headers = ["content-type"]
  }
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/apigateway/${local.name}"
  retention_in_days = var.log_retention_days
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      responseLength = "$context.responseLength"
      latencyMs      = "$context.responseLatency"
      integrationErr = "$context.integrationErrorMessage"
    })
  }

  default_route_settings {
    # A demo endpoint with no auth: cap it so a stray script cannot run up a bill.
    throttling_burst_limit = 20
    throttling_rate_limit  = 10
  }
}

locals {
  routes = {
    "POST /uploads"      = aws_lambda_function.presign.invoke_arn
    "POST /generate"     = aws_lambda_function.generate.invoke_arn
    "GET /gallery"       = aws_lambda_function.gallery.invoke_arn
    "DELETE /memes/{id}" = aws_lambda_function.delete.invoke_arn
  }

  route_functions = {
    "POST /uploads"      = aws_lambda_function.presign.function_name
    "POST /generate"     = aws_lambda_function.generate.function_name
    "GET /gallery"       = aws_lambda_function.gallery.function_name
    "DELETE /memes/{id}" = aws_lambda_function.delete.function_name
  }
}

resource "aws_apigatewayv2_integration" "lambda" {
  for_each = local.routes

  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = each.value
  payload_format_version = "2.0"
  timeout_milliseconds   = 29000
}

resource "aws_apigatewayv2_route" "route" {
  for_each = local.routes

  api_id    = aws_apigatewayv2_api.api.id
  route_key = each.key
  target    = "integrations/${aws_apigatewayv2_integration.lambda[each.key].id}"
}

resource "aws_lambda_permission" "apigw" {
  for_each = local.route_functions

  # statement_id only permits [A-Za-z0-9-_], so strip spaces, slashes and the
  # braces from path parameters such as "DELETE /memes/{id}".
  statement_id  = "AllowAPIGatewayInvoke-${replace(each.key, "/[^A-Za-z0-9]/", "-")}"
  action        = "lambda:InvokeFunction"
  function_name = each.value
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}

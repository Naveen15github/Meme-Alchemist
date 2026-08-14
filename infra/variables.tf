variable "project_name" {
  description = "Short name used to prefix every resource."
  type        = string
  default     = "meme-alchemist"
}

variable "aws_region" {
  description = "Region for all regional resources. Must support Amazon Bedrock Nova."
  type        = string
  default     = "us-east-1"
}

variable "bedrock_model_id" {
  description = "Bedrock model used for caption generation."
  type        = string
  default     = "amazon.nova-lite-v1:0"
}

variable "max_upload_bytes" {
  description = "Largest image the API will accept."
  type        = number
  default     = 8388608 # 8 MiB
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention. Keeps demo costs near zero."
  type        = number
  default     = 14
}

variable "upload_expiry_days" {
  description = "Original uploads are transient; expire them to control storage cost."
  type        = number
  default     = 7
}

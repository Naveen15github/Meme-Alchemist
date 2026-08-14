"""Central configuration, read from environment with safe defaults.

Every value has a default so unit tests can import the module without a
fully-populated environment.
"""
import os

UPLOAD_BUCKET = os.environ.get("UPLOAD_BUCKET", "")
PROCESSED_BUCKET = os.environ.get("PROCESSED_BUCKET", "")
TABLE_NAME = os.environ.get("TABLE_NAME", "")

# Public CloudFront origin that fronts the processed bucket under /memes/*.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", os.environ.get("AWS_REGION", "us-east-1"))

# 8 MB ceiling, enforced both at presign time and again before processing.
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(8 * 1024 * 1024)))

# Rekognition only accepts JPEG and PNG, so that is exactly what we accept.
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}
CONTENT_TYPE_EXT = {"image/jpeg": "jpg", "image/png": "png"}

# Longest edge of the rendered meme. Keeps output small and fast to load.
OUTPUT_MAX_EDGE = int(os.environ.get("OUTPUT_MAX_EDGE", "1080"))

REKOGNITION_MAX_LABELS = 12
REKOGNITION_MIN_CONFIDENCE = 70.0

# Total attempts against Bedrock before we give up and use a local caption.
BEDROCK_MAX_ATTEMPTS = int(os.environ.get("BEDROCK_MAX_ATTEMPTS", "3"))
BEDROCK_BASE_BACKOFF_SECONDS = float(os.environ.get("BEDROCK_BASE_BACKOFF_SECONDS", "0.4"))
BEDROCK_READ_TIMEOUT_SECONDS = float(os.environ.get("BEDROCK_READ_TIMEOUT_SECONDS", "8"))

GALLERY_PAGE_SIZE = int(os.environ.get("GALLERY_PAGE_SIZE", "24"))

"""POST /generate — the full pipeline: Rekognition -> Bedrock -> Pillow -> S3 -> DynamoDB."""
import re
import time
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from common import config, obs
from common.http import ApiError, fail, ok, parse_json_body
from generate import captions, memeimg

_s3 = boto3.client("s3")
_rekognition = boto3.client("rekognition")
_dynamodb = boto3.resource("dynamodb")

# uploads/<uuid4>.<jpg|png>
_KEY_PATTERN = re.compile(r"^uploads/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(jpg|png)$")


def _validate_key(key: str) -> str:
    if not isinstance(key, str) or not _KEY_PATTERN.match(key):
        raise ApiError(400, "INVALID_KEY", "That upload reference is not valid. Please upload the image again.")
    return key


def _head_upload(key: str) -> dict:
    try:
        head = _s3.head_object(Bucket=config.UPLOAD_BUCKET, Key=key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound"):
            raise ApiError(404, "UPLOAD_NOT_FOUND", "We couldn't find that upload. Please try uploading again.")
        raise

    size = head.get("ContentLength", 0)
    if size <= 0:
        raise ApiError(400, "EMPTY_FILE", "That file appears to be empty.")
    if size > config.MAX_UPLOAD_BYTES:
        raise ApiError(
            413, "FILE_TOO_LARGE",
            f"That image is {size // (1024 * 1024)} MB. Please use one under {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )

    content_type = (head.get("ContentType") or "").split(";")[0].strip().lower()
    if content_type not in config.ALLOWED_CONTENT_TYPES:
        raise ApiError(415, "UNSUPPORTED_TYPE", "Please upload a JPEG or PNG image.")

    return {"size": size, "contentType": content_type}


def _detect_labels(key: str) -> list[str]:
    """Rekognition labels, highest confidence first. Never raises."""
    try:
        response = _rekognition.detect_labels(
            Image={"S3Object": {"Bucket": config.UPLOAD_BUCKET, "Name": key}},
            MaxLabels=config.REKOGNITION_MAX_LABELS,
            MinConfidence=config.REKOGNITION_MIN_CONFIDENCE,
        )
    except Exception as exc:  # noqa: BLE001 - degrade to the mystery caption path
        obs.warn("rekognition_failed", errorType=type(exc).__name__, error=str(exc)[:300])
        return []

    labels = sorted(response.get("Labels", []), key=lambda item: item.get("Confidence", 0), reverse=True)
    names = [item["Name"] for item in labels if item.get("Name")]
    if not names:
        obs.warn("rekognition_no_labels", key=key)
    return names


def _persist(item: dict) -> None:
    _dynamodb.Table(config.TABLE_NAME).put_item(Item=item)


def handler(event, context):
    obs.bind_request(context)
    started = time.time()

    try:
        body = parse_json_body(event)
        key = _validate_key(body.get("key", ""))
        meme_id = key.split("/")[-1].rsplit(".", 1)[0]

        with obs.stage("validate_upload"):
            meta = _head_upload(key)

        with obs.stage("rekognition"):
            labels = _detect_labels(key)
        obs.log("labels_detected", count=len(labels), labels=labels[:8])

        with obs.stage("caption"):
            top, bottom, source = captions.build_caption(labels, seed=meme_id)

        with obs.stage("render"):
            original = _s3.get_object(Bucket=config.UPLOAD_BUCKET, Key=key)["Body"].read()
            meme_bytes = memeimg.render_meme(original, top, bottom)

        output_key = f"memes/{meme_id}.jpg"
        with obs.stage("store"):
            _s3.put_object(
                Bucket=config.PROCESSED_BUCKET,
                Key=output_key,
                Body=meme_bytes,
                ContentType="image/jpeg",
                CacheControl="public, max-age=31536000, immutable",
            )

        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        image_url = f"{config.PUBLIC_BASE_URL}/{output_key}" if config.PUBLIC_BASE_URL else f"/{output_key}"
        caption_text = " / ".join(part for part in (top, bottom) if part)

        record = {
            "id": meme_id,
            "gsiBucket": "meme",  # single partition so the gallery can sort by time
            "imageUrl": image_url,
            "caption": caption_text,
            "topText": top,
            "bottomText": bottom,
            "labels": labels[:8],
            "captionSource": source,
            "createdAt": created_at,
        }
        with obs.stage("persist"):
            _persist(record)

        obs.log(
            "generate_complete",
            memeId=meme_id,
            captionSource=source,
            labelCount=len(labels),
            bytes=len(meme_bytes),
            totalMs=round((time.time() - started) * 1000),
        )

        return ok({
            "id": meme_id,
            "imageUrl": image_url,
            "caption": caption_text,
            "topText": top,
            "bottomText": bottom,
            "labels": labels[:8],
            "captionSource": source,
            "createdAt": created_at,
        })

    except ApiError as err:
        obs.warn("request_rejected", code=err.code, status=err.status, message=err.message)
        return fail(err)
    except Exception as exc:  # noqa: BLE001
        obs.error("unhandled_error", errorType=type(exc).__name__, error=str(exc)[:800])
        return fail(ApiError(500, "INTERNAL_ERROR", "Something went wrong brewing that meme. Please try again."))

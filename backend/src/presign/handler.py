"""POST /uploads — hand the browser a short-lived presigned PUT URL.

Uploading straight to S3 keeps large images off API Gateway (10 MB payload
limit) and keeps the generate Lambda fast.
"""
import uuid

import boto3
from botocore.config import Config as BotoConfig

from common import config, obs
from common.http import ApiError, fail, ok, parse_json_body

_s3 = boto3.client("s3", config=BotoConfig(signature_version="s3v4"))

_URL_TTL_SECONDS = 300


def handler(event, context):
    obs.bind_request(context)
    try:
        body = parse_json_body(event)

        content_type = str(body.get("contentType", "")).split(";")[0].strip().lower()
        if content_type not in config.ALLOWED_CONTENT_TYPES:
            raise ApiError(415, "UNSUPPORTED_TYPE", "Please upload a JPEG or PNG image.")

        # Advisory only — the real size check happens in generate via head_object.
        size = body.get("size")
        if isinstance(size, (int, float)) and size > config.MAX_UPLOAD_BYTES:
            raise ApiError(
                413, "FILE_TOO_LARGE",
                f"Please use an image under {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
            )

        meme_id = str(uuid.uuid4())
        key = f"uploads/{meme_id}.{config.CONTENT_TYPE_EXT[content_type]}"

        upload_url = _s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": config.UPLOAD_BUCKET, "Key": key, "ContentType": content_type},
            ExpiresIn=_URL_TTL_SECONDS,
        )

        obs.log("presign_issued", memeId=meme_id, contentType=content_type)
        return ok({"id": meme_id, "key": key, "uploadUrl": upload_url, "expiresIn": _URL_TTL_SECONDS})

    except ApiError as err:
        obs.warn("request_rejected", code=err.code, status=err.status)
        return fail(err)
    except Exception as exc:  # noqa: BLE001
        obs.error("unhandled_error", errorType=type(exc).__name__, error=str(exc)[:800])
        return fail(ApiError(500, "INTERNAL_ERROR", "Could not start that upload. Please try again."))

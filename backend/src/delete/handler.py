"""DELETE /memes/{id} — remove a meme, if you hold its delete token.

Deletes the DynamoDB record first and the S3 object second. If the S3 delete
fails the record is already gone, which leaves an orphaned object rather than a
gallery entry pointing at a missing image — the harmless direction to fail in.
"""
import re

import boto3

from common import config, obs, tokens
from common.http import ApiError, fail, ok

_s3 = boto3.client("s3")
_dynamodb = boto3.resource("dynamodb")

_ID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _meme_id(event: dict) -> str:
    raw = (event.get("pathParameters") or {}).get("id", "")
    if not isinstance(raw, str) or not _ID_PATTERN.match(raw):
        raise ApiError(400, "INVALID_ID", "That is not a valid meme reference.")
    return raw


def _token(event: dict) -> str:
    # Header names arrive lowercased on HTTP API payload format 2.0, but be
    # tolerant in case this handler is invoked directly.
    headers = {str(k).lower(): v for k, v in (event.get("headers") or {}).items()}
    token = headers.get("x-delete-token", "")
    if not token:
        raise ApiError(401, "MISSING_TOKEN", "You can only delete memes you created on this device.")
    return token


def handler(event, context):
    obs.bind_request(context)
    try:
        meme_id = _meme_id(event)
        token = _token(event)

        table = _dynamodb.Table(config.TABLE_NAME)
        item = table.get_item(Key={"id": meme_id}).get("Item")
        if not item:
            raise ApiError(404, "NOT_FOUND", "That meme no longer exists.")

        if not tokens.verify_token(token, item.get("deleteTokenHash", "")):
            obs.warn("delete_forbidden", memeId=meme_id)
            raise ApiError(403, "FORBIDDEN", "You can only delete memes you created on this device.")

        # Conditioned on the row still existing so two concurrent deletes
        # cannot both report success.
        try:
            table.delete_item(
                Key={"id": meme_id},
                ConditionExpression="attribute_exists(id)",
            )
        except _dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            raise ApiError(404, "NOT_FOUND", "That meme no longer exists.")

        try:
            _s3.delete_object(Bucket=config.PROCESSED_BUCKET, Key=f"memes/{meme_id}.jpg")
        except Exception as exc:  # noqa: BLE001 - record is already gone; log and move on
            obs.warn("delete_object_failed", memeId=meme_id, errorType=type(exc).__name__,
                     error=str(exc)[:300])

        obs.log("delete_complete", memeId=meme_id)
        return ok({"id": meme_id, "deleted": True})

    except ApiError as err:
        obs.warn("request_rejected", code=err.code, status=err.status)
        return fail(err)
    except Exception as exc:  # noqa: BLE001
        obs.error("unhandled_error", errorType=type(exc).__name__, error=str(exc)[:800])
        return fail(ApiError(500, "INTERNAL_ERROR", "Could not delete that meme. Please try again."))

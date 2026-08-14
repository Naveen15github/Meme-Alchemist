"""GET /gallery — most recent memes, newest first."""
import boto3
from boto3.dynamodb.conditions import Key

from common import config, obs
from common.http import ApiError, fail, ok

_dynamodb = boto3.resource("dynamodb")


def handler(event, context):
    obs.bind_request(context)
    try:
        params = event.get("queryStringParameters") or {}
        try:
            limit = int(params.get("limit", config.GALLERY_PAGE_SIZE))
        except (TypeError, ValueError):
            limit = config.GALLERY_PAGE_SIZE
        limit = max(1, min(limit, 60))

        table = _dynamodb.Table(config.TABLE_NAME)
        response = table.query(
            IndexName="byCreatedAt",
            KeyConditionExpression=Key("gsiBucket").eq("meme"),
            ScanIndexForward=False,  # newest first
            Limit=limit,
        )

        items = [
            {
                "id": item.get("id"),
                "imageUrl": item.get("imageUrl"),
                "caption": item.get("caption"),
                "labels": item.get("labels", []),
                "captionSource": item.get("captionSource"),
                "createdAt": item.get("createdAt"),
            }
            for item in response.get("Items", [])
        ]

        obs.log("gallery_listed", count=len(items))
        return ok({"items": items, "count": len(items)})

    except Exception as exc:  # noqa: BLE001 - an empty gallery beats a broken page
        obs.error("gallery_failed", errorType=type(exc).__name__, error=str(exc)[:500])
        return fail(ApiError(500, "INTERNAL_ERROR", "Could not load the gallery right now."))

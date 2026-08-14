"""HTTP helpers for API Gateway HTTP API (payload format 2.0)."""
import json

from . import obs

# CORS is also configured on the HTTP API itself; these headers make the
# Lambda responses correct even when invoked directly (e.g. smoke tests).
_CORS = {
    "access-control-allow-origin": "*",
    "access-control-allow-headers": "content-type",
    "access-control-allow-methods": "GET,POST,OPTIONS",
}


class ApiError(Exception):
    """An error that is safe to show the user verbatim."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def respond(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json", **_CORS},
        "body": json.dumps(body, default=str),
    }


def ok(body: dict) -> dict:
    return respond(200, body)


def fail(err: ApiError) -> dict:
    return respond(
        err.status,
        {"error": {"code": err.code, "message": err.message}, "requestId": obs.current_request_id()},
    )


def parse_json_body(event: dict) -> dict:
    """Parse a JSON request body, tolerating base64 encoding and empty bodies."""
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        import base64

        try:
            raw = base64.b64decode(raw).decode("utf-8")
        except Exception:
            raise ApiError(400, "INVALID_BODY", "Request body could not be decoded.")
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        raise ApiError(400, "INVALID_BODY", "Request body must be valid JSON.")
    if not isinstance(parsed, dict):
        raise ApiError(400, "INVALID_BODY", "Request body must be a JSON object.")
    return parsed

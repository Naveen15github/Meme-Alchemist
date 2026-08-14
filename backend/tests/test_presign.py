import json

from presign import handler as presign_handler


def _event(body: dict) -> dict:
    return {"body": json.dumps(body), "isBase64Encoded": False}


def _body(response) -> dict:
    return json.loads(response["body"])


def test_issues_a_presigned_url_for_jpeg(context):
    response = presign_handler.handler(_event({"contentType": "image/jpeg"}), context)
    assert response["statusCode"] == 200

    body = _body(response)
    assert body["key"].startswith("uploads/")
    assert body["key"].endswith(".jpg")
    assert body["uploadUrl"].startswith("https://")
    assert body["id"] in body["key"]


def test_png_gets_a_png_extension(context):
    body = _body(presign_handler.handler(_event({"contentType": "image/png"}), context))
    assert body["key"].endswith(".png")


def test_rejects_unsupported_content_type(context):
    response = presign_handler.handler(_event({"contentType": "image/gif"}), context)
    assert response["statusCode"] == 415
    assert _body(response)["error"]["code"] == "UNSUPPORTED_TYPE"


def test_rejects_missing_content_type(context):
    assert presign_handler.handler(_event({}), context)["statusCode"] == 415


def test_rejects_oversized_declared_size(context):
    response = presign_handler.handler(
        _event({"contentType": "image/jpeg", "size": 20 * 1024 * 1024}), context
    )
    assert response["statusCode"] == 413
    assert _body(response)["error"]["code"] == "FILE_TOO_LARGE"


def test_rejects_malformed_json(context):
    response = presign_handler.handler({"body": "{not json", "isBase64Encoded": False}, context)
    assert response["statusCode"] == 400


def test_tolerates_content_type_with_parameters(context):
    response = presign_handler.handler(_event({"contentType": "image/jpeg; charset=binary"}), context)
    assert response["statusCode"] == 200


def test_ids_are_unique(context):
    ids = {
        _body(presign_handler.handler(_event({"contentType": "image/jpeg"}), context))["id"]
        for _ in range(5)
    }
    assert len(ids) == 5


def test_cors_headers_present(context):
    response = presign_handler.handler(_event({"contentType": "image/jpeg"}), context)
    assert response["headers"]["access-control-allow-origin"] == "*"

"""End-to-end handler tests against moto, including the fallback path."""
import io
import json
import uuid

import pytest
from PIL import Image

from conftest import PROCESSED_BUCKET, UPLOAD_BUCKET, FakeRekognition, make_image_bytes
from generate import captions
from generate import handler as generate_handler


@pytest.fixture(autouse=True)
def offline_bedrock(monkeypatch):
    """Default every test to the fallback path; tests that care override it.

    This mirrors reality on a throttled account and keeps tests hermetic.
    """
    monkeypatch.setattr(
        captions, "_invoke_bedrock",
        lambda labels: (_ for _ in ()).throw(Exception("ThrottlingException: Too many tokens per day")),
    )


@pytest.fixture(autouse=True)
def fake_rekognition(monkeypatch):
    monkeypatch.setattr(generate_handler, "_rekognition", FakeRekognition())


def _event(key) -> dict:
    return {"body": json.dumps({"key": key}), "isBase64Encoded": False}


def _body(response) -> dict:
    return json.loads(response["body"])


def _new_key(ext: str = "jpg") -> str:
    return f"uploads/{uuid.uuid4()}.{ext}"


class TestHappyPath:
    def test_returns_a_meme(self, context, upload_image, s3):
        key = upload_image(_new_key())
        response = generate_handler.handler(_event(key), context)
        assert response["statusCode"] == 200

        body = _body(response)
        assert body["id"] == key.split("/")[1].rsplit(".", 1)[0]
        assert body["imageUrl"] == f"https://cdn.example.test/memes/{body['id']}.jpg"
        assert body["caption"]
        assert body["labels"] == ["Dog", "Pet", "Animal"]

    def test_writes_a_real_jpeg_to_the_processed_bucket(self, context, upload_image, s3):
        key = upload_image(_new_key())
        body = _body(generate_handler.handler(_event(key), context))

        stored = s3.get_object(Bucket=PROCESSED_BUCKET, Key=f"memes/{body['id']}.jpg")
        assert stored["ContentType"] == "image/jpeg"
        assert Image.open(io.BytesIO(stored["Body"].read())).format == "JPEG"

    def test_records_the_meme_in_dynamodb(self, context, upload_image, ddb):
        from conftest import TABLE_NAME

        key = upload_image(_new_key())
        body = _body(generate_handler.handler(_event(key), context))

        item = ddb.Table(TABLE_NAME).get_item(Key={"id": body["id"]})["Item"]
        assert item["caption"] == body["caption"]
        assert item["gsiBucket"] == "meme"
        assert item["captionSource"] == "fallback"
        assert item["createdAt"].endswith("Z")

    def test_png_upload_produces_a_jpeg_meme(self, context, upload_image, s3):
        key = upload_image(_new_key("png"), content_type="image/png", body=make_image_bytes(fmt="PNG"))
        body = _body(generate_handler.handler(_event(key), context))
        assert body["imageUrl"].endswith(".jpg")

    def test_uses_bedrock_caption_when_available(self, context, upload_image, monkeypatch):
        monkeypatch.setattr(captions, "_invoke_bedrock", lambda labels: ("MODEL", "WROTE THIS"))
        body = _body(generate_handler.handler(_event(upload_image(_new_key())), context))
        assert body["captionSource"] == "bedrock"
        assert body["caption"] == "MODEL / WROTE THIS"


class TestFallbackResilience:
    """The demo must survive every one of these without showing an error."""

    def test_bedrock_throttled_still_returns_a_meme(self, context, upload_image):
        response = generate_handler.handler(_event(upload_image(_new_key())), context)
        assert response["statusCode"] == 200

        body = _body(response)
        assert body["captionSource"] == "fallback"
        assert (body["topText"], body["bottomText"]) in captions._THEMES["dog"]["captions"]

    def test_rekognition_failure_still_returns_a_meme(self, context, upload_image, monkeypatch):
        monkeypatch.setattr(
            generate_handler, "_rekognition",
            FakeRekognition(raises=Exception("InternalServerError")),
        )
        response = generate_handler.handler(_event(upload_image(_new_key())), context)

        assert response["statusCode"] == 200
        body = _body(response)
        assert body["labels"] == []
        assert (body["topText"], body["bottomText"]) in captions._MYSTERY_CAPTIONS

    def test_no_labels_still_returns_a_meme(self, context, upload_image, monkeypatch):
        monkeypatch.setattr(generate_handler, "_rekognition", FakeRekognition(labels=[]))
        response = generate_handler.handler(_event(upload_image(_new_key())), context)

        assert response["statusCode"] == 200
        assert (_body(response)["topText"], _body(response)["bottomText"]) in captions._MYSTERY_CAPTIONS

    def test_unknown_labels_still_returns_a_meme(self, context, upload_image, monkeypatch):
        monkeypatch.setattr(generate_handler, "_rekognition", FakeRekognition(labels=["Astrolabe"]))
        response = generate_handler.handler(_event(upload_image(_new_key())), context)

        assert response["statusCode"] == 200
        assert _body(response)["caption"]

    def test_both_rekognition_and_bedrock_down(self, context, upload_image, monkeypatch):
        """Total upstream failure - the user still gets a downloadable meme."""
        monkeypatch.setattr(generate_handler, "_rekognition", FakeRekognition(raises=Exception("down")))
        response = generate_handler.handler(_event(upload_image(_new_key())), context)
        assert response["statusCode"] == 200
        assert _body(response)["imageUrl"]


class TestValidation:
    @pytest.mark.parametrize("key", [
        "",
        "not-a-key",
        "uploads/../../etc/passwd",
        "uploads/whatever.jpg",
        "other/11111111-2222-3333-4444-555555555555.jpg",
        "uploads/11111111-2222-3333-4444-555555555555.exe",
        "uploads/11111111-2222-3333-4444-555555555555.jpg/../x",
    ])
    def test_rejects_malformed_keys(self, context, key):
        response = generate_handler.handler(_event(key), context)
        assert response["statusCode"] == 400
        assert _body(response)["error"]["code"] == "INVALID_KEY"

    def test_rejects_missing_upload(self, context):
        response = generate_handler.handler(_event(_new_key()), context)
        assert response["statusCode"] == 404
        assert _body(response)["error"]["code"] == "UPLOAD_NOT_FOUND"

    def test_rejects_oversized_file(self, context, upload_image):
        oversized = b"\xff\xd8\xff" + b"0" * (9 * 1024 * 1024)
        key = upload_image(_new_key(), body=oversized)
        response = generate_handler.handler(_event(key), context)

        assert response["statusCode"] == 413
        assert _body(response)["error"]["code"] == "FILE_TOO_LARGE"

    def test_rejects_wrong_content_type(self, context, upload_image):
        key = upload_image(_new_key(), content_type="application/pdf")
        response = generate_handler.handler(_event(key), context)

        assert response["statusCode"] == 415
        assert _body(response)["error"]["code"] == "UNSUPPORTED_TYPE"

    def test_rejects_empty_file(self, context, upload_image):
        key = upload_image(_new_key(), body=b"")
        assert generate_handler.handler(_event(key), context)["statusCode"] == 400

    def test_rejects_malformed_body(self, context):
        response = generate_handler.handler({"body": "{oops", "isBase64Encoded": False}, context)
        assert response["statusCode"] == 400

    def test_corrupt_image_returns_a_clean_error_not_a_crash(self, context, upload_image):
        key = upload_image(_new_key(), body=b"this is definitely not an image")
        response = generate_handler.handler(_event(key), context)

        assert response["statusCode"] == 500
        assert _body(response)["error"]["code"] == "INTERNAL_ERROR"
        assert "requestId" in _body(response)

"""Delete is the only destructive endpoint, so its authorisation gets scrutiny."""
import json
import uuid

import pytest

from common import tokens
from conftest import PROCESSED_BUCKET, TABLE_NAME
from delete import handler as delete_handler


def _event(meme_id, token=None, header_name="x-delete-token"):
    event = {"pathParameters": {"id": meme_id}}
    if token is not None:
        event["headers"] = {header_name: token}
    return event


def _body(response):
    return json.loads(response["body"])


@pytest.fixture
def stored_meme(s3, ddb):
    """Create a meme record plus its S3 object, returning (id, plaintext token)."""
    def _make():
        meme_id = str(uuid.uuid4())
        token = tokens.new_token()
        s3.put_object(Bucket=PROCESSED_BUCKET, Key=f"memes/{meme_id}.jpg",
                      Body=b"\xff\xd8\xffnot-a-real-jpeg", ContentType="image/jpeg")
        ddb.Table(TABLE_NAME).put_item(Item={
            "id": meme_id,
            "gsiBucket": "meme",
            "imageUrl": f"https://cdn.example.test/memes/{meme_id}.jpg",
            "caption": "A / B",
            "labels": ["Dog"],
            "captionSource": "fallback",
            "createdAt": "2026-08-15T00:00:00Z",
            "deleteTokenHash": tokens.hash_token(token),
        })
        return meme_id, token

    return _make


class TestTokens:
    def test_tokens_are_unique_and_long(self):
        minted = {tokens.new_token() for _ in range(200)}
        assert len(minted) == 200
        assert all(len(t) >= 32 for t in minted)

    def test_hash_is_stable_and_not_the_token(self):
        token = tokens.new_token()
        assert tokens.hash_token(token) == tokens.hash_token(token)
        assert tokens.hash_token(token) != token

    def test_verify_accepts_only_the_right_token(self):
        token = tokens.new_token()
        digest = tokens.hash_token(token)

        assert tokens.verify_token(token, digest) is True
        assert tokens.verify_token(tokens.new_token(), digest) is False
        assert tokens.verify_token("", digest) is False
        assert tokens.verify_token(token, "") is False


class TestAuthorisation:
    def test_deletes_with_the_correct_token(self, context, stored_meme, s3, ddb):
        meme_id, token = stored_meme()

        response = delete_handler.handler(_event(meme_id, token), context)
        assert response["statusCode"] == 200
        assert _body(response)["deleted"] is True

        assert "Item" not in ddb.Table(TABLE_NAME).get_item(Key={"id": meme_id})
        with pytest.raises(s3.exceptions.NoSuchKey):
            s3.get_object(Bucket=PROCESSED_BUCKET, Key=f"memes/{meme_id}.jpg")

    def test_rejects_a_wrong_token(self, context, stored_meme, ddb):
        meme_id, _ = stored_meme()

        response = delete_handler.handler(_event(meme_id, tokens.new_token()), context)
        assert response["statusCode"] == 403
        assert _body(response)["error"]["code"] == "FORBIDDEN"
        # The meme must survive a failed attempt.
        assert "Item" in ddb.Table(TABLE_NAME).get_item(Key={"id": meme_id})

    def test_rejects_a_missing_token(self, context, stored_meme, ddb):
        meme_id, _ = stored_meme()

        response = delete_handler.handler(_event(meme_id), context)
        assert response["statusCode"] == 401
        assert "Item" in ddb.Table(TABLE_NAME).get_item(Key={"id": meme_id})

    def test_rejects_an_empty_token(self, context, stored_meme):
        meme_id, _ = stored_meme()
        assert delete_handler.handler(_event(meme_id, ""), context)["statusCode"] == 401

    def test_accepts_uppercase_header_name(self, context, stored_meme):
        """Direct invocations may not lowercase headers the way HTTP API does."""
        meme_id, token = stored_meme()
        response = delete_handler.handler(_event(meme_id, token, "X-Delete-Token"), context)
        assert response["statusCode"] == 200

    def test_one_memes_token_cannot_delete_another(self, context, stored_meme, ddb):
        first_id, first_token = stored_meme()
        second_id, _ = stored_meme()

        response = delete_handler.handler(_event(second_id, first_token), context)
        assert response["statusCode"] == 403
        assert "Item" in ddb.Table(TABLE_NAME).get_item(Key={"id": second_id})


class TestValidation:
    @pytest.mark.parametrize("meme_id", [
        "", "not-a-uuid", "../../etc/passwd", "memes/x.jpg",
        "11111111-2222-3333-4444-55555555555",  # too short
        "ZZZZZZZZ-2222-3333-4444-555555555555",  # non-hex
    ])
    def test_rejects_malformed_ids(self, context, meme_id):
        response = delete_handler.handler(_event(meme_id, "token"), context)
        assert response["statusCode"] == 400
        assert _body(response)["error"]["code"] == "INVALID_ID"

    def test_missing_path_parameters(self, context):
        assert delete_handler.handler({"headers": {"x-delete-token": "t"}}, context)["statusCode"] == 400

    def test_unknown_meme_is_404(self, context):
        response = delete_handler.handler(_event(str(uuid.uuid4()), "token"), context)
        assert response["statusCode"] == 404

    def test_deleting_twice_is_404_the_second_time(self, context, stored_meme):
        meme_id, token = stored_meme()

        assert delete_handler.handler(_event(meme_id, token), context)["statusCode"] == 200
        assert delete_handler.handler(_event(meme_id, token), context)["statusCode"] == 404


class TestGeneratedMemesAreDeletable:
    def test_generate_returns_a_token_that_actually_works(self, context, upload_image, monkeypatch):
        """The end-to-end contract: create a meme, then delete it with what you got."""
        from generate import captions
        from generate import handler as generate_handler
        from conftest import FakeRekognition

        monkeypatch.setattr(generate_handler, "_rekognition", FakeRekognition())
        monkeypatch.setattr(captions, "_invoke_bedrock", lambda labels: ("A", "B"))

        key = f"uploads/{uuid.uuid4()}.jpg"
        upload_image(key)
        created = json.loads(generate_handler.handler(
            {"body": json.dumps({"key": key}), "isBase64Encoded": False}, context)["body"])

        assert created["deleteToken"]

        response = delete_handler.handler(_event(created["id"], created["deleteToken"]), context)
        assert response["statusCode"] == 200

    def test_gallery_never_exposes_the_token_hash(self, context, stored_meme):
        from gallery import handler as gallery_handler

        stored_meme()
        items = json.loads(gallery_handler.handler({}, context)["body"])["items"]

        assert items, "expected at least one meme"
        for item in items:
            assert "deleteTokenHash" not in item
            assert "deleteToken" not in item

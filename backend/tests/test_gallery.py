import json

import pytest

from conftest import TABLE_NAME
from gallery import handler as gallery_handler


@pytest.fixture
def seed_memes(ddb):
    table = ddb.Table(TABLE_NAME)
    for index in range(5):
        table.put_item(Item={
            "id": f"gallery-test-{index}",
            "gsiBucket": "meme",
            "imageUrl": f"https://cdn.example.test/memes/gallery-test-{index}.jpg",
            "caption": f"CAPTION {index}",
            "labels": ["Dog"],
            "captionSource": "fallback",
            "createdAt": f"2026-08-1{index}T00:00:00Z",
        })
    return table


def _body(response) -> dict:
    return json.loads(response["body"])


def test_returns_items_newest_first(context, seed_memes):
    response = gallery_handler.handler({"queryStringParameters": None}, context)
    assert response["statusCode"] == 200

    items = _body(response)["items"]
    created = [item["createdAt"] for item in items]
    assert created == sorted(created, reverse=True)


def test_returns_expected_shape(context, seed_memes):
    item = _body(gallery_handler.handler({"queryStringParameters": None}, context))["items"][0]
    assert set(item) == {"id", "imageUrl", "caption", "labels", "captionSource", "createdAt"}


def test_respects_limit(context, seed_memes):
    response = gallery_handler.handler({"queryStringParameters": {"limit": "2"}}, context)
    assert len(_body(response)["items"]) == 2


def test_caps_absurd_limits(context, seed_memes):
    response = gallery_handler.handler({"queryStringParameters": {"limit": "99999"}}, context)
    assert response["statusCode"] == 200


def test_ignores_non_numeric_limit(context, seed_memes):
    response = gallery_handler.handler({"queryStringParameters": {"limit": "abc"}}, context)
    assert response["statusCode"] == 200


def test_missing_event_keys_do_not_crash(context, seed_memes):
    assert gallery_handler.handler({}, context)["statusCode"] == 200


def test_failure_returns_clean_error(context, monkeypatch):
    class Broken:
        def Table(self, _name):
            raise Exception("DynamoDB unavailable")

    monkeypatch.setattr(gallery_handler, "_dynamodb", Broken())
    response = gallery_handler.handler({}, context)

    assert response["statusCode"] == 500
    assert _body(response)["error"]["code"] == "INTERNAL_ERROR"

"""Test bootstrap.

Environment and the moto mock are started at *import* time, before any test
module is collected, because the handlers build their boto3 clients at module
scope. Starting the mock inside a fixture would be too late.
"""
import io
import os

import boto3
import pytest

UPLOAD_BUCKET = "test-uploads"
PROCESSED_BUCKET = "test-memes"
TABLE_NAME = "test-memes-table"
REGION = "us-east-1"

os.environ.update({
    "AWS_DEFAULT_REGION": REGION,
    "AWS_REGION": REGION,
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_SECURITY_TOKEN": "testing",
    "AWS_SESSION_TOKEN": "testing",
    "UPLOAD_BUCKET": UPLOAD_BUCKET,
    "PROCESSED_BUCKET": PROCESSED_BUCKET,
    "TABLE_NAME": TABLE_NAME,
    "PUBLIC_BASE_URL": "https://cdn.example.test",
    "MAX_UPLOAD_BYTES": str(8 * 1024 * 1024),
    "BEDROCK_MAX_ATTEMPTS": "2",
    "BEDROCK_BASE_BACKOFF_SECONDS": "0",  # keep the retry tests fast
})

from moto import mock_aws  # noqa: E402

_mock = mock_aws()
_mock.start()


def _create_infra() -> None:
    s3 = boto3.client("s3", region_name=REGION)
    for bucket in (UPLOAD_BUCKET, PROCESSED_BUCKET):
        try:
            s3.create_bucket(Bucket=bucket)
        except s3.exceptions.BucketAlreadyOwnedByYou:
            pass

    ddb = boto3.client("dynamodb", region_name=REGION)
    existing = ddb.list_tables().get("TableNames", [])
    if TABLE_NAME not in existing:
        ddb.create_table(
            TableName=TABLE_NAME,
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "id", "AttributeType": "S"},
                {"AttributeName": "gsiBucket", "AttributeType": "S"},
                {"AttributeName": "createdAt", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[{
                "IndexName": "byCreatedAt",
                "KeySchema": [
                    {"AttributeName": "gsiBucket", "KeyType": "HASH"},
                    {"AttributeName": "createdAt", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }],
        )


_create_infra()


class FakeContext:
    aws_request_id = "test-request-id"
    function_name = "test"
    memory_limit_in_mb = 512


@pytest.fixture
def context():
    return FakeContext()


@pytest.fixture
def s3():
    return boto3.client("s3", region_name=REGION)


@pytest.fixture
def ddb():
    return boto3.resource("dynamodb", region_name=REGION)


def make_image_bytes(size: tuple[int, int] = (640, 480), fmt: str = "JPEG") -> bytes:
    """A small real image, so Pillow is exercised for real rather than mocked."""
    from PIL import Image

    img = Image.new("RGB", size, (40, 90, 160))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


@pytest.fixture
def upload_image(s3):
    """Put a real image in the uploads bucket and return its key."""
    def _put(key: str = "uploads/11111111-2222-3333-4444-555555555555.jpg",
             content_type: str = "image/jpeg",
             body: bytes | None = None):
        s3.put_object(
            Bucket=UPLOAD_BUCKET,
            Key=key,
            Body=body if body is not None else make_image_bytes(),
            ContentType=content_type,
        )
        return key

    return _put


class FakeRekognition:
    """Stand-in for the Rekognition client; moto's coverage of DetectLabels
    does not let us control the returned labels, and the labels are what the
    caption logic branches on."""

    def __init__(self, labels=None, raises=None):
        self._labels = labels if labels is not None else ["Dog", "Pet", "Animal"]
        self._raises = raises

    def detect_labels(self, **kwargs):
        if self._raises:
            raise self._raises
        return {
            "Labels": [
                {"Name": name, "Confidence": 99.0 - index}
                for index, name in enumerate(self._labels)
            ]
        }

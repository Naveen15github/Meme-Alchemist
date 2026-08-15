# API Reference

Base URL comes from the Terraform output `api_base_url`:

```bash
cd infra && terraform output -raw api_base_url
# https://<api-id>.execute-api.us-east-1.amazonaws.com
```

The API is public and unauthenticated. CORS allows any origin. The stage is
throttled to **10 requests/second with a burst of 20**.

All responses are `application/json`. Errors share one shape:

```json
{
  "error": { "code": "FILE_TOO_LARGE", "message": "Please use an image under 8 MB." },
  "requestId": "8f2c1e5a-..."
}
```

`message` is always safe to show a user verbatim. `requestId` matches the
`requestId` field in CloudWatch Logs.

---

## The flow

Three calls, in order:

```
POST /uploads       ──▶  presigned S3 URL
PUT  <that URL>     ──▶  bytes go straight to S3 (not through the API)
POST /generate      ──▶  the finished meme + a one-time delete token
DELETE /memes/{id}  ──▶  remove a meme, if you hold its token
```

---

## `POST /uploads`

Asks for a presigned URL to upload one image. Nothing is created until the
browser actually PUTs to the returned URL.

**Request**

```json
{ "contentType": "image/jpeg", "size": 482913 }
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `contentType` | string | yes | `image/jpeg` or `image/png` only |
| `size` | number | no | Bytes. Advisory — lets an oversized file fail before uploading |

**Response `200`**

```json
{
  "id": "3f8a1c22-9d41-4b7e-9f0a-2c5e1b7d8a44",
  "key": "uploads/3f8a1c22-9d41-4b7e-9f0a-2c5e1b7d8a44.jpg",
  "uploadUrl": "https://meme-alchemist-uploads-ab12cd34.s3.amazonaws.com/...",
  "expiresIn": 300
}
```

The URL is valid for **5 minutes**. `id` becomes the meme's id.

**Errors**

| Status | Code | When |
|---|---|---|
| 400 | `INVALID_BODY` | Body is not a JSON object |
| 413 | `FILE_TOO_LARGE` | `size` exceeds 8 MB |
| 415 | `UNSUPPORTED_TYPE` | `contentType` is not JPEG or PNG |

---

## `PUT <uploadUrl>`

Upload the raw bytes to S3. **The `content-type` header must exactly match the
`contentType` sent to `/uploads`** — it is part of the signature.

```bash
curl -X PUT "$UPLOAD_URL" \
     -H 'content-type: image/jpeg' \
     --data-binary @photo.jpg
```

Returns `200` with an empty body. A `403` usually means the URL expired or the
content type did not match.

---

## `POST /generate`

Runs the pipeline: Rekognition → Bedrock (or fallback) → Pillow → S3 → DynamoDB.
Typically completes in **2–5 seconds**.

**Request**

```json
{ "key": "uploads/3f8a1c22-9d41-4b7e-9f0a-2c5e1b7d8a44.jpg" }
```

`key` must be exactly the value returned by `/uploads`; it is validated against
`^uploads/<uuid4>\.(jpg|png)$`.

**Response `200`**

```json
{
  "id": "3f8a1c22-9d41-4b7e-9f0a-2c5e1b7d8a44",
  "imageUrl": "https://d1234abcd.cloudfront.net/memes/3f8a1c22-....jpg",
  "caption": "I KNOCKED IT OVER / AND I FEEL NOTHING",
  "topText": "I KNOCKED IT OVER",
  "bottomText": "AND I FEEL NOTHING",
  "labels": ["Cat", "Pet", "Animal", "Mammal"],
  "captionSource": "bedrock",
  "createdAt": "2026-08-14T09:31:07Z"
}
```

| Field | Notes |
|---|---|
| `imageUrl` | Public CloudFront URL, cached immutably |
| `labels` | Up to 8 Rekognition labels, highest confidence first. May be `[]` |
| `captionSource` | `"bedrock"` if the model wrote it, `"fallback"` if the local library did |
| `deleteToken` | Returned **once**, never again. Store it to enable `DELETE /memes/{id}` |

### `captionSource` and the reliability guarantee

`POST /generate` returns **200 with a usable meme** even when Bedrock is
throttled, denied or slow, and even when Rekognition returns nothing. Those
degrade to `captionSource: "fallback"`; they are never surfaced as errors,
because a working meme beats an error screen. The UI shows a small note when a
caption came from the fallback library.

The only 5xx is a genuine internal failure — for example, bytes that are not a
decodable image.

**Errors**

| Status | Code | When |
|---|---|---|
| 400 | `INVALID_KEY` | `key` does not match the expected pattern |
| 400 | `EMPTY_FILE` | The uploaded object is zero bytes |
| 404 | `UPLOAD_NOT_FOUND` | No object at that key (URL expired, or PUT never happened) |
| 413 | `FILE_TOO_LARGE` | Object exceeds 8 MB |
| 415 | `UNSUPPORTED_TYPE` | Stored `Content-Type` is not JPEG or PNG |
| 500 | `INTERNAL_ERROR` | Undecodable image, or an unexpected failure |

---

## `DELETE /memes/{id}`

Deletes a meme — the DynamoDB record and the S3 object — if you hold its
delete token.

### Why a token

The API has no accounts, so "may this caller delete this meme?" cannot be
answered by identity. Instead, `POST /generate` mints a random 192-bit token
and returns it **once**. Only its SHA-256 hash is stored, so the database never
contains anything that grants deletion, and `GET /gallery` never exposes it.

This is capability-based authorisation: whoever holds the token may delete,
which in practice means *the browser that created the meme*. Without it, any
visitor could empty the gallery.

**Request**

```
DELETE /memes/3f8a1c22-9d41-4b7e-9f0a-2c5e1b7d8a44
x-delete-token: EEWSEh01yJNV...
```

**Response `200`**

```json
{ "id": "3f8a1c22-9d41-4b7e-9f0a-2c5e1b7d8a44", "deleted": true }
```

**Errors**

| Status | Code | When |
|---|---|---|
| 400 | `INVALID_ID` | `id` is not a UUID |
| 401 | `MISSING_TOKEN` | No `x-delete-token` header |
| 403 | `FORBIDDEN` | Token does not match this meme |
| 404 | `NOT_FOUND` | Already deleted, or never existed |

Deletion order is record-then-object: if the S3 delete fails, the gallery entry
is already gone, leaving an orphaned object rather than a tile pointing at a
missing image. The failure is logged as `delete_object_failed`.

Note that CloudFront may serve a deleted image from cache until its TTL expires.
Nothing links to it once the record is gone.

### Memes without a token

Memes created before this endpoint existed — or on another device — have no
stored hash and therefore cannot be deleted through the API by anyone. Use
`./scripts/admin-memes.sh`, which acts with your AWS credentials directly:

```bash
./scripts/admin-memes.sh list                # show every meme and whether it is deletable
./scripts/admin-memes.sh delete <id> [<id>…] # delete specific memes
./scripts/admin-memes.sh delete-untokened    # delete every meme with no token
./scripts/admin-memes.sh delete-all          # empty the gallery
```

---

## `GET /gallery`

Most recent memes, newest first.

**Query parameters**

| Name | Default | Notes |
|---|---|---|
| `limit` | 24 | Clamped to 1–60. Non-numeric values fall back to the default |

**Response `200`**

```json
{
  "items": [
    {
      "id": "3f8a1c22-...",
      "imageUrl": "https://d1234abcd.cloudfront.net/memes/3f8a1c22-....jpg",
      "caption": "I KNOCKED IT OVER / AND I FEEL NOTHING",
      "labels": ["Cat", "Pet"],
      "captionSource": "bedrock",
      "createdAt": "2026-08-14T09:31:07Z"
    }
  ],
  "count": 1
}
```

---

## Worked example

```bash
API="$(cd infra && terraform output -raw api_base_url)"

PRESIGN=$(curl -sS -X POST "$API/uploads" \
  -H 'content-type: application/json' \
  -d '{"contentType":"image/jpeg","size":482913}')

UPLOAD_URL=$(echo "$PRESIGN" | python -c 'import json,sys;print(json.load(sys.stdin)["uploadUrl"])')
KEY=$(echo "$PRESIGN" | python -c 'import json,sys;print(json.load(sys.stdin)["key"])')

curl -sS -X PUT "$UPLOAD_URL" -H 'content-type: image/jpeg' --data-binary @photo.jpg

curl -sS -X POST "$API/generate" \
  -H 'content-type: application/json' \
  -d "{\"key\":\"$KEY\"}"
```

`scripts/e2e-test.sh` does exactly this and additionally verifies the returned
image is a real JPEG served through CloudFront.

---

## Observability

Every Lambda emits structured JSON with the request id on each line. Useful
CloudWatch Logs Insights queries:

```
fields @timestamp, reason, labels, theme
| filter event = "fallback_used"
| sort @timestamp desc
```

```
fields @timestamp, stage, ms
| filter event = "stage_ok"
| stats avg(ms), max(ms) by stage
```

Key events: `presign_issued`, `labels_detected`, `bedrock_ok`,
`bedrock_attempt_failed`, `fallback_used`, `rekognition_failed`,
`generate_complete`, `stage_ok`, `stage_failed`, `request_rejected`.

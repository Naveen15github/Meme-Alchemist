#!/usr/bin/env bash
# Drives the deployed API exactly as the browser does: presign, PUT the bytes,
# generate, then verify the meme is fetchable through CloudFront and is a real
# JPEG. This is the check that proves the live app works.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; BLUE=$'\033[0;34m'; NC=$'\033[0m'

# --- Cross-platform helpers -------------------------------------------------
# Under Git Bash the AWS CLI and python are native Windows binaries and cannot
# read POSIX paths, so translate any path handed to them.
winpath() {
  if command -v cygpath >/dev/null 2>&1; then cygpath -w "$1"; else printf '%s' "$1"; fi
}

# Prefer the backend virtualenv: it is the interpreter we know has Pillow.
if [ -x "$ROOT/backend/.venv/Scripts/python.exe" ]; then
  PY="$ROOT/backend/.venv/Scripts/python.exe"
elif [ -x "$ROOT/backend/.venv/bin/python" ]; then
  PY="$ROOT/backend/.venv/bin/python"
else
  PY="python"
fi

cd "$ROOT/infra"
API_URL="$(terraform output -raw api_base_url)"
APP_URL="$(terraform output -raw app_url)"

# Keep scratch files inside the repo so native tools can reach them.
WORK="$ROOT/.e2e-tmp"
rm -rf "$WORK"; mkdir -p "$WORK"
trap 'rm -rf "$WORK"' EXIT

IMAGE="$WORK/test.jpg"

echo ""
echo "${BLUE}End-to-end test against $API_URL${NC}"
echo "──────────────────────────────────────────"

# --- 1. A photo-like JPEG so Rekognition has something to label -------------
"$PY" - "$(winpath "$IMAGE")" <<'PY'
import sys
from PIL import Image, ImageDraw

img = Image.new("RGB", (900, 675), (118, 168, 96))
draw = ImageDraw.Draw(img)
draw.ellipse([250, 150, 650, 520], fill=(232, 196, 140))   # a blobby subject
draw.ellipse([330, 250, 390, 310], fill=(30, 30, 30))      # eyes
draw.ellipse([510, 250, 570, 310], fill=(30, 30, 30))
draw.rectangle([0, 560, 900, 675], fill=(92, 134, 74))     # ground
img.save(sys.argv[1], "JPEG", quality=90)
PY

SIZE="$(wc -c < "$IMAGE" | tr -d ' ')"
echo "  1. built a test image ($SIZE bytes)"

# --- 2. Presign -------------------------------------------------------------
presign="$(curl -sS -X POST "$API_URL/uploads" \
  -H 'content-type: application/json' \
  -d "{\"contentType\":\"image/jpeg\",\"size\":$SIZE}")"

printf '%s' "$presign" > "$WORK/presign.json"
upload_url="$("$PY" -c "import json,sys;print(json.load(open(sys.argv[1]))['uploadUrl'])" "$(winpath "$WORK/presign.json")")"
key="$("$PY" -c "import json,sys;print(json.load(open(sys.argv[1]))['key'])" "$(winpath "$WORK/presign.json")")"
echo "  2. presigned  -> $key"

# --- 3. Upload straight to S3 ----------------------------------------------
put_status="$(curl -sS -o /dev/null -w '%{http_code}' -X PUT "$upload_url" \
  -H 'content-type: image/jpeg' --data-binary "@$IMAGE")"
[ "$put_status" = "200" ] || { echo "${RED}  PUT to S3 failed: HTTP $put_status${NC}"; exit 1; }
echo "  3. uploaded   -> 200"

# --- 4. Generate the meme ---------------------------------------------------
curl -sS -X POST "$API_URL/generate" \
  -H 'content-type: application/json' \
  -d "{\"key\":\"$key\"}" > "$WORK/result.json"

"$PY" - "$(winpath "$WORK/result.json")" <<'PY'
import json, sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
if "error" in data:
    print("  generate returned an error:", data["error"])
    sys.exit(1)

for field in ("id", "imageUrl", "caption"):
    assert data.get(field), "missing field: " + field

labels = ", ".join(data.get("labels", [])[:5]) or "(none)"
print("  4. generated  -> {} caption".format(data.get("captionSource")))
print("     labels:  " + labels)
print("     caption: " + data["caption"].replace("\n", " "))
PY

image_url="$("$PY" -c "import json,sys;print(json.load(open(sys.argv[1]))['imageUrl'])" "$(winpath "$WORK/result.json")")"
meme_id="$("$PY" -c "import json,sys;print(json.load(open(sys.argv[1]))['id'])" "$(winpath "$WORK/result.json")")"

# --- 5. Fetch it back through CloudFront ------------------------------------
# A brand-new distribution can 403 briefly while OAC settles.
echo "  5. fetching   -> $image_url"
code=""
for attempt in 1 2 3 4 5 6 7 8; do
  code="$(curl -sS -o "$WORK/out.jpg" -w '%{http_code}' "$image_url" || true)"
  [ "$code" = "200" ] && break
  echo "     attempt $attempt: HTTP $code, retrying in 10s…"
  sleep 10
done
[ "$code" = "200" ] || { echo "${RED}  could not fetch the meme: HTTP $code${NC}"; exit 1; }

"$PY" - "$(winpath "$WORK/out.jpg")" <<'PY'
import sys
from PIL import Image

with Image.open(sys.argv[1]) as img:
    assert img.format == "JPEG", "expected JPEG, got %s" % img.format
    print("     verified JPEG %dx%d" % img.size)
PY

# --- 6. It should now appear in the gallery ---------------------------------
gallery="$(curl -sS "$API_URL/gallery?limit=60")"
if [[ "$gallery" == *"$meme_id"* ]]; then
  echo "  6. gallery    -> meme is listed"
else
  echo "  6. gallery    -> not listed yet (eventual consistency)"
fi

echo "──────────────────────────────────────────"
echo "${GREEN}End-to-end test passed.${NC}"
echo "Open the app: $APP_URL"
echo ""

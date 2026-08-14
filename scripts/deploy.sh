#!/usr/bin/env bash
# Full deploy: infrastructure, backend, frontend, then a live smoke test.
#
# Designed to succeed in one pass and to be safely re-runnable.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REGION="${AWS_REGION:-us-east-1}"
SKIP_PREFLIGHT="${SKIP_PREFLIGHT:-0}"

GREEN=$'\033[0;32m'; BLUE=$'\033[0;34m'; RED=$'\033[0;31m'; NC=$'\033[0m'
step() { echo ""; echo "${BLUE}==> $1${NC}"; }

# --- 1. Preflight -----------------------------------------------------------
if [ "$SKIP_PREFLIGHT" != "1" ]; then
  step "Preflight checks"
  bash "$ROOT/scripts/preflight-check.sh"
fi

# --- 2. Build the Pillow layer ---------------------------------------------
step "Building Pillow Lambda layer"
bash "$ROOT/backend/layer/build_layer.sh"

# Stale bytecode would otherwise change the deployment package hash.
find "$ROOT/backend/src" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true

# --- 3. Infrastructure ------------------------------------------------------
step "Applying Terraform"
cd "$ROOT/infra"

if [ ! -f backend.hcl ]; then
  echo "${RED}infra/backend.hcl is missing. Run ./scripts/bootstrap.sh first.${NC}" >&2
  exit 1
fi

terraform init -backend-config=backend.hcl -input=false -upgrade >/dev/null
terraform apply -auto-approve -input=false

API_URL="$(terraform output -raw api_base_url)"
APP_URL="$(terraform output -raw app_url)"
SITE_BUCKET="$(terraform output -raw site_bucket)"
DISTRIBUTION_ID="$(terraform output -raw cloudfront_distribution_id)"

echo ""
echo "    API : $API_URL"
echo "    App : $APP_URL"

# --- 4. Smoke-test the API before building the frontend against it ----------
step "Smoke-testing the API"
gallery_status="$(curl -s -o /dev/null -w '%{http_code}' "$API_URL/gallery?limit=1")"
if [ "$gallery_status" != "200" ]; then
  echo "${RED}GET /gallery returned $gallery_status — aborting before frontend build.${NC}" >&2
  exit 1
fi
echo "    GET /gallery -> 200"

presign_status="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API_URL/uploads" \
  -H 'content-type: application/json' -d '{"contentType":"image/jpeg","size":1024}')"
if [ "$presign_status" != "200" ]; then
  echo "${RED}POST /uploads returned $presign_status — aborting.${NC}" >&2
  exit 1
fi
echo "    POST /uploads -> 200"

# --- 5. Frontend ------------------------------------------------------------
step "Building the frontend"
cd "$ROOT/frontend"
[ -d node_modules ] || npm ci --no-fund --no-audit
VITE_API_BASE_URL="$API_URL" npm run build

step "Uploading to S3"
# Hashed assets get a long TTL; the HTML shell must never be cached.
aws s3 sync dist/ "s3://$SITE_BUCKET/" --delete \
  --exclude "index.html" \
  --cache-control "public,max-age=31536000,immutable"

aws s3 cp dist/index.html "s3://$SITE_BUCKET/index.html" \
  --cache-control "no-cache,must-revalidate" \
  --content-type "text/html"

step "Invalidating CloudFront"
invalidation_id="$(aws cloudfront create-invalidation \
  --distribution-id "$DISTRIBUTION_ID" \
  --paths "/*" \
  --query 'Invalidation.Id' --output text)"
echo "    invalidation $invalidation_id created"

# --- 6. Done ----------------------------------------------------------------
echo ""
echo "${GREEN}────────────────────────────────────────────${NC}"
echo "${GREEN} Deployed.${NC}"
echo ""
echo "  App : $APP_URL"
echo "  API : $API_URL"
echo ""
echo "  End-to-end check:  ./scripts/e2e-test.sh"
echo "  Tear everything down: ./scripts/destroy.sh"
echo "${GREEN}────────────────────────────────────────────${NC}"

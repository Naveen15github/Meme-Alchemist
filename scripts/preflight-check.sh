#!/usr/bin/env bash
# Fail fast, before Terraform touches anything, on the things that actually
# block a first-attempt deploy. Every check prints how to fix itself.
set -uo pipefail

REGION="${AWS_REGION:-us-east-1}"
MODEL_ID="${BEDROCK_MODEL_ID:-amazon.nova-lite-v1:0}"

GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; YELLOW=$'\033[1;33m'; DIM=$'\033[2m'; NC=$'\033[0m'
FAILED=0
WARNED=0

pass() { echo "  ${GREEN}✓${NC} $1"; }
fail() { echo "  ${RED}✗${NC} $1"; FAILED=$((FAILED + 1)); }
warn() { echo "  ${YELLOW}!${NC} $1"; WARNED=$((WARNED + 1)); }
note() { echo "    ${DIM}$1${NC}"; }

echo ""
echo "Meme Alchemist — preflight (region: $REGION)"
echo "───────────────────────────────────────────────"

# --- 1. Tooling -------------------------------------------------------------
echo ""
echo "Tooling"
for tool in aws terraform node npm python; do
  if command -v "$tool" >/dev/null 2>&1; then
    pass "$tool found"
  else
    fail "$tool is not installed or not on PATH"
  fi
done

if command -v terraform >/dev/null 2>&1; then
  tf_version="$(terraform version -json 2>/dev/null | python -c 'import json,sys; print(json.load(sys.stdin)["terraform_version"])' 2>/dev/null || echo "unknown")"
  note "terraform $tf_version"
fi

# --- 2. Credentials ---------------------------------------------------------
echo ""
echo "AWS credentials"
if identity="$(aws sts get-caller-identity --output json 2>/dev/null)"; then
  account="$(echo "$identity" | python -c 'import json,sys; print(json.load(sys.stdin)["Account"])')"
  arn="$(echo "$identity" | python -c 'import json,sys; print(json.load(sys.stdin)["Arn"])')"
  pass "authenticated as $arn"
  note "account $account"
else
  fail "AWS credentials are missing or expired"
  note "Fix: run 'aws configure' or export AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY"
  echo ""
  echo "${RED}Preflight failed. Nothing was deployed.${NC}"
  exit 1
fi

# --- 3. Region supports Bedrock Nova ---------------------------------------
echo ""
echo "Amazon Bedrock"
if models="$(aws bedrock list-foundation-models --region "$REGION" --output json 2>/dev/null)"; then
  # Bash substring matching rather than `| grep -q`: grep short-circuits and
  # closes the pipe, which makes the writer die of SIGPIPE and `pipefail`
  # report a successful match as a failure.
  if [[ "$models" == *"\"$MODEL_ID\""* ]]; then
    pass "$MODEL_ID is offered in $REGION"
  else
    fail "$MODEL_ID is not offered in $REGION"
    note "Fix: deploy to us-east-1 (or another Nova region), or set TF_VAR_bedrock_model_id"
  fi
else
  fail "cannot reach Bedrock in $REGION — the region may not support it"
  note "Fix: use us-east-1, or check the bedrock:ListFoundationModels permission"
fi

# --- 4. Model access is actually granted -----------------------------------
# Listing a model does not mean the account may invoke it. Only a real
# InvokeModel call distinguishes "access not enabled" from "ready".
if command -v python >/dev/null 2>&1; then
  probe="$(mktemp)"
  out="$(mktemp)"
  cat > "$probe" <<'JSON'
{"messages":[{"role":"user","content":[{"text":"ok"}]}],"inferenceConfig":{"maxTokens":5}}
JSON

  # The AWS CLI is a native Windows binary under Git Bash, so it cannot read a
  # POSIX /tmp path. Translate when cygpath is available.
  probe_arg="$probe"; out_arg="$out"
  if command -v cygpath >/dev/null 2>&1; then
    probe_arg="$(cygpath -w "$probe")"
    out_arg="$(cygpath -w "$out")"
  fi

  err="$(aws bedrock-runtime invoke-model \
          --region "$REGION" \
          --model-id "$MODEL_ID" \
          --content-type application/json \
          --accept application/json \
          --body "fileb://$probe_arg" \
          "$out_arg" 2>&1 >/dev/null)"
  status=$?

  err_lower="$(printf '%s' "$err" | tr '[:upper:]' '[:lower:]')"

  if [ $status -eq 0 ]; then
    pass "model access is enabled and the model responded"
  elif [[ "$err_lower" == *accessdenied* || "$err_lower" == *"not authorized"* || "$err_lower" == *"don't have access"* ]]; then
    fail "Bedrock model access is NOT enabled for this account"
    note ""
    note "Fix this BEFORE deploying — it takes about a minute:"
    note "  1. Open https://${REGION}.console.aws.amazon.com/bedrock/home?region=${REGION}#/modelaccess"
    note "  2. Click 'Modify model access' (or 'Enable specific models')"
    note "  3. Tick the 'Amazon' provider models — at minimum Nova Lite"
    note "  4. Click Next, then Submit. Access is usually granted instantly."
    note "  5. Re-run this script."
    note ""
  elif [[ "$err_lower" == *throttling* || "$err_lower" == *"too many tokens"* || "$err_lower" == *servicequota* ]]; then
    warn "model access IS enabled, but the account is currently throttled"
    note "$(printf '%s' "$err" | tail -1)"
    note "The app handles this: captions fall back to the built-in joke library,"
    note "and switch back to Bedrock automatically once the quota resets."
    note "Deployment can proceed safely."
  else
    warn "could not confirm model access"
    note "$(printf '%s' "$err" | tail -1)"
  fi
  rm -f "$probe" "$out"
fi

# --- 5. Service quotas / permissions we depend on ---------------------------
echo ""
echo "Supporting services"
aws s3api list-buckets >/dev/null 2>&1 && pass "S3 reachable" || fail "cannot list S3 buckets"
aws dynamodb list-tables --region "$REGION" >/dev/null 2>&1 && pass "DynamoDB reachable" || fail "cannot reach DynamoDB"
aws lambda list-functions --region "$REGION" --max-items 1 >/dev/null 2>&1 && pass "Lambda reachable" || fail "cannot reach Lambda"
aws cloudfront list-distributions >/dev/null 2>&1 && pass "CloudFront reachable" || fail "cannot reach CloudFront"
aws rekognition list-collections --region "$REGION" >/dev/null 2>&1 && pass "Rekognition reachable" || warn "could not confirm Rekognition access"

# --- 6. Pillow layer must be built for Linux --------------------------------
echo ""
echo "Build artifacts"
LAYER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/backend/layer/build/python"
if [ -d "$LAYER_DIR" ] && ls "$LAYER_DIR"/PIL/*x86_64-linux-gnu.so >/dev/null 2>&1; then
  pass "Pillow layer is built for linux/x86_64"
else
  warn "Pillow layer not built yet"
  note "deploy.sh builds it automatically (backend/layer/build_layer.sh)"
fi

# --- Verdict ----------------------------------------------------------------
echo ""
echo "───────────────────────────────────────────────"
if [ "$FAILED" -gt 0 ]; then
  echo "${RED}Preflight failed: $FAILED blocking issue(s). Nothing was deployed.${NC}"
  echo "Fix the items marked ✗ above, then re-run: ./scripts/preflight-check.sh"
  echo ""
  exit 1
fi

if [ "$WARNED" -gt 0 ]; then
  echo "${GREEN}Preflight passed${NC} with $WARNED warning(s) — safe to deploy."
else
  echo "${GREEN}Preflight passed. Ready to deploy.${NC}"
fi
echo ""
exit 0

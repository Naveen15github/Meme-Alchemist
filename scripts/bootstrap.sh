#!/usr/bin/env bash
# One-time setup of the Terraform remote state backend.
#
# Creates a versioned, encrypted, private S3 bucket for state and writes
# infra/backend.hcl. State locking uses S3 native locking (use_lockfile),
# which replaced the DynamoDB lock table in Terraform 1.11+ — see DECISIONS.md.
#
# Safe to re-run: every step is idempotent.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REGION="${AWS_REGION:-us-east-1}"

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
BUCKET="meme-alchemist-tfstate-${ACCOUNT_ID}"
KEY="meme-alchemist/terraform.tfstate"

echo "==> Terraform state bucket: s3://${BUCKET}"

if aws s3api head-bucket --bucket "$BUCKET" >/dev/null 2>&1; then
  echo "    already exists"
else
  if [ "$REGION" = "us-east-1" ]; then
    # us-east-1 rejects a LocationConstraint.
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" >/dev/null
  else
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
      --create-bucket-configuration "LocationConstraint=$REGION" >/dev/null
  fi
  echo "    created"
fi

aws s3api put-public-access-block --bucket "$BUCKET" \
  --public-access-block-configuration \
  "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" >/dev/null

aws s3api put-bucket-versioning --bucket "$BUCKET" \
  --versioning-configuration Status=Enabled >/dev/null

aws s3api put-bucket-encryption --bucket "$BUCKET" \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}' >/dev/null

echo "    versioning + encryption + public access block applied"

cat > "$ROOT/infra/backend.hcl" <<EOF
bucket       = "${BUCKET}"
key          = "${KEY}"
region       = "${REGION}"
encrypt      = true
use_lockfile = true
EOF

echo "==> Wrote infra/backend.hcl"

cd "$ROOT/infra"
terraform init -backend-config=backend.hcl -input=false -reconfigure

echo ""
echo "==> Bootstrap complete. Next: ./scripts/deploy.sh"

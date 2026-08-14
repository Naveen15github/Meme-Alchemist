#!/usr/bin/env bash
# Tear down everything this project created, so it stops costing anything.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
YELLOW=$'\033[1;33m'; GREEN=$'\033[0;32m'; NC=$'\033[0m'

cd "$ROOT/infra"

echo ""
echo "${YELLOW}This destroys the Meme Alchemist stack:${NC}"
echo "  - CloudFront distribution, S3 buckets (uploads, memes, site) and their contents"
echo "  - Lambda functions, the Pillow layer, API Gateway, DynamoDB table, IAM roles, log groups"
echo ""
echo "The Terraform state bucket is NOT deleted (remove it by hand if you want it gone)."
echo ""

if [ "${FORCE:-0}" != "1" ]; then
  read -r -p "Type 'destroy' to confirm: " answer
  [ "$answer" = "destroy" ] || { echo "Aborted."; exit 1; }
fi

# force_destroy on the buckets lets Terraform remove them while objects remain,
# but emptying them first makes the destroy faster and more reliable.
for output in uploads_bucket processed_bucket site_bucket; do
  if bucket="$(terraform output -raw "$output" 2>/dev/null)" && [ -n "$bucket" ]; then
    echo "==> Emptying s3://$bucket"
    aws s3 rm "s3://$bucket" --recursive --only-show-errors || true
  fi
done

echo "==> terraform destroy"
terraform destroy -auto-approve -input=false

echo ""
echo "${GREEN}Everything torn down. Ongoing cost is now zero.${NC}"

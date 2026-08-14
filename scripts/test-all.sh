#!/usr/bin/env bash
# Everything that can be checked without deploying.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; BLUE=$'\033[0;34m'; NC=$'\033[0m'
FAILED=0

section() { echo ""; echo "${BLUE}==> $1${NC}"; }
check()   { if [ "$1" -eq 0 ]; then echo "${GREEN}    $2 passed${NC}"; else echo "${RED}    $2 FAILED${NC}"; FAILED=1; fi }

# --- Backend ----------------------------------------------------------------
section "Backend tests (pytest + moto)"
cd "$ROOT/backend"
if [ -x ".venv/Scripts/python.exe" ]; then
  PYTHON=".venv/Scripts/python.exe"      # Windows
elif [ -x ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"              # macOS / Linux
else
  PYTHON="python"
fi
"$PYTHON" -m pytest
check $? "backend"

# --- Frontend ---------------------------------------------------------------
section "Frontend tests (vitest + testing-library)"
cd "$ROOT/frontend"
[ -d node_modules ] || npm ci --no-fund --no-audit
npm test --silent
check $? "frontend"

# --- Terraform --------------------------------------------------------------
section "Terraform fmt"
cd "$ROOT/infra"
terraform fmt -check -recursive
check $? "terraform fmt"

section "Terraform validate"
if [ -f backend.hcl ]; then
  terraform init -backend-config=backend.hcl -input=false -upgrade >/dev/null 2>&1
else
  terraform init -backend=false -input=false >/dev/null 2>&1
fi
terraform validate
check $? "terraform validate"

section "Terraform plan (sanity check)"
if [ -f backend.hcl ] && aws sts get-caller-identity >/dev/null 2>&1; then
  terraform plan -input=false -lock=false -out=/dev/null >/dev/null
  check $? "terraform plan"
else
  echo "    skipped (no remote backend configured or no AWS credentials)"
fi

# --- Verdict ----------------------------------------------------------------
echo ""
if [ "$FAILED" -eq 0 ]; then
  echo "${GREEN}All checks passed.${NC}"
  exit 0
fi
echo "${RED}Some checks failed.${NC}"
exit 1

#!/usr/bin/env bash
# Owner-side meme management, using your AWS credentials rather than the
# public API.
#
# The public DELETE endpoint is capability-based: only the browser that created
# a meme holds its delete token. That is the right default for an unauthenticated
# app, but it means memes created before delete tokens existed - or created on
# another device - have no button in the UI. This script is the escape hatch.
#
#   ./scripts/admin-memes.sh list
#   ./scripts/admin-memes.sh delete <meme-id> [<meme-id> ...]
#   ./scripts/admin-memes.sh delete-untokened     # every meme with no delete token
#   ./scripts/admin-memes.sh delete-all           # empty the gallery
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; YELLOW=$'\033[1;33m'; NC=$'\033[0m'

cd "$ROOT/infra"
TABLE="$(terraform output -raw table_name)"
BUCKET="$(terraform output -raw processed_bucket)"
REGION="${AWS_REGION:-us-east-1}"

if [ -x "$ROOT/backend/.venv/Scripts/python.exe" ]; then
  PY="$ROOT/backend/.venv/Scripts/python.exe"
elif [ -x "$ROOT/backend/.venv/bin/python" ]; then
  PY="$ROOT/backend/.venv/bin/python"
else
  PY="python"
fi

winpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -w "$1"; else printf '%s' "$1"; fi; }

scan() {
  aws dynamodb scan --table-name "$TABLE" --region "$REGION" --output json
}

remove_one() {
  local id="$1"
  aws dynamodb delete-item --table-name "$TABLE" --region "$REGION" \
    --key "{\"id\":{\"S\":\"$id\"}}" >/dev/null
  aws s3 rm "s3://$BUCKET/memes/$id.jpg" --only-show-errors 2>/dev/null || true
  echo "  ${GREEN}deleted${NC} $id"
}

# Emit "id<TAB>hasToken<TAB>caption" for each meme, newest first.
rows() {
  local tmp="$ROOT/.admin-scan.json"
  scan > "$tmp"
  "$PY" - "$(winpath "$tmp")" <<'PY'
import json, sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
items = data.get("Items", [])
items.sort(key=lambda i: i.get("createdAt", {}).get("S", ""), reverse=True)
for item in items:
    has_token = "yes" if item.get("deleteTokenHash", {}).get("S") else "no"
    print("\t".join([
        item.get("id", {}).get("S", ""),
        has_token,
        item.get("caption", {}).get("S", "").replace("\n", " ")[:60],
    ]))
PY
  rm -f "$tmp"
}

COMMAND="${1:-list}"
shift || true

case "$COMMAND" in
  list)
    echo ""
    printf "%-38s %-9s %s\n" "MEME ID" "DELETABLE" "CAPTION"
    printf "%-38s %-9s %s\n" "--------------------------------------" "---------" "-------"
    rows | while IFS=$'\t' read -r id has_token caption; do
      printf "%-38s %-9s %s\n" "$id" "$has_token" "$caption"
    done
    echo ""
    echo "DELETABLE = has a delete token, so it shows a delete button in the app."
    ;;

  delete)
    [ $# -gt 0 ] || { echo "${RED}Usage: $0 delete <meme-id> [...]${NC}" >&2; exit 1; }
    for id in "$@"; do remove_one "$id"; done
    ;;

  delete-untokened)
    ids="$(rows | awk -F'\t' '$2 == "no" { print $1 }')"
    if [ -z "$ids" ]; then echo "Nothing to do - every meme already has a delete token."; exit 0; fi
    count="$(printf '%s\n' "$ids" | wc -l | tr -d ' ')"
    echo "${YELLOW}This deletes $count meme(s) that predate delete tokens.${NC}"
    if [ "${FORCE:-0}" != "1" ]; then
      read -r -p "Type 'yes' to continue: " answer
      [ "$answer" = "yes" ] || { echo "Aborted."; exit 1; }
    fi
    printf '%s\n' "$ids" | while read -r id; do [ -n "$id" ] && remove_one "$id"; done
    ;;

  delete-all)
    ids="$(rows | cut -f1)"
    if [ -z "$ids" ]; then echo "Gallery is already empty."; exit 0; fi
    count="$(printf '%s\n' "$ids" | wc -l | tr -d ' ')"
    echo "${YELLOW}This empties the gallery - $count meme(s).${NC}"
    if [ "${FORCE:-0}" != "1" ]; then
      read -r -p "Type 'empty the gallery' to continue: " answer
      [ "$answer" = "empty the gallery" ] || { echo "Aborted."; exit 1; }
    fi
    printf '%s\n' "$ids" | while read -r id; do [ -n "$id" ] && remove_one "$id"; done
    ;;

  *)
    echo "Unknown command: $COMMAND" >&2
    sed -n '4,12p' "${BASH_SOURCE[0]}" >&2
    exit 1
    ;;
esac

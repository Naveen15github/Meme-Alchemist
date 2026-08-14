#!/usr/bin/env bash
# Build the Pillow Lambda layer for the Lambda runtime architecture.
#
# We deliberately do NOT need Docker: pip can fetch prebuilt manylinux wheels
# for a target platform/interpreter from any host OS. That keeps `deploy.sh`
# runnable on Windows, macOS and Linux identically.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$HERE/build"
PY_VERSION="3.12"
PLATFORM="manylinux2014_x86_64"
PILLOW_VERSION="11.3.0"

echo "==> Rebuilding Pillow layer (Pillow $PILLOW_VERSION, py$PY_VERSION, $PLATFORM)"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/python"

python -m pip install \
  --quiet \
  --platform "$PLATFORM" \
  --implementation cp \
  --python-version "$PY_VERSION" \
  --only-binary=:all: \
  --target "$BUILD_DIR/python" \
  "Pillow==$PILLOW_VERSION"

# Trim test/doc weight that would otherwise ship to Lambda.
find "$BUILD_DIR/python" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true

if ! ls "$BUILD_DIR"/python/PIL/*x86_64-linux-gnu.so >/dev/null 2>&1; then
  echo "ERROR: layer does not contain Linux binaries - refusing to continue." >&2
  exit 1
fi

echo "==> Layer ready: $BUILD_DIR ($(du -sh "$BUILD_DIR" | cut -f1))"

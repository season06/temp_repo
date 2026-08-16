#!/usr/bin/env bash
# 為每個支援的 Python 次版產出一顆 sourceless(.pyc-only)wheel。
# 每顆與 OS 無關、綁對應 CPython 次版(cpXY-none-any)。
set -euo pipefail

VERSIONS=(3.11 3.12 3.13)

rm -rf dist
for v in "${VERSIONS[@]}"; do
  echo "=== building for Python $v ==="
  uv build --wheel --python "$v"
done

echo "=== done ==="
ls -1 dist

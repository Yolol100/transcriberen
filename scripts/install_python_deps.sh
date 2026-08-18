#!/usr/bin/env bash
set -euo pipefail

ROOT="${GITHUB_WORKSPACE:-$(pwd)}"
LOCK="$ROOT/requirements.lock"

if [[ ! -f "$LOCK" ]]; then
  echo "missing requirements.lock" >&2
  exit 1
fi

grep -Fx 'trafilatura==2.1.0 --hash=sha256:0eded5207a806445ddebbe36eae30b9035fe6a2f233c36f6fe82663fca8b9d30  # trafilatura-2.1.0-py3-none-any.whl' "$LOCK" >/dev/null

python -m pip --isolated install \
  --disable-pip-version-check \
  --no-input \
  --index-url https://pypi.org/simple \
  --require-hashes \
  --only-binary=:all: \
  -r "$LOCK"
python -m pip check

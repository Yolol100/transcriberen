#!/usr/bin/env bash
set -euo pipefail

ROOT="${GITHUB_WORKSPACE:-$(pwd)}"
LOCK="$ROOT/requirements.lock"

if [[ ! -f "$LOCK" ]]; then
  echo "missing requirements.lock" >&2
  exit 1
fi

python -m pip --isolated install \
  --disable-pip-version-check \
  --no-input \
  --require-hashes \
  --only-binary=:all: \
  -r "$LOCK"
python -m pip check

#!/usr/bin/env bash
set -euo pipefail

TRAFILATURA_VERSION="2.1.0"
TRAFILATURA_WHEEL="trafilatura-${TRAFILATURA_VERSION}-py3-none-any.whl"
TRAFILATURA_WHEEL_SHA256="0eded5207a806445ddebbe36eae30b9035fe6a2f233c36f6fe82663fca8b9d30"
REQUIREMENT="trafilatura==${TRAFILATURA_VERSION}"
TMP_ROOT="$(mktemp -d "${RUNNER_TEMP:-/tmp}/webactueel-python-deps.XXXXXX")"
trap 'rm -rf "$TMP_ROOT"' EXIT

grep -Fx "$REQUIREMENT" requirements.txt >/dev/null
python -m pip download --disable-pip-version-check --no-input --no-deps --only-binary=:all: --dest "$TMP_ROOT" "$REQUIREMENT"
test -f "$TMP_ROOT/$TRAFILATURA_WHEEL"
printf '%s  %s\n' "$TRAFILATURA_WHEEL_SHA256" "$TMP_ROOT/$TRAFILATURA_WHEEL" | sha256sum -c -
python -m pip install --disable-pip-version-check --no-input "$TMP_ROOT/$TRAFILATURA_WHEEL"
python -m pip check

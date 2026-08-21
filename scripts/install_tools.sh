#!/usr/bin/env bash
set -euo pipefail

ROOT="${GITHUB_WORKSPACE:-$(pwd)}"
BIN_DIR="$ROOT/tools/bin"
YT_DLP_VERSION="2026.08.20.234504"
DENO_VERSION="2.9.5"

SYSTEM_YT_DLP="$(command -v yt-dlp || true)"
SYSTEM_DENO="$(command -v deno || true)"
if [[ -z "$SYSTEM_YT_DLP" ]]; then
  echo "yt-dlp $YT_DLP_VERSION is required on the dedicated runner" >&2
  exit 2
fi
if [[ -z "$SYSTEM_DENO" ]]; then
  echo "deno $DENO_VERSION is required on the dedicated runner" >&2
  exit 2
fi
if [[ "$("$SYSTEM_YT_DLP" --version)" != "$YT_DLP_VERSION" ]]; then
  echo "yt-dlp version mismatch; required $YT_DLP_VERSION" >&2
  exit 2
fi
if ! "$SYSTEM_DENO" --version | head -n 1 | grep -Fx "deno $DENO_VERSION" >/dev/null; then
  echo "deno version mismatch; required $DENO_VERSION" >&2
  exit 2
fi

mkdir -p "$BIN_DIR"
ln -sfn "$SYSTEM_YT_DLP" "$BIN_DIR/yt-dlp"
ln -sfn "$SYSTEM_DENO" "$BIN_DIR/deno"

if [[ -n "${GITHUB_PATH:-}" ]]; then
  printf '%s\n' "$BIN_DIR" >> "$GITHUB_PATH"
fi

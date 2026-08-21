#!/usr/bin/env bash
set -euo pipefail

ROOT="${GITHUB_WORKSPACE:-$(pwd)}"
BIN_DIR="$ROOT/tools/bin"
YT_DLP_VERSION="2026.08.20.234504"
YT_DLP_SHA256="8962aa45f945ae5aa11ab49acab365e8baef569ec995149f99ae0ae3a19cae93"
DENO_VERSION="2.9.5"
DENO_SHA256="8b010a3b1a4a0188a67cdb8a7a27348b2a501af78aec7fc74f2ace167368d530"

mkdir -p "$BIN_DIR"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

verify_sha256() {
  local file="$1"
  local expected="$2"
  local label="$3"
  local actual
  actual="$(sha256sum "$file" | awk '{print $1}')"
  if [[ "$actual" != "$expected" ]]; then
    printf 'SHA-256 mismatch for %s: expected=%s actual=%s\n' "$label" "$expected" "$actual" >&2
    return 1
  fi
  printf 'SHA-256 verified for %s: %s\n' "$label" "$actual"
}

download() {
  local url="$1"
  local output="$2"
  curl --fail --location --silent --show-error \
    --retry 3 --retry-delay 2 --connect-timeout 20 --max-time 180 \
    --proto '=https' --tlsv1.2 --noproxy '*' \
    "$url" -o "$output"
}

deno_reported_version() {
  local executable="$1"
  "$executable" --version | head -n 1 | awk '$1 == "deno" {print $2}'
}

SYSTEM_YT_DLP="$(command -v yt-dlp || true)"
if [[ -n "$SYSTEM_YT_DLP" && "$("$SYSTEM_YT_DLP" --version)" == "$YT_DLP_VERSION" ]]; then
  ln -sfn "$SYSTEM_YT_DLP" "$BIN_DIR/yt-dlp.bin"
else
  download \
    "https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/download/${YT_DLP_VERSION}/yt-dlp" \
    "$TMP_DIR/yt-dlp"
  verify_sha256 "$TMP_DIR/yt-dlp" "$YT_DLP_SHA256" "yt-dlp ${YT_DLP_VERSION}"
  install -m 0755 "$TMP_DIR/yt-dlp" "$BIN_DIR/yt-dlp.bin"
fi

SYSTEM_DENO="$(command -v deno || true)"
if [[ -n "$SYSTEM_DENO" && "$(deno_reported_version "$SYSTEM_DENO")" == "$DENO_VERSION" ]]; then
  ln -sfn "$SYSTEM_DENO" "$BIN_DIR/deno"
else
  download \
    "https://github.com/denoland/deno/releases/download/v${DENO_VERSION}/deno-x86_64-unknown-linux-gnu.zip" \
    "$TMP_DIR/deno.zip"
  verify_sha256 "$TMP_DIR/deno.zip" "$DENO_SHA256" "Deno ${DENO_VERSION} linux-x86_64 zip"
  python3 - "$TMP_DIR/deno.zip" "$BIN_DIR/deno" <<'PY'
import pathlib
import sys
import zipfile

archive = pathlib.Path(sys.argv[1])
target = pathlib.Path(sys.argv[2])
with zipfile.ZipFile(archive) as zf:
    data = zf.read("deno")
target.write_bytes(data)
target.chmod(0o755)
PY
fi

cat > "$BIN_DIR/yt-dlp" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail
HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "$HERE/yt-dlp.bin" --js-runtimes "deno:$HERE/deno" "$@"
WRAPPER
chmod 0755 "$BIN_DIR/yt-dlp"

printf 'yt-dlp binary version: '
"$BIN_DIR/yt-dlp.bin" --version
printf 'Deno binary version: '
"$BIN_DIR/deno" --version | head -n 1
printf 'yt-dlp wrapper version: '
"$BIN_DIR/yt-dlp" --version

test "$("$BIN_DIR/yt-dlp.bin" --version)" = "$YT_DLP_VERSION"
test "$("$BIN_DIR/yt-dlp" --version)" = "$YT_DLP_VERSION"
test "$(deno_reported_version "$BIN_DIR/deno")" = "$DENO_VERSION"

if [[ -n "${GITHUB_PATH:-}" ]]; then
  printf '%s\n' "$BIN_DIR" >> "$GITHUB_PATH"
fi

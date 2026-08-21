#!/usr/bin/env bash
set -euo pipefail

INSTALL_WHISPER="${1:-false}"
ROOT="${GITHUB_WORKSPACE:-$(pwd)}"
BIN_DIR="$ROOT/tools/bin"
MODEL_DIR="$ROOT/tools/models"
TMP_ROOT="$(mktemp -d "${RUNNER_TEMP:-/tmp}/webactueel-tools.XXXXXX")"
trap 'rm -rf "$TMP_ROOT"' EXIT
mkdir -p "$BIN_DIR" "$MODEL_DIR"

curl_https() {
  curl --fail --silent --show-error --location \
    --proto '=https' --proto-redir '=https' --tlsv1.2 --noproxy '*' \
    --retry 3 --retry-all-errors --connect-timeout 20 --max-time 300 "$@"
}

verify_sha256() {
  local expected="$1"
  local file="$2"
  printf '%s  %s\n' "$expected" "$file" | sha256sum -c -
}

DENO_VERSION="v2.9.5"
DENO_SHA256="8b010a3b1a4a0188a67cdb8a7a27348b2a501af78aec7fc74f2ace167368d530"
DENO_ARCHIVE="$TMP_ROOT/deno-x86_64-unknown-linux-gnu.zip"
curl_https "https://github.com/denoland/deno/releases/download/${DENO_VERSION}/deno-x86_64-unknown-linux-gnu.zip" -o "$DENO_ARCHIVE"
verify_sha256 "$DENO_SHA256" "$DENO_ARCHIVE"
python3 - "$DENO_ARCHIVE" "$TMP_ROOT/deno" <<'PY'
import pathlib
import sys
import zipfile
archive = pathlib.Path(sys.argv[1])
out = pathlib.Path(sys.argv[2])
with zipfile.ZipFile(archive) as zf:
    info = zf.getinfo("deno")
    if info.is_dir() or info.filename != "deno":
        raise SystemExit("unexpected Deno archive layout")
    with zf.open(info) as src, out.open("wb") as dst:
        while chunk := src.read(1024 * 1024):
            dst.write(chunk)
PY
install -m 0755 "$TMP_ROOT/deno" "$BIN_DIR/deno"
"$BIN_DIR/deno" --version

# Resolve the current official yt-dlp nightly release only long enough to learn
# the exact immutable tag and digest. The release candidate branch converts this
# resolution into a reviewed source pin before merge.
YT_DLP_LATEST_URL="$(curl_https --output /dev/null --write-out '%{url_effective}' \
  'https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/latest')"
case "$YT_DLP_LATEST_URL" in
  https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/tag/*) ;;
  *) echo "unexpected yt-dlp nightly release URL: $YT_DLP_LATEST_URL" >&2; exit 1 ;;
esac
YT_DLP_VERSION="${YT_DLP_LATEST_URL##*/}"
if [[ ! "$YT_DLP_VERSION" =~ ^[0-9]{4}\.[0-9]{2}\.[0-9]{2}\.[0-9]{6}$ ]]; then
  echo "unexpected yt-dlp nightly tag: $YT_DLP_VERSION" >&2
  exit 1
fi
YT_DLP_RELEASE_BASE="https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/download/${YT_DLP_VERSION}"
YT_DLP_CHECKSUMS="$TMP_ROOT/SHA2-256SUMS"
YT_DLP_DOWNLOAD="$TMP_ROOT/yt-dlp.bin"
curl_https "${YT_DLP_RELEASE_BASE}/SHA2-256SUMS" -o "$YT_DLP_CHECKSUMS"
YT_DLP_SHA256="$(python3 - "$YT_DLP_CHECKSUMS" <<'PY'
import pathlib
import re
import sys
matches = []
for line in pathlib.Path(sys.argv[1]).read_text(encoding='utf-8').splitlines():
    match = re.fullmatch(r'([0-9a-fA-F]{64})\s+\*?yt-dlp', line.strip())
    if match:
        matches.append(match.group(1).lower())
if len(matches) != 1:
    raise SystemExit(f'expected exactly one yt-dlp checksum, got {len(matches)}')
print(matches[0])
PY
)"
curl_https "${YT_DLP_RELEASE_BASE}/yt-dlp" -o "$YT_DLP_DOWNLOAD"
verify_sha256 "$YT_DLP_SHA256" "$YT_DLP_DOWNLOAD"
install -m 0755 "$YT_DLP_DOWNLOAD" "$BIN_DIR/yt-dlp.bin"
cat > "$BIN_DIR/yt-dlp" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
exec "$HERE/yt-dlp.bin" --js-runtimes "deno:$HERE/deno" "$@"
WRAPPER
chmod +x "$BIN_DIR/yt-dlp"
"$BIN_DIR/yt-dlp" --version
printf 'yt-dlp=%s\nsha256=%s\n' "$YT_DLP_VERSION" "$YT_DLP_SHA256" > "$ROOT/tools/yt-dlp-resolution.txt"

if [[ "$INSTALL_WHISPER" == "true" ]]; then
  WHISPER_VERSION="v1.9.2"
  WHISPER_SHA256="46811a3ecf584307480a220b9ef5ff81b7b22dc41577cbc274ce3afc61f753b1"
  WHISPER_ARCHIVE="$TMP_ROOT/whisper-bin-ubuntu-x64.tar.gz"
  curl_https "https://github.com/ggml-org/whisper.cpp/releases/download/${WHISPER_VERSION}/whisper-bin-ubuntu-x64.tar.gz" -o "$WHISPER_ARCHIVE"
  verify_sha256 "$WHISPER_SHA256" "$WHISPER_ARCHIVE"
  mkdir -p "$TMP_ROOT/whisper-extract"
  tar -xzf "$WHISPER_ARCHIVE" -C "$TMP_ROOT/whisper-extract"
  WHISPER_BIN="$(find "$TMP_ROOT/whisper-extract" -type f -name 'whisper-cli' -perm -111 -print -quit)"
  test -n "$WHISPER_BIN"
  install -m 0755 "$WHISPER_BIN" "$BIN_DIR/whisper-cli"

  WHISPER_MODEL_REVISION="5359861c739e955e79d9a303bcbc70fb988958b1"
  WHISPER_MODEL_SHA256="60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe"
  WHISPER_MODEL_DOWNLOAD="$TMP_ROOT/ggml-base.bin"
  curl_https "https://huggingface.co/ggerganov/whisper.cpp/resolve/${WHISPER_MODEL_REVISION}/ggml-base.bin?download=true" -o "$WHISPER_MODEL_DOWNLOAD"
  verify_sha256 "$WHISPER_MODEL_SHA256" "$WHISPER_MODEL_DOWNLOAD"
  install -m 0644 "$WHISPER_MODEL_DOWNLOAD" "$MODEL_DIR/ggml-base.bin"
fi

if [[ -n "${GITHUB_PATH:-}" ]]; then
  printf '%s\n' "$BIN_DIR" >> "$GITHUB_PATH"
fi

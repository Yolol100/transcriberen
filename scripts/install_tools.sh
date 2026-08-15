#!/usr/bin/env bash
set -euo pipefail

INSTALL_WHISPER="${1:-false}"
ROOT="${GITHUB_WORKSPACE:-$(pwd)}"
BIN_DIR="$ROOT/tools/bin"
MODEL_DIR="$ROOT/tools/models"
mkdir -p "$BIN_DIR" "$MODEL_DIR"

YT_DLP_VERSION="2026.07.04"
YT_DLP_SHA256="495be29ff4d9d4e9be7eabdfef225221e5d5282e77f2f505abc6dca80349f3fd"
curl -fsSL "https://github.com/yt-dlp/yt-dlp/releases/download/${YT_DLP_VERSION}/yt-dlp" -o "$BIN_DIR/yt-dlp.bin"
echo "${YT_DLP_SHA256}  $BIN_DIR/yt-dlp.bin" | sha256sum -c -
chmod +x "$BIN_DIR/yt-dlp.bin"
cat > "$BIN_DIR/yt-dlp" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
exec "$HERE/yt-dlp.bin" --js-runtimes node "$@"
WRAPPER
chmod +x "$BIN_DIR/yt-dlp"
"$BIN_DIR/yt-dlp" --version

if [[ "$INSTALL_WHISPER" == "true" ]]; then
  WHISPER_VERSION="v1.9.2"
  WHISPER_SHA256="46811a3ecf584307480a220b9ef5ff81b7b22dc41577cbc274ce3afc61f753b1"
  WHISPER_ARCHIVE="${RUNNER_TEMP:-/tmp}/whisper-bin-ubuntu-x64.tar.gz"
  curl -fsSL "https://github.com/ggml-org/whisper.cpp/releases/download/${WHISPER_VERSION}/whisper-bin-ubuntu-x64.tar.gz" -o "$WHISPER_ARCHIVE"
  echo "${WHISPER_SHA256}  $WHISPER_ARCHIVE" | sha256sum -c -
  mkdir -p "${RUNNER_TEMP:-/tmp}/whisper-extract"
  tar -xzf "$WHISPER_ARCHIVE" -C "${RUNNER_TEMP:-/tmp}/whisper-extract"
  WHISPER_BIN="$(find "${RUNNER_TEMP:-/tmp}/whisper-extract" -type f -name 'whisper-cli' -perm -111 | head -n 1)"
  test -n "$WHISPER_BIN"
  cp "$WHISPER_BIN" "$BIN_DIR/whisper-cli"
  chmod +x "$BIN_DIR/whisper-cli"

  WHISPER_MODEL_REVISION="5359861c739e955e79d9a303bcbc70fb988958b1"
  WHISPER_MODEL_SHA256="60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe"
  curl -fsSL "https://huggingface.co/ggerganov/whisper.cpp/resolve/${WHISPER_MODEL_REVISION}/ggml-base.bin?download=true" -o "$MODEL_DIR/ggml-base.bin"
  echo "${WHISPER_MODEL_SHA256}  $MODEL_DIR/ggml-base.bin" | sha256sum -c -
fi

{
  echo "$BIN_DIR"
} >> "${GITHUB_PATH:-/dev/null}" 2>/dev/null || true

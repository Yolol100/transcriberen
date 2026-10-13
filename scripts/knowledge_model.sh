#!/usr/bin/env bash
# GitHub-hosted local inference: no external inference endpoint, no user-provided key.
set -euo pipefail
DEST="${1:?directory}"
mkdir -p "$DEST/model" "$DEST/llama"
RUNTIME_URL='https://github.com/ggml-org/llama.cpp/releases/download/b11425/llama-b11425-bin-ubuntu-x64.tar.gz'
RUNTIME_SHA='6a47856d08ecc4030b2fa8b8bf761c96d142d689567f69a0f75e42de430dc34c'
# GGUF weights are anonymously publicly downloadable. They are NOT a hosted inference API.
MODEL_URL='https://huggingface.co/ggml-org/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q4_K_M.gguf'
MODEL_SHA='d2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5'
curl --fail --location --retry 3 --max-time 1200 --proto '=https' --tlsv1.2 --output "$DEST/llama.tar.gz" "$RUNTIME_URL"
echo "$RUNTIME_SHA  $DEST/llama.tar.gz" | sha256sum --check --status || { echo 'llama release hash mismatch' >&2; exit 2; }
tar -tzf "$DEST/llama.tar.gz" > "$DEST/llama-members.txt"
grep -Eq '(^|/)llama-server$' "$DEST/llama-members.txt" || { echo 'llama-server binary not found in pinned release' >&2; exit 2; }
tar -xzf "$DEST/llama.tar.gz" -C "$DEST/llama" --no-same-owner --no-same-permissions
curl --fail --location --retry 3 --max-time 2400 --proto '=https' --tlsv1.2 --output "$DEST/model/model.gguf" "$MODEL_URL"
echo "$MODEL_SHA  $DEST/model/model.gguf" | sha256sum --check --status || { echo 'GGUF model hash mismatch' >&2; exit 2; }
SERVER="$(find "$DEST/llama" -type f -name 'llama-server' -print -quit)"
test -n "$SERVER" || exit 2
chmod +x "$SERVER"
export LD_LIBRARY_PATH="$(dirname "$SERVER"):${LD_LIBRARY_PATH:-}"
"$SERVER" --model "$DEST/model/model.gguf" --host 127.0.0.1 --port 8080 --ctx-size 8192 --threads 4 > "$DEST/llama.log" 2>&1 &
pid=$!
echo "$pid" > "$DEST/llama.pid"
for i in $(seq 1 100); do
  if curl --silent --fail --max-time 2 'http://127.0.0.1:8080/health' > /dev/null; then
    echo "Local inference ready, pid=$pid" >&2
    exit 0
  fi
  if ! kill -0 "$pid" 2>/dev/null; then echo 'local inference terminated' >&2; exit 2; fi
  sleep 2
done
echo 'local inference not ready' >&2
exit 2
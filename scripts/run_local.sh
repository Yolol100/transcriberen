#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REQUEST_INPUT="${1:-}"
if [[ -z "$REQUEST_INPUT" ]]; then
  echo "usage: bash scripts/run_local.sh <request.json>" >&2
  exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required" >&2
  exit 2
fi

REQUEST_PATH="$(python3 - "$REQUEST_INPUT" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1]).expanduser().resolve()
if not path.is_file():
    raise SystemExit(f"request file not found: {path}")
print(path)
PY
)"

cd "$ROOT"
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy || true

python3 - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit(f"Python 3.12+ required; found {sys.version.split()[0]}")
PY

bash scripts/install_tools.sh
export PATH="$ROOT/tools/bin:$PATH"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
if [[ -d results ]]; then
  mv results "results.previous.$STAMP"
fi

RUNTIME_SHA="local-unversioned"
if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  RUNTIME_SHA="$(git rev-parse HEAD)"
fi

export GITHUB_WORKSPACE="$ROOT"
export GITHUB_REPOSITORY="Yolol100/transcriberen"
export GITHUB_SHA="$RUNTIME_SHA"
export GITHUB_RUN_ID="local-$STAMP"
export GITHUB_RUN_ATTEMPT="1"
export GITHUB_WORKFLOW_REF="local:scripts/run_local.sh"
export GITHUB_EVENT_NAME="local"
export TRANSCRIBE_EXECUTION_TARGET="local"

REQUEST_FILE="$REQUEST_PATH" python3 scripts/resolve_request.py
REQUEST_FILE="$ROOT/resolved-request.json" python3 scripts/captions_runtime.py
python3 scripts/validate_result.py results/result.json

(
  cd results
  find . -type f ! -name SHA256SUMS.txt -print0 \
    | sort -z \
    | xargs -0 sha256sum \
    | sed 's#  \./#  #' \
    > SHA256SUMS.txt
  test -s SHA256SUMS.txt
  sha256sum -c SHA256SUMS.txt
)

python3 - <<'PY'
import json
from pathlib import Path
result = json.loads(Path('results/result.json').read_text(encoding='utf-8'))
print(f"status={result['status']}")
if result['status'] == 'ok':
    print(f"transcript={Path('results/transcript.txt').resolve()}")
elif result['status'] in {'access_blocked', 'error'}:
    raise SystemExit(result.get('error') or result['status'])
PY

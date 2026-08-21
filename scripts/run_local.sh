#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REQUEST_INPUT="${1:-}"

if [[ -z "$REQUEST_INPUT" ]]; then
  echo "usage: bash scripts/run_local.sh <request.json>" >&2
  exit 2
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required (Python 3.12 recommended)" >&2
  exit 2
fi

REQUEST_PATH="$(python3 - "$REQUEST_INPUT" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1]).expanduser().resolve()
if not p.is_file():
    raise SystemExit(f"request file not found: {p}")
print(p)
PY
)"

cd "$ROOT"

# Keep local YouTube execution on the machine's direct connection. The
# controlled runtime intentionally does not inherit proxy configuration.
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy || true

VENV="$ROOT/.local-runtime-venv"
if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

python - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit(f"Python 3.12+ required; found {sys.version.split()[0]}")
print(f"python={sys.version.split()[0]}")
PY

bash scripts/install_python_deps.sh
bash scripts/install_tools.sh false
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
export GITHUB_REPOSITORY_VISIBILITY="local"

REQUEST_FILE="$REQUEST_PATH" python scripts/resolve_request_hardened.py
python - <<'PY'
import json
from pathlib import Path
req = json.loads(Path('resolved-request.json').read_text(encoding='utf-8'))
if req.get('enabled') is not True:
    raise SystemExit('request is disabled; nothing to execute')
PY

REQUEST_FILE="$ROOT/resolved-request.json" python scripts/runtime_topic_filter.py
if [[ -f results/youtube-index.json ]]; then
  python scripts/normalize_youtube_result_v2.py results/youtube-index.json
fi
python scripts/validate_result.py results/result.json

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

python - <<'PY'
import json
from pathlib import Path
r = json.loads(Path('results/result.json').read_text(encoding='utf-8'))
yt = ((r.get('metadata') or {}).get('youtube') or {})
print('')
print('local runtime complete')
print(f"request_id={r.get('request_id')}")
print(f"mode={r.get('detected_mode')}")
if r.get('detected_mode') == 'youtube':
    print(f"collection_status={yt.get('collection_status')}")
    print(f"selected_count={yt.get('selected_count')}")
    print(f"transcript_count={yt.get('transcript_count')}")
    print(f"comment_review_candidate_count={yt.get('comment_review_candidate_count')}")
print(f"results={Path('results').resolve()}")
PY

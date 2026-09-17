#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REQUEST_INPUT="${1:-}"
[[ -n "$REQUEST_INPUT" ]] || { echo "usage: bash scripts/run_local.sh <channel-request.json>" >&2; exit 2; }
REQUEST_PATH="$(python3 - "$REQUEST_INPUT" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]).expanduser().resolve()
if not p.is_file(): raise SystemExit(f"request file not found: {p}")
print(p)
PY
)"
cd "$ROOT"
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy || true
python3 - <<'PY'
import sys
if sys.version_info < (3, 12): raise SystemExit("Python 3.12+ required")
PY
bash scripts/install_tools.sh
export PATH="$ROOT/tools/bin:$PATH"
export GITHUB_WORKSPACE="$ROOT" GITHUB_REPOSITORY="Yolol100/transcriberen" GITHUB_SHA="$(git rev-parse HEAD 2>/dev/null || echo local-unversioned)" GITHUB_RUN_ID="local" GITHUB_RUN_ATTEMPT="1" GITHUB_WORKFLOW_REF="local:scripts/run_local.sh" GITHUB_EVENT_NAME="local" TRANSCRIBE_EXECUTION_TARGET="local"
REQUEST_FILE="$REQUEST_PATH" python3 scripts/resolve_request.py
REQUEST_FILE="$ROOT/resolved-request.json" python3 scripts/channel_runtime.py
python3 scripts/validate_result.py results/result.json
(
  cd results
  find . -type f ! -name SHA256SUMS.txt -print0 | sort -z | xargs -0 sha256sum | sed 's#  \./#  #' > SHA256SUMS.txt
  test -s SHA256SUMS.txt
  sha256sum -c SHA256SUMS.txt
)
python3 - <<'PY'
import json
from pathlib import Path
r=json.loads(Path('results/result.json').read_text())
print(f"status={r['status']}")
print(f"matched_2026={r.get('counts',{}).get('matched_2026',0)}")
print(f"captions_ok={r.get('counts',{}).get('captions_ok',0)}")
print(f"archive={Path('results/channel-corpus.zip').resolve()}")
if r['status'] in {'access_blocked','error'}: raise SystemExit(r.get('error') or r['status'])
PY

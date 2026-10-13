#!/usr/bin/env bash
# Read-only download of a corpus already present as an artifact/release in THIS repo.
set -euo pipefail
KIND="${1:?run or release}"; ID="${2:?GitHub run ID or release tag}"; DEST="${3:?output dir}"
: "${GITHUB_REPOSITORY:?run only under GitHub Actions}" "${GH_TOKEN:?GitHub-generated workflow token required}"
test "$GITHUB_REPOSITORY" = 'Yolol100/transcriberen' || { echo 'wrong repository' >&2; exit 2; }
mkdir -p "$DEST"
case "$KIND" in
  run)
    [[ "$ID" =~ ^[1-9][0-9]{5,15}$ ]] || { echo 'invalid run ID' >&2; exit 2; }
    # An arbitrary repository workflow artifact is not an accepted caption source.
    run_name="$(gh api "repos/$GITHUB_REPOSITORY/actions/runs/$ID" --jq '.name')"
    run_repo="$(gh api "repos/$GITHUB_REPOSITORY/actions/runs/$ID" --jq '.repository.full_name')"
    test "$run_name" = 'Transcribe Public Source' && test "$run_repo" = "$GITHUB_REPOSITORY" || { echo 'not this repository transcription run' >&2; exit 2; }
    gh run download "$ID" --repo "$GITHUB_REPOSITORY" --pattern 'transcription-result-*' --dir "$DEST"
    mapfile -d '' inputs < <(find "$DEST" -type f -name 'channel-corpus.zip' -print0)
    test "${#inputs[@]}" -eq 1 || { echo 'expected exactly one channel-corpus.zip artifact' >&2; exit 2; }
    ;;
  release)
    [[ "$ID" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$ ]] || { echo 'invalid release tag' >&2; exit 2; }
    # User has to explicitly supply archive assets to a release. Never publish local Library material implicitly.
    gh release download "$ID" --repo "$GITHUB_REPOSITORY" --pattern 'YouTube_Kennisbron_Master.part-*.zip' --dir "$DEST" --clobber
    mapfile -d '' inputs < <(find "$DEST" -maxdepth 1 -type f -name 'YouTube_Kennisbron_Master.part-*.zip' -print0 | sort -z)
    test "${#inputs[@]}" -gt 0 || { echo 'no corpus shards in GitHub release' >&2; exit 2; }
    ;;
  *) echo 'unsupported source kind' >&2; exit 2 ;;
esac
# Pass only exact paths, without shell-evaluating archive names or source text.
printf '%s\n' "${inputs[@]}" > "$DEST/INPUT-FILES.txt"
echo "Source archives detected: ${#inputs[@]}" >&2
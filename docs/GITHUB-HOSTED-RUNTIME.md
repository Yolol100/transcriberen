# GitHub-hosted transcription runtime

The production queue uses only GitHub Actions hosted compute. There is no MSI, self-hosted runner, custom runner label, or machine fallback in the production path.

## Production path

1. Append exactly one request at `requests/queue/<request_id>.json` on `runtime-requests`.
2. GitHub-hosted `resolve` validates the immutable transport request and records the trusted `main` SHA.
3. GitHub-hosted `ubuntu-24.04` executes that exact SHA.
4. Channel discovery inspects at most 1000 `/videos` entries.
5. Per-video acquisition prefers bounded accountless public InnerTube/timedtext routes and falls back to the pinned yt-dlp toolchain.
6. Only exact 2026 upload dates enter the corpus.
7. At most 7 top-level comments are requested; comment-only failures remain non-gating and make the result partial.
8. Result, manifest, progress, current-run index, deterministic ZIP and checksums are validated.
9. GitHub attests the checksum receipt and uploads the result artifact.
10. Core access blocking is terminal. The run fails clearly after evidence is preserved; it never switches to another machine, login, cookie, proxy, CAPTCHA or token route.

## Control and compute

The GitHub connector/plugin can create requests, inspect commits and workflow state, and retrieve artifacts. It is the control surface. GitHub-hosted Actions is the execution surface.

## Optional local parity

`scripts/run_local.sh` remains available for manual parity/debugging. It is not part of queued production execution and is not a fallback for GitHub-hosted jobs.

## Safety boundaries

- no direct video, Short or playlist request;
- no media or audio download;
- no FFmpeg or Whisper;
- no cookies or logged-in sessions;
- no browser profile reuse;
- no proxy;
- no CAPTCHA or PO-token bypass;
- no automatic project/Skill knowledge promotion.

## Rollback

Revert the hosted-only migration commits in Git. Historical queue requests remain immutable audit evidence. Do not add a machine fallback as an emergency workaround; restore only through a reviewed repository change with the full contract/test/security update.

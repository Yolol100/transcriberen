# Threat model

## Assets

- Request intent and rights/access provenance.
- Public-source metadata and bounded task-scoped analysis content.
- Project/Skill knowledge promotion decisions.
- GitHub workflow identity, commit SHA, result hashes and attestations.
- Dedicated self-hosted runner integrity and its host operating environment.

## Trust boundaries

1. User/controller -> request validator.
2. Validator -> public network/YouTube.
3. Upstream source text -> normalization and comment candidate triage.
4. Runtime -> GitHub artifact/provenance storage.
5. Controlled-runtime evidence -> `webactueel-workflow` semantic review -> Project/Skill write gate.
6. `runtime-requests-selfhosted` transport -> GitHub-hosted resolver -> dedicated self-hosted runtime executing trusted `main`.

## Main threats and controls

- **SSRF / DNS rebinding:** public-address validation, request-time DNS pinning, redirect revalidation, proxy fail-closed in the direct HTTP path.
- **Unbounded resource use:** hard item/scan/comment limits, bounded defaults, timeouts and explicit unbounded opt-in under hard caps.
- **Prompt injection in sources/comments:** evidence is marked untrusted; comment ranking never promotes or executes source instructions.
- **Personal-data leakage:** direct commenter identity is removed and obvious identifiers in comment text are redacted. Public runs may persist bounded task-scoped transcript/comment analysis only when `analysis_content_allowed=true`; persisted text remains untrusted evidence and requires semantic review before promotion or reuse.
- **Stale/misattributed evidence:** exact source-set binding plus request hash, workflow ref, head SHA, run ID/attempt and checksum attestation.
- **Supply-chain substitution:** GitHub Actions are pinned to reviewed commit SHAs; release-critical downloaded tools are version- and digest-bound. yt-dlp uses the reviewed nightly `2026.08.20.234504` with SHA-256 `8962aa45f945ae5aa11ab49acab365e8baef569ec995149f99ae0ae3a19cae93`; the runtime does not silently auto-update to `latest`.
- **Access-control bypass:** cookies/login/proxy/CAPTCHA/media fallback are not activated for blocked public YouTube. An upstream anti-bot/access denial remains `access_blocked` evidence.
- **Legal/contractual overreach:** accountless analysis of publicly available YouTube captions, metadata and public comments is separated from republication/reuse. `youtube_access_basis` is provenance metadata; requested reuse remains separately gated by a concrete reviewed `rights_basis`.
- **Untrusted code on a public-repository self-hosted runner:** the self-hosted lane has no pull-request or generic reusable-workflow trigger, accepts only append-only queue pushes on `runtime-requests-selfhosted`, validates transport on a GitHub-hosted runner first and checks out only trusted `main` on the self-hosted host. Dedicated labels keep unrelated workflows off the runner.
- **Persistent-host credential theft or cross-job residue:** the runner host must be dedicated, contain no unrelated secrets or personal session state, use checkout with persisted credentials disabled, and be removed/disabled when not needed. Repository source controls do not replace OS-level isolation and patching.

## Residual risks

- Source text can contain identifiers not caught by simple redaction; semantic review remains required before reuse/promotion.
- YouTube/yt-dlp exposure of comments and replies is best effort, not proof of global completeness.
- YouTube can still impose server-side anti-bot, rate-limit or access restrictions on anonymous runtimes; these remain observable failures rather than a reason to enable bypasses.
- A persistent self-hosted runner is not an ephemeral clean VM. The repository can constrain triggers and trusted checkout paths but cannot prove host cleanliness, patch level or absence of unrelated credentials.
- Repository branch protection, runner enrollment/removal and host isolation are administration controls outside this repository's source tree and must be enforced in GitHub/host settings.

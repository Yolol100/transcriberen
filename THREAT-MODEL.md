# Threat model

## Assets

- Request intent and rights/access provenance.
- Public-source metadata and bounded task-scoped analysis content.
- Project/Skill knowledge promotion decisions.
- GitHub workflow identity, commit SHA, result hashes and attestations.

## Trust boundaries

1. User/controller -> request validator.
2. Validator -> public network/YouTube.
3. Upstream source text -> normalization and comment candidate triage.
4. Runtime -> GitHub artifact/provenance storage.
5. Controlled-runtime evidence -> `webactueel-workflow` semantic review -> Project/Skill write gate.

## Main threats and controls

- **SSRF / DNS rebinding:** public-address validation, request-time DNS pinning, redirect revalidation, proxy fail-closed in the direct HTTP path.
- **Unbounded resource use:** hard item/scan/comment limits, bounded defaults, timeouts and explicit unbounded opt-in under hard caps.
- **Prompt injection in sources/comments:** evidence is marked untrusted; comment ranking never promotes or executes source instructions.
- **Personal-data leakage:** direct commenter identity is removed and obvious identifiers in comment text are redacted. Public runs may persist bounded task-scoped transcript/comment analysis only when `analysis_content_allowed=true`; persisted text remains untrusted evidence and requires semantic review before promotion or reuse.
- **Stale/misattributed evidence:** exact source-set binding plus request hash, workflow ref, head SHA, run ID/attempt and checksum attestation.
- **Supply-chain substitution:** GitHub Actions are pinned to reviewed commit SHAs; release-critical downloaded tools are version- and digest-bound. yt-dlp uses the reviewed nightly `2026.08.20.234504` with SHA-256 `8962aa45f945ae5aa11ab49acab365e8baef569ec995149f99ae0ae3a19cae93`; the runtime does not silently auto-update to `latest`.
- **Access-control bypass:** cookies/login/proxy/CAPTCHA/media fallback are not activated for blocked public YouTube. An upstream anti-bot/access denial remains `access_blocked` evidence.
- **Legal/contractual overreach:** accountless analysis of publicly available YouTube captions, metadata and public comments is separated from republication/reuse. `youtube_access_basis` is provenance metadata; requested reuse remains separately gated by a concrete reviewed `rights_basis`.

## Residual risks

- Source text can contain identifiers not caught by simple redaction; semantic review remains required before reuse/promotion.
- YouTube/yt-dlp exposure of comments and replies is best effort, not proof of global completeness.
- YouTube can still impose server-side anti-bot, rate-limit or access restrictions on anonymous runtimes; these remain observable failures rather than a reason to enable bypasses.
- Repository branch protection is an account administration control outside this repository's source tree and must be enforced in GitHub settings/rulesets.

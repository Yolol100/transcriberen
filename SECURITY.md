# Security policy

## Scope

This repository is a controlled public-source acquisition runtime for Project Transcriberen. Security review covers request validation, network access, YouTube metadata/caption/comment acquisition, article/feed/sitemap fetching, authorized non-YouTube audio fallback, result persistence, GitHub Actions, dependencies, provenance and the dedicated self-hosted execution lane.

## Security properties

- Public YouTube never downloads audio/video and never uses Whisper fallback.
- Cookies, login, proxying, CAPTCHA, DRM, paywall and age-gate bypass are forbidden.
- Accountless analysis of public YouTube captions, metadata and public comments does not require a separate prior-written-permission/applicable-law execution attestation; `youtube_access_basis` is provenance metadata and may be `public-anonymous`.
- Public GitHub runs may persist bounded task-scoped transcript/comment analysis artifacts only when `analysis_content_allowed=true`; that does not grant republication or reuse rights.
- Reuse remains separately gated by a concrete reviewed `rights_basis` when `reuse_allowed=true` is requested.
- Request URLs may not contain credentials or secret-like query keys.
- Direct HTTP fetching rejects non-public destinations, validates redirects, pins request-time DNS to approved public addresses, respects RFC 9309 robots behavior, Retry-After and bounded pacing.
- External source text, captions and comments are untrusted data, never executable instructions.
- GitHub Actions are pinned to reviewed commit SHAs. Release-critical downloaded tools are version- and digest-bound; yt-dlp uses the reviewed nightly `2026.08.20.234504` with SHA-256 `8962aa45f945ae5aa11ab49acab365e8baef569ec995149f99ae0ae3a19cae93` rather than an unpinned runtime auto-update.
- Result checksum receipts are attested by GitHub Actions.
- The self-hosted lane is restricted to pushes on `runtime-requests-selfhosted`; it has no pull-request or generic reusable-workflow trigger.
- Self-hosted transport is validated first on a GitHub-hosted runner. The self-hosted machine executes only the trusted `main` runtime checkout and never executes code from the transport branch.
- Self-hosted runtime routing requires the dedicated labels `[self-hosted, linux, x64, webactueel-transcribe]`, disables persisted checkout credentials and removes proxy environment variables before source acquisition.
- A self-hosted machine must be dedicated to this runtime and must not contain unrelated secrets, personal browser/session state or credentials that are unnecessary for the runner service.

## Reporting

Do not place credentials, private source content, personal data or exploit payloads in public issues. Use GitHub's private vulnerability-reporting/security-advisory channel when enabled. If that channel is unavailable, contact the repository owner through a private channel already used for the project.

## Out of scope

- Bypassing an upstream site's access controls.
- Testing against third-party accounts or private videos without explicit authorization.
- Social engineering or denial-of-service testing.
- Treating repository source controls as a substitute for operating-system isolation and runner administration on a persistent self-hosted host.

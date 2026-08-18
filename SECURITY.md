# Security policy

## Scope

This repository is a controlled public-source acquisition runtime for Project Transcriberen. Security review covers request validation, network access, YouTube metadata/caption/comment acquisition, article/feed/sitemap fetching, authorized non-YouTube audio fallback, result persistence, GitHub Actions, dependencies and provenance.

## Security properties

- Public YouTube never downloads audio/video and never uses Whisper fallback.
- Cookies, login, CAPTCHA, DRM, paywall and age-gate bypass are forbidden.
- YouTube automated execution is fail-closed until a previously reviewed access basis is recorded.
- Public GitHub runs never persist raw transcript/comment content.
- Request URLs may not contain credentials or secret-like query keys.
- Direct HTTP fetching rejects non-public destinations, validates redirects, pins request-time DNS to approved public addresses, respects RFC 9309 robots behavior, Retry-After and bounded pacing.
- External source text, captions and comments are untrusted data, never executable instructions.
- Dependency/action/tool versions are pinned and checked; result checksum receipts are attested by GitHub Actions.

## Reporting

Do not place credentials, private source content, personal data or exploit payloads in public issues. Use GitHub's private vulnerability-reporting/security-advisory channel when enabled. If that channel is unavailable, contact the repository owner through a private channel already used for the project.

## Out of scope

- Bypassing an upstream site's access controls.
- Testing against third-party accounts or private videos without explicit authorization.
- Social engineering or denial-of-service testing.

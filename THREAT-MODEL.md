# Threat model

## Assets

- Request intent and rights/access basis.
- Public-source metadata and temporary analysis content.
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
- **Personal-data leakage:** direct commenter identity is removed, obvious identifiers in comment text are redacted, public GitHub runs cannot persist raw content, metadata is minimized when content persistence is disabled.
- **Stale/misattributed evidence:** exact source-set binding plus request hash, workflow ref, head SHA, run ID/attempt and checksum attestation.
- **Supply-chain substitution:** action/tool SHA pins, Python wheel hashes, lock regeneration audit, pip-audit, Dependency Review and CodeQL.
- **Access-control bypass:** cookies/login/proxy/CAPTCHA/media fallback are not activated for blocked public YouTube.
- **Legal/contractual overreach:** YouTube automated acquisition fails closed unless a reviewed access basis is supplied; the runtime never creates that legal conclusion itself.

## Residual risks

- Source text can contain identifiers not caught by simple redaction; semantic review remains required before reuse/promotion.
- YouTube/yt-dlp exposure of comments and replies is best effort, not proof of global completeness.
- Repository branch protection is an account administration control outside this repository's source tree and must be enforced in GitHub settings/rulesets.

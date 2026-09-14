# Branch retention policy

Status: active repository-governance policy
Scope: `Yolol100/transcriberen` Git branch references only

## Authority boundary

This repository remains a generic technical capability/evidence adapter. Branch names, commits and this retention policy are repository-operational state, not Project Transcriberen truth. Project scope and source truth remain in the registered Drive project sources.

## Retention classes

### Permanent

- `main` — canonical reusable source.
- `runtime-requests` and `runtime-requests-selfhosted` — retain only while they are registered runtime transport refs. They do not override `main` as source authority.

### Provider-managed ephemeral

- `dependabot/*` — retain while the corresponding provider-managed update or pull request is active; GitHub may remove these after normal PR lifecycle completion.

### Historical/development retained

The following branch families are explicitly retained as historical/development refs until a safe admin-capable deletion sweep is available:

- `agent/*`
- `feature/*`
- `fix/*`
- `qa/*`
- `maintenance/*`
- `portfolio/*`
- `source-policy-*`
- `sync/*`
- `toolkit-*`
- `upgrade/*`
- dated migration/runtime branches such as `deno-*`
- `__do-not-use`

These refs have no production, project-source or controller authority merely because they exist. In particular, previously aligned refs such as `agent/post-merge-status-evidence`, `agent/topic-filter-private-output` and `__do-not-use` are retained historical refs, not active runtime entrypoints.

## Safe deletion gate

A retained historical/development ref may be deleted only when all of the following are rechecked immediately before deletion:

1. it is not `main` and is not a currently registered runtime transport ref;
2. it has no open pull request or active workflow/request dependency;
3. comparison with `main` proves that deletion will not discard unique unrecovered source that must be preserved;
4. any required evidence has already been retained in an immutable run artifact, issue/PR record, release artifact or other approved evidence store;
5. deletion uses a branch-delete/admin-capable surface; do not emulate deletion with force rewrites;
6. post-delete readback proves the intended ref is absent and `main` is unchanged.

If any condition is unknown, retain the branch and record the reason instead of deleting it.

## Prohibited behavior

- Do not force-rewrite historical refs merely to make them match `main`.
- Do not treat a retained branch as project truth.
- Do not keep target/client-specific runtime data on `main` under the guise of retention.
- Do not delete a branch solely because its name looks old.

## Review

Review retained historical/development refs during repository-governance audits and after major runtime migrations. Cleanup is gap-only: delete only refs that pass the safe deletion gate; otherwise explicit retention is the accepted state.

# Repository governance

This repository is a generic controlled runtime. The default branch must stay reusable and must not store real request state.

## Required main-branch controls

Configure GitHub Rulesets or branch protection for `main` with all of these controls:

- require a pull request before merging;
- require the current Toolkit Contract, CodeQL (Python and Actions), Dependency Audit/Dependency Review, and Dependency Lock Audit checks;
- require branches to be up to date before merging;
- block force pushes and branch deletion;
- do not allow bypass for normal contributors;
- prefer signed commits when the repository administration model supports them.

## Required runtime-requests controls

`runtime-requests` is an operational append-only transport branch, not a development branch. Configure a GitHub Ruleset or branch protection so normal contributors cannot rewrite or delete history, force-push, or bypass the queue contract. Automated request creation may append exactly one `requests/queue/<request_id>.json` file per transport commit; the workflow independently validates that invariant before using the request.

## Required runtime-requests-selfhosted controls

`runtime-requests-selfhosted` is a second operational append-only transport branch for the dedicated self-hosted lane. Apply the same history, force-push, deletion and append-only protections as `runtime-requests`.

The self-hosted workflow must remain narrower than the normal hosted workflow:

- trigger only from pushes to `runtime-requests-selfhosted` under `requests/queue/*.json`;
- never add `pull_request`, `pull_request_target` or generic reusable-workflow triggers to the self-hosted lane;
- resolve and validate the transport request on a GitHub-hosted runner before the self-hosted job is eligible;
- route the runtime job only to `[self-hosted, linux, x64, webactueel-transcribe]`;
- never execute code from the transport branch on the self-hosted machine; the runtime checkout must stay pinned to `main` with persisted credentials disabled;
- keep the self-hosted machine dedicated and free of unrelated secrets, credentials and personal browser/session state.

Because the repository is public, repository source controls cannot make a persistent self-hosted runner equivalent to an isolated GitHub-hosted VM. Host isolation, runner enrollment/removal and branch/ruleset enforcement remain repository-administration responsibilities.

The runtime supports `workflow_dispatch` for manual/debug runs, immutable request-queue pushes on `runtime-requests` for normal Chat/connector routing, immutable request-queue pushes on `runtime-requests-selfhosted` for the dedicated direct-network lane, and `workflow_call` for registered repo-to-repo callers. Do not commit live request data to `requests/transcribe.json`; that file is only a disabled generic example/local input.

Branch protection and Rulesets are external repository-administration controls. Repository code and tests can document and detect their absence, but cannot enforce them without GitHub administration permissions.

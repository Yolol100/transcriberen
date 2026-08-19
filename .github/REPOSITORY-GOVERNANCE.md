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

The runtime supports `workflow_dispatch` for manual/debug runs, immutable request-queue pushes on `runtime-requests` for Chat/connector routing, and `workflow_call` for registered repo-to-repo callers. Do not commit live request data to `requests/transcribe.json`; that file is only a disabled generic example/local input.

Branch protection and Rulesets are external repository-administration controls. Repository code and tests can document and detect their absence, but cannot enforce them without GitHub administration permissions.

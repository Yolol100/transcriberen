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

The runtime workflow is started with `workflow_dispatch`. Do not commit live request data to `requests/transcribe.json`; that file is only a disabled generic example/local input.

Branch protection is an external repository-administration control. Repository code and tests can document and detect its absence, but cannot enforce it without GitHub administration permissions.

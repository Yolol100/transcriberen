# Corpus Knowledge Review (additional, isolated capability)

This is a **GitHub-hosted execution** extension. It never changes channel acquisition, collection limits, the append-only `runtime-requests` branch or `toolkit-contract.json`. No OpenAI API key, user-defined secret, other account, MCP server, self-hosted runner, or second repository is required.

## What actually runs

Unlike **new acquisition**, which remains limited to 2026 videos and 7 newly fetched comments, **retrospective analysis of owner-supplied archive evidence intentionally includes older years and every already-saved comment (subject to safe size limits)**. This never expands YouTube network acquisition.

The manually dispatched `Corpus Knowledge Review` GitHub Action downloads a prior `Transcribe Public Source` artifact from **this** repository, or a ZIP shard collection deliberately published to a same-repository GitHub Release by its owner. It validates ZIP member paths and per-video identifiers, checks transcript hashes and selects a deterministic logical batch of **500 unique video IDs**. Each batch is divided into retryable slices of 20 videos (at most four concurrent jobs).

In `review` mode the GitHub-hosted runner downloads SHA-256 verified `llama.cpp` (`b11425`, `6a47856d08ecc4030b2fa8b8bf761c96d142d689567f69a0f75e42de430dc34c`) from GitHub and the public Apache-2.0 `ggml-org/Qwen3-1.7B-GGUF` Q4_K_M model (`d2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5`). Model inference occurs on the runner itself at `127.0.0.1`. The weights are a public anonymous **dependency download**, not a hosted inference service or additional account. A missing download or checksum mismatch is a blocker, never grounds for sending input to a different service.

**Do not use GitHub Models:** it was retired on July 30, 2026. GitHub Copilot from a personal repository would require additional credentials that are out of scope.

## Run from GitHub Actions

1. Open **Actions → Corpus Knowledge Review → Run workflow** after this branch is merged to `main`.
2. For `source_kind=run`, enter a prior same-repo **Transcribe Public Source run ID**, whose `transcription-result-*` artifact contains `channel-corpus.zip`.
3. For existing v15 Library shard files, `source_kind=release` accepts same-repo release assets matching `YouTube_Kennisbron_Master.part-*.zip`. The private ChatGPT Library cannot be fetched from a GitHub-hosted runner without an additional integration. **Do not upload third-party copyrighted or private transcripts to a public release without redistribution rights.** No source artifact/release means `BLOCKED_SOURCE`.
   When using a release, publish the matching authorized `YouTube_Kennisbron_Master.zip` metadata index as well, and set `master_sha256` to its verified SHA-256. The reviewer requires an exact ID match between all supplied shards and this pinned index, and uses its corrected v15 routes/authority. A missing index, changed SHA, conflicting video identity or missing comment fails closed. Never publish private/copyrighted files without authorization.
   Before any historical review starts, the validator also reads `YouTube_Kennisbron_Shards_2026-10-03.json` from that SHA-pinned master and requires every declared shard ZIP to have the exact filename, file size and SHA-256, with no missing/extra shards and a manifest record total equal to the routing index. Existing same-repo channel-run artifacts continue to use their original receipt validator. These guards do not authorize republication or count as an AI review.
4. Choose `batch=1` for the first 500 videos. `scope=inventory` only checks archive membership; it **does not** review semantics. Choose `scope=slice`, `slice=0` for 20 videos or `scope=batch` for all 500 split across 25 slices. The last batch has fewer slices automatically.
5. Review the `knowledge-review-batch-*-slice-*` workflow artifacts. `resume_run_id` can target an earlier Corpus Knowledge Review run. Only outputs with the same video, transcript digest, comment digest, model digest and policy version can be reused, including completed chunks of an interrupted video.

## Resume integrity and long-course transcripts

Downloaded run artifacts are **untrusted input**. Before reusing a previous video review, the reviewer now validates the input text digest, model digest, reviewer policy, chunk-size, source metadata, each exact transcript/comment span, per-chunk evidence claims, and completion flags. A mismatched or malformed checkpoint is reprocessed instead of being marked complete. If the chunk layout changes, previous model output is not silently reused. No saved record can set `project_source_compared`, `primary_sources_verified`, `human_qa_approved` or `auto_promoted` to true through the review pipeline.

Some verified historical master-shard transcripts exceed 2 MB; the importer accepts complete UTF-8 text up to a bounded 3 MB per-video limit. It still rejects over-limit items rather than truncating them. These are evidence-integrity fixes, not a broader YouTube acquisition policy or knowledge-promotion authorization.

## Provenance and bounded historical-corpus intake

Retrospective video transcripts are accepted only up to **3,000,000 UTF-8 bytes per video**, without truncation. This historical evidence limit is recorded in `knowledge-analysis-contract.json`, validated by the repository doctor, and is separate from the unchanged public channel acquisition contract. Previously analyzed source bytes are never silently discarded.

A previous `Corpus Knowledge Review` result is resumable only when its GitHub run originated from **`workflow_dispatch` on `main` at the identical immutable code commit (`GITHUB_SHA`)**. The review additionally checks the current source metadata, full transcript/comment digests, comment retrieval status, analysis policy, model digest, chunk spans and anchored evidence against the original text. Old or tampered checkpoints are reprocessed or explicitly rejected; a zero-claim chunk is not automatically proof of factual verification.

## Evidence boundaries

- `inventory_only`: archive/input identity and batch selection checked; no semantic review.
- `review_in_progress`: some chunks read; never final.
- `ai_reviewed_pending_independent_verification`: every available transcript character and stored comment chunk was passed to local inference and the candidate claims contain verifiable exact excerpt positions. This is **not** expert review, verified technical truth, Skill acceptance or project acceptance.
- `no_transcript`: original video transcript unavailable and no saved comments.
- `no_transcript_comments_reviewed`: saved comments were analyzed but the video itself has no available transcript.
- `ai_reviewed_unverified_legacy_source_hash`: local analysis read the inline transcript text, but the legacy shard's declared SHA-256 differs from those exact bytes; independent integrity verification is mandatory before any promotion.
- `blocked_local_model` / `blocked_time_budget`: partial evidence, safe retry needed.

Some older Library shard records embed extra timestamped transcript material. Their recorded original transcript SHA-256 can differ from the SHA-256 of the complete inline text (2,160 of 3,201 records in a checked shard). The importer preserves BOTH hashes and records an explicit `legacy_claim_mismatch` warning rather than silently changing source material or aborting every unrelated video.

Channel source manifests with `partial`/`access_blocked` statuses preserve unresolved counts and partial reasons in `inventory.json`. Their valid saved transcripts may be examined, but the source never becomes falsely complete.

The module **never** automatically writes to Google Drive, a live Skill, a project source or any production website. Creator claims, comment complaints and AI-generated suggestions remain hypotheses. The repo has no private Library, live Drive project comparison or independent official source validation mechanism. `webactueel-workflow` and the relevant specialist must review and accept any knowledge changes elsewhere, with source provenance and current official documentation.

Each artifact holds only short evidence snippets (maximum 110 characters), metadata, source IDs, SHA-256s, offsets, status and reviewer warnings. Raw transcripts and comment collections are not committed to `main` or included in review outputs. GitHub Actions artifacts and release assets from public repositories can be accessible to other readers: apply privacy/copyright restrictions before publishing source ZIPs.

## Validated release regression

Pull-request CI runs a SHA-pinned local-model canary plus an end-to-end synthetic ZIP input through `scripts/knowledge_analyze.py` and confirms that transcript and comment chunks reach persisted JSON evidence. The model binaries/weights use a GitHub Actions cache, and hashes are revalidated on every use. This tests functional local inference but does not validate the 18,875-video corpus or expert accuracy.

## Limits

The public GitHub standard `ubuntu-24.04` runner has 4 CPUs and 16 GB RAM; local 1.7B-model inference is slower and less reliable than larger hosted models. There is a six-hour maximum job duration; each slice has a shorter explicit time budget and records resumable partial checkpoints. Inference source accuracy is not guaranteed: independent QA remains mandatory for any material source/Skill update.

The built-in, automatically generated `GITHUB_TOKEN` is used *only* to read artifacts or releases from this same repository. No manually supplied token, PAT, user API key or hosted AI inference API is used.

## Local validation

```
python -m unittest discover -s tests -p 'test_knowledge_analysis.py' -v
python scripts/knowledge_analyze.py --source /path/to/channel-corpus.zip --mode inventory --batch 1 --slice 0 --slice-size 20
```

Tests use deterministic fake inference responses, never a network model or YouTube request. The existing acquisition code and its suite remain unchanged.


## Phase 4: source-bound claim comparison without automatic knowledge updates

The model reads transcript/comment chunks. Its per-video `claims` are hypotheses,
not an authoritative assessment of Webactueel, WordPress, or any external product.
Only the central `webactueel-workflow` owner may coordinate project-source
comparison and promotion. The source contents are intentionally **not** copied
into this public repository or sent to a hosted AI service.

When a real owner-authorized review run has produced compact video JSON files,
run the offline **read-only** classification preparation step from trusted source:

```bash
python scripts/knowledge_phase4.py \
  --reviews-dir "$RUNNER_TEMP/results/videos" \
  --out "$RUNNER_TEMP/results/phase4-proposals.json"
```

GitHub Actions now emits this evidence-only proposal ledger after a fully successful
local AI slice. PRs additionally exercise it after a real SHA-pinned Qwen3
**synthetic fixture** canary. Neither operation fetches project/official sources,
confirms ownership, or approves claims. Without a corpus release there is no
full-corpus phase-4 ledger or finished review. GitHub Actions artifacts expire.

**Four proposed categories** (all require later independent project-source and
specialist review; none means accepted, promoted or auto-written):

- `UPDATE`: genuinely new candidate; require exactly one specialist owner,
  a verified current project-source ID + SHA-256, a dated official HTTPS source,
  concrete rationale and subsequent external QA approval. Submitted fields alone
  never prove that the sources were checked.
- `ALREADY_COVERED`: claim apparently covered by an existing project rule; cite
  its current source ID/hash and explain the match; no duplicate source write.
- `REJECTED`: non-transferable, conflicting, misleading, stale or unsupported
  claim with an explicit rationale. A model comment is never a creator quotation.
- `NEEDS_VERIFICATION`: safe **default**; includes unknown/partial access,
  missing source comparisons, mutable platform facts and unreviewed claims.

To import *reviewer-proposed* categories offline, supply `--decisions decisions.json`
(an array with each `claim_id`, `category`, `rationale`, and, where required,
`project_source_id`, `project_source_sha256`, `owner`,
`official_source_url`, `official_checked_at`). The decision file must
remain outside committed repository/project sources until reviewed by the
right owner. Its URLs/hashes are untrusted references, not source readback.
A legacy transcript digest mismatch forbids `UPDATE` proposals pending
source remediation; partially reviewed videos are excluded.

The output deliberately retains
`external_project_sources_fetched=false`,
`official_sources_checked_by_tool=false`,
`human_qa_approved=false`, `auto_promoted=false`, and
`source_quote_rechecked_against_raw_transcript=false`. All four category
labels are **proposals**. The owner must separately verify the exact
Library/Drive source, its version/hash, the underlying evidence excerpt,
the current primary official source and real runtime scope; then perform
any authorized project or Skill write through the Webactueel controller.
Never present this ledger as an AI-vetted source of truth, 18,875 completed
reviews or authorization to republish caption/comment archives.


## Phase 5 — independent end-to-end acceptance and blocked-source handling

A green PR model canary only proves synthetic archive -> pinned localhost
Qwen3 -> JSON evidence -> non-promoting phase-4 ledger. It does **not**
prove that the historical corpus has been read, that claims are true or that
missing/blocked captions/comments have become available.

Before accepting a real owner-authorized corpus run:

1. Reconfirm the **live Project Transcriberen** source-set and authorized
   Library master version, ZIP SHA-256, master routing and shard-manifest
   SHA-256s. Do not silently replace project facts with constants from this
   repository. A public GitHub release of third-party transcripts/comments
   requires established redistribution rights; without one accepted GitHub
   source keep the status \`BLOCKED_SOURCE\` and **do not dispatch**.
2. Match each workflow run to the immutable trusted main SHA, fixed model
   and inference engine digests, correct authorized source identifier and
   source receipt. Validate *all* expected logical 500-video batches and
   20-video slices against a deterministic sorted list of source video IDs,
   including the smaller final batch. Missing, duplicated, truncated or
   mismatched slices are **not** successful completion.
3. For every selected video require the original signed-off source context,
   exact transcript and saved-comment chunk coverage, checked model output
   per span, bounded evidence offsets, preserved source integrity statuses
   and explicit partial/blocked/missing data. The phase-4 ledger now
   cross-checks saved completed chunks and their claim counters; its
   \`source_quote_rechecked_against_raw_transcript=false\` remains accurate.
   A claim cannot be marked independently verified on that basis alone.
4. Verify unique source IDs, model/route versions, deduplication, no
   misattributed community comments and no missing chunks. Reconcile
   claim categories with the current Drive owner source and official
   primary evidence. \`UPDATE\`, \`ALREADY_COVERED\` and \`REJECTED\`
   in GitHub remain *proposed* dispositions, not domain acceptances.
5. A suitable specialist owner must independently approve each proposed
   project-source change using live source hashes and rollback/readback.
   Corpus ingestion never automatically writes to a Skill, Project Drive
   source, user memory, production website or another repository.
6. Read back all mandatory repository checks on the final **main** commit:
   Repository Doctor, Toolkit Contract/unittests, Dependency Audit,
   CodeQL and the PR synthetic local-Qwen3 end-to-end canary. Distinguish
   PR canary evidence from actual reviewed-corpus production receipts.

**Release decision:** \`CODE_QA_PASS\` is allowed only for the implementation
with proven checks. \`FULL_CORPUS_ACCEPTED\` requires every source, run,
video, model and owner-check above. A missing right or GitHub artifact,
a count shortfall, partial comments/captions, unconfirmed source hashes or
missing independent approval yields \`NO_GO\` / \`BLOCKED_SOURCE\`
for the affected completeness or knowledge-promotion claim.

The repository is public and the current workflow uses same-repo artifacts
or explicitly authorized release assets only. GitHub administration rules
such as force-push/deletion bypass and review protection require suitable
GitHub admin readback; a \`protected=true\` branch bit or green Actions
cannot close the open administrative-governance issue. Never loosen branch
protection or publish rights-restricted archive bytes as a workaround.

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

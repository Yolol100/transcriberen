# ChatGPT to GitHub corpus handoff

The GitHub repository stays public. Source ZIPs and source quotes must not be published in Git, Releases, Actions inputs, logs, or public artifacts.

The current ChatGPT GitHub connector cannot upload a conversation ZIP directly to a GitHub-hosted Actions runner. This missing private source transport is BLOCKED, not a completed feature.

Proposed route after an authorized bridge exists: ChatGPT ZIP intake and SHA validation, private source storage, narrow GitHub OIDC fetch, 500-video review batches, exact source and model receipts, independent project/Skill comparison, and results returned privately to ChatGPT.

Source comparison categories are provisional: UPDATE, ALREADY_COVERED, REJECTED, NEEDS_VERIFICATION. Nothing updates canonical sources automatically.

Techniques: context-engineering, retrieval-grounding, prompt-chaining, closed-loop-execution, adversarial-validation, and independent-verifier. Stop at an unavailable connector instead of simulating success.

References: GitHub OIDC/AWS documentation, LlamaIndex hash-based deduplication, Hugging Face Datasets checkpointing, and llama.cpp structured JSON.

# External caption corpus intake

This repository keeps its network acquisition runtime narrow: one direct public YouTube video or Short, one real caption track. A supplied batch corpus does **not** expand that network capability.

`validate_external_corpus.py` is a separate local file-intake capability for user-supplied corpus packages. It verifies the package before any transcript is considered for research.

## Validate

```bash
python scripts/validate_external_corpus.py /path/to/OUTPUT.zip --output-dir external-corpus-intake --json
```

The validator checks:

- safe ZIP structure before extraction (no traversal, symlinks or duplicate paths; bounded member count and uncompressed size);
- one canonical run receipt and optional matching `RESULT-RECEIPT_LATEST.json`;
- receipt/manifest run ID, version, status, counts and partial-reason parity;
- manifest SHA-256 and result ZIP SHA-256 from the receipt;
- every `saved` transcript against `RUN-SHA256.txt`;
- unique video IDs and safe `items/` paths.

It writes:

- `external-corpus-intake.json` — compact validated provenance and terminal status;
- `candidate-index.json` and `candidate-index.csv` — metadata plus transcript SHA-256 for later claim extraction.

Transcript text is deliberately omitted from these normalized indexes.

## Knowledge boundary

A validated package is `evidence_only`. `partial` remains `partial`. Validation proves package integrity and traceability; it does not prove the truth or currentness of statements inside a transcript.

Before promotion to a Webactueel project source or Skill:

1. extract the specific claim;
2. deduplicate it against current project knowledge;
3. verify changeable product/platform facts against current primary or official sources;
4. assign exactly one content owner;
5. let that owner accept or reject the claim;
6. use the normal project-source write, rollback, readback and QA gates.

This capability never stores project identity or project source-set versions as repository truth.

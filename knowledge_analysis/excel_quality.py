"""Conservative, offline preflight for Excel-derived YouTube discovery evidence.

Inputs are untrusted discovery records. A contextual match is NOT a verified claim,
creator endorsement, project source change, or permission to write.
"""
from __future__ import annotations

import csv
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
MAX_CSV_BYTES = 120 * 1024 * 1024
MAX_ROWS = 250_000
MAX_EXCERPT = 4_000


def normalize_video_id(value: str) -> str:
    """Drop only Excel's literal leading apostrophe; never change the ID bytes."""
    video_id = str(value).strip()
    if video_id.startswith("'") and VIDEO_ID.fullmatch(video_id[1:]):
        video_id = video_id[1:]
    if not VIDEO_ID.fullmatch(video_id):
        raise ValueError("Malformed video ID")
    return video_id

# Bound each matching decision to nearby context, rather than entire transcripts.
ENTITY_RULES: dict[str, tuple[str, str]] = {
    "microsoft clarity": (r"\b(?:microsoft\s+)?clarity\b", r"\bmicrosoft\s+clarity\b|\b(?:heatmaps?|session\s+recordings?|click\s+maps?|behavior(?:al)?\s+analytics)\b"),
    "rag": (r"\brag\b|\bretrieval[ -]augmented\s+generation\b", r"\bretrieval[ -]augmented\s+generation\b|\b(?:retriev(?:al|e)|embeddings?|vector\s+(?:store|database|search)|llm|knowledge\s+base|rag\s+(?:pipeline|system|workflow))\b"),
    "zero to one": (r"\bzero\s+to\s+one\b", r"\b(?:peter\s+thiel|blake\s+masters|zero\s+to\s+one\s+(?:book|by\s+peter)|book\s+(?:called|titled|named)?\s*zero\s+to\s+one|read(?:ing)?\s+(?:the\s+)?(?:book\s+)?zero\s+to\s+one)\b"),
    "the one thing": (r"\bthe\s+one\s+thing\b", r"\b(?:gary\s+keller|jay\s+papasan|the\s+one\s+thing\s+(?:book|by\s+gary)|book\s+(?:called|titled|named)?\s*the\s+one\s+thing|read(?:ing)?\s+(?:the\s+)?(?:book\s+)?the\s+one\s+thing)\b"),
    "astro": (r"\bastro\b", r"\b(?:astro\.build|static\s+site\s+generator|islands?\s+architecture|web\s+framework|astro\s+(?:component|project|site|framework)|npm\s+create\s+astro)\b"),
    "atomic habits": (r"\b(?:atomic|a\s+tomic|tomic)\s+habits\b", r"\b(?:james\s+clear|atomic\s+habits\s+(?:book|by)|book\s+(?:called|titled|named)?\s*atomic\s+habits|read\s+(?:the\s+)?book)\b|\b(?:book|author|habit\s+formation)\b"),
}


@dataclass(frozen=True)
class EntityReview:
    canonical_entity: str
    gate: str
    reason: str
    auto_promoted: bool = False


def classify_entity(entity: str, excerpt: str, title: str = "") -> EntityReview:
    """Classify a local excerpt for *review priority*, never for truth/acceptance.

    A title match alone cannot establish contextual evidence. An ambiguous or
    unsupported match remains open for human review, rather than being rejected.
    """
    canonical = " ".join(str(entity).casefold().split())
    rule = ENTITY_RULES.get(canonical)
    if rule is None:
        return EntityReview(canonical, "NOT_RULED_NEEDS_REVIEW", "No specific context rule; inspect source manually")
    if not isinstance(excerpt, str) or len(excerpt) > MAX_EXCERPT:
        return EntityReview(canonical, "AMBIGUOUS_NEEDS_REVIEW", "Excerpt missing or exceeds review bound")
    text = " ".join(excerpt.casefold().split())
    mention_re, context_re = map(lambda item: re.compile(item, re.IGNORECASE), rule)
    matches = list(mention_re.finditer(text))
    if not matches:
        return EntityReview(canonical, "AMBIGUOUS_NEEDS_REVIEW", "Entity name absent from evidence excerpt (title alone is insufficient)")
    for match in matches:
        # Restrict corroborating terms to the SAME local phrase, not a different
        # discussion elsewhere in the video. This remains candidate-level only.
        near = text[max(0, match.start() - 135): min(len(text), match.end() + 135)]
        if context_re.search(near):
            # Do not accept a match simply because its own bare name occurs.
            # Full proper product/book names are meaningful local context.
            if canonical == "microsoft clarity" and not (
                re.search(r"\bmicrosoft\s+clarity\b", near)
                or re.search(r"\b(?:heatmaps?|session\s+recordings?|click\s+maps?|behavior(?:al)?\s+analytics)\b", near)
            ):
                continue
            if canonical == "rag" and not (
                re.search(r"\bretrieval[ -]augmented\s+generation\b", near)
                or re.search(r"\b(?:retriev(?:al|e)|embeddings?|vector\s+(?:store|database|search)|llm|knowledge\s+base|rag\s+(?:pipeline|system|workflow))\b", near)
            ):
                continue
            return EntityReview(canonical, "CONTEXT_PRESENT_UNVERIFIED", "Local topic/book context present; independent claim and source check required")
    return EntityReview(canonical, "AMBIGUOUS_NEEDS_REVIEW", "No supporting context close to ambiguous name")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_CSV_BYTES:
        raise ValueError("CSV missing, symlinked or above maximum input size")
    # Corrupted zero-byte exports must never enter the review pipeline.
    with path.open("rb") as check:
        for chunk in iter(lambda: check.read(1024 * 1024), b""):
            if b"\x00" in chunk:
                raise ValueError("Corrupt CSV contains NUL bytes")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError("CSV headers missing or duplicated")
        rows: list[dict[str, str]] = []
        for row in reader:
            if len(rows) >= MAX_ROWS:
                raise ValueError("CSV row limit exceeded")
            if None in row or any(v is None for v in row.values()):
                raise ValueError("Inconsistent CSV row width")
            rows.append(row)
    return rows


def _require_columns(rows: list[dict[str, str]], names: set[str], label: str) -> None:
    if not rows or not names.issubset(rows[0]):
        raise ValueError(f"{label}: expected columns {sorted(names)} and nonempty input")


def inspect_mentions(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    _require_columns(rows, {"Bron", "Video ID", "Fragment"}, "mention export")
    out = []
    for row in rows:
        entity = " ".join(row["Bron"].casefold().split())
        if entity not in ENTITY_RULES:
            continue  # Unruled entities are not automatically rejected or approved.
        vid = normalize_video_id(row["Video ID"])
        result = classify_entity(entity, row["Fragment"], row.get("Videotitel", ""))
        out.append({"video_id": vid, "canonical_entity": result.canonical_entity,
                    "gate": result.gate, "reason": result.reason, "auto_promoted": "false"})
    return out


def _flag(value: str, label: str, *, dutch: bool) -> bool:
    norm = str(value).strip().casefold()
    valid = ({"ja", "yes", "true", "1"} if dutch else {"true", "1", "yes", "ja"})
    invalid = {"nee", "no", "false", "0"}
    if norm in valid:
        return True
    if norm in invalid:
        return False
    raise ValueError(f"Invalid/missing exact-date flag for {label}")


def compare_date_flags(excel: list[dict[str, str]], raw: list[dict[str, str]]) -> list[dict[str, str]]:
    """Require matching unique video-ID sets; report disagreement, never rewrite dates."""
    _require_columns(excel, {"Video ID", "Datum betrouwbaar", "Datum"}, "Excel video-index export")
    _require_columns(raw, {"video_id", "date_verified", "date"}, "raw video-screening export")
    ids: dict[str, dict[str, str]] = {}
    for row in raw:
        vid = normalize_video_id(row["video_id"])
        if vid in ids:
            raise ValueError("Invalid or duplicate raw video ID")
        _flag(row["date_verified"], vid, dutch=False)
        ids[vid] = row
    seen = set()
    conflicts = []
    for row in excel:
        vid = normalize_video_id(row["Video ID"])
        if vid in seen:
            raise ValueError("Invalid or duplicate Excel video ID")
        seen.add(vid)
        if vid not in ids:
            raise ValueError("Excel video ID missing in raw video scan")
        excel_exact = _flag(row["Datum betrouwbaar"], vid, dutch=True)
        raw_row = ids[vid]
        raw_exact = _flag(raw_row["date_verified"], vid, dutch=False)
        if excel_exact != raw_exact:
            conflicts.append({"video_id": vid, "excel_exact": str(excel_exact).lower(),
                              "raw_exact": str(raw_exact).lower(),
                              "excel_date": row["Datum"], "raw_date": raw_row["date"],
                              "review": "REQUIRES_SOURCE_VERIFICATION_NO_AUTO_CORRECTION"})
    if seen != set(ids):
        raise ValueError("Raw video IDs missing from Excel index")
    return conflicts


def review_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    return dict(sorted(Counter(r["gate"] for r in rows).items()))

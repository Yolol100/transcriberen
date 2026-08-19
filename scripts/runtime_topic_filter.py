#!/usr/bin/env python3
"""Runtime entrypoint that adds explainable metadata topic filtering.

The canonical runtime remains scripts/runtime.py. This wrapper narrows hydrated
YouTube candidates before selection when youtube.include_keywords is present.
It deliberately filters metadata only; transcript text is not needed to decide
whether a channel video belongs to the requested topic.
"""
import json
import re
from pathlib import Path

import youtube_runtime


_ORIGINAL_COLLECT = youtube_runtime.collect
_ORIGINAL_YEAR_MATCHES = youtube_runtime.year_matches
_ORIGINAL_DISCOVERY_PLAYLIST_END = youtube_runtime._discovery_playlist_end


def _normalized_tokens(value):
    """Normalize separators so cold-email, cold_email and cold email are equal."""
    text = str(value or "").casefold()
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    return tuple(token for token in text.split() if token)


def _metadata_tokens(meta):
    values = [meta.get("title"), meta.get("description")]
    for key in ("tags", "categories"):
        raw = meta.get(key) or []
        if isinstance(raw, (list, tuple, set)):
            values.extend(raw)
        else:
            values.append(raw)
    return set(_normalized_tokens(" ".join(str(value or "") for value in values)))


def include_keywords_match(meta, yt):
    """OR across keyword phrases; every token in a phrase must be present."""
    phrases = yt.get("include_keywords") or []
    if not phrases:
        return True
    haystack = _metadata_tokens(meta)
    for phrase in phrases:
        wanted = _normalized_tokens(phrase)
        if wanted and all(token in haystack for token in wanted):
            return True
    return False


def _filtered_year_matches(meta, yt):
    return _ORIGINAL_YEAR_MATCHES(meta, yt) and include_keywords_match(meta, yt)


def _topic_aware_playlist_end(req):
    yt = req.get("youtube", {})
    if yt.get("include_keywords"):
        # Topic filtering needs the configured scan window, not merely max_items;
        # otherwise an early non-topic prefix could hide later matching videos.
        scan_limit = int(yt.get("scan_limit", 500))
        return scan_limit or None
    return _ORIGINAL_DISCOVERY_PLAYLIST_END(req)


def collect_with_topic_filter(req, results_dir):
    youtube_runtime.year_matches = _filtered_year_matches
    youtube_runtime._discovery_playlist_end = _topic_aware_playlist_end
    try:
        content, index = _ORIGINAL_COLLECT(req, results_dir)
    finally:
        youtube_runtime.year_matches = _ORIGINAL_YEAR_MATCHES
        youtube_runtime._discovery_playlist_end = _ORIGINAL_DISCOVERY_PLAYLIST_END

    keywords = list((req.get("youtube") or {}).get("include_keywords") or [])
    index["include_keywords"] = keywords
    index["topic_filter_basis"] = "metadata:title+description+tags+categories" if keywords else None
    index["topic_filter_normalization"] = "casefold+separator-to-space+token-match" if keywords else None
    Path(results_dir, "youtube-index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return content, index


def main():
    # Importing runtime patches youtube_runtime.run to the bounded subprocess
    # adapter. Keep that side effect inside actual execution so unit-test import
    # order cannot leak runtime state into unrelated tests.
    import runtime as base_runtime

    youtube_runtime.collect = collect_with_topic_filter
    base_runtime.youtube_runtime.collect = collect_with_topic_filter
    base_runtime.main()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Runtime entrypoint that adds explainable metadata topic filtering.

The canonical extraction policy remains scripts/runtime.py. This wrapper adds
metadata topic filtering, bounded accountless InnerTube/yt-dlp fallback and
production subtitle-normalization hardening before calling that runtime.
"""
import json
import re
from pathlib import Path

import innertube_runtime
import youtube_runtime


_ORIGINAL_COLLECT = youtube_runtime.collect
_ORIGINAL_YEAR_MATCHES = youtube_runtime.year_matches
_ORIGINAL_DISCOVERY_PLAYLIST_END = youtube_runtime._discovery_playlist_end
_ORIGINAL_METADATA_FOR = youtube_runtime.metadata_for
_ORIGINAL_DOWNLOAD_CAPTION = youtube_runtime.download_caption
_ORIGINAL_COMMENTS_FOR = youtube_runtime.comments_for
_TIMING_RE = re.compile(
    r"(?:\d{1,2}:)?\d{2}:\d{2}[,.]\d{3}\s+-->\s+"
    r"(?:\d{1,2}:)?\d{2}:\d{2}[,.]\d{3}"
)
_BLOCK_HEADERS = {"STYLE", "REGION"}
_HEADER_METADATA_PREFIXES = ("Kind:", "Language:")


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
        scan_limit = int(yt.get("scan_limit", 500))
        return scan_limit or None
    return _ORIGINAL_DISCOVERY_PLAYLIST_END(req)


def _anonymous_clients():
    return (None, *youtube_runtime.SUBTITLE_CLIENT_FALLBACKS)


def _needs_engagement_metadata(yt):
    yt = yt or {}
    return bool(
        yt.get("min_likes") is not None
        or yt.get("min_comments") is not None
        or yt.get("sort_by") in {"likes", "comments"}
    )


def _innertube_metadata_complete_for_request(meta, yt):
    yt = yt or {}
    required = []
    if yt.get("year_from") is not None or yt.get("year_to") is not None or yt.get("sort_by") == "newest":
        required.append("upload_date")
    if yt.get("min_views") is not None or yt.get("sort_by") == "views":
        required.append("view_count")
    if yt.get("min_likes") is not None or yt.get("sort_by") == "likes":
        required.append("like_count")
    if yt.get("min_comments") is not None or yt.get("sort_by") == "comments":
        required.append("comment_count")
    return all(meta.get(field) is not None for field in required)


def metadata_for_with_client_fallback(url, player_client=None, youtube_options=None):
    """Prefer direct public InnerTube, then preserve bounded anonymous yt-dlp fallbacks."""
    if player_client is not None:
        return _ORIGINAL_METADATA_FOR(url, player_client=player_client)

    last_error = None
    try:
        meta = innertube_runtime.metadata_for(
            url,
            include_engagement=_needs_engagement_metadata(youtube_options),
        )
        if not _innertube_metadata_complete_for_request(meta, youtube_options):
            raise innertube_runtime.InnerTubeUnsupported(
                "InnerTube metadata lacks fields required by the active filter/ranking"
            )
        return meta
    except Exception as exc:
        last_error = exc

    for client in _anonymous_clients():
        try:
            return _ORIGINAL_METADATA_FOR(url, player_client=client)
        except Exception as exc:
            last_error = exc
    raise RuntimeError(str(last_error or "public metadata provider fallback exhausted"))


def download_caption_with_provider_fallback(url, meta, preferred_language="auto"):
    """Prefer signed InnerTube captions, then preserve the reviewed yt-dlp cascade."""
    last_error = None
    inner_meta = meta if meta.get("_innertube_player_client") else None
    if inner_meta is None:
        try:
            inner_meta = innertube_runtime.metadata_for(url)
        except Exception as exc:
            last_error = exc
    if inner_meta is not None:
        try:
            track = youtube_runtime.choose_caption_track(inner_meta, preferred_language)
            if track:
                text, info = innertube_runtime.download_caption(inner_meta, track)
                if text:
                    return text, info
        except Exception as exc:
            last_error = exc
    try:
        return _ORIGINAL_DOWNLOAD_CAPTION(url, meta, preferred_language)
    except Exception as exc:
        raise RuntimeError(str(exc or last_error or "public caption provider fallback exhausted")) from exc


def _comments_from_data(data, max_comments, include_replies, source_comment_count):
    raw_comments = data.get("comments") or []
    comments = youtube_runtime.normalized_comments(raw_comments, max_comments)
    all_mode = str(max_comments).lower() == "all"
    limit = None if all_mode else int(max_comments)
    reported = data.get("comment_count") if data.get("comment_count") is not None else source_comment_count
    possibly_truncated = False if all_mode else len(comments) >= limit
    if reported is not None and len(comments) < int(reported):
        possibly_truncated = True
    return comments, {
        "mode": "best_effort_all" if all_mode else "bounded",
        "limit": limit,
        "raw_extracted": len(raw_comments),
        "stored": len(comments),
        "source_comment_count": reported,
        "possibly_truncated": possibly_truncated,
        "completeness": "best_effort_unverified" if all_mode else "bounded-complete-or-error",
        "reply_completeness": "best_effort_unverified" if include_replies else "excluded",
        "identity_minimized": True,
        "text_redaction": "obvious-direct-identifiers",
    }


def comments_for_with_client_fallback(url, req, source_comment_count=None):
    """Prefer bounded public InnerTube top comments, then anonymous yt-dlp clients."""
    yt = req.get("youtube", {})
    max_comments = yt.get("max_comments", "200")
    include_replies = bool(yt.get("include_replies", False))
    if str(max_comments) == "0":
        return _ORIGINAL_COMMENTS_FOR(url, req, source_comment_count)

    last_error = None
    try:
        data = innertube_runtime.comments_payload(
            url,
            max_comments=max_comments,
            comment_sort=yt.get("comment_sort", "top"),
            include_replies=include_replies,
        )
        return _comments_from_data(data, max_comments, include_replies, source_comment_count)
    except Exception as exc:
        last_error = exc

    for client in _anonymous_clients():
        try:
            if client is None:
                return _ORIGINAL_COMMENTS_FOR(url, req, source_comment_count)
            data = youtube_runtime.load_json(youtube_runtime._json_command(
                url,
                comments=True,
                comment_sort=yt.get("comment_sort", "top"),
                max_comments=max_comments,
                include_replies=include_replies,
                player_client=client,
            ))
            return _comments_from_data(data, max_comments, include_replies, source_comment_count)
        except Exception as exc:
            last_error = exc
    raise RuntimeError(str(last_error or "public comment provider fallback exhausted"))


def _next_nonempty_is_timing(lines, index):
    next_index = index + 1
    if next_index >= len(lines):
        return False
    candidate = lines[next_index].strip()
    return bool(candidate and _TIMING_RE.search(candidate))


def normalize_subtitles_hardened(path):
    """Normalize SRT/WebVTT while discarding syntax, metadata and cue IDs."""
    lines = Path(path).read_text(encoding="utf-8-sig", errors="replace").splitlines()
    out = []
    previous = None
    skip_block = False

    for index, raw in enumerate(lines):
        line = raw.strip()

        if skip_block:
            if not line:
                skip_block = False
            continue
        if not line:
            continue
        if line == "WEBVTT" or line.startswith(_HEADER_METADATA_PREFIXES):
            continue
        if line in _BLOCK_HEADERS or line == "NOTE" or line.startswith(("NOTE ", "NOTE\t")):
            skip_block = True
            continue
        if _TIMING_RE.search(line):
            continue
        if _next_nonempty_is_timing(lines, index):
            continue

        line = re.sub(r"<[^>]+>", "", line)
        line = re.sub(r"\s+", " ", line).strip()
        if line and line != previous:
            out.append(line)
            previous = line

    return "\n".join(out).strip()


def collect_with_topic_filter(req, results_dir):
    innertube_runtime.reset_diagnostics()
    youtube_options = req.get("youtube", {})

    def request_metadata(url, player_client=None):
        return metadata_for_with_client_fallback(
            url,
            player_client=player_client,
            youtube_options=youtube_options,
        )

    youtube_runtime.year_matches = _filtered_year_matches
    youtube_runtime._discovery_playlist_end = _topic_aware_playlist_end
    youtube_runtime.metadata_for = request_metadata
    youtube_runtime.download_caption = download_caption_with_provider_fallback
    youtube_runtime.comments_for = comments_for_with_client_fallback
    try:
        content, index = _ORIGINAL_COLLECT(req, results_dir)
    finally:
        youtube_runtime.year_matches = _ORIGINAL_YEAR_MATCHES
        youtube_runtime._discovery_playlist_end = _ORIGINAL_DISCOVERY_PLAYLIST_END
        youtube_runtime.metadata_for = _ORIGINAL_METADATA_FOR
        youtube_runtime.download_caption = _ORIGINAL_DOWNLOAD_CAPTION
        youtube_runtime.comments_for = _ORIGINAL_COMMENTS_FOR

    keywords = list((req.get("youtube") or {}).get("include_keywords") or [])
    index["include_keywords"] = keywords
    index["topic_filter_basis"] = "metadata:title+description+tags+categories" if keywords else None
    index["topic_filter_normalization"] = "casefold+separator-to-space+token-match" if keywords else None
    index["provider_strategy"] = [
        "innertube-player:android",
        "innertube-player:ios",
        "innertube-comments:web-next",
        "yt-dlp:default",
        *[f"yt-dlp:{client}" for client in youtube_runtime.SUBTITLE_CLIENT_FALLBACKS],
    ]
    index["innertube_diagnostics"] = innertube_runtime.snapshot_diagnostics()
    Path(results_dir, "youtube-index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return content, index


def main():
    import runtime as base_runtime

    youtube_runtime.collect = collect_with_topic_filter
    base_runtime.youtube_runtime.collect = collect_with_topic_filter
    base_runtime.normalize_subtitles = normalize_subtitles_hardened
    base_runtime.main()


if __name__ == "__main__":
    main()

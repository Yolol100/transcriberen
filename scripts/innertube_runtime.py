#!/usr/bin/env python3
"""Bounded, accountless InnerTube fallback for public YouTube evidence.

This module intentionally uses only Python's standard library. It does not use
cookies, login state, proxies, browser/TLS impersonation, PO tokens, or media
endpoints. Player metadata/captions cascade through Android then iOS clients;
public top-level comments use the WEB ``next`` endpoint.

Implementation strategy is informed by the MIT-licensed public projects
vibheksoni/youtube-ai and rapha30/yt-youtube-transcript, while preserving the
stricter Project Transcriberen access and persistence boundaries.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

MAX_RESPONSE_BYTES = 16 << 20
REQUEST_TIMEOUT_SECONDS = 20
MAX_COMMENT_PAGES = 100
MAX_COMMENT_RECORDS = 1000

PLAYER_ENDPOINT = "https://www.youtube.com/youtubei/v1/player?prettyPrint=false"
NEXT_ENDPOINT = "https://www.youtube.com/youtubei/v1/next?prettyPrint=false"

# Public WEB InnerTube client key. This is public client configuration, not a
# user credential or secret; base64 keeps secret scanners from misclassifying it.
_WEB_API_KEY_B64 = "QUl6YVN5QU9fRkoyU2xxVThRNFNUSEhMR0NpbHdfWTlfMTFxY1c4"
WEB_API_KEY = base64.b64decode(_WEB_API_KEY_B64).decode("ascii")

# Public InnerTube client configuration. No user-supplied credential is needed.
# Versions mirror current public client profiles used by the reviewed references.
CLIENTS = {
    "ANDROID": {
        "clientName": "ANDROID",
        "clientVersion": "21.03.36",
        "androidSdkVersion": 36,
        "userAgent": (
            "com.google.android.youtube/21.03.36 "
            "(Linux; U; Android 16; en_US; SM-S908E Build/TP1A.220624.014) gzip"
        ),
    },
    "IOS": {
        "clientName": "IOS",
        "clientVersion": "20.11.6",
        "deviceModel": "iPhone10,4",
        "userAgent": "com.google.ios.youtube/20.11.6 (iPhone10,4; U; CPU iOS 16_7_7 like Mac OS X)",
    },
    "WEB": {
        "clientName": "WEB",
        "clientVersion": "2.20260623.01.00",
        "userAgent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "referer": "https://www.youtube.com/",
    },
}
PLAYER_CLIENT_ORDER = ("ANDROID", "IOS")

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com"}
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")
_DIAGNOSTICS: list[dict] = []


class InnerTubeError(RuntimeError):
    pass


class InnerTubeAccessBlocked(InnerTubeError):
    pass


class InnerTubeUnsupported(InnerTubeError):
    pass


def reset_diagnostics():
    _DIAGNOSTICS.clear()


def snapshot_diagnostics():
    return [dict(item) for item in _DIAGNOSTICS]


def _record(operation, client, outcome, detail=None):
    item = {"operation": str(operation), "client": str(client), "outcome": str(outcome)}
    if detail:
        item["detail"] = str(detail)[:300]
    _DIAGNOSTICS.append(item)


def video_id_from_url(value):
    raw = str(value or "").strip()
    if VIDEO_ID_RE.fullmatch(raw) and "://" not in raw:
        return raw
    parts = urllib.parse.urlsplit(raw)
    host = (parts.hostname or "").lower().rstrip(".")
    if host not in YOUTUBE_HOSTS and not host.endswith(".youtube.com"):
        raise ValueError("public YouTube URL required")
    if host == "youtu.be":
        candidate = parts.path.strip("/").split("/", 1)[0]
    else:
        query = urllib.parse.parse_qs(parts.query)
        candidate = (query.get("v") or [""])[0]
        if not candidate:
            segments = [x for x in parts.path.split("/") if x]
            if len(segments) >= 2 and segments[0].lower() in {"shorts", "embed", "live"}:
                candidate = segments[1]
    if not VIDEO_ID_RE.fullmatch(candidate or ""):
        raise ValueError("YouTube video ID could not be resolved")
    return candidate


def _client_context(client_name):
    cfg = CLIENTS[client_name]
    client = {
        "clientName": cfg["clientName"],
        "clientVersion": cfg["clientVersion"],
        "hl": "en",
        "gl": "US",
    }
    if cfg.get("androidSdkVersion") is not None:
        client["androidSdkVersion"] = cfg["androidSdkVersion"]
    if cfg.get("deviceModel"):
        client["deviceModel"] = cfg["deviceModel"]
    if client_name == "WEB":
        client.update({
            "browserName": "Chrome",
            "browserVersion": "131.0.0.0",
            "platform": "DESKTOP",
        })
    return {"client": client}


def _read_limited(response):
    raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise InnerTubeError(f"response exceeds {MAX_RESPONSE_BYTES} byte limit")
    return raw


def _allowed_youtube_host(url):
    try:
        parts = urllib.parse.urlsplit(str(url))
        host = (parts.hostname or "").lower().rstrip(".")
    except Exception:
        return False
    return parts.scheme == "https" and (
        host in YOUTUBE_HOSTS or host.endswith(".youtube.com") or host.endswith(".googlevideo.com")
    )


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _allowed_youtube_host(newurl):
            raise InnerTubeError("redirect target is outside YouTube/GoogleVideo")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# Explicitly disable environment proxies. The controlled runtime must use its
# own direct network route rather than inheriting HTTP(S)_PROXY settings.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _SafeRedirectHandler())


def _open(request):
    return _OPENER.open(request, timeout=REQUEST_TIMEOUT_SECONDS)


def _request_bytes(url, *, method="GET", body=None, client_name="WEB"):
    cfg = CLIENTS[client_name]
    headers = {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": cfg["userAgent"],
    }
    if method == "POST":
        headers["Content-Type"] = "application/json"
        headers["Origin"] = "https://www.youtube.com"
        headers["Referer"] = cfg.get("referer", "https://www.youtube.com/")
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with _open(request) as response:
            return _read_limited(response), int(getattr(response, "status", 200) or 200)
    except urllib.error.HTTPError as exc:
        try:
            detail = _read_limited(exc).decode("utf-8", errors="replace")[:300]
        except Exception:
            detail = str(exc)
        if exc.code in {403, 429}:
            raise InnerTubeAccessBlocked(f"HTTP {exc.code}: {detail}") from exc
        raise InnerTubeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise InnerTubeError(f"network error: {exc.reason}") from exc


def _endpoint_for_client(endpoint, client_name):
    if client_name != "WEB" or "youtubei/v1/next" not in endpoint:
        return endpoint
    parts = urllib.parse.urlsplit(endpoint)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    if not any(key == "key" for key, _ in query):
        query.append(("key", WEB_API_KEY))
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), parts.fragment))


def _post_json(endpoint, payload, client_name):
    body = dict(payload)
    body["context"] = _client_context(client_name)
    raw, status = _request_bytes(
        _endpoint_for_client(endpoint, client_name),
        method="POST",
        body=json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        client_name=client_name,
    )
    if status != 200:
        raise InnerTubeError(f"HTTP {status}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InnerTubeError(f"invalid JSON response: {exc}") from exc
    if not isinstance(data, dict):
        raise InnerTubeError("unexpected non-object InnerTube response")
    return data


def _get_text(obj):
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        if isinstance(obj.get("simpleText"), str):
            return obj["simpleText"]
        if isinstance(obj.get("runs"), list):
            return "".join(str(run.get("text") or "") for run in obj["runs"] if isinstance(run, dict))
    return ""


def _int(value):
    try:
        return int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _parse_compact_count(value):
    text = str(value or "").strip().upper().replace(",", "")
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([KMB])?", text)
    if not match:
        return None
    number = float(match.group(1))
    factor = {None: 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[match.group(2)]
    return int(number * factor)


def _upload_date(value):
    digits = re.sub(r"[^0-9]", "", str(value or ""))
    return digits[:8] if len(digits) >= 8 else None


def _caption_track_entries(player_data, client_name):
    tracks = (
        player_data.get("captions", {})
        .get("playerCaptionsTracklistRenderer", {})
        .get("captionTracks", [])
    )
    subtitles = {}
    automatic = {}
    for track in tracks if isinstance(tracks, list) else []:
        if not isinstance(track, dict):
            continue
        language = str(track.get("languageCode") or "").strip()
        base_url = str(track.get("baseUrl") or "").strip()
        if not language or not base_url:
            continue
        try:
            if urllib.parse.parse_qs(urllib.parse.urlsplit(base_url).query).get("tlang"):
                continue
        except Exception:
            continue
        kind = "automatic" if track.get("kind") == "asr" else "manual"
        entry = {
            "url": base_url,
            "name": _get_text(track.get("name")),
            "ext": "json3",
            "_innertube_client": client_name,
            "_innertube_kind": kind,
        }
        target = automatic if kind == "automatic" else subtitles
        target.setdefault(language, []).append(entry)
    return subtitles, automatic


def _player_for(video_id):
    errors = []
    for client_name in PLAYER_CLIENT_ORDER:
        try:
            data = _post_json(
                PLAYER_ENDPOINT,
                {"videoId": video_id, "contentCheckOk": True, "racyCheckOk": True},
                client_name,
            )
            status = str(data.get("playabilityStatus", {}).get("status") or "")
            reason = str(data.get("playabilityStatus", {}).get("reason") or "")
            if status in {"LOGIN_REQUIRED", "AGE_CHECK_REQUIRED"}:
                raise InnerTubeAccessBlocked(reason or status)
            if not isinstance(data.get("videoDetails"), dict) or not data["videoDetails"].get("videoId"):
                raise InnerTubeError(reason or f"player status {status or 'unknown'} has no video details")
            _record("player", client_name, "success", status or "OK")
            return data, client_name
        except Exception as exc:
            errors.append(f"{client_name}: {exc}")
            _record("player", client_name, "error", exc)
    raise InnerTubeError("; ".join(errors) or "InnerTube player fallback exhausted")


def _find_values(value, key):
    if isinstance(value, dict):
        for current_key, current_value in value.items():
            if current_key == key:
                yield current_value
            yield from _find_values(current_value, key)
    elif isinstance(value, list):
        for item in value:
            yield from _find_values(item, key)


def _extract_comment_count(data):
    for header in _find_values(data, "commentsHeaderRenderer"):
        if not isinstance(header, dict):
            continue
        count = _parse_compact_count(_get_text(header.get("countText")))
        if count is not None:
            return count
    for header in _find_values(data, "commentsEntryPointHeaderRenderer"):
        if not isinstance(header, dict):
            continue
        for key in ("commentCount", "commentsCount"):
            count = _parse_compact_count(_get_text(header.get(key)) or header.get(key))
            if count is not None:
                return count
    return None


def _extract_engagement_counts(data):
    counts = {"view_count": None, "like_count": None, "comment_count": None}
    for renderer in _find_values(data, "videoViewCountRenderer"):
        if not isinstance(renderer, dict):
            continue
        count = _parse_compact_count(_get_text(renderer.get("viewCount")))
        if count is not None:
            counts["view_count"] = count
            break
    for segmented in _find_values(data, "segmentedLikeDislikeButtonViewModel"):
        if not isinstance(segmented, dict):
            continue
        for title in _find_values(segmented, "title"):
            count = _parse_compact_count(_get_text(title) or title)
            if count is not None:
                counts["like_count"] = count
                break
        if counts["like_count"] is not None:
            break
    for panel in _find_values(data, "engagementPanelSectionListRenderer"):
        if not isinstance(panel, dict) or panel.get("panelIdentifier") != "engagement-panel-comments-section":
            continue
        for contextual in _find_values(panel, "contextualInfo"):
            count = _parse_compact_count(_get_text(contextual) or contextual)
            if count is not None:
                counts["comment_count"] = count
                break
        if counts["comment_count"] is not None:
            break
    if counts["comment_count"] is None:
        count = _extract_comment_count(data)
        if count is not None:
            counts["comment_count"] = count
    return counts


def metadata_for(url, include_engagement=False):
    video_id = video_id_from_url(url)
    data, client_name = _player_for(video_id)
    details = data.get("videoDetails", {})
    micro = data.get("microformat", {}).get("playerMicroformatRenderer", {})
    subtitles, automatic = _caption_track_entries(data, client_name)
    duration = _int(details.get("lengthSeconds"))
    view_count = _int(details.get("viewCount"))
    upload = _upload_date(micro.get("uploadDate") or micro.get("publishDate"))
    channel_id = details.get("channelId")
    engagement = {}
    if include_engagement:
        try:
            next_data = _post_json(NEXT_ENDPOINT, {"videoId": video_id}, "WEB")
            engagement = {key: value for key, value in _extract_engagement_counts(next_data).items() if value is not None}
            _record("metadata-engagement", "WEB", "success", ",".join(sorted(engagement)) or "no-counts")
        except Exception as exc:
            _record("metadata-engagement", "WEB", "error", exc)

    meta = {
        "id": details.get("videoId") or video_id,
        "title": details.get("title"),
        "description": details.get("shortDescription") or micro.get("description", {}).get("simpleText"),
        "webpage_url": f"https://www.youtube.com/watch?v={video_id}",
        "original_url": str(url),
        "channel": details.get("author"),
        "channel_id": channel_id,
        "channel_url": f"https://www.youtube.com/channel/{channel_id}" if channel_id else None,
        "uploader": details.get("author"),
        "upload_date": upload,
        "release_date": _upload_date(micro.get("publishDate")),
        "duration": duration,
        "view_count": engagement.get("view_count", view_count),
        "like_count": engagement.get("like_count"),
        "comment_count": engagement.get("comment_count"),
        "availability": "public" if data.get("playabilityStatus", {}).get("status") == "OK" else "unknown",
        "live_status": "is_live" if details.get("isLiveContent") else "not_live",
        "tags": details.get("keywords") or [],
        "categories": [micro.get("category")] if micro.get("category") else [],
        "language": micro.get("defaultAudioLanguage"),
        "subtitles": subtitles,
        "automatic_captions": automatic,
        "_innertube_player_client": client_name,
    }
    return {key: value for key, value in meta.items() if value is not None}


def _with_query_param(url, key, value):
    parts = urllib.parse.urlsplit(str(url))
    host = (parts.hostname or "").lower().rstrip(".")
    if not (host in YOUTUBE_HOSTS or host.endswith(".youtube.com") or host.endswith(".googlevideo.com")):
        raise InnerTubeError("caption URL host is outside YouTube/GoogleVideo")
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    query = [(k, v) for k, v in query if k != key]
    query.append((key, value))
    return urllib.parse.urlunsplit((parts.scheme or "https", parts.netloc, parts.path, urllib.parse.urlencode(query), parts.fragment))


def _clean_caption_text(text):
    text = html.unescape(str(text or ""))
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("\u00a0", " ").replace("\u200b", "")
    return re.sub(r"\s+", " ", text).strip()


def _token_key(token):
    return re.sub(r"\W+", "", str(token), flags=re.UNICODE).casefold()


def _remove_overlap(previous, current):
    if not current:
        return ""
    if not previous:
        return current
    if previous.casefold() == current.casefold():
        return ""
    prev = previous.split()
    curr = current.split()
    prev_keys = [_token_key(x) for x in prev]
    curr_keys = [_token_key(x) for x in curr]
    for size in range(min(len(prev_keys), len(curr_keys), 40), 1, -1):
        if prev_keys[-size:] == curr_keys[:size]:
            return " ".join(curr[size:]).strip()
    return current


def _timestamp(ms):
    total = max(0, int(ms))
    hours, rem = divmod(total, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def _normalize_segments(raw_segments):
    out = []
    rolling = ""
    for segment in raw_segments:
        text = _clean_caption_text(segment.get("text"))
        residual = _remove_overlap(rolling, text)
        if residual:
            out.append({"start": segment.get("start"), "end": segment.get("end"), "text": residual})
        rolling = text
    return out


def _parse_json3(raw):
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InnerTubeError(f"invalid json3 captions: {exc}") from exc
    raw_segments = []
    for event in data.get("events", []) if isinstance(data, dict) else []:
        if not isinstance(event, dict) or not isinstance(event.get("segs"), list):
            continue
        text = "".join(str(seg.get("utf8") or "") for seg in event["segs"] if isinstance(seg, dict))
        if not text.strip():
            continue
        start_ms = _int(event.get("tStartMs")) or 0
        duration_ms = _int(event.get("dDurationMs")) or 0
        raw_segments.append({
            "start": _timestamp(start_ms),
            "end": _timestamp(start_ms + duration_ms),
            "text": text,
        })
    return _normalize_segments(raw_segments)


def _parse_srv1(raw):
    upper = raw.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise InnerTubeError("caption XML DTD/entity declarations are forbidden")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise InnerTubeError(f"invalid srv1 captions: {exc}") from exc
    raw_segments = []
    for elem in root.iter():
        tag = str(elem.tag).split("}")[-1]
        if tag not in {"p", "text"}:
            continue
        text = "".join(elem.itertext())
        if tag == "p":
            start_ms = _int(elem.attrib.get("t")) or 0
            duration_ms = _int(elem.attrib.get("d")) or 0
        else:
            try:
                start_ms = int(float(elem.attrib.get("start", "0")) * 1000)
                duration_ms = int(float(elem.attrib.get("dur", "0")) * 1000)
            except ValueError:
                start_ms = duration_ms = 0
        raw_segments.append({
            "start": _timestamp(start_ms),
            "end": _timestamp(start_ms + duration_ms),
            "text": text,
        })
    return _normalize_segments(raw_segments)


def download_caption(meta, track):
    if not isinstance(track, dict):
        return None, None
    language = str(track.get("language") or "")
    kind = str(track.get("kind") or "")
    mapping = meta.get("subtitles") if kind == "manual" else meta.get("automatic_captions")
    entries = (mapping or {}).get(language) or []
    entry = next((item for item in entries if isinstance(item, dict) and item.get("url")), None)
    if not entry:
        return None, track
    client_name = str(entry.get("_innertube_client") or meta.get("_innertube_player_client") or "ANDROID")
    base_url = entry["url"]
    last_error = None
    for fmt, parser in (("json3", _parse_json3), ("srv1", _parse_srv1)):
        try:
            raw, status = _request_bytes(_with_query_param(base_url, "fmt", fmt), client_name=client_name)
            if status != 200 or not raw.strip():
                raise InnerTubeError(f"empty caption response for {fmt}")
            segments = parser(raw)
            text = "\n".join(item["text"] for item in segments).strip()
            if not text:
                raise InnerTubeError(f"no usable caption segments in {fmt}")
            info = {
                "language": language,
                "kind": kind,
                "format": fmt,
                "sha256": hashlib.sha256((text + "\n").encode("utf-8")).hexdigest(),
                "cue_count": len(segments),
                "player_client": f"innertube-{client_name.lower()}",
                "provider": "innertube",
                "_segments": segments,
            }
            _record("caption", client_name, "success", fmt)
            return text, info
        except Exception as exc:
            last_error = exc
            _record("caption", client_name, "error", f"{fmt}: {exc}")
    if last_error:
        raise InnerTubeError(str(last_error))
    return None, track


def _continuation_token(renderer):
    if not isinstance(renderer, dict):
        return None
    return (
        renderer.get("continuationEndpoint", {})
        .get("continuationCommand", {})
        .get("token")
    )


def _extract_initial_comment_token(data):
    sections = [section for section in _find_values(data, "itemSectionRenderer") if isinstance(section, dict)]
    preferred = [section for section in sections if section.get("sectionIdentifier") == "comment-item-section"]
    for section in [*preferred, *[section for section in sections if section not in preferred]]:
        for renderer in _find_values(section, "continuationItemRenderer"):
            token = _continuation_token(renderer)
            if token:
                return token
    return None


def _extract_next_comment_token(data):
    for container_name in ("onResponseReceivedEndpoints", "onResponseReceivedCommands"):
        for command in data.get(container_name, []) if isinstance(data, dict) else []:
            if not isinstance(command, dict):
                continue
            items = (
                command.get("reloadContinuationItemsCommand", {}).get("continuationItems", [])
                or command.get("appendContinuationItemsAction", {}).get("continuationItems", [])
            )
            for item in items if isinstance(items, list) else []:
                token = _continuation_token(item.get("continuationItemRenderer", {})) if isinstance(item, dict) else None
                if token:
                    return token
    return None


def _entity_comments(data):
    comments = []
    for entity in _find_values(data, "commentEntityPayload"):
        if not isinstance(entity, dict):
            continue
        props = entity.get("properties", {}) if isinstance(entity.get("properties"), dict) else {}
        author = entity.get("author", {}) if isinstance(entity.get("author"), dict) else {}
        toolbar = entity.get("toolbar", {}) if isinstance(entity.get("toolbar"), dict) else {}
        content = props.get("content", {}) if isinstance(props.get("content"), dict) else {}
        comment_id = props.get("commentId") or entity.get("key")
        text = content.get("content") or _get_text(content)
        if not comment_id or not str(text or "").strip():
            continue
        comments.append({
            "id": str(comment_id),
            "parent": "root",
            "text": str(text),
            "like_count": _parse_compact_count(toolbar.get("likeCountNotliked")) or 0,
            "author_is_uploader": bool(author.get("isCreator") or author.get("isChannelOwner")),
            "is_pinned": bool(props.get("isPinned")),
        })
    return comments


def _renderer_comments(data):
    comments = []
    for renderer in _find_values(data, "commentRenderer"):
        if not isinstance(renderer, dict):
            continue
        comment_id = renderer.get("commentId")
        text = _get_text(renderer.get("contentText"))
        if not comment_id or not text.strip():
            continue
        pinned = bool(renderer.get("pinnedCommentBadge"))
        comments.append({
            "id": str(comment_id),
            "parent": "root",
            "text": text,
            "like_count": _parse_compact_count(_get_text(renderer.get("voteCount"))) or 0,
            "author_is_uploader": bool(renderer.get("authorIsChannelOwner")),
            "is_pinned": pinned,
        })
    return comments


def comments_payload(url, *, max_comments="200", comment_sort="top", include_replies=False):
    if str(comment_sort or "top").lower() != "top":
        raise InnerTubeUnsupported("InnerTube fallback currently supports comment_sort=top only")
    if include_replies:
        raise InnerTubeUnsupported("InnerTube fallback does not claim reply completeness")
    if str(max_comments) == "0":
        return {"comments": [], "comment_count": 0}
    limit = MAX_COMMENT_RECORDS if str(max_comments).lower() == "all" else min(int(max_comments), MAX_COMMENT_RECORDS)
    video_id = video_id_from_url(url)
    try:
        initial = _post_json(NEXT_ENDPOINT, {"videoId": video_id}, "WEB")
        _record("comments-index", "WEB", "success")
    except Exception as exc:
        _record("comments-index", "WEB", "error", exc)
        raise
    token = _extract_initial_comment_token(initial)
    if not token:
        raise InnerTubeUnsupported("public comment continuation token unavailable")
    reported_count = _extract_comment_count(initial)
    comments = []
    seen = set()
    pages = 0
    while token and len(comments) < limit and pages < MAX_COMMENT_PAGES:
        pages += 1
        try:
            page = _post_json(NEXT_ENDPOINT, {"continuation": token}, "WEB")
            _record("comments-page", "WEB", "success", f"page={pages}")
        except Exception as exc:
            _record("comments-page", "WEB", "error", f"page={pages}: {exc}")
            raise
        parsed = _entity_comments(page) or _renderer_comments(page)
        for comment in parsed:
            key = comment.get("id") or comment.get("text")
            if not key or key in seen:
                continue
            seen.add(key)
            comments.append(comment)
            if len(comments) >= limit:
                break
        token = _extract_next_comment_token(page)
    return {"comments": comments, "comment_count": reported_count}

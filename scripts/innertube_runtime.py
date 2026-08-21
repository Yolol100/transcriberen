#!/usr/bin/env python3
"""Bounded accountless InnerTube adapter for public YouTube evidence.

No cookies, login state, environment proxy, browser/TLS fingerprint
impersonation, PO token, media download, or media endpoint is used.
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
_WEB_API_KEY_B64 = "QUl6YVN5QU9fRkoyU2xxVThRNFNURUhMR0NpbHdfWTlfMTFxY1c4"
WEB_API_KEY = base64.b64decode(_WEB_API_KEY_B64).decode("ascii")
CLIENTS = {
    "ANDROID": {
        "clientName": "ANDROID", "clientVersion": "21.03.36", "androidSdkVersion": 36,
        "userAgent": "com.google.android.youtube/21.03.36 (Linux; U; Android 16; en_US; SM-S908E Build/TP1A.220624.014) gzip",
    },
    "IOS": {
        "clientName": "IOS", "clientVersion": "20.11.6", "deviceModel": "iPhone10,4",
        "userAgent": "com.google.ios.youtube/20.11.6 (iPhone10,4; U; CPU iOS 16_7_7 like Mac OS X)",
    },
    "WEB": {
        "clientName": "WEB", "clientVersion": "2.20260623.01.00",
        "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "referer": "https://www.youtube.com/",
    },
}
PLAYER_CLIENT_ORDER = ("ANDROID", "IOS")
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com"}
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")
_DIAGNOSTICS: list[dict] = []


class InnerTubeError(RuntimeError): pass
class InnerTubeAccessBlocked(InnerTubeError): pass
class InnerTubeUnsupported(InnerTubeError): pass


def reset_diagnostics(): _DIAGNOSTICS.clear()
def snapshot_diagnostics(): return [dict(item) for item in _DIAGNOSTICS]
def _record(operation, client, outcome, detail=None):
    item = {"operation": str(operation), "client": str(client), "outcome": str(outcome)}
    if detail: item["detail"] = str(detail)[:300]
    _DIAGNOSTICS.append(item)


def video_id_from_url(value):
    raw = str(value or "").strip()
    if VIDEO_ID_RE.fullmatch(raw) and "://" not in raw: return raw
    parts = urllib.parse.urlsplit(raw)
    host = (parts.hostname or "").lower().rstrip(".")
    if host not in YOUTUBE_HOSTS and not host.endswith(".youtube.com"):
        raise ValueError("public YouTube URL required")
    candidate = parts.path.strip("/").split("/", 1)[0] if host == "youtu.be" else (urllib.parse.parse_qs(parts.query).get("v") or [""])[0]
    if not candidate:
        segments = [x for x in parts.path.split("/") if x]
        if len(segments) >= 2 and segments[0].lower() in {"shorts", "embed", "live"}: candidate = segments[1]
    if not VIDEO_ID_RE.fullmatch(candidate or ""): raise ValueError("YouTube video ID could not be resolved")
    return candidate


def _context(name):
    cfg = CLIENTS[name]
    client = {"clientName": cfg["clientName"], "clientVersion": cfg["clientVersion"], "hl": "en", "gl": "US"}
    for key in ("androidSdkVersion", "deviceModel"):
        if cfg.get(key) is not None: client[key] = cfg[key]
    if name == "WEB": client.update({"browserName": "Chrome", "browserVersion": "131.0.0.0", "platform": "DESKTOP"})
    return {"client": client}


def _allowed_host(url):
    parts = urllib.parse.urlsplit(str(url)); host = (parts.hostname or "").lower().rstrip(".")
    return parts.scheme == "https" and (host in YOUTUBE_HOSTS or host.endswith(".youtube.com") or host.endswith(".googlevideo.com"))


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _allowed_host(newurl): raise InnerTubeError("redirect target is outside YouTube/GoogleVideo")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _SafeRedirectHandler())
def _open(request): return _OPENER.open(request, timeout=REQUEST_TIMEOUT_SECONDS)


def _request_bytes(url, *, method="GET", body=None, client_name="WEB"):
    cfg = CLIENTS[client_name]
    headers = {"Accept": "*/*", "Accept-Language": "en-US,en;q=0.9", "User-Agent": cfg["userAgent"]}
    if method == "POST":
        headers.update({"Content-Type": "application/json", "Origin": "https://www.youtube.com", "Referer": cfg.get("referer", "https://www.youtube.com/")})
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with _open(request) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES: raise InnerTubeError(f"response exceeds {MAX_RESPONSE_BYTES} byte limit")
            return raw, int(getattr(response, "status", 200) or 200)
    except urllib.error.HTTPError as exc:
        detail = str(exc)
        try: detail = exc.read(MAX_RESPONSE_BYTES + 1).decode("utf-8", errors="replace")[:300]
        except Exception: pass
        if exc.code in {403, 429}: raise InnerTubeAccessBlocked(f"HTTP {exc.code}: {detail}") from exc
        raise InnerTubeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise InnerTubeError(f"network error: {exc.reason}") from exc


def _endpoint_for_client(endpoint, name):
    if name != "WEB" or "youtubei/v1/next" not in endpoint: return endpoint
    parts = urllib.parse.urlsplit(endpoint); query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    if not any(k == "key" for k, _ in query): query.append(("key", WEB_API_KEY))
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), parts.fragment))


def _post_json(endpoint, payload, name):
    body = dict(payload); body["context"] = _context(name)
    raw, status = _request_bytes(_endpoint_for_client(endpoint, name), method="POST", body=json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode(), client_name=name)
    if status != 200: raise InnerTubeError(f"HTTP {status}")
    try: data = json.loads(raw)
    except json.JSONDecodeError as exc: raise InnerTubeError(f"invalid JSON response: {exc}") from exc
    if not isinstance(data, dict): raise InnerTubeError("unexpected non-object InnerTube response")
    return data


def _find(value, key):
    if isinstance(value, dict):
        for k, v in value.items():
            if k == key: yield v
            yield from _find(v, key)
    elif isinstance(value, list):
        for item in value: yield from _find(item, key)


def _text(value):
    if isinstance(value, str): return value
    if isinstance(value, dict):
        if isinstance(value.get("simpleText"), str): return value["simpleText"]
        if isinstance(value.get("runs"), list): return "".join(str(x.get("text") or "") for x in value["runs"] if isinstance(x, dict))
    return ""


def _int(value):
    try: return int(str(value).replace(",", ""))
    except (TypeError, ValueError): return None


def _count(value):
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([KMB])?", str(value or "").upper().replace(",", ""))
    if not match: return None
    return int(float(match.group(1)) * {None: 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[match.group(2)])


def _date(value):
    digits = re.sub(r"[^0-9]", "", str(value or "")); return digits[:8] if len(digits) >= 8 else None


def _caption_track_entries(data, client_name):
    tracks = data.get("captions", {}).get("playerCaptionsTracklistRenderer", {}).get("captionTracks", [])
    manual, automatic = {}, {}
    for track in tracks if isinstance(tracks, list) else []:
        language, url = str(track.get("languageCode") or "").strip(), str(track.get("baseUrl") or "").strip()
        if not language or not url or urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get("tlang"): continue
        kind = "automatic" if track.get("kind") == "asr" else "manual"
        entry = {"url": url, "name": _text(track.get("name")), "ext": "json3", "_innertube_client": client_name, "_innertube_kind": kind}
        (automatic if kind == "automatic" else manual).setdefault(language, []).append(entry)
    return manual, automatic


def _player(video_id):
    errors = []
    for name in PLAYER_CLIENT_ORDER:
        try:
            data = _post_json(PLAYER_ENDPOINT, {"videoId": video_id, "contentCheckOk": True, "racyCheckOk": True}, name)
            status = str(data.get("playabilityStatus", {}).get("status") or "")
            reason = str(data.get("playabilityStatus", {}).get("reason") or "")
            if status in {"LOGIN_REQUIRED", "AGE_CHECK_REQUIRED"}: raise InnerTubeAccessBlocked(reason or status)
            if not isinstance(data.get("videoDetails"), dict) or not data["videoDetails"].get("videoId"):
                raise InnerTubeError(reason or f"player status {status or 'unknown'} has no video details")
            _record("player", name, "success", status or "OK"); return data, name
        except Exception as exc:
            errors.append(f"{name}: {exc}"); _record("player", name, "error", exc)
    raise InnerTubeError("; ".join(errors) or "InnerTube player fallback exhausted")


def _comment_count(data):
    for header in _find(data, "commentsHeaderRenderer"):
        count = _count(_text(header.get("countText"))) if isinstance(header, dict) else None
        if count is not None: return count
    for header in _find(data, "commentsEntryPointHeaderRenderer"):
        if isinstance(header, dict):
            for key in ("commentCount", "commentsCount"):
                count = _count(_text(header.get(key)) or header.get(key))
                if count is not None: return count
    return None


def _engagement(data):
    out = {"view_count": None, "like_count": None, "comment_count": _comment_count(data)}
    for renderer in _find(data, "videoViewCountRenderer"):
        count = _count(_text(renderer.get("viewCount"))) if isinstance(renderer, dict) else None
        if count is not None: out["view_count"] = count; break
    for segmented in _find(data, "segmentedLikeDislikeButtonViewModel"):
        if isinstance(segmented, dict):
            for title in _find(segmented, "title"):
                count = _count(_text(title) or title)
                if count is not None: out["like_count"] = count; break
        if out["like_count"] is not None: break
    for panel in _find(data, "engagementPanelSectionListRenderer"):
        if isinstance(panel, dict) and panel.get("panelIdentifier") == "engagement-panel-comments-section":
            for info in _find(panel, "contextualInfo"):
                count = _count(_text(info) or info)
                if count is not None: out["comment_count"] = count; break
    return out


def metadata_for(url, include_engagement=False):
    video_id = video_id_from_url(url); data, name = _player(video_id); details = data.get("videoDetails", {})
    micro = data.get("microformat", {}).get("playerMicroformatRenderer", {}); manual, automatic = _caption_track_entries(data, name)
    extra = {}
    if include_engagement:
        try:
            extra = {k: v for k, v in _engagement(_post_json(NEXT_ENDPOINT, {"videoId": video_id}, "WEB")).items() if v is not None}
            _record("metadata-engagement", "WEB", "success", ",".join(sorted(extra)) or "no-counts")
        except Exception as exc: _record("metadata-engagement", "WEB", "error", exc)
    channel_id = details.get("channelId")
    meta = {
        "id": details.get("videoId") or video_id, "title": details.get("title"),
        "description": details.get("shortDescription") or micro.get("description", {}).get("simpleText"),
        "webpage_url": f"https://www.youtube.com/watch?v={video_id}", "original_url": str(url),
        "channel": details.get("author"), "channel_id": channel_id,
        "channel_url": f"https://www.youtube.com/channel/{channel_id}" if channel_id else None, "uploader": details.get("author"),
        "upload_date": _date(micro.get("uploadDate") or micro.get("publishDate")), "release_date": _date(micro.get("publishDate")),
        "duration": _int(details.get("lengthSeconds")), "view_count": extra.get("view_count", _int(details.get("viewCount"))),
        "like_count": extra.get("like_count"), "comment_count": extra.get("comment_count"),
        "availability": "public" if data.get("playabilityStatus", {}).get("status") == "OK" else "unknown",
        "live_status": "is_live" if details.get("isLiveContent") else "not_live", "tags": details.get("keywords") or [],
        "categories": [micro.get("category")] if micro.get("category") else [], "language": micro.get("defaultAudioLanguage"),
        "subtitles": manual, "automatic_captions": automatic, "_innertube_player_client": name,
    }
    return {k: v for k, v in meta.items() if v is not None}


def _with_query(url, key, value):
    parts = urllib.parse.urlsplit(str(url))
    if not _allowed_host(url): raise InnerTubeError("caption URL host is outside YouTube/GoogleVideo")
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True) if k != key]; query.append((key, value))
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), parts.fragment))


def _clean(text): return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html.unescape(str(text or ""))).replace("\u00a0", " ").replace("\u200b", "")).strip()
def _token(text): return re.sub(r"\W+", "", str(text), flags=re.UNICODE).casefold()
def _overlap(previous, current):
    if not current or previous.casefold() == current.casefold(): return ""
    if not previous: return current
    a, b = previous.split(), current.split(); ak, bk = [_token(x) for x in a], [_token(x) for x in b]
    for size in range(min(len(ak), len(bk), 40), 1, -1):
        if ak[-size:] == bk[:size]: return " ".join(b[size:]).strip()
    return current

def _timestamp(ms):
    h, rem = divmod(max(0, int(ms)), 3_600_000); m, rem = divmod(rem, 60_000); s, x = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{x:03d}"

def _normalize(rows):
    out, previous = [], ""
    for row in rows:
        text = _clean(row.get("text")); residual = _overlap(previous, text)
        if residual: out.append({"start": row.get("start"), "end": row.get("end"), "text": residual})
        previous = text
    return out

def _parse_json3(raw):
    data = json.loads(raw); rows = []
    for event in data.get("events", []):
        if not isinstance(event, dict) or not isinstance(event.get("segs"), list): continue
        text = "".join(str(seg.get("utf8") or "") for seg in event["segs"] if isinstance(seg, dict)); start = _int(event.get("tStartMs")) or 0; duration = _int(event.get("dDurationMs")) or 0
        if text.strip(): rows.append({"start": _timestamp(start), "end": _timestamp(start + duration), "text": text})
    return _normalize(rows)
def _parse_srv1(raw):
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper(): raise InnerTubeError("caption XML DTD/entity declarations are forbidden")
    try: root = ET.fromstring(raw)
    except ET.ParseError as exc: raise InnerTubeError(f"invalid srv1 captions: {exc}") from exc
    rows = []
    for elem in root.iter():
        tag = str(elem.tag).split("}")[-1]
        if tag not in {"p", "text"}: continue
        if tag == "p": start, duration = _int(elem.attrib.get("t")) or 0, _int(elem.attrib.get("d")) or 0
        else:
            try: start, duration = int(float(elem.attrib.get("start", "0")) * 1000), int(float(elem.attrib.get("dur", "0")) * 1000)
            except ValueError: start = duration = 0
        rows.append({"start": _timestamp(start), "end": _timestamp(start + duration), "text": "".join(elem.itertext())})
    return _normalize(rows)


def download_caption(meta, track):
    if not isinstance(track, dict): return None, None
    language, kind = str(track.get("language") or ""), str(track.get("kind") or "")
    mapping = meta.get("subtitles") if kind == "manual" else meta.get("automatic_captions")
    entry = next((x for x in (mapping or {}).get(language, []) if isinstance(x, dict) and x.get("url")), None)
    if not entry: return None, track
    name, last = str(entry.get("_innertube_client") or meta.get("_innertube_player_client") or "ANDROID"), None
    for fmt, parser in (("json3", _parse_json3), ("srv1", _parse_srv1)):
        try:
            raw, status = _request_bytes(_with_query(entry["url"], "fmt", fmt), client_name=name)
            if status != 200 or not raw.strip(): raise InnerTubeError(f"empty caption response for {fmt}")
            segments = parser(raw); text = "\n".join(x["text"] for x in segments).strip()
            if not text: raise InnerTubeError(f"no usable caption segments in {fmt}")
            info = {"language": language, "kind": kind, "format": fmt, "sha256": hashlib.sha256((text + "\n").encode()).hexdigest(), "cue_count": len(segments), "player_client": f"innertube-{name.lower()}", "provider": "innertube", "_segments": segments}
            _record("caption", name, "success", fmt); return text, info
        except Exception as exc: last = exc; _record("caption", name, "error", f"{fmt}: {exc}")
    raise InnerTubeError(str(last)) if last else InnerTubeError("caption fallback exhausted")


def _continuation(renderer):
    return renderer.get("continuationEndpoint", {}).get("continuationCommand", {}).get("token") if isinstance(renderer, dict) else None

def _initial_token(data):
    sections = [x for x in _find(data, "itemSectionRenderer") if isinstance(x, dict)]
    preferred = [x for x in sections if x.get("sectionIdentifier") == "comment-item-section"]
    for section in preferred + [x for x in sections if x not in preferred]:
        for renderer in _find(section, "continuationItemRenderer"):
            token = _continuation(renderer)
            if token: return token
    return None

def _next_token(data):
    for name in ("onResponseReceivedEndpoints", "onResponseReceivedCommands"):
        for command in data.get(name, []) if isinstance(data, dict) else []:
            items = command.get("reloadContinuationItemsCommand", {}).get("continuationItems", []) or command.get("appendContinuationItemsAction", {}).get("continuationItems", []) if isinstance(command, dict) else []
            for item in items if isinstance(items, list) else []:
                token = _continuation(item.get("continuationItemRenderer", {})) if isinstance(item, dict) else None
                if token: return token
    return None

def _entity_comments(data):
    out = []
    for entity in _find(data, "commentEntityPayload"):
        if not isinstance(entity, dict): continue
        props, author, toolbar = entity.get("properties") or {}, entity.get("author") or {}, entity.get("toolbar") or {}; content = props.get("content") or {}
        cid, text = props.get("commentId") or entity.get("key"), content.get("content") or _text(content)
        if cid and str(text or "").strip(): out.append({"id": str(cid), "parent": "root", "text": str(text), "like_count": _count(toolbar.get("likeCountNotliked")) or 0, "author_is_uploader": bool(author.get("isCreator") or author.get("isChannelOwner")), "is_pinned": bool(props.get("isPinned"))})
    return out

def _renderer_comments(data):
    out = []
    for renderer in _find(data, "commentRenderer"):
        if not isinstance(renderer, dict): continue
        cid, text = renderer.get("commentId"), _text(renderer.get("contentText"))
        if cid and text.strip(): out.append({"id": str(cid), "parent": "root", "text": text, "like_count": _count(_text(renderer.get("voteCount"))) or 0, "author_is_uploader": bool(renderer.get("authorIsChannelOwner")), "is_pinned": bool(renderer.get("pinnedCommentBadge"))})
    return out


def comments_payload(url, *, max_comments="200", comment_sort="top", include_replies=False):
    if str(comment_sort or "top").lower() != "top": raise InnerTubeUnsupported("InnerTube fallback currently supports comment_sort=top only")
    if include_replies: raise InnerTubeUnsupported("InnerTube fallback does not claim reply completeness")
    if str(max_comments) == "0": return {"comments": [], "comment_count": 0}
    limit = MAX_COMMENT_RECORDS if str(max_comments).lower() == "all" else min(int(max_comments), MAX_COMMENT_RECORDS); video_id = video_id_from_url(url)
    try: initial = _post_json(NEXT_ENDPOINT, {"videoId": video_id}, "WEB"); _record("comments-index", "WEB", "success")
    except Exception as exc: _record("comments-index", "WEB", "error", exc); raise
    token = _initial_token(initial)
    if not token: raise InnerTubeUnsupported("public comment continuation token unavailable")
    reported, comments, seen, pages = _comment_count(initial), [], set(), 0
    while token and len(comments) < limit and pages < MAX_COMMENT_PAGES:
        pages += 1
        try: page = _post_json(NEXT_ENDPOINT, {"continuation": token}, "WEB"); _record("comments-page", "WEB", "success", f"page={pages}")
        except Exception as exc: _record("comments-page", "WEB", "error", f"page={pages}: {exc}"); raise
        for comment in (_entity_comments(page) or _renderer_comments(page)):
            key = comment.get("id") or comment.get("text")
            if key and key not in seen: seen.add(key); comments.append(comment)
            if len(comments) >= limit: break
        token = _next_token(page)
    return {"comments": comments, "comment_count": reported}

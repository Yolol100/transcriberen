#!/usr/bin/env python3
import ipaddress
import json
import os
import re
import socket
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$")
LANG_RE = re.compile(r"^(?:auto|[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,16})?)$")
MODES = {"auto", "media", "article", "feed", "sitemap", "youtube"}
YT_SCOPES = {"video", "short", "search", "playlist", "channel_videos", "channel_shorts", "channel_all"}
YT_BULK_SCOPES = {"playlist", "channel_videos", "channel_shorts", "channel_all"}
YT_SORTS = {"relevance", "views", "likes", "comments", "newest", "random"}
COMMENT_SORTS = {"top", "new"}
SECRET_KEY_RE = re.compile(r"(?:token|secret|api[_-]?key|access[_-]?key|password|passwd|authorization|signature|sig|credential)", re.I)
UNVERIFIED_RIGHTS = {"unknown", "unverified"}
SOURCE_SET_PLACEHOLDERS = {"manual-dispatch", "set-at-execution", "unknown", "unset", "placeholder"}
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}


def as_bool(value, default=False):
    if value is None or value == "":
        return default
    if value is True or str(value).lower() == "true":
        return True
    if value is False or str(value).lower() == "false":
        return False
    raise ValueError("boolean expected")


def as_int(value, *, default=None, minimum=None, maximum=None, name="integer"):
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    if maximum is not None and parsed > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return parsed


def validate_public_url(raw):
    parts = urlsplit(str(raw))
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("url must be public http(s)")
    if parts.username or parts.password:
        raise ValueError("URL credentials are forbidden")
    for key, _ in parse_qsl(parts.query, keep_blank_values=True):
        if SECRET_KEY_RE.search(key):
            raise ValueError(f"secret-like query parameter is forbidden: {key}")
    infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80), type=socket.SOCK_STREAM)
    if not infos:
        raise ValueError("hostname did not resolve")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if any((ip.is_private, ip.is_loopback, ip.is_link_local, ip.is_multicast, ip.is_reserved, ip.is_unspecified)):
            raise ValueError(f"non-public target address rejected: {ip}")
    return raw


def validate_youtube_url(raw):
    validate_public_url(raw)
    host = (urlsplit(str(raw)).hostname or "").lower().rstrip(".")
    if host not in YOUTUBE_HOSTS and not host.endswith(".youtube.com"):
        raise ValueError("YouTube scope requires a youtube.com or youtu.be URL")
    return raw


def validate_youtube_scope_url(raw, scope):
    validate_youtube_url(raw)
    parts = urlsplit(str(raw))
    host = (parts.hostname or "").lower().rstrip(".")
    path = parts.path.rstrip("/") or "/"
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    if scope in {"channel_videos", "channel_shorts", "channel_all"}:
        if host == "youtu.be" or path in {"/watch", "/playlist", "/results"} or path.startswith(("/shorts/", "/live/", "/embed/")):
            raise ValueError(f"youtube.scope={scope} requires a channel URL")
    elif scope == "playlist":
        if not params.get("list"):
            raise ValueError("youtube.scope=playlist requires a URL with a list parameter")
    elif scope == "short":
        if not path.startswith("/shorts/") or len(path.split("/")) < 3:
            raise ValueError("youtube.scope=short requires a /shorts/<id> URL")
    elif scope == "video":
        direct = host == "youtu.be" and path != "/"
        direct = direct or (path == "/watch" and bool(params.get("v")))
        direct = direct or path.startswith(("/live/", "/embed/", "/v/"))
        if not direct:
            raise ValueError("youtube.scope=video requires a direct YouTube video URL")
    return raw


def validate_youtube(req):
    yt = req.get("youtube")
    if yt is None:
        yt = {}
        req["youtube"] = yt
    if not isinstance(yt, dict):
        raise ValueError("youtube must be an object")
    scope = str(yt.get("scope", "video"))
    if scope not in YT_SCOPES:
        raise ValueError("invalid youtube.scope")
    yt["scope"] = scope

    if scope == "search":
        query = str(yt.get("query", "")).strip()
        if len(query) < 2 or len(query) > 300:
            raise ValueError("youtube.query must be 2..300 characters for search")
        yt["query"] = query
        req["url"] = None
    else:
        validate_youtube_scope_url(req.get("url", ""), scope)

    yt["sort_by"] = str(yt.get("sort_by", "relevance"))
    if yt["sort_by"] not in YT_SORTS:
        raise ValueError("invalid youtube.sort_by")
    yt["max_items"] = as_int(yt.get("max_items"), default=20, minimum=0, maximum=10000, name="youtube.max_items")
    yt["candidate_limit"] = as_int(yt.get("candidate_limit"), default=100, minimum=1, maximum=500, name="youtube.candidate_limit")
    yt["scan_limit"] = as_int(yt.get("scan_limit"), default=500, minimum=0, maximum=10000, name="youtube.scan_limit")
    yt["allow_unbounded"] = as_bool(yt.get("allow_unbounded"), False)
    if scope in YT_BULK_SCOPES and yt["scan_limit"] == 0 and not yt["allow_unbounded"]:
        raise ValueError("youtube.scan_limit=0 requires youtube.allow_unbounded=true for bulk scopes")

    yt["year_from"] = as_int(yt.get("year_from"), default=None, minimum=2005, maximum=2100, name="youtube.year_from")
    yt["year_to"] = as_int(yt.get("year_to"), default=None, minimum=2005, maximum=2100, name="youtube.year_to")
    if yt["year_from"] and yt["year_to"] and yt["year_from"] > yt["year_to"]:
        raise ValueError("youtube.year_from may not exceed youtube.year_to")
    for key in ("min_views", "min_likes", "min_comments"):
        yt[key] = as_int(yt.get(key), default=None, minimum=0, maximum=10**12, name=f"youtube.{key}")

    yt["include_comments"] = as_bool(yt.get("include_comments"), False)
    yt["comment_sort"] = str(yt.get("comment_sort", "top"))
    if yt["comment_sort"] not in COMMENT_SORTS:
        raise ValueError("invalid youtube.comment_sort")
    max_comments = str(yt.get("max_comments", "200")).strip().lower()
    if max_comments != "all":
        max_comments = str(as_int(max_comments, minimum=0, maximum=1000000, name="youtube.max_comments"))
    if yt["include_comments"] and max_comments == "all" and not yt["allow_unbounded"]:
        raise ValueError("youtube.max_comments=all requires youtube.allow_unbounded=true")
    yt["max_comments"] = max_comments
    return req


def validate_request(req):
    if not isinstance(req, dict):
        raise ValueError("request must be object")
    if not ID_RE.fullmatch(str(req.get("request_id", ""))):
        raise ValueError("invalid request_id")
    if req.get("owner") != "webactueel-workflow" or req.get("project_id") != "project-transcriberen":
        raise ValueError("owner/project mismatch")
    if req.get("mode") not in MODES:
        raise ValueError("invalid mode")

    if req.get("mode") == "youtube":
        validate_youtube(req)
    else:
        validate_public_url(req.get("url", ""))

    if not LANG_RE.fullmatch(str(req.get("language", "auto"))):
        raise ValueError("invalid language")
    req["language"] = str(req.get("language", "auto"))
    req["allow_audio_fallback"] = as_bool(req.get("allow_audio_fallback"), False)
    req["audio_access_authorized"] = as_bool(req.get("audio_access_authorized"), False)
    req["analysis_content_allowed"] = as_bool(req.get("analysis_content_allowed"), req.get("mode") == "youtube")
    req["reuse_allowed"] = as_bool(req.get("reuse_allowed"), False)

    basis = str(req.get("rights_basis", "")).strip()
    if not basis or len(basis) > 200:
        raise ValueError("rights_basis is required")
    if req["reuse_allowed"] and basis.lower() in UNVERIFIED_RIGHTS | {"analysis-only", "analysis-paraphrase-only"}:
        raise ValueError("reuse_allowed=true requires a concrete verified rights_basis")
    if req["allow_audio_fallback"]:
        if req.get("mode") == "youtube":
            raise ValueError("public YouTube is captions/comments/metadata only; audio fallback is forbidden")
        if not req["audio_access_authorized"]:
            raise ValueError("audio fallback requires audio_access_authorized=true")
        if basis.lower() in UNVERIFIED_RIGHTS | {"analysis-only", "analysis-paraphrase-only"}:
            raise ValueError("audio fallback requires a concrete authorization/rights_basis")

    context = req.get("source_context")
    source_set_version = str((context or {}).get("source_set_version", "")).strip()
    if not isinstance(context, dict) or context.get("project_id") != "project-transcriberen" or not source_set_version:
        raise ValueError("valid source_context is required")
    if source_set_version.casefold() in SOURCE_SET_PLACEHOLDERS:
        raise ValueError("source_context.source_set_version must name a concrete current source set")
    return req


def from_dispatch():
    youtube = {
        "scope": os.environ.get("INPUT_YOUTUBE_SCOPE", "video"),
        "query": os.environ.get("INPUT_YOUTUBE_QUERY", ""),
        "sort_by": os.environ.get("INPUT_YOUTUBE_SORT_BY", "relevance"),
        "max_items": os.environ.get("INPUT_YOUTUBE_MAX_ITEMS", "20"),
        "candidate_limit": os.environ.get("INPUT_YOUTUBE_CANDIDATE_LIMIT", "100"),
        "scan_limit": os.environ.get("INPUT_YOUTUBE_SCAN_LIMIT", "500"),
        "allow_unbounded": as_bool(os.environ.get("INPUT_YOUTUBE_ALLOW_UNBOUNDED"), False),
        "year_from": os.environ.get("INPUT_YOUTUBE_YEAR_FROM", ""),
        "year_to": os.environ.get("INPUT_YOUTUBE_YEAR_TO", ""),
        "min_views": os.environ.get("INPUT_YOUTUBE_MIN_VIEWS", ""),
        "min_likes": os.environ.get("INPUT_YOUTUBE_MIN_LIKES", ""),
        "min_comments": os.environ.get("INPUT_YOUTUBE_MIN_COMMENTS", ""),
        "include_comments": as_bool(os.environ.get("INPUT_YOUTUBE_INCLUDE_COMMENTS"), False),
        "comment_sort": os.environ.get("INPUT_YOUTUBE_COMMENT_SORT", "top"),
        "max_comments": os.environ.get("INPUT_YOUTUBE_MAX_COMMENTS", "200"),
    }
    return {
        "enabled": True,
        "request_id": f"dispatch-{os.environ.get('GITHUB_RUN_ID', 'manual')}",
        "owner": "webactueel-workflow",
        "project_id": "project-transcriberen",
        "url": os.environ.get("INPUT_URL", ""),
        "mode": os.environ.get("INPUT_MODE", "auto"),
        "language": os.environ.get("INPUT_LANGUAGE", "auto"),
        "allow_audio_fallback": as_bool(os.environ.get("INPUT_ALLOW_AUDIO_FALLBACK"), False),
        "audio_access_authorized": as_bool(os.environ.get("INPUT_AUDIO_ACCESS_AUTHORIZED"), False),
        "analysis_content_allowed": as_bool(os.environ.get("INPUT_ANALYSIS_CONTENT_ALLOWED"), True),
        "reuse_allowed": as_bool(os.environ.get("INPUT_REUSE_ALLOWED"), False),
        "rights_basis": os.environ.get("INPUT_RIGHTS_BASIS", "analysis-paraphrase-only"),
        "youtube": youtube,
        "requested_by": "workflow_dispatch",
        "source_context": {
            "project_id": "project-transcriberen",
            "source_set_version": os.environ.get("INPUT_SOURCE_SET_VERSION", "")
        }
    }


def main():
    event = os.environ.get("GITHUB_EVENT_NAME", "push")
    req = from_dispatch() if event == "workflow_dispatch" else json.loads(Path(os.environ.get("REQUEST_FILE", "requests/transcribe.json")).read_text(encoding="utf-8"))
    run = bool(req.get("enabled"))
    if run:
        req = validate_request(req)
    Path("resolved-request.json").write_text(json.dumps(req, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    out = os.environ.get("GITHUB_OUTPUT")
    values = {
        "run": str(run).lower(),
        "request_id": str(req.get("request_id", "none")),
        "install_whisper": str(bool(req.get("allow_audio_fallback") and req.get("audio_access_authorized"))).lower(),
        "reuse_allowed": str(bool(req.get("reuse_allowed"))).lower(),
        "persist_content": str(bool(req.get("analysis_content_allowed") or req.get("reuse_allowed"))).lower(),
    }
    if out:
        with open(out, "a", encoding="utf-8") as handle:
            for key, value in values.items():
                handle.write(f"{key}={value}\n")
    else:
        print(json.dumps(values))


if __name__ == "__main__":
    main()
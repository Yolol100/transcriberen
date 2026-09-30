#!/usr/bin/env python3
"""Caption-first public routes for YouTube videos/Shorts.

The simple public path can use Google's timedtext caption endpoint directly;
when richer metadata is available it prefers anonymous InnerTube player clients.
No cookies, login state, proxying, PO tokens, media download, or browser/TLS
impersonation are introduced here.
"""
from __future__ import annotations

import urllib.parse
import xml.etree.ElementTree as ET

TIMEDTEXT_ENDPOINT = "https://video.google.com/timedtext"
PLAYER_ENDPOINTS = (
    "https://youtubei.googleapis.com/youtubei/v1/player?prettyPrint=false",
    "https://www.youtube.com/youtubei/v1/player?prettyPrint=false",
)

PLAYER_CLIENTS = {
    "ANDROID_VR": {
        "clientName": "ANDROID_VR",
        "clientVersion": "1.61.48",
        "androidSdkVersion": 32,
        "deviceModel": "Quest 3",
        "userAgent": (
            "com.google.android.apps.youtube.vr.oculus/1.61.48 "
            "(Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip"
        ),
    },
    "IOS": {
        "clientName": "IOS",
        "clientVersion": "20.10.4",
        "deviceModel": "iPhone16,2",
        "userAgent": (
            "com.google.ios.youtube/20.10.4 "
            "(iPhone16,2; U; CPU iOS 18_3_2 like Mac OS X)"
        ),
    },
    "TVHTML5_SIMPLY_EMBEDDED_PLAYER": {
        "clientName": "TVHTML5_SIMPLY_EMBEDDED_PLAYER",
        "clientVersion": "2.0",
        "userAgent": (
            "Mozilla/5.0 (PlayStation; PlayStation 4/12.00) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15"
        ),
    },
    "MWEB": {
        "clientName": "MWEB",
        "clientVersion": "2.20250606.01.00",
        "userAgent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_3 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 "
            "Mobile/15E148 Safari/604.1"
        ),
    },
}

PLAYER_CLIENT_ORDER = (
    "ANDROID_VR",
    "IOS",
    "TVHTML5_SIMPLY_EMBEDDED_PLAYER",
    "MWEB",
    "ANDROID",
)


def _with_public_key(endpoint: str, api_key: str) -> str:
    parts = urllib.parse.urlsplit(endpoint)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    if not any(key == "key" for key, _ in query):
        query.append(("key", api_key))
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), parts.fragment)
    )


def _timedtext_url(video_id: str, *, track=None) -> str:
    query = [("v", video_id)]
    if track is None:
        query.append(("type", "list"))
    else:
        query.append(("type", "track"))
        language = str(track.get("lang_code") or "").strip()
        if language:
            query.append(("lang", language))
        name = str(track.get("name") or "").strip()
        if name:
            query.append(("name", name))
        track_id = str(track.get("id") or "").strip()
        if track_id:
            query.append(("id", track_id))
    return TIMEDTEXT_ENDPOINT + "?" + urllib.parse.urlencode(query)


def _parse_track_list(runtime, raw: bytes):
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise runtime.InnerTubeError("timedtext XML DTD/entity declarations are forbidden")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise runtime.InnerTubeError(f"invalid timedtext track list: {exc}") from exc
    tracks = []
    for elem in root.iter():
        if str(elem.tag).split("}")[-1] != "track":
            continue
        language = str(elem.attrib.get("lang_code") or "").strip()
        if not language:
            continue
        name = str(elem.attrib.get("name") or "").strip()
        raw_kind = str(elem.attrib.get("kind") or "").strip().lower()
        automatic = (
            raw_kind == "asr"
            or "automatic" in name.casefold()
            or "auto-generated" in name.casefold()
        )
        tracks.append({
            "id": str(elem.attrib.get("id") or "").strip(),
            "name": name,
            "lang_code": language,
            "kind": "automatic" if automatic else "manual",
        })
    return tracks


def timedtext_metadata(runtime, url: str):
    """Get minimal caption metadata without loading a YouTube player response."""
    video_id = runtime.video_id_from_url(url)
    raw, status = runtime._request_bytes(_timedtext_url(video_id), client_name="WEB")
    if status != 200:
        raise runtime.InnerTubeError(f"timedtext list returned HTTP {status}")
    tracks = _parse_track_list(runtime, raw)
    if not tracks:
        raise runtime.InnerTubeUnsupported("timedtext returned no public caption tracks")
    manual, automatic = {}, {}
    for track in tracks:
        entry = {
            "url": _timedtext_url(video_id, track=track),
            "name": track["name"],
            "ext": "srv1",
            "_innertube_client": "WEB",
            "_innertube_kind": track["kind"],
            "_timedtext_direct": True,
        }
        target = automatic if track["kind"] == "automatic" else manual
        target.setdefault(track["lang_code"], []).append(entry)
    runtime._record("timedtext-list", "WEB", "success", f"tracks:{len(tracks)}")
    return {
        "id": video_id,
        "webpage_url": f"https://www.youtube.com/watch?v={video_id}",
        "original_url": str(url),
        "availability": "public",
        "subtitles": manual,
        "automatic_captions": automatic,
        "_timedtext_direct": True,
    }


def apply(runtime) -> None:
    """Install the caption-first anonymous client cascade on innertube_runtime."""
    runtime.CLIENTS.update({name: dict(cfg) for name, cfg in PLAYER_CLIENTS.items()})
    runtime.PLAYER_CLIENT_ORDER = PLAYER_CLIENT_ORDER
    runtime.YOUTUBE_HOSTS.add("video.google.com")


def metadata_for(runtime, url: str, *, include_engagement: bool = False):
    """Try direct timedtext plus public player hosts without weakening rich metadata."""
    apply(runtime)
    direct_meta = None
    errors = []
    try:
        direct_meta = timedtext_metadata(runtime, url)
    except Exception as exc:
        errors.append(f"video.google.com: {exc}")
        runtime._record("timedtext-list", "WEB", "error", exc)

    original_endpoint = runtime.PLAYER_ENDPOINT
    try:
        for endpoint in PLAYER_ENDPOINTS:
            runtime.PLAYER_ENDPOINT = _with_public_key(endpoint, runtime.WEB_API_KEY)
            try:
                return runtime.metadata_for(url, include_engagement=include_engagement)
            except Exception as exc:
                errors.append(f"{urllib.parse.urlsplit(endpoint).hostname}: {exc}")
    finally:
        runtime.PLAYER_ENDPOINT = original_endpoint

    if direct_meta is not None:
        return direct_meta
    raise runtime.InnerTubeError("; ".join(errors) or "caption provider fallback exhausted")

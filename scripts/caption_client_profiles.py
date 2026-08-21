#!/usr/bin/env python3
"""Caption-first InnerTube client profiles for public YouTube videos/Shorts.

This module only changes which anonymous public player clients/endpoints are
tried for caption discovery. It does not add cookies, login state, proxying,
PO tokens, media download, or browser/TLS impersonation.
"""
from __future__ import annotations

import urllib.parse

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


def apply(runtime) -> None:
    """Install the caption-first anonymous client cascade on innertube_runtime."""
    runtime.CLIENTS.update({name: dict(cfg) for name, cfg in PLAYER_CLIENTS.items()})
    runtime.PLAYER_CLIENT_ORDER = PLAYER_CLIENT_ORDER


def metadata_for(runtime, url: str, *, include_engagement: bool = False):
    """Try public player hosts in order while keeping the existing metadata shape."""
    apply(runtime)
    original_endpoint = runtime.PLAYER_ENDPOINT
    errors = []
    try:
        for endpoint in PLAYER_ENDPOINTS:
            runtime.PLAYER_ENDPOINT = _with_public_key(endpoint, runtime.WEB_API_KEY)
            try:
                return runtime.metadata_for(url, include_engagement=include_engagement)
            except Exception as exc:
                errors.append(f"{urllib.parse.urlsplit(endpoint).hostname}: {exc}")
    finally:
        runtime.PLAYER_ENDPOINT = original_endpoint
    raise runtime.InnerTubeError("; ".join(errors) or "caption player endpoint fallback exhausted")

#!/usr/bin/env python3
import ipaddress
import json
import os
import re
import socket
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$")
LANG_RE = re.compile(r"^(?:auto|[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})?)$")
MODES = {"auto", "media", "article", "feed", "sitemap"}
SECRET_KEY_RE = re.compile(r"(?:token|secret|api[_-]?key|access[_-]?key|password|passwd|authorization|signature|sig|credential)", re.I)
UNVERIFIED_RIGHTS = {"unknown", "analysis-only", "unverified"}


def as_bool(value, default=False):
    if value is None or value == "":
        return default
    if value is True or str(value).lower() == "true":
        return True
    if value is False or str(value).lower() == "false":
        return False
    raise ValueError("boolean expected")


def as_int(value, default, minimum, maximum):
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("integer expected") from exc
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"integer must be between {minimum} and {maximum}")
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


def validate_request(req):
    if not isinstance(req, dict):
        raise ValueError("request must be object")
    if not ID_RE.fullmatch(str(req.get("request_id", ""))):
        raise ValueError("invalid request_id")
    if req.get("owner") != "webactueel-workflow" or req.get("project_id") != "project-transcriberen":
        raise ValueError("owner/project mismatch")
    validate_public_url(req.get("url", ""))
    if req.get("mode") not in MODES:
        raise ValueError("invalid mode")
    if not LANG_RE.fullmatch(str(req.get("language", "auto"))):
        raise ValueError("invalid language")
    req["max_items"] = as_int(req.get("max_items"), 0, 0, 5000)
    req["allow_audio_fallback"] = as_bool(req.get("allow_audio_fallback"), False)
    req["audio_access_authorized"] = as_bool(req.get("audio_access_authorized"), False)
    req["reuse_allowed"] = as_bool(req.get("reuse_allowed"), False)
    basis = str(req.get("rights_basis", "")).strip()
    if not basis or len(basis) > 160:
        raise ValueError("rights_basis is required")
    if req["reuse_allowed"] and basis.lower() in UNVERIFIED_RIGHTS:
        raise ValueError("reuse_allowed=true requires a concrete verified rights_basis")
    if req["allow_audio_fallback"]:
        if not req["audio_access_authorized"]:
            raise ValueError("audio fallback requires audio_access_authorized=true")
        if basis.lower() in UNVERIFIED_RIGHTS:
            raise ValueError("audio fallback requires a concrete authorization/rights_basis")
    context = req.get("source_context")
    if not isinstance(context, dict) or context.get("project_id") != "project-transcriberen" or not str(context.get("source_set_version", "")).strip():
        raise ValueError("valid source_context is required")
    return req


def from_dispatch():
    return {
        "enabled": True,
        "request_id": f"dispatch-{os.environ.get('GITHUB_RUN_ID', 'manual')}",
        "owner": "webactueel-workflow",
        "project_id": "project-transcriberen",
        "url": os.environ.get("INPUT_URL", ""),
        "mode": os.environ.get("INPUT_MODE", "auto"),
        "language": os.environ.get("INPUT_LANGUAGE", "auto"),
        "max_items": as_int(os.environ.get("INPUT_MAX_ITEMS"), 0, 0, 5000),
        "allow_audio_fallback": as_bool(os.environ.get("INPUT_ALLOW_AUDIO_FALLBACK"), False),
        "audio_access_authorized": as_bool(os.environ.get("INPUT_AUDIO_ACCESS_AUTHORIZED"), False),
        "reuse_allowed": as_bool(os.environ.get("INPUT_REUSE_ALLOWED"), False),
        "rights_basis": os.environ.get("INPUT_RIGHTS_BASIS", "analysis-only"),
        "requested_by": "workflow_dispatch",
        "source_context": {
            "project_id": "project-transcriberen",
            "source_set_version": os.environ.get("INPUT_SOURCE_SET_VERSION", "manual-dispatch")
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
        "reuse_allowed": str(bool(req.get("reuse_allowed"))).lower()
    }
    if out:
        with open(out, "a", encoding="utf-8") as handle:
            for key, value in values.items():
                handle.write(f"{key}={value}\n")
    else:
        print(json.dumps(values))


if __name__ == "__main__":
    main()

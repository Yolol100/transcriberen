#!/usr/bin/env python3
"""Bounded resilience layer for the generic accountless YouTube runtime.

Applied by runtime_hardened.py. It deliberately keeps all existing policy gates:
no cookies, accounts, proxies, PO-token bypass or media downloads.
"""
import json
import random
import re
import time
from pathlib import Path

ITEM_DELAY_MIN_SECONDS = 5.0
ITEM_DELAY_MAX_SECONDS = 10.0
RATE_LIMIT_DELAYS = (60, 180, 300)
TRANSIENT_DELAYS = (3, 8, 20)
SUBTITLE_CLIENTS = ("tv", "mweb", "web_safari", "web_embedded")
RATE_LIMIT_MARKERS = ("http error 429", "too many requests", "rate limit")
TRANSIENT_MARKERS = (
    "incomplete data received", "remote end closed connection", "connection reset",
    "remotedisconnected", "timed out", "timeout", "temporary failure", "name resolution",
    "ssl eof", "http error 500", "http error 502", "http error 503", "http error 504",
)


def _error_text(completed):
    return str(getattr(completed, "stderr", "") or "").casefold()


def _delays(completed):
    if getattr(completed, "returncode", 1) == 124:
        return ()
    text = _error_text(completed)
    if any(marker in text for marker in RATE_LIMIT_MARKERS):
        return RATE_LIMIT_DELAYS
    if any(marker in text for marker in TRANSIENT_MARKERS):
        return TRANSIENT_DELAYS
    return ()


def _append_extractor_arg(cmd, value):
    cmd = list(cmd)
    try:
        idx = cmd.index("--extractor-args") + 1
    except ValueError:
        cmd += ["--extractor-args", "youtube:" + value]
        return cmd
    current = str(cmd[idx])
    if current.startswith("youtube:"):
        body = current[len("youtube:"):]
        cmd[idx] = "youtube:" + (body + ";" if body else "") + value
    else:
        cmd += ["--extractor-args", "youtube:" + value]
    return cmd


def apply(module):
    """Patch one imported youtube_runtime module in-place and return it."""
    if getattr(module, "_webactueel_resilience_applied", False):
        return module

    original_json_command = module._json_command
    original_subtitle_command = module.subtitle_command
    original_comments_for = module.comments_for
    original_classify_comment_error = module.classify_comment_error
    original_collect = module.collect

    state = {"include_replies": False, "last_selected_item": False}

    def run_recovering(command):
        completed = module.run(command, check=False)
        for delay in _delays(completed):
            if completed.returncode == 0 or completed.returncode == 124:
                break
            time.sleep(delay)
            completed = module.run(command, check=False)
        return completed

    def load_json(command):
        completed = run_recovering(command)
        if completed.returncode != 0 or not str(completed.stdout or "").strip():
            raise RuntimeError(str(completed.stderr or "")[-4000:] or "yt-dlp returned no JSON")
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"yt-dlp returned invalid JSON: {exc}") from exc

    def json_command(source, *, flat=False, comments=False, comment_sort="top", max_comments="200", playlist_end=None):
        cmd = original_json_command(
            source, flat=flat, comments=comments, comment_sort=comment_sort,
            max_comments=max_comments, playlist_end=playlist_end,
        )
        if not comments:
            return cmd
        limit = "all" if str(max_comments).lower() == "all" else str(int(max_comments))
        include_replies = bool(state["include_replies"])
        bounded = f"{limit},all,all,all" if include_replies else f"{limit},{limit},0,0"
        try:
            idx = cmd.index("--extractor-args") + 1
            current = str(cmd[idx])
            current = re.sub(r"max_comments=[^;]+", f"max_comments={bounded}", current)
            if "raise_incomplete_data=" not in current:
                current += ";raise_incomplete_data=1"
            cmd[idx] = current
        except ValueError:
            cmd = _append_extractor_arg(cmd, f"max_comments={bounded};raise_incomplete_data=1")
        return cmd

    def subtitle_command(url, track, output_template, player_client=None):
        cmd = original_subtitle_command(url, track, output_template)
        if player_client:
            cmd = _append_extractor_arg(cmd, f"player_client={player_client}")
        return cmd

    def attempt_caption(url, track, tmp, player_client=None):
        completed = run_recovering(subtitle_command(url, track, tmp / "source.%(ext)s", player_client))
        files = sorted([*tmp.glob("source*.vtt"), *tmp.glob("source*.srt")])
        for subtitle_file in files:
            segments = module.subtitle_segments(subtitle_file)
            text = "\n".join(item["text"] for item in segments).strip()
            if text:
                info = {
                    **track,
                    "format": subtitle_file.suffix.lstrip("."),
                    "command_exit": completed.returncode,
                    "sha256": module.sha256_text(text + "\n"),
                    "cue_count": len(segments),
                    "player_client": player_client or "default",
                    "_segments": segments,
                }
                return text, info, completed
        return None, None, completed

    def download_caption(url, meta, preferred_language="auto"):
        if state["last_selected_item"]:
            time.sleep(random.uniform(ITEM_DELAY_MIN_SECONDS, ITEM_DELAY_MAX_SECONDS))
        state["last_selected_item"] = True

        track = module.choose_caption_track(meta, preferred_language)
        if not track:
            return None, None
        import tempfile
        with tempfile.TemporaryDirectory(prefix="webactueel-youtube-sub-") as tmpdir:
            tmp = Path(tmpdir)
            text, info, completed = attempt_caption(url, track, tmp)
            if text:
                return text, info
            last = completed
            for client in SUBTITLE_CLIENTS:
                for path in tmp.glob("source*"):
                    if path.is_file():
                        path.unlink()
                text, info, last = attempt_caption(url, track, tmp, client)
                if text:
                    return text, info
            if last.returncode != 0:
                raise RuntimeError(str(last.stderr or "")[-4000:] or "subtitle download failed")
        return None, track

    def comments_for(url, req, source_comment_count=None):
        state["include_replies"] = bool((req.get("youtube") or {}).get("include_replies", False))
        comments, summary = original_comments_for(url, req, source_comment_count)
        summary = dict(summary or {})
        if str((req.get("youtube") or {}).get("max_comments", "200")).lower() != "all":
            summary["completeness"] = "bounded-complete-or-error"
        summary["reply_completeness"] = "best_effort_unverified" if state["include_replies"] else "excluded"
        summary["incomplete_data_policy"] = "error"
        return comments, summary

    def classify_comment_error(value):
        message = str(value or "").casefold()
        if "incomplete data received" in message or any(marker in message for marker in RATE_LIMIT_MARKERS):
            return "error"
        return original_classify_comment_error(value)

    def collect(req, results_dir):
        state["include_replies"] = bool((req.get("youtube") or {}).get("include_replies", False))
        state["last_selected_item"] = False
        content, index = original_collect(req, results_dir)
        results_dir = Path(results_dir)
        items = index.get("items") or []
        retry_items = []
        for record in items:
            components = []
            if record.get("status") == "caption_error":
                components.append("caption")
            if record.get("comment_status") in {"error", "access_blocked"}:
                components.append("comments")
            if components:
                retry_items.append({
                    "id": record.get("id"), "artifact_id": record.get("artifact_id"),
                    "url": record.get("url"), "components": components,
                    "caption_status": record.get("status"), "comment_status": record.get("comment_status"),
                })
        (results_dir / "retry-queue.json").write_text(json.dumps({
            "schema_version": "webactueel-youtube-retry-queue/1.0",
            "request_id": req.get("request_id"), "retryable_item_count": len(retry_items), "items": retry_items,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        yt = req.get("youtube") or {}
        if yt.get("comment_selection") == "knowledge":
            handoff_items = [{
                "item_id": record.get("id"), "artifact_id": record.get("artifact_id"),
                "url": record.get("url"), "title": (record.get("metadata") or {}).get("title"),
                "upload_date": (record.get("metadata") or {}).get("upload_date"),
                "caption_sha256": record.get("transcript_sha256"), "caption_status": record.get("status"),
                "comment_status": record.get("comment_status"),
                "review_candidate_count": record.get("comment_review_candidates", 0),
            } for record in items]
            (results_dir / "knowledge-handoff.json").write_text(json.dumps({
                "schema_version": "webactueel-knowledge-handoff/1.0",
                "request_id": req.get("request_id"),
                "target_owner": (req.get("knowledge_context") or {}).get("target_owner"),
                "goal": (req.get("knowledge_context") or {}).get("goal"),
                "source_trust": "controlled-runtime-evidence-not-project-truth",
                "content_included": False,
                "semantic_review_required": True, "currentness_review_required": True,
                "deduplication_required": True, "conflict_check_required": True,
                "items": handoff_items,
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        bad_comments = {"error", "access_blocked"}
        if any(record.get("comment_status") in bad_comments for record in items):
            index["collection_status"] = "partial"
        index["schema_version"] = "webactueel-youtube-collection/1.1"
        index["comment_error_count"] = sum(record.get("comment_status") in bad_comments for record in items)
        index["retryable_item_count"] = len(retry_items)
        index["retry_queue_file"] = "retry-queue.json"
        index["knowledge_handoff_file"] = "knowledge-handoff.json" if yt.get("comment_selection") == "knowledge" else None
        index["include_replies"] = bool(yt.get("include_replies", False))
        index["item_delay_seconds"] = [ITEM_DELAY_MIN_SECONDS, ITEM_DELAY_MAX_SECONDS]
        (results_dir / "youtube-index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return content, index

    module.load_json = load_json
    module._json_command = json_command
    module.subtitle_command = subtitle_command
    module.download_caption = download_caption
    module.comments_for = comments_for
    module.classify_comment_error = classify_comment_error
    module.collect = collect
    module._webactueel_resilience_applied = True
    return module

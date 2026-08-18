"""Temporary live QA matrix. This file must not ship on main."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import youtube_runtime as yt


def check(name, fn):
    print(f"::group::{name}")
    value = fn()
    print(json.dumps(value, ensure_ascii=False, default=str) if isinstance(value, (dict, list)) else value)
    print("::endgroup::")
    return value


def manual_caption():
    url = "https://www.youtube.com/watch?v=QRS8MkLhQmM"
    meta = yt.metadata_for(url)
    track = yt.choose_caption_track(meta, "auto")
    assert track and yt.language_family(track["language"]) == "en" and track["kind"] == "manual", track
    text, info = yt.download_caption(url, meta, "auto")
    assert text and len(text) > 100 and info["kind"] == "manual"
    return {"id": meta.get("id"), "caption": info, "chars": len(text)}


def automatic_caption():
    url = "https://www.youtube.com/watch?v=8YoUxe5ncPo"
    meta = yt.metadata_for(url)
    track = yt.choose_caption_track(meta, "auto")
    assert track and yt.language_family(track["language"]) == "en" and track["kind"] == "automatic", track
    text, info = yt.download_caption(url, meta, "auto")
    assert text and len(text) > 100 and info["kind"] == "automatic"
    return {"id": meta.get("id"), "caption": info, "chars": len(text)}


def playlist_discovery():
    req = {
        "url": "https://www.youtube.com/playlist?list=PLt5yu3-wZAlSLRHmI1qNm0wjyVNWw1pCU",
        "youtube": {"scope": "playlist", "max_items": 1, "scan_limit": 5, "sort_by": "relevance"},
    }
    items, info = yt.discover_candidates_detailed(req)
    assert items, info
    return {"first": items[0], "discovery": info}


def channel_discovery():
    req = {
        "url": "https://www.youtube.com/@creativecommons",
        "youtube": {"scope": "channel_videos", "max_items": 2, "scan_limit": 2, "sort_by": "relevance"},
    }
    items, info = yt.discover_candidates_detailed(req)
    assert len(items) >= 1, info
    return {"items": items[:2], "discovery": info}


def shorts_discovery_and_direct_route():
    req = {
        "url": "https://www.youtube.com/@YouTube",
        "youtube": {"scope": "channel_shorts", "max_items": 5, "scan_limit": 5, "sort_by": "relevance"},
    }
    items, info = yt.discover_candidates_detailed(req)
    assert items, info
    first_id = items[0].get("id")
    assert first_id
    short_url = f"https://www.youtube.com/shorts/{first_id}"
    meta = yt.metadata_for(short_url)
    assert meta.get("id") == first_id
    for item in items[:5]:
        candidate_meta = yt.metadata_for(f"https://www.youtube.com/shorts/{item['id']}")
        track = yt.choose_caption_track(candidate_meta, "auto")
        if not track:
            continue
        text, caption = yt.download_caption(f"https://www.youtube.com/shorts/{item['id']}", candidate_meta, "auto")
        if text:
            return {"direct_short": first_id, "caption_short": item["id"], "caption": caption, "chars": len(text), "discovery": info}
    raise AssertionError("No captioned Short found in first 5 @YouTube Shorts")


def search_rank_filter_and_comments():
    req = {
        "language": "auto", "analysis_content_allowed": False, "reuse_allowed": False,
        "youtube": {
            "scope": "search", "query": "python tutorial", "candidate_limit": 5, "max_items": 2,
            "sort_by": "views", "include_comments": True, "comment_sort": "top", "max_comments": "2",
        },
    }
    candidates, discovery = yt.discover_candidates_detailed(req)
    assert candidates, discovery
    hydrated = []
    comment_target = None
    for candidate in candidates:
        meta = yt.metadata_for(candidate["url"])
        hydrated.append({"url": candidate["url"], "meta": meta})
        if comment_target is None and int(meta.get("comment_count") or 0) > 0:
            comment_target = (candidate["url"], meta)
    ranked = yt.rank_metadata(hydrated, "views")
    assert ranked and all((ranked[i]["meta"].get("view_count") or 0) >= (ranked[i + 1]["meta"].get("view_count") or 0) for i in range(len(ranked) - 1))
    assert comment_target is not None, "No comment-enabled target in first 5 search results"
    comments, summary = yt.comments_for(comment_target[0], req, comment_target[1].get("comment_count"))
    assert isinstance(comments, list) and len(comments) <= 2
    assert summary["identity_minimized"] is True and summary["mode"] == "bounded"
    assert all("author" not in c and "author_id" not in c and "id" not in c for c in comments)
    return {
        "candidate_count": len(candidates), "top_id": ranked[0]["meta"].get("id"),
        "comments": len(comments), "comment_summary": summary, "discovery": discovery,
    }


def main():
    check("manual English caption", manual_caption)
    check("automatic English caption", automatic_caption)
    check("playlist discovery", playlist_discovery)
    check("channel videos discovery", channel_discovery)
    check("channel Shorts + direct Short caption", shorts_discovery_and_direct_route)
    check("search ranking + bounded comments", search_rank_filter_and_comments)
    print("LIVE YOUTUBE QA: OK")


if __name__ == "__main__":
    main()

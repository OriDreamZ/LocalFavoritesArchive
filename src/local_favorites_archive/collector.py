from datetime import datetime, timezone
import re
from typing import Any

from .models import MediaItem, Post


_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def clean_post_text(text: str | None) -> str:
    """Remove link tokens while preserving the readable line structure."""
    lines = [re.sub(r"[ \t]+", " ", _URL_RE.sub("", line)).strip() for line in (text or "").splitlines()]
    cleaned: list[str] = []
    for line in lines:
        if line or (cleaned and cleaned[-1]):
            cleaned.append(line)
    while cleaned and not cleaned[-1]:
        cleaned.pop()
    return "\n".join(cleaned)


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def pick_profile_path(hrefs: list[str]) -> str | None:
    reserved = {"home", "explore", "notifications", "messages", "search", "settings", "login", "signup", "compose", "tos", "privacy", "i"}
    for href in hrefs:
        path = href.split("?", 1)[0].rstrip("/")
        parts = [part for part in path.split("/") if part]
        if len(parts) == 1 and parts[0].lower() not in reserved:
            return f"/{parts[0]}"
    return None


def _unwrap_tweet(result: Any) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    if result.get("tweet") and isinstance(result["tweet"], dict):
        return result["tweet"]
    if result.get("tweet_results", {}).get("result"):
        return _unwrap_tweet(result["tweet_results"]["result"])
    return result


def _timeline_tweets(payload: Any) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for node in _walk(payload):
        entry_id = str(node.get("entryId") or node.get("entry_id") or "")
        if not entry_id.startswith("tweet-"):
            continue
        for child in _walk(node.get("content") or {}):
            result = (child.get("tweet_results") or {}).get("result")
            tweet = _unwrap_tweet(result)
            if tweet and tweet.get("rest_id") and isinstance(tweet.get("legacy"), dict):
                results.append(tweet)
                break
    if results:
        return results
    return [node for node in _walk(payload) if node.get("rest_id") and isinstance(node.get("legacy"), dict)]


def posts_from_x_response(payload: Any) -> list[Post]:
    posts: dict[str, Post] = {}
    for node in _timeline_tweets(payload):
        legacy = node.get("legacy")
        post_id = node.get("rest_id")
        core = node.get("core") or {}
        if not post_id or not isinstance(legacy, dict) or not (legacy.get("full_text") or legacy.get("created_at")):
            continue
        user_result = ((core.get("user_results") or {}).get("result") or {})
        user_legacy = user_result.get("legacy") or {}
        user_core = user_result.get("core") or {}
        handle = user_core.get("screen_name") or user_legacy.get("screen_name", "")
        author_name = user_core.get("name") or user_legacy.get("name", "")
        created = None
        try:
            created = datetime.strptime(legacy.get("created_at", ""), "%a %b %d %H:%M:%S %z %Y")
        except ValueError:
            pass
        media: list[MediaItem] = []
        for index, item in enumerate((legacy.get("extended_entities") or {}).get("media", [])):
            kind = "video" if item.get("type") in {"video", "animated_gif"} else "image"
            if kind == "video":
                variants = [v for v in (item.get("video_info") or {}).get("variants", []) if v.get("url") and v.get("content_type") == "video/mp4"]
                variants.sort(key=lambda variant: variant.get("bitrate", 0))
                source = variants[-1]["url"] if variants else ""
                mime = "video/mp4"
            else:
                source = item.get("media_url_https", "") + "?name=orig"
                mime = "image/jpeg"
            if source:
                info = item.get("original_info") or {}
                media.append(MediaItem(index=index, kind=kind, source_url=source, mime_type=mime, width=info.get("width"), height=info.get("height")))
        note_text = (((node.get("note_tweet") or {}).get("note_tweet_results") or {}).get("result") or {}).get("text")
        posts[str(post_id)] = Post(
            post_id=str(post_id), url=f"https://x.com/{handle or 'i'}/status/{post_id}",
            text=clean_post_text(note_text or legacy.get("full_text", "")), author_id=str(user_result.get("rest_id") or ""),
            author_handle=handle, author_name=author_name, published_at=created,
            collected_at=datetime.now(timezone.utc), reply_to_id=legacy.get("in_reply_to_status_id_str"),
            quote_id=legacy.get("quoted_status_id_str"), language=legacy.get("lang"), raw=node, media=media,
        )
    return list(posts.values())

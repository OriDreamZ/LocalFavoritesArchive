from datetime import datetime, timezone
from typing import Any
from .models import MediaItem, Post


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _pick_video_url(media: dict[str, Any]) -> str:
    variants = media.get("video_info", {}).get("variants", [])
    candidates = [v for v in variants if v.get("url")]
    candidates.sort(key=lambda item: (item.get("bitrate") or 0, item.get("content_type", "")))
    return candidates[-1]["url"] if candidates else media.get("media_url_https", "")


def normalize_post(raw: dict[str, Any]) -> Post:
    author = raw.get("author") or {}
    post_id = str(raw.get("id") or raw.get("id_str") or raw.get("rest_id") or "")
    media_items: list[MediaItem] = []
    for index, item in enumerate(raw.get("media") or raw.get("extended_entities", {}).get("media", []) or []):
        kind = "video" if item.get("type") in {"video", "animated_gif"} or item.get("video_info") else "image"
        source_url = _pick_video_url(item) if kind == "video" else item.get("media_url_https") or item.get("url", "")
        media_items.append(MediaItem(index=index, kind=kind, source_url=source_url, mime_type=item.get("mime_type"), width=item.get("original_info", {}).get("width"), height=item.get("original_info", {}).get("height")))
    return Post(
        post_id=post_id,
        url=raw.get("url") or (f"https://x.com/{author.get('screen_name', '_')}/status/{post_id}" if post_id else ""),
        text=raw.get("text") or raw.get("full_text") or raw.get("note_tweet", {}).get("text", ""),
        author_id=str(author.get("id") or author.get("rest_id") or ""),
        author_handle=author.get("screen_name") or author.get("username") or "",
        author_name=author.get("name") or "",
        published_at=_parse_time(raw.get("created_at") or raw.get("created_at_iso")),
        collected_at=datetime.now(timezone.utc),
        reply_to_id=str(raw.get("in_reply_to_status_id_str")) if raw.get("in_reply_to_status_id_str") else None,
        quote_id=str(raw.get("quoted_status_id_str")) if raw.get("quoted_status_id_str") else None,
        language=raw.get("lang"),
        raw=raw,
        media=media_items,
    )

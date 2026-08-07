from datetime import datetime, timezone
import re
from typing import Any

from .models import MediaItem, Post, PostLink


_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def _normalize_whitespace(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    cleaned: list[str] = []
    for line in lines:
        if line or (cleaned and cleaned[-1]):
            cleaned.append(line)
    while cleaned and not cleaned[-1]:
        cleaned.pop()
    return "\n".join(cleaned)


def normalize_post_text(
    text: str | None,
    url_entities: list[dict[str, Any]],
    media_entities: list[dict[str, Any]],
) -> tuple[str, list[PostLink]]:
    source = text or ""
    media_urls = {item.get("url") for item in media_entities if item.get("url")}
    urls = {item.get("url"): item for item in url_entities if item.get("url")}
    parts: list[str] = []
    links: list[PostLink] = []
    cursor = 0

    for match in _URL_RE.finditer(source):
        token = match.group(0)
        parts.append(source[cursor:match.start()])
        if token in media_urls:
            replacement = ""
        else:
            entity = urls.get(token) or {}
            replacement = entity.get("display_url") or entity.get("expanded_url") or token
            expanded_url = entity.get("expanded_url") or token
            links.append(PostLink(len(links), replacement, expanded_url, token))
        parts.append(replacement)
        cursor = match.end()

    parts.append(source[cursor:])
    return _normalize_whitespace("".join(parts)), links


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
        note_result = (((node.get("note_tweet") or {}).get("note_tweet_results") or {}).get("result") or {})
        note_text = note_result.get("text")
        entities = legacy.get("entities") or {}
        url_entities = ((note_result.get("entity_set") or {}).get("urls") or []) if note_text else (entities.get("urls") or [])
        media_entities = [
            *(entities.get("media") or []),
            *((legacy.get("extended_entities") or {}).get("media") or []),
        ]
        normalized_text, links = normalize_post_text(note_text or legacy.get("full_text", ""), url_entities, media_entities)
        posts[str(post_id)] = Post(
            post_id=str(post_id), url=f"https://x.com/{handle or 'i'}/status/{post_id}",
            text=normalized_text, author_id=str(user_result.get("rest_id") or ""),
            author_handle=handle, author_name=author_name, published_at=created,
            collected_at=datetime.now(timezone.utc), reply_to_id=legacy.get("in_reply_to_status_id_str"),
            quote_id=legacy.get("quoted_status_id_str"), language=legacy.get("lang"), raw=node, media=media, links=links,
        )
    return list(posts.values())


def post_from_dom_payload(value: dict[str, Any]) -> Post | None:
    post_id = str(value.get("post_id") or "").strip()
    handle = str(value.get("author_handle") or "").lstrip("@").strip()
    url = str(value.get("url") or "").strip()
    if not post_id or not handle or not url.startswith(("https://x.com/", "https://twitter.com/")):
        return None
    published_at = None
    try:
        published_at = datetime.fromisoformat(str(value.get("published_at") or "").replace("Z", "+00:00"))
    except ValueError:
        pass
    links = [
        PostLink(index, link, link, link)
        for index, link in enumerate(value.get("links") or [])
        if isinstance(link, str) and link.startswith(("https://", "http://"))
    ]
    media = []
    for index, item in enumerate(value.get("media") or []):
        source = str(item.get("source_url") or "")
        kind = str(item.get("kind") or "")
        if kind in {"image", "video"} and source.startswith(("https://", "http://")):
            is_video_thumbnail = "amplify_video_thumb" in source
            media.append(MediaItem(
                index, "video" if is_video_thumbnail else kind, source,
                "video/thumbnail" if is_video_thumbnail else item.get("mime_type"),
                status="deferred" if is_video_thumbnail else "queued",
            ))
    return Post(
        post_id=post_id, url=url, text=_normalize_whitespace(str(value.get("text") or "")),
        author_id=str(value.get("author_id") or ""), author_handle=handle,
        author_name=str(value.get("author_name") or handle), published_at=published_at,
        collected_at=datetime.now(timezone.utc), raw={"source": "dom", "post": value},
        media=media, links=links,
    )

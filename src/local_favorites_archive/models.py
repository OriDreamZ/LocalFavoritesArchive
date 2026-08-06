from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class MediaItem:
    index: int
    kind: str
    source_url: str
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    duration_ms: int | None = None
    local_path: str | None = None
    status: str = "queued"
    error: str | None = None


@dataclass
class PostLink:
    index: int
    display_url: str
    expanded_url: str
    short_url: str


@dataclass
class Post:
    post_id: str
    url: str
    text: str
    author_id: str
    author_handle: str
    author_name: str
    published_at: datetime | None
    collected_at: datetime
    reply_to_id: str | None = None
    quote_id: str | None = None
    language: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    media: list[MediaItem] = field(default_factory=list)
    links: list[PostLink] = field(default_factory=list)

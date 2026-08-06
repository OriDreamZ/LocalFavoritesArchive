from datetime import datetime, timezone
import pytest
from local_favorites_archive.models import MediaItem, Post
from local_favorites_archive.storage import ArchiveStore


def sample_post(text="hello archive", post_id="42", handle="a", published_at=None, collected_at=None, with_media=True):
    published_at = published_at or datetime(2024, 1, 2, tzinfo=timezone.utc)
    collected_at = collected_at or datetime.now(timezone.utc)
    media = [MediaItem(0, "image", "https://pbs.twimg.com/media/a.jpg?name=orig")] if with_media else []
    return Post(post_id, f"https://x.com/{handle}/status/{post_id}", text, "1", handle, handle.title(), published_at, collected_at, raw={"id": post_id}, media=media)


def test_upsert_is_idempotent_and_searchable(tmp_path):
    store = ArchiveStore(tmp_path)
    assert store.upsert_post(sample_post()) is True
    assert store.upsert_post(sample_post("hello updated")) is False
    rows = store.list_posts(query="updated")
    assert len(rows) == 1
    assert rows[0]["post_id"] == "42"
    detail = store.get_post("42")
    assert detail["media"][0]["source_url"].startswith("https://pbs.twimg.com")
    assert (tmp_path / "raw" / "42.json").exists()


def test_media_path_is_stable(tmp_path):
    store = ArchiveStore(tmp_path)
    first = store.media_path("42", 0, "https://example/a.jpg")
    assert first == store.media_path("42", 0, "https://example/a.jpg")
    assert first.parent.name == "42"


def test_posts_sort_by_time_in_both_directions(tmp_path):
    store = ArchiveStore(tmp_path)
    store.upsert_post(sample_post(post_id="1", published_at=datetime(2024, 1, 1, tzinfo=timezone.utc)))
    store.upsert_post(sample_post(post_id="2", published_at=datetime(2024, 2, 1, tzinfo=timezone.utc)))

    assert [row["post_id"] for row in store.list_posts(sort="published_at", direction="asc")] == ["1", "2"]
    assert [row["post_id"] for row in store.list_posts(sort="published_at", direction="desc")] == ["2", "1"]


def test_posts_sort_by_author_case_insensitively(tmp_path):
    store = ArchiveStore(tmp_path)
    store.upsert_post(sample_post(post_id="1", handle="zebra"))
    store.upsert_post(sample_post(post_id="2", handle="Alpha"))

    assert [row["author_handle"] for row in store.list_posts(sort="author", direction="asc")] == ["Alpha", "zebra"]
    assert [row["author_handle"] for row in store.list_posts(sort="author", direction="desc")] == ["zebra", "Alpha"]


def test_post_count_matches_filters_and_page_slice(tmp_path):
    store = ArchiveStore(tmp_path)
    store.upsert_post(sample_post(text="alpha first", post_id="1", handle="alice"))
    store.upsert_post(sample_post(text="alpha second", post_id="2", handle="alice"))
    store.upsert_post(sample_post(text="beta", post_id="3", handle="bob"))

    assert store.count_posts(query="alpha", author="alice") == 2
    page = store.list_posts(sort="published_at", direction="asc", limit=1, offset=1)
    assert len(page) == 1


def test_text_filter_returns_only_posts_without_media(tmp_path):
    store = ArchiveStore(tmp_path)
    store.upsert_post(sample_post(post_id="1", with_media=True))
    store.upsert_post(sample_post(post_id="2", with_media=False))

    assert [row["post_id"] for row in store.list_posts(media_type="text")] == ["2"]
    assert store.count_posts(media_type="text") == 1


def test_tags_can_be_managed_assigned_and_filtered(tmp_path):
    store = ArchiveStore(tmp_path)
    store.upsert_post(sample_post(post_id="1"))
    store.upsert_post(sample_post(post_id="2"))

    tag = store.create_tag("待读", "#2563eb")
    assert store.assign_tag("1", tag["id"]) is True
    assert store.assign_tag("1", tag["id"]) is False
    assert store.get_post("1")["tags"] == [{"id": tag["id"], "name": "待读", "color": "#2563eb"}]
    assert [row["post_id"] for row in store.list_posts(tag_id=tag["id"])] == ["1"]
    assert store.count_posts(tag_id=tag["id"]) == 1

    updated = store.update_tag(tag["id"], "已整理", "#0f766e")
    assert updated["name"] == "已整理"
    assert store.list_tags()[0]["post_count"] == 1
    assert store.remove_tag("1", tag["id"]) is True
    assert store.get_post("1")["tags"] == []
    assert store.delete_tag(tag["id"]) is True
    assert store.list_tags() == []


def test_tag_names_are_unique_case_insensitively(tmp_path):
    store = ArchiveStore(tmp_path)
    store.create_tag("Read Later", "#2563eb")

    with pytest.raises(ValueError, match="already exists"):
        store.create_tag("read later", "#16a34a")


def test_overview_stats_reports_archive_aggregates(tmp_path):
    store = ArchiveStore(tmp_path)
    store.upsert_post(sample_post(
        post_id="1",
        handle="alice",
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        collected_at=datetime(2024, 1, 10, tzinfo=timezone.utc),
    ))
    store.upsert_post(sample_post(
        post_id="2",
        handle="bob",
        published_at=datetime(2024, 1, 3, tzinfo=timezone.utc),
        collected_at=datetime(2024, 2, 10, tzinfo=timezone.utc),
        with_media=False,
    ))
    tag = store.create_tag("待读", "#2563eb")
    store.assign_tag("1", tag["id"])
    with store._connect() as db:
        db.execute("UPDATE media SET status='downloaded', byte_size=2048 WHERE post_id='1'")

    stats = store.overview_stats(now=datetime(2024, 2, 15, tzinfo=timezone.utc))

    assert stats["posts_total"] == 2
    assert stats["authors_total"] == 2
    assert stats["tagged_posts"] == 1
    assert stats["tag_coverage_percent"] == 50.0
    assert stats["media_total"] == 1
    assert stats["media_downloaded"] == 1
    assert stats["media_failed"] == 0
    assert stats["media_completion_percent"] == 100.0
    assert stats["image_posts"] == 1
    assert stats["video_posts"] == 0
    assert stats["text_posts"] == 1
    assert stats["archive_days"] == 3
    assert stats["storage_bytes"] == 2048
    assert len(stats["monthly_additions"]) == 12
    assert stats["monthly_additions"][-2:] == [
        {"month": "2024-01", "count": 1},
        {"month": "2024-02", "count": 1},
    ]


def test_overview_stats_handles_empty_media_and_zero_months(tmp_path):
    stats = ArchiveStore(tmp_path).overview_stats(now=datetime(2024, 2, 15, tzinfo=timezone.utc))

    assert stats["media_completion_percent"] == 0.0
    assert stats["tag_coverage_percent"] == 0.0
    assert stats["archive_days"] == 0
    assert stats["storage_bytes"] == 0
    assert [item["count"] for item in stats["monthly_additions"]] == [0] * 12


def test_list_media_failures_joins_post_context(tmp_path):
    store = ArchiveStore(tmp_path)
    store.upsert_post(sample_post(post_id="7", handle="alice"))
    with store._connect() as db:
        db.execute("UPDATE media SET status='failed', error='timeout' WHERE post_id='7'")

    assert store.list_media_failures() == [{
        "post_id": "7",
        "author_name": "Alice",
        "author_handle": "alice",
        "url": "https://x.com/alice/status/7",
        "published_at": "2024-01-02T00:00:00+00:00",
        "media_index": 0,
        "kind": "image",
        "source_url": "https://pbs.twimg.com/media/a.jpg?name=orig",
        "error": "timeout",
    }]

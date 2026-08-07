import asyncio
from datetime import datetime, timezone

import httpx

from local_favorites_archive.downloader import MediaDownloader
from local_favorites_archive.models import MediaItem, Post
from local_favorites_archive.storage import ArchiveStore


def sample_post(post_id: str) -> Post:
    return Post(
        post_id=post_id,
        url=f"https://x.com/alice/status/{post_id}",
        text=f"post {post_id}",
        author_id="author-1",
        author_handle="alice",
        author_name="Alice",
        published_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
        collected_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
        raw={"id": post_id},
        media=[MediaItem(0, "image", "https://pbs.twimg.com/media/a.jpg?name=orig")],
    )


def test_downloader_with_empty_targets_downloads_nothing(tmp_path, monkeypatch):
    store = ArchiveStore(tmp_path)
    store.upsert_post(sample_post("1"))
    requests = []

    def unexpected_stream(*args, **kwargs):
        requests.append((args, kwargs))
        raise AssertionError("empty targets must not request media")

    monkeypatch.setattr(httpx.AsyncClient, "stream", unexpected_stream)

    assert asyncio.run(MediaDownloader(store).run(targets=[])) == {
        "downloaded": 0,
        "failed": 0,
    }
    assert requests == []


def test_downloader_targets_do_not_process_other_queued_media(tmp_path, monkeypatch):
    store = ArchiveStore(tmp_path)
    store.upsert_post(sample_post("1"))
    store.upsert_post(sample_post("2"))
    requested_urls = []

    class FakeResponse:
        headers = {"content-type": "image/jpeg"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        def raise_for_status(self):
            return None

        async def aiter_bytes(self):
            yield b"media"

    def fake_stream(self, method, url):
        requested_urls.append(url)
        return FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)

    result = asyncio.run(MediaDownloader(store).run(targets=[("1", 0)]))

    assert result == {"downloaded": 1, "failed": 0}
    assert requested_urls == ["https://pbs.twimg.com/media/a.jpg?name=orig"]
    assert store.get_post("1")["media"][0]["status"] == "downloaded"
    assert store.get_post("2")["media"][0]["status"] == "queued"


def test_downloader_skips_deferred_video_thumbnail(tmp_path, monkeypatch):
    store = ArchiveStore(tmp_path)
    post = sample_post("3")
    post.media = [MediaItem(0, "video", "https://pbs.twimg.com/amplify_video_thumb/1/img/a.jpg", "video/thumbnail", status="deferred")]
    store.upsert_post(post)
    monkeypatch.setattr(httpx.AsyncClient, "stream", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("thumbnail must not download")))
    assert asyncio.run(MediaDownloader(store).run()) == {"downloaded": 0, "failed": 0}

import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .collector import posts_from_x_response
from .config import Settings
from .downloader import MediaDownloader
from .storage import ArchiveStore


class TagPayload(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")

    @field_validator("name")
    @classmethod
    def strip_and_validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("tag name cannot be blank")
        return value


def create_app(settings: Settings) -> FastAPI:
    settings.ensure_dirs()
    store = ArchiveStore(settings.archive_root)
    app = FastAPI(title="Local Favorites Archive")
    static = Path(__file__).parent / "static"
    state: dict[str, Any] = {"state": "idle"}
    download_lock = asyncio.Lock()
    background_tasks: set[asyncio.Task] = set()

    def schedule(coroutine) -> None:
        task = asyncio.create_task(coroutine)
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)

    async def download_pending(mark_finished: bool = False) -> None:
        async with download_lock:
            await MediaDownloader(store, settings.max_media_concurrency).run()
            with store._connect() as db:
                downloaded = db.execute("SELECT COUNT(*) FROM media WHERE status='downloaded'").fetchone()[0]
                failed = db.execute("SELECT COUNT(*) FROM media WHERE status='failed'").fetchone()[0]
                queued = db.execute("SELECT COUNT(*) FROM media WHERE status='queued'").fetchone()[0]
            state.update({"downloaded": downloaded, "failed": failed, "queued": queued})
            if mark_finished:
                state.update({"state": "finished", "message": "同步与媒体下载完成"})

    @app.get("/api/posts")
    def posts(q: str = "", author: str = "", media_type: str = "", date_from: str = "", date_to: str = "", sort: str = "published_at", direction: str = "desc", limit: int = Query(100, le=200), offset: int = 0, tag_id: int | None = Query(None, ge=1)):
        return store.list_posts(q, author, media_type, date_from, date_to, sort, direction, limit, offset, tag_id)

    @app.get("/api/posts/count")
    def post_count(q: str = "", author: str = "", media_type: str = "", date_from: str = "", date_to: str = "", tag_id: int | None = Query(None, ge=1)):
        return {"total": store.count_posts(q, author, media_type, date_from, date_to, tag_id)}

    @app.get("/api/posts/{post_id}")
    def post(post_id: str):
        value = store.get_post(post_id)
        if not value: raise HTTPException(404)
        return value

    @app.get("/api/tags")
    def tags():
        return store.list_tags()

    @app.post("/api/tags", status_code=status.HTTP_201_CREATED)
    def create_tag(payload: TagPayload):
        try:
            return store.create_tag(payload.name, payload.color)
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    @app.patch("/api/tags/{tag_id}")
    def update_tag(tag_id: int, payload: TagPayload):
        try:
            tag = store.update_tag(tag_id, payload.name, payload.color)
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        if not tag:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "tag not found")
        return tag

    @app.delete("/api/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_tag(tag_id: int):
        if not store.delete_tag(tag_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "tag not found")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post("/api/posts/{post_id}/tags/{tag_id}")
    def assign_post_tag(post_id: str, tag_id: int):
        if not store.get_post(post_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "post not found")
        tag = store.get_tag(tag_id)
        if not tag:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "tag not found")
        return {"assigned": store.assign_tag(post_id, tag_id), "tag": tag}

    @app.delete("/api/posts/{post_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
    def remove_post_tag(post_id: str, tag_id: int):
        if not store.get_post(post_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "post not found")
        store.remove_tag(post_id, tag_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/media/{post_id}/{filename}")
    def media(post_id: str, filename: str):
        target = (store.media_dir / post_id / filename).resolve()
        if store.media_dir.resolve() not in target.parents or not target.is_file(): raise HTTPException(404)
        return FileResponse(target)

    @app.post("/api/ingest/x-response")
    async def ingest_x_response(payload: dict[str, Any]):
        posts = posts_from_x_response(payload)
        added = sum(1 for value in posts if store.upsert_post(value))
        state.update({
            "state": "collecting",
            "discovered": state.get("discovered", 0) + len(posts),
            "new": state.get("new", 0) + added,
            "message": "正在从已登录的 Chrome 接收 Likes",
        })
        schedule(download_pending())
        return {"discovered": len(posts), "new": added}

    @app.post("/api/ingest/start")
    def ingest_start():
        state.clear()
        state.update({"state": "starting", "discovered": 0, "new": 0, "message": "Chrome 扩展已连接，正在打开 Likes 页面"})
        return {"state": "starting"}

    async def finish_ingest():
        try:
            state.update({"state": "downloading", "message": "Likes 采集完成，正在下载媒体"})
            await download_pending(mark_finished=True)
        except Exception as exc:
            state.update({"state": "error", "error": str(exc)})

    @app.post("/api/ingest/finish")
    async def ingest_finish():
        asyncio.create_task(finish_ingest())
        return {"state": "downloading"}

    @app.get("/api/sync/status")
    def sync_status():
        with store._connect() as db:
            posts_total = db.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
            authors_total = db.execute(
                "SELECT COUNT(DISTINCT author_handle) FROM posts WHERE author_handle <> ''"
            ).fetchone()[0]
            media_total = db.execute("SELECT COUNT(*) FROM media").fetchone()[0]
            media_downloaded = db.execute("SELECT COUNT(*) FROM media WHERE status='downloaded'").fetchone()[0]
            media_queued = db.execute("SELECT COUNT(*) FROM media WHERE status='queued'").fetchone()[0]
            media_failed = db.execute("SELECT COUNT(*) FROM media WHERE status='failed'").fetchone()[0]
        return {
            **state,
            "archive_path": str(settings.archive_root.resolve()),
            "posts_total": posts_total,
            "authors_total": authors_total,
            "media_total": media_total,
            "media_downloaded": media_downloaded,
            "media_queued": media_queued,
            "media_failed": media_failed,
        }

    app.mount("/assets", StaticFiles(directory=static), name="assets")

    @app.get("/", include_in_schema=False)
    def index(): return FileResponse(static / "index.html")

    return app

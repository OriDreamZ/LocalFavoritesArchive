import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .collector import post_from_dom_payload, posts_from_x_response
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


class ArchiveSettingsPayload(BaseModel):
    stop_after_existing: int = Field(ge=0, le=100000)


class DeletePostsPayload(BaseModel):
    post_ids: list[str] = Field(min_length=1, max_length=200)

    @field_validator("post_ids")
    @classmethod
    def validate_post_ids(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("post IDs cannot be blank")
        return list(dict.fromkeys(normalized))


def create_app(settings: Settings) -> FastAPI:
    settings.ensure_dirs()
    store = ArchiveStore(settings.archive_root)
    app = FastAPI(title="Local Favorites Archive")
    static = Path(__file__).parent / "static"
    state: dict[str, Any] = {
        "state": "idle",
        "existing_streak": 0,
        "stop_trigger_streak": 0,
        "stop_after_existing": store.get_stop_after_existing(),
        "stop_requested": False,
    }
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

    active_states = {"starting", "collecting", "downloading", "retrying"}

    def ensure_retry_available() -> None:
        if state.get("state") in active_states or download_lock.locked():
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "当前有同步或媒体下载任务正在执行",
            )

    async def retry_failed_media(
        targets: list[tuple[str, int]] | None,
        requested: int,
    ) -> None:
        claimed: list[tuple[str, int]] = []
        try:
            async with download_lock:
                claimed = store.claim_failed_media(targets)
                result = await MediaDownloader(
                    store,
                    settings.max_media_concurrency,
                ).run(targets=claimed)
            state.update({
                "state": "finished",
                "retry_requested": requested,
                "retry_downloaded": result["downloaded"],
                "retry_failed": result["failed"],
                "message": (
                    f"媒体重试完成：成功 {result['downloaded']}，"
                    f"失败 {result['failed']}"
                ),
            })
        except Exception as exc:
            if claimed:
                store.restore_claimed_media_failures(claimed, str(exc))
            state.update({
                "state": "error",
                "retry_requested": requested,
                "retry_downloaded": 0,
                "retry_failed": len(claimed),
                "error": str(exc),
                "message": f"媒体重试失败：{exc}",
            })

    def start_media_retry(
        targets: list[tuple[str, int]] | None,
        requested: int,
    ) -> dict[str, int | str]:
        state.update({
            "state": "retrying",
            "retry_requested": requested,
            "retry_downloaded": 0,
            "retry_failed": 0,
            "message": f"正在重试 {requested} 个失败媒体",
        })
        schedule(retry_failed_media(targets, requested))
        return {"state": "retrying", "requested": requested}

    @app.get("/api/posts")
    def posts(q: str = "", author: str = "", media_type: str = "", date_from: str = "", date_to: str = "", sort: str = "published_at", direction: str = "desc", limit: int = Query(100, le=200), offset: int = 0, tag_id: int | None = Query(None, ge=1), tag_ids: list[int] = Query(default=[]), tag_mode: str = Query("any", pattern="^(all|any)$")):
        return store.list_posts(q, author, media_type, date_from, date_to, sort, direction, limit, offset, tag_id, tag_ids, tag_mode)

    @app.get("/api/posts/count")
    def post_count(q: str = "", author: str = "", media_type: str = "", date_from: str = "", date_to: str = "", tag_id: int | None = Query(None, ge=1), tag_ids: list[int] = Query(default=[]), tag_mode: str = Query("any", pattern="^(all|any)$")):
        return {"total": store.count_posts(q, author, media_type, date_from, date_to, tag_id, tag_ids, tag_mode)}

    @app.delete("/api/posts")
    def delete_posts(payload: DeletePostsPayload):
        return store.delete_posts(payload.post_ids)

    @app.get("/api/stats/overview")
    def overview_stats():
        return store.overview_stats()

    @app.get("/api/sync/failures")
    def sync_failures():
        return store.list_media_failures()

    @app.post("/api/sync/failures/retry")
    async def retry_all_sync_failures():
        ensure_retry_available()
        requested = store.count_media_failures()
        if requested == 0:
            return {"state": state.get("state", "idle"), "requested": 0}
        return JSONResponse(
            start_media_retry(None, requested),
            status_code=status.HTTP_202_ACCEPTED,
        )

    @app.post("/api/sync/failures/{post_id}/{media_index}/retry")
    async def retry_one_sync_failure(post_id: str, media_index: int):
        ensure_retry_available()
        requested = store.count_media_failures(post_id, media_index)
        if requested == 0:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                "失败媒体记录不存在或已被处理",
            )
        return JSONResponse(
            start_media_retry([(post_id, media_index)], requested),
            status_code=status.HTTP_202_ACCEPTED,
        )

    @app.get("/api/settings")
    def archive_settings():
        return {"stop_after_existing": store.get_stop_after_existing()}

    @app.patch("/api/settings")
    def update_archive_settings(payload: ArchiveSettingsPayload):
        value = store.set_stop_after_existing(payload.stop_after_existing)
        state["stop_after_existing"] = value
        return {"stop_after_existing": value}

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
        return await ingest_posts(posts)

    async def ingest_posts(posts):
        existing_streak = state.get("existing_streak", 0)
        added = 0
        for value in posts:
            if store.upsert_post(value):
                added += 1
                existing_streak = 0
            else:
                existing_streak += 1
        threshold = store.get_stop_after_existing()
        was_stopped = state.get("stop_requested", False)
        stop_reached = threshold > 0 and existing_streak >= threshold
        stop_requested = was_stopped or stop_reached
        stop_trigger_streak = state.get("stop_trigger_streak", 0)
        if stop_reached and not was_stopped:
            stop_trigger_streak = existing_streak
        state.update({
            "state": "collecting",
            "discovered": state.get("discovered", 0) + len(posts),
            "new": state.get("new", 0) + added,
            "existing_streak": existing_streak,
            "stop_trigger_streak": stop_trigger_streak,
            "stop_after_existing": threshold,
            "stop_requested": stop_requested,
            "message": "正在从已登录的 Chrome 接收 Likes",
        })
        schedule(download_pending())
        return {
            "discovered": len(posts),
            "new": added,
            "existing_streak": existing_streak,
            "stop_trigger_streak": stop_trigger_streak,
            "stop_after_existing": threshold,
            "stop_requested": stop_requested,
        }

    @app.post("/api/ingest/dom-posts")
    async def ingest_dom_posts(payload: dict[str, Any]):
        values = payload.get("posts")
        if not isinstance(values, list) or len(values) > 100:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "推文批次必须为不超过 100 条的数组")
        posts = [post for value in values if isinstance(value, dict) if (post := post_from_dom_payload(value))]
        return await ingest_posts(posts)

    @app.post("/api/ingest/start")
    def ingest_start():
        state.clear()
        state.update({
            "existing_streak": 0,
            "stop_trigger_streak": 0,
            "stop_after_existing": store.get_stop_after_existing(),
            "stop_requested": False,
        })
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

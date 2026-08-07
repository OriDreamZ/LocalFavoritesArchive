from fastapi.testclient import TestClient
from datetime import datetime, timezone
import time
from local_favorites_archive.config import Settings
from local_favorites_archive.models import MediaItem, Post
from local_favorites_archive.storage import ArchiveStore
from local_favorites_archive.web import create_app


def x_post(post_id: str) -> dict:
    return {
        "rest_id": post_id,
        "core": {"user_results": {"result": {
            "rest_id": "author-1",
            "legacy": {"screen_name": "alice", "name": "Alice"},
        }}},
        "legacy": {
            "full_text": f"post {post_id}",
            "created_at": "Tue Jan 02 03:04:05 +0000 2024",
        },
    }


def x_payload(*post_ids: str) -> dict:
    return {"data": {"entries": [
        {"entryId": f"tweet-{post_id}", "content": {"itemContent": {
            "tweet_results": {"result": x_post(post_id)}
        }}}
        for post_id in post_ids
    ]}}


def add_failed_media(store: ArchiveStore, post_id: str) -> None:
    from datetime import datetime, timezone

    store.upsert_post(Post(
        post_id=post_id,
        url=f"https://x.com/alice/status/{post_id}",
        text=f"post {post_id}",
        author_id="author-1",
        author_handle="alice",
        author_name="Alice",
        published_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
        collected_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
        raw={"id": post_id},
        media=[MediaItem(0, "image", f"https://example.com/{post_id}.jpg")],
    ))
    with store._connect() as db:
        db.execute(
            "UPDATE media SET status='failed',error='timeout' WHERE post_id=?",
            (post_id,),
        )


def test_local_api_and_ui(tmp_path):
    client = TestClient(create_app(Settings(archive_root=tmp_path)))
    assert client.get("/").status_code == 200
    response = client.get("/api/posts")
    assert response.status_code == 200
    assert response.json() == []
    assert client.get("/api/sync/status").json()["state"] == "idle"
    assert 'id="direction"' in client.get("/").text
    assert "Chrome 扩展" in client.get("/").text
    assert 'id="sync-progress"' in client.get("/").text
    assert 'id="media-progress"' in client.get("/").text
    assert 'id="archive-path"' in client.get("/").text
    assert 'id="page-size"' in client.get("/").text
    assert 'id="prev-page"' in client.get("/").text
    assert 'id="next-page"' in client.get("/").text
    assert 'id="page-info"' in client.get("/").text
    assert 'value="text"' in client.get("/").text
    assert 'id="tag-filter"' in client.get("/").text
    assert 'id="workspace-tags"' in client.get("/").text
    assert 'id="tag-form"' in client.get("/").text
    assert 'id="page-number"' in client.get("/").text
    assert 'id="jump-page"' in client.get("/").text
    assert client.get("/api/posts/count").json() == {"total": 0}


def test_retry_all_failed_media_runs_only_claimed_failures(tmp_path, monkeypatch):
    store = ArchiveStore(tmp_path)
    add_failed_media(store, "1")
    add_failed_media(store, "2")
    captured = []

    async def fake_download(self, targets=None):
        captured.append(targets)
        with self.store._connect() as db:
            db.executemany(
                "UPDATE media SET status='downloaded',error=NULL "
                "WHERE post_id=? AND media_index=?",
                targets,
            )
        return {"downloaded": len(targets), "failed": 0}

    monkeypatch.setattr("local_favorites_archive.web.MediaDownloader.run", fake_download)
    client = TestClient(create_app(Settings(archive_root=tmp_path)))

    response = client.post("/api/sync/failures/retry")
    assert response.status_code == 202
    assert response.json() == {"state": "retrying", "requested": 2}
    for _ in range(50):
        if client.get("/api/sync/status").json()["state"] == "finished":
            break
        time.sleep(0.01)

    assert captured == [[("1", 0), ("2", 0)]]
    status = client.get("/api/sync/status").json()
    assert status["retry_requested"] == 2
    assert status["retry_downloaded"] == 2
    assert status["retry_failed"] == 0
    assert client.get("/api/sync/failures").json() == []


def test_retry_single_failed_media_and_missing_target(tmp_path, monkeypatch):
    store = ArchiveStore(tmp_path)
    add_failed_media(store, "1")
    add_failed_media(store, "2")
    captured = []

    async def fake_download(self, targets=None):
        captured.append(targets)
        return {"downloaded": 0, "failed": len(targets)}

    monkeypatch.setattr("local_favorites_archive.web.MediaDownloader.run", fake_download)
    client = TestClient(create_app(Settings(archive_root=tmp_path)))

    response = client.post("/api/sync/failures/1/0/retry")
    assert response.status_code == 202
    assert response.json() == {"state": "retrying", "requested": 1}
    for _ in range(50):
        if client.get("/api/sync/status").json()["state"] == "finished":
            break
        time.sleep(0.01)

    assert captured == [[("1", 0)]]
    assert client.post("/api/sync/failures/missing/0/retry").status_code == 404


def test_retry_rejects_active_sync_and_handles_empty_failures(tmp_path):
    client = TestClient(create_app(Settings(archive_root=tmp_path)))

    empty = client.post("/api/sync/failures/retry")
    assert empty.status_code == 200
    assert empty.json() == {"state": "idle", "requested": 0}

    client.post("/api/ingest/start")
    busy = client.post("/api/sync/failures/retry")
    assert busy.status_code == 409
    assert "正在执行" in busy.json()["detail"]


def test_sync_center_exposes_explicit_media_retry_controls(tmp_path):
    client = TestClient(create_app(Settings(archive_root=tmp_path)))
    html = client.get("/").text
    script = client.get("/assets/app.js").text

    assert 'id="retry-all-failures"' in html
    assert 'id="retry-failures-message"' in html
    assert "data-retry-media" in script
    assert "/api/sync/failures/retry" in script
    assert "function retryMediaFailures" in script
    assert "retrying" in script
    assert "['starting', 'collecting', 'downloading', 'retrying']" in script
    assert "媒体重试完成：成功" in script
    assert "媒体重试失败：" in script
    assert "loadSyncFailures()" in script
    assert "loadOverview()" in script


def test_api_errors_expose_status_for_retry_conflicts(tmp_path):
    script = TestClient(create_app(Settings(archive_root=tmp_path))).get("/assets/app.js").text

    assert "error.status = response.status" in script
    assert "error.status === 404" in script


def test_date_filters_have_visible_distinct_labels(tmp_path):
    client = TestClient(create_app(Settings(archive_root=tmp_path)))
    html = client.get("/").text
    script = client.get("/assets/app.js").text

    assert '<span>起始日期</span>' in html
    assert 'id="from" type="date" aria-label="起始日期"' in html
    assert '<span>截至日期</span>' in html
    assert 'id="to" type="date" aria-label="截至日期"' in html
    assert html.count('<span class="date-placeholder" aria-hidden="true">年/月/日</span>') == 2
    assert "syncDateInputState" in script


def test_ui_uses_approved_archive_library_shell(tmp_path):
    html = TestClient(create_app(Settings(archive_root=tmp_path))).get("/").text

    assert 'class="app-sidebar"' in html
    assert 'id="collection"' in html
    assert 'id="workspace-sync"' in html
    assert 'id="overview-posts-total"' in html
    assert 'id="overview-authors-total"' in html
    assert 'id="overview-media-completion"' in html
    assert "收藏归档" in html
    assert "收藏总览" in html
    assert "我的收藏" in html
    assert "同步中心" in html


def test_ui_has_four_workspace_dashboard_shell(tmp_path):
    html = TestClient(create_app(Settings(archive_root=tmp_path))).get("/").text

    for route in ("overview", "favorites", "sync", "tags"):
        assert f'href="#{route}"' in html
        assert f'id="workspace-{route}"' in html
        assert f'data-workspace="{route}"' in html
    for element_id in (
        "nav-posts-count",
        "nav-failures-count",
        "nav-tags-count",
        "overview-posts-total",
        "overview-authors-total",
        "overview-media-completion",
        "overview-tagged-posts",
        "overview-distribution",
        "overview-monthly-additions",
        "overview-archive-days",
        "overview-storage-bytes",
        "sync-failures",
        "back-to-top",
    ):
        assert f'id="{element_id}"' in html
    assert 'id="tag-dialog"' not in html
    assert 'id="tag-manager-open"' not in html
    assert 'id="image-viewer"' in html


def test_ui_has_local_image_viewer_controls(tmp_path):
    html = TestClient(create_app(Settings(archive_root=tmp_path))).get("/").text

    for element_id in (
        "image-viewer",
        "viewer-image",
        "viewer-canvas",
        "viewer-prev",
        "viewer-next",
        "viewer-zoom-out",
        "viewer-zoom-in",
        "viewer-rotate-left",
        "viewer-rotate-right",
        "viewer-reset",
        "viewer-close",
    ):
        assert f'id="{element_id}"' in html


def test_image_viewer_serves_explicit_fit_logic(tmp_path):
    client = TestClient(create_app(Settings(archive_root=tmp_path)))
    script = client.get("/assets/app.js").text

    assert "function fitViewerImage" in script
    assert "viewerFitScale" in script
    assert "translate(calc(-50%" in script


def test_ui_script_binds_real_summary_statistics(tmp_path):
    script = TestClient(create_app(Settings(archive_root=tmp_path))).get("/assets/app.js").text

    assert "overview-posts-total" in script
    assert "overview-authors-total" in script
    assert "overview-media-completion" in script
    assert "syncStateLabel" in script


def test_ui_script_routes_four_workspaces_and_renders_overview(tmp_path):
    script = TestClient(create_app(Settings(archive_root=tmp_path))).get("/assets/app.js").text

    for token in (
        "WORKSPACES",
        "function normalizeRoute",
        "function activateWorkspace",
        "hashchange",
        "aria-current",
        "function loadOverview",
        "function formatBytes",
        "/api/stats/overview",
        "overview-monthly-additions",
        "overview-distribution",
    ):
        assert token in script
    assert "history.replaceState(null, '', `#${route}`)" in script


def test_ui_script_uses_tag_workspace_instead_of_dialog(tmp_path):
    script = TestClient(create_app(Settings(archive_root=tmp_path))).get("/assets/app.js").text

    assert "tag-dialog" not in script
    assert "openTagManager" not in script
    assert "window.location.hash = '#tags'" in script
    assert "refreshAfterTagChange" in script
    assert "loadOverview" in script


def test_tag_refresh_preserves_current_page_and_position(tmp_path):
    script = TestClient(create_app(Settings(archive_root=tmp_path))).get("/assets/app.js").text
    function_body = script.split(
        "async function refreshPostTags(", 1
    )[1].split("\n}", 1)[0]

    assert "await loadTags()" in function_body
    assert "renderPostTags(article.querySelector('.post-tags'), detail)" in function_body
    assert "await load()" not in function_body
    assert "removedTagId" in function_body
    assert "$('tag-filter').value === String(removedTagId)" in function_body
    assert "await refreshAfterTagChange()" in function_body
    assert "refreshPostTags(article, remove.dataset.tagId)" in script
    assert "refreshPostTags(article)" in script


def test_ui_script_renders_sync_failures_and_back_to_top(tmp_path):
    script = TestClient(create_app(Settings(archive_root=tmp_path))).get("/assets/app.js").text

    assert "function loadSyncFailures" in script
    assert "/api/sync/failures" in script
    assert "sync-failures" in script
    assert "failure-error" in script
    assert "back-to-top" in script
    assert "window.scrollY > 480" in script
    assert "window.scrollTo({top: 0, behavior: 'smooth'})" in script
    assert "formatNumber(failures.length)" not in script


def test_ui_renders_structured_post_links_safely(tmp_path):
    script = TestClient(create_app(Settings(archive_root=tmp_path))).get("/assets/app.js").text

    assert "function renderPostText" in script
    assert "function safeHttpUrl" in script
    assert 'class="post-link"' in script
    assert 'target="_blank"' in script
    assert 'rel="noreferrer"' in script
    assert "detail.links" in script


def test_favorites_has_synchronized_top_and_bottom_pagination(tmp_path):
    client = TestClient(create_app(Settings(archive_root=tmp_path)))
    html = client.get("/").text
    script = client.get("/assets/app.js").text

    assert 'aria-label="顶部推文分页"' in html
    assert html.count('class="pagination') == 2
    assert html.count('data-page-action="prev"') == 2
    assert html.count('data-page-action="next"') == 2
    assert html.count('data-page-action="jump"') == 2
    assert html.count('data-page-info') == 2
    assert html.count('data-page-number') == 2
    assert html.count('id="prev-page"') == 1
    assert "function setupPagination" in script
    assert "document.querySelectorAll('.pagination')" in script
    assert "scrollToCollectionStart" in script
    assert "async function changePage" in script
    assert "await changePage" in script


def test_ingest_x_response_persists_liked_post(tmp_path):
    client = TestClient(create_app(Settings(archive_root=tmp_path)))
    result = {
        "rest_id": "99",
        "core": {"user_results": {"result": {"rest_id": "7", "legacy": {"screen_name": "alice", "name": "Alice"}}}},
        "legacy": {"full_text": "from chrome", "created_at": "Tue Jan 02 03:04:05 +0000 2024"},
    }
    payload = {"data": {"entries": [{"entryId": "tweet-99", "content": {"itemContent": {"tweet_results": {"result": result}}}}]}}

    response = client.post("/api/ingest/x-response", json=payload)

    assert response.status_code == 200
    result = response.json()
    assert result["discovered"] == 1
    assert result["new"] == 1
    assert result["existing_streak"] == 0
    assert result["stop_after_existing"] == 50
    assert result["stop_requested"] is False
    assert client.get("/api/posts").json()[0]["text"] == "from chrome"


def test_sync_settings_are_validated_and_persisted(tmp_path):
    settings = Settings(archive_root=tmp_path)
    client = TestClient(create_app(settings))

    assert client.get("/api/settings").json() == {"stop_after_existing": 50}
    assert client.patch("/api/settings", json={"stop_after_existing": 2}).json() == {
        "stop_after_existing": 2
    }
    assert client.patch("/api/settings", json={"stop_after_existing": -1}).status_code == 422
    assert client.patch("/api/settings", json={"stop_after_existing": 100001}).status_code == 422
    assert TestClient(create_app(settings)).get("/api/settings").json() == {
        "stop_after_existing": 2
    }


def test_existing_streak_crosses_batches_resets_on_new_and_latches_stop(tmp_path):
    client = TestClient(create_app(Settings(archive_root=tmp_path)))
    client.patch("/api/settings", json={"stop_after_existing": 2})
    client.post("/api/ingest/x-response", json=x_payload("1", "2"))
    client.post("/api/ingest/start")

    first = client.post("/api/ingest/x-response", json=x_payload("1")).json()
    assert first["existing_streak"] == 1
    assert first["stop_requested"] is False

    second = client.post("/api/ingest/x-response", json=x_payload("2")).json()
    assert second["existing_streak"] == 2
    assert second["stop_requested"] is True
    assert second["stop_trigger_streak"] == 2

    latched = client.post("/api/ingest/x-response", json=x_payload("3")).json()
    assert latched["existing_streak"] == 0
    assert latched["stop_requested"] is True
    assert latched["stop_trigger_streak"] == 2

    client.post("/api/ingest/start")
    status = client.get("/api/sync/status").json()
    assert status["existing_streak"] == 0
    assert status["stop_requested"] is False
    assert status["stop_trigger_streak"] == 0


def test_zero_threshold_never_requests_stop(tmp_path):
    client = TestClient(create_app(Settings(archive_root=tmp_path)))
    client.patch("/api/settings", json={"stop_after_existing": 0})
    client.post("/api/ingest/x-response", json=x_payload("1", "2", "3"))
    client.post("/api/ingest/start")

    result = client.post("/api/ingest/x-response", json=x_payload("1", "2", "3")).json()

    assert result["existing_streak"] == 3
    assert result["stop_after_existing"] == 0
    assert result["stop_requested"] is False


def test_delete_posts_api_accepts_selected_ids_and_validates_bounds(tmp_path):
    client = TestClient(create_app(Settings(archive_root=tmp_path)))
    client.post("/api/ingest/x-response", json=x_payload("1", "2"))

    response = client.request(
        "DELETE", "/api/posts", json={"post_ids": ["1", "missing"]}
    )

    assert response.status_code == 200
    assert response.json()["deleted"] == ["1"]
    assert response.json()["not_found"] == ["missing"]
    assert client.get("/api/posts/1").status_code == 404
    assert client.get("/api/posts/2").status_code == 200
    assert client.request("DELETE", "/api/posts", json={"post_ids": []}).status_code == 422
    assert client.request(
        "DELETE", "/api/posts", json={"post_ids": [str(i) for i in range(201)]}
    ).status_code == 422


def test_favorites_supports_selected_post_deletion(tmp_path):
    client = TestClient(create_app(Settings(archive_root=tmp_path)))
    html = client.get("/").text
    script = client.get("/assets/app.js").text

    for element_id in (
        "select-page", "selection-count", "delete-selected", "delete-message"
    ):
        assert f'id="{element_id}"' in html
    assert "selectedPostIds" in script
    assert 'class="post-select"' in script
    assert "function updateSelectionControls" in script
    assert "function clearPostSelection" in script
    assert "永久删除所选" in script
    assert "method: 'DELETE'" in script
    assert "post_ids" in script


def test_sync_center_edits_and_displays_existing_post_limit(tmp_path):
    client = TestClient(create_app(Settings(archive_root=tmp_path)))
    html = client.get("/").text
    script = client.get("/assets/app.js").text

    for element_id in (
        "stop-after-existing", "save-sync-settings", "sync-settings-message",
        "existing-streak",
    ):
        assert f'id="{element_id}"' in html
    assert "async function loadArchiveSettings" in script
    assert "'/api/settings'" in script
    assert "stop_after_existing" in script
    assert "existing_streak" in script
    assert "stop_requested" in script
    assert "已达到连续已有推文停止条件" in script


def test_extension_can_announce_start(tmp_path):
    client = TestClient(create_app(Settings(archive_root=tmp_path)))

    assert client.post("/api/ingest/start").json() == {"state": "starting"}
    status = client.get("/api/sync/status").json()
    assert status["state"] == "starting"
    assert status["discovered"] == 0


def test_status_reports_archive_path_and_persistent_counts(tmp_path):
    settings = Settings(archive_root=tmp_path)
    def result(post_id, author_id, handle, name):
        return {"rest_id": post_id, "core": {"user_results": {"result": {"rest_id": author_id, "core": {"screen_name": handle, "name": name}}}}, "legacy": {"full_text": f"persistent {post_id}", "created_at": "Tue Jan 02 03:04:05 +0000 2024"}}

    payload = {"data": {"entries": [
        {"entryId": "tweet-99", "content": {"itemContent": {"tweet_results": {"result": result("99", "7", "alice", "Alice")}}}},
        {"entryId": "tweet-100", "content": {"itemContent": {"tweet_results": {"result": result("100", "7", "alice", "Alice")}}}},
        {"entryId": "tweet-101", "content": {"itemContent": {"tweet_results": {"result": result("101", "8", "bob", "Bob")}}}},
    ]}}
    first_client = TestClient(create_app(settings))
    first_client.post("/api/ingest/x-response", json=payload)

    restarted_client = TestClient(create_app(settings))
    status = restarted_client.get("/api/sync/status").json()

    assert status["archive_path"] == str(tmp_path.resolve())
    assert status["posts_total"] == 3
    assert status["authors_total"] == 2
    assert status["media_total"] == 0
    assert restarted_client.get("/api/posts").json()[0]["text"].startswith("persistent")


def test_ingest_schedules_progressive_media_download(tmp_path, monkeypatch):
    calls = []

    async def fake_download(self):
        calls.append(True)
        return {"downloaded": 0, "failed": 0}

    monkeypatch.setattr("local_favorites_archive.web.MediaDownloader.run", fake_download)
    client = TestClient(create_app(Settings(archive_root=tmp_path)))
    result = {"rest_id": "1", "core": {"user_results": {"result": {"rest_id": "7", "legacy": {"screen_name": "alice", "name": "Alice"}}}}, "legacy": {"full_text": "post", "created_at": "Tue Jan 02 03:04:05 +0000 2024"}}
    payload = {"data": {"entries": [{"entryId": "tweet-1", "content": {"itemContent": {"tweet_results": {"result": result}}}}]}}

    client.post("/api/ingest/x-response", json=payload)
    for _ in range(20):
        if calls:
            break
        time.sleep(0.01)

    assert calls == [True]


def test_tag_api_manages_assignments_and_filters_posts(tmp_path):
    client = TestClient(create_app(Settings(archive_root=tmp_path)))
    result = {
        "rest_id": "99",
        "core": {"user_results": {"result": {"rest_id": "7", "legacy": {"screen_name": "alice", "name": "Alice"}}}},
        "legacy": {"full_text": "tag me", "created_at": "Tue Jan 02 03:04:05 +0000 2024"},
    }
    client.post("/api/ingest/x-response", json={"data": {"result": result}})

    created = client.post("/api/tags", json={"name": "待读", "color": "#2563eb"})
    assert created.status_code == 201
    tag = created.json()
    assert client.post("/api/tags", json={"name": "待读", "color": "#16a34a"}).status_code == 409
    assert client.post(f"/api/posts/99/tags/{tag['id']}").status_code == 200
    assert client.get("/api/posts/99").json()["tags"][0]["name"] == "待读"
    assert client.get(f"/api/posts?tag_id={tag['id']}").json()[0]["post_id"] == "99"
    assert client.get(f"/api/posts/count?tag_id={tag['id']}").json() == {"total": 1}

    updated = client.patch(f"/api/tags/{tag['id']}", json={"name": "已整理", "color": "#0f766e"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "已整理"
    assert client.delete(f"/api/posts/99/tags/{tag['id']}").status_code == 204
    assert client.delete(f"/api/tags/{tag['id']}").status_code == 204
    assert client.get("/api/tags").json() == []


def test_multi_tag_query_parameters_filter_posts_and_count_consistently(tmp_path):
    store = ArchiveStore(tmp_path)
    for post_id in ("1", "2", "3"):
        store.upsert_post(Post(
            post_id=post_id,
            url=f"https://x.com/alice/status/{post_id}",
            text=f"post {post_id}",
            author_id="author-1",
            author_handle="alice",
            author_name="Alice",
            published_at=None,
            collected_at=datetime.now(timezone.utc),
            raw={"id": post_id},
        ))
    first = store.create_tag("第一标签", "#2563eb")
    second = store.create_tag("第二标签", "#16a34a")
    store.assign_tag("1", first["id"])
    store.assign_tag("1", second["id"])
    store.assign_tag("2", first["id"])
    store.assign_tag("3", second["id"])
    client = TestClient(create_app(Settings(archive_root=tmp_path)))
    query = f"tag_ids={first['id']}&tag_ids={second['id']}&tag_mode=all"

    assert [item["post_id"] for item in client.get(f"/api/posts?{query}").json()] == ["1"]
    assert client.get(f"/api/posts/count?{query}").json() == {"total": 1}
    union = client.get(f"/api/posts?tag_ids={first['id']}&tag_ids={second['id']}&tag_mode=any")
    assert {item["post_id"] for item in union.json()} == {"1", "2", "3"}


def test_tag_api_validates_input_and_missing_records(tmp_path):
    client = TestClient(create_app(Settings(archive_root=tmp_path)))

    assert client.post("/api/tags", json={"name": "   ", "color": "#2563eb"}).status_code == 422
    assert client.post("/api/tags", json={"name": "valid", "color": "blue"}).status_code == 422
    assert client.patch("/api/tags/999", json={"name": "missing", "color": "#2563eb"}).status_code == 404
    assert client.post("/api/posts/missing/tags/999").status_code == 404


def test_overview_and_failure_endpoints(tmp_path):
    client = TestClient(create_app(Settings(archive_root=tmp_path)))

    stats = client.get("/api/stats/overview")
    failures = client.get("/api/sync/failures")

    assert stats.status_code == 200
    assert stats.json()["posts_total"] == 0
    assert len(stats.json()["monthly_additions"]) == 12
    assert failures.status_code == 200
    assert failures.json() == []

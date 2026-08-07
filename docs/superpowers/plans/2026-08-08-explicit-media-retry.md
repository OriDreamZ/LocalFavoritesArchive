# 媒体下载失败显式重试实施计划

> **供智能代理执行：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，逐项执行并用复选框跟踪进度。

**目标：** 在同步中心增加全部失败媒体重试和单条失败媒体重试，并完整说明同步期间隐式重试、网页显式重试与命令行重试的行为差异。

**架构：** 存储层负责原子认领仍为失败状态的目标，下载器支持可选的精确目标集合，Web 层使用现有下载锁在后台执行任务并公开 `retrying` 状态。前端通过两个专用 POST 接口触发重试，依据同步状态禁用控件，并在完成后刷新失败列表、统计和收藏内容。

**技术栈：** Python 3.11+、SQLite、FastAPI、httpx、原生 HTML/CSS/JavaScript、pytest。

---

## 文件结构

- 修改 `src/local_favorites_archive/storage.py`：统计、认领和异常恢复失败媒体。
- 修改 `src/local_favorites_archive/downloader.py`：支持只下载明确的 `(post_id, media_index)` 目标集合。
- 修改 `src/local_favorites_archive/web.py`：增加批量与单条重试接口、后台任务和重试状态。
- 修改 `src/local_favorites_archive/static/index.html`：增加全部重试按钮和面板状态区域。
- 修改 `src/local_favorites_archive/static/app.js`：渲染单条按钮、发起重试、禁用控件和完成刷新。
- 修改 `src/local_favorites_archive/static/styles.css`：调整失败记录操作列和窄屏布局。
- 修改 `tests/test_storage.py`：覆盖失败项认领和状态恢复。
- 新建 `tests/test_downloader.py`：覆盖下载器目标集合过滤。
- 修改 `tests/test_web.py`：覆盖 API、后台状态和前端契约。
- 修改 `tests/test_project_documentation.py`：约束 README 和长期文档的重试说明。
- 修改 `README.md` 及六份 `docs/*.md`：说明显式、隐式和命令行重试行为。

### 任务 1：存储层原子认领失败媒体

**文件：**

- 修改：`src/local_favorites_archive/storage.py`
- 测试：`tests/test_storage.py`

- [ ] **步骤 1：编写失败项认领测试**

在 `tests/test_storage.py` 追加：

```python
def test_claim_failed_media_only_queues_requested_failures(tmp_path):
    store = ArchiveStore(tmp_path)
    store.upsert_post(sample_post(post_id="1"))
    store.upsert_post(sample_post(post_id="2"))
    store.upsert_post(sample_post(post_id="3"))
    with store._connect() as db:
        db.execute("UPDATE media SET status='failed', error='first' WHERE post_id='1'")
        db.execute("UPDATE media SET status='failed', error='second' WHERE post_id='2'")
        db.execute("UPDATE media SET status='queued' WHERE post_id='3'")

    claimed = store.claim_failed_media([("1", 0), ("3", 0)])

    assert claimed == [("1", 0)]
    with store._connect() as db:
        states = {
            row["post_id"]: (row["status"], row["error"])
            for row in db.execute("SELECT post_id,status,error FROM media")
        }
    assert states == {
        "1": ("queued", None),
        "2": ("failed", "second"),
        "3": ("queued", None),
    }


def test_claim_all_failed_media_is_not_limited_to_failure_list_page(tmp_path):
    store = ArchiveStore(tmp_path)
    for index in range(205):
        store.upsert_post(sample_post(post_id=str(index)))
    with store._connect() as db:
        db.execute("UPDATE media SET status='failed', error='timeout'")

    assert store.count_media_failures() == 205
    assert len(store.list_media_failures()) == 200
    assert len(store.claim_failed_media()) == 205
    assert store.count_media_failures() == 0


def test_restore_claimed_media_failures_only_changes_queued_targets(tmp_path):
    store = ArchiveStore(tmp_path)
    store.upsert_post(sample_post(post_id="1"))
    store.upsert_post(sample_post(post_id="2"))
    with store._connect() as db:
        db.execute("UPDATE media SET status='queued' WHERE post_id='1'")
        db.execute("UPDATE media SET status='downloaded' WHERE post_id='2'")

    store.restore_claimed_media_failures([("1", 0), ("2", 0)], "task failed")

    with store._connect() as db:
        states = {
            row["post_id"]: (row["status"], row["error"])
            for row in db.execute("SELECT post_id,status,error FROM media")
        }
    assert states == {
        "1": ("failed", "task failed"),
        "2": ("downloaded", None),
    }
```

- [ ] **步骤 2：运行测试并确认先失败**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_storage.py -k "claim_failed or restore_claimed" -v
```

预期：因 `count_media_failures`、`claim_failed_media` 和 `restore_claimed_media_failures` 尚不存在而失败。

- [ ] **步骤 3：实现失败媒体统计、认领和恢复**

在 `ArchiveStore` 中、`list_media_failures` 之前加入：

```python
    def count_media_failures(
        self,
        post_id: str | None = None,
        media_index: int | None = None,
    ) -> int:
        where = ["status='failed'"]
        args: list[Any] = []
        if post_id is not None:
            where.append("post_id=?")
            args.append(post_id)
        if media_index is not None:
            where.append("media_index=?")
            args.append(media_index)
        with self._connect() as db:
            return db.execute(
                f"SELECT COUNT(*) FROM media WHERE {' AND '.join(where)}",
                args,
            ).fetchone()[0]

    def claim_failed_media(
        self,
        targets: list[tuple[str, int]] | None = None,
    ) -> list[tuple[str, int]]:
        with self._connect() as db:
            if targets is None:
                rows = db.execute(
                    "SELECT post_id,media_index FROM media "
                    "WHERE status='failed' ORDER BY post_id,media_index"
                ).fetchall()
            else:
                rows = []
                for post_id, media_index in dict.fromkeys(targets):
                    row = db.execute(
                        "SELECT post_id,media_index FROM media "
                        "WHERE post_id=? AND media_index=? AND status='failed'",
                        (post_id, media_index),
                    ).fetchone()
                    if row:
                        rows.append(row)
            claimed = [(row["post_id"], row["media_index"]) for row in rows]
            db.executemany(
                "UPDATE media SET status='queued',error=NULL "
                "WHERE post_id=? AND media_index=? AND status='failed'",
                claimed,
            )
        return claimed

    def restore_claimed_media_failures(
        self,
        targets: list[tuple[str, int]],
        error: str,
    ) -> None:
        with self._connect() as db:
            db.executemany(
                "UPDATE media SET status='failed',error=? "
                "WHERE post_id=? AND media_index=? AND status='queued'",
                [(error[:500], post_id, media_index) for post_id, media_index in targets],
            )
```

该实现只认领事务执行时仍为 `failed` 的记录，并只恢复仍为 `queued` 的已认领目标。

- [ ] **步骤 4：运行存储测试**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_storage.py -v
```

预期：全部存储测试通过。

- [ ] **步骤 5：提交存储层改动**

```powershell
git add src/local_favorites_archive/storage.py tests/test_storage.py
git commit -m "feat: claim failed media for retry"
```

### 任务 2：下载器支持精确目标集合

**文件：**

- 修改：`src/local_favorites_archive/downloader.py`
- 新建：`tests/test_downloader.py`

- [ ] **步骤 1：编写定向下载失败测试**

新建 `tests/test_downloader.py`：

```python
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
    store.upsert_post(sample_post(post_id="1"))
    requests = []

    async def unexpected_stream(*args, **kwargs):
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
    store.upsert_post(sample_post(post_id="1"))
    store.upsert_post(sample_post(post_id="2"))
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
```

- [ ] **步骤 2：运行测试并确认参数尚不支持**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_downloader.py -v
```

预期：`MediaDownloader.run()` 不接受 `targets` 参数，测试失败。

- [ ] **步骤 3：实现目标集合过滤**

将 `MediaDownloader.run` 签名和查询部分改为：

```python
    async def run(
        self,
        targets: list[tuple[str, int]] | None = None,
    ) -> dict[str, int]:
        stats = {"downloaded": 0, "failed": 0}
        if targets == []:
            return stats
        where = ["status != 'downloaded'", "source_url != ''"]
        args: list[object] = []
        if targets is not None:
            unique_targets = list(dict.fromkeys(targets))
            where.append(
                "(" + " OR ".join(
                    "(post_id=? AND media_index=?)" for _ in unique_targets
                ) + ")"
            )
            args.extend(value for target in unique_targets for value in target)
        with self.store._connect() as db:
            rows = [
                dict(row)
                for row in db.execute(
                    f"SELECT * FROM media WHERE {' AND '.join(where)}",
                    args,
                ).fetchall()
            ]
```

删除函数后部原有的第二次 `stats = {"downloaded": 0, "failed": 0}`，其余下载、成功和失败更新逻辑保持不变。`targets=None` 继续保持同步与命令行处理全部未下载媒体的行为。

- [ ] **步骤 4：运行下载器和存储测试**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_downloader.py tests\test_storage.py -v
```

预期：全部测试通过；集合外的排队媒体保持 `queued`。

- [ ] **步骤 5：提交下载器改动**

```powershell
git add src/local_favorites_archive/downloader.py tests/test_downloader.py
git commit -m "feat: download selected media targets"
```

### 任务 3：增加失败媒体重试 API 和后台状态

**文件：**

- 修改：`src/local_favorites_archive/web.py`
- 测试：`tests/test_web.py`

- [ ] **步骤 1：编写批量、单条和冲突接口测试**

在 `tests/test_web.py` 顶部增加 `from local_favorites_archive.models import MediaItem, Post` 和 `from local_favorites_archive.storage import ArchiveStore`，并增加一个创建含媒体推文的测试辅助函数。随后追加：

```python
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
```

- [ ] **步骤 2：运行接口测试并确认路由不存在**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_web.py -k "retry_all_failed or retry_single_failed or retry_rejects" -v
```

预期：重试接口返回 404，测试失败。

- [ ] **步骤 3：实现重试后台任务和辅助检查**

在 `create_app` 中、`download_pending` 之后增加：

```python
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
```

- [ ] **步骤 4：实现两个重试路由**

从 `fastapi.responses` 导入 `JSONResponse`，在 `/api/sync/failures` 之后增加：

```python
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
```

- [ ] **步骤 5：运行接口与既有同步测试**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_web.py -v
```

预期：全部 Web 测试通过；既有采集与媒体下载行为未改变。

- [ ] **步骤 6：提交 Web API 改动**

```powershell
git add src/local_favorites_archive/web.py tests/test_web.py
git commit -m "feat: expose failed media retry API"
```

### 任务 4：在同步中心增加显式重试控件

**文件：**

- 修改：`src/local_favorites_archive/static/index.html`
- 修改：`src/local_favorites_archive/static/app.js`
- 修改：`src/local_favorites_archive/static/styles.css`
- 测试：`tests/test_web.py`

- [ ] **步骤 1：编写前端契约测试**

在 `tests/test_web.py` 追加：

```python
def test_sync_center_exposes_explicit_media_retry_controls(tmp_path):
    client = TestClient(create_app(Settings(archive_root=tmp_path)))
    html = client.get("/").text
    script = client.get("/assets/app.js").text

    assert 'id="retry-all-failures"' in html
    assert 'id="retry-failures-message"' in html
    assert 'data-retry-media' in script
    assert "/api/sync/failures/retry" in script
    assert "function retryMediaFailures" in script
    assert "retrying" in script
    assert "['starting', 'collecting', 'downloading', 'retrying']" in script
    assert "loadSyncFailures()" in script
    assert "loadOverview()" in script


def test_api_errors_expose_status_for_retry_conflicts(tmp_path):
    script = TestClient(create_app(Settings(archive_root=tmp_path))).get("/assets/app.js").text

    assert "error.status = response.status" in script
    assert "error.status === 404" in script
```

- [ ] **步骤 2：运行前端契约测试并确认控件缺失**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_web.py -k "explicit_media_retry or retry_conflicts" -v
```

预期：HTML 和 JavaScript 尚无重试控件，测试失败。

- [ ] **步骤 3：增加全部重试按钮和面板消息**

将失败面板标题改为：

```html
<div class="panel-heading failure-heading">
  <div><span class="section-kicker">MEDIA FAILURES</span><h2 id="failures-title">媒体下载失败记录</h2></div>
  <div class="failure-heading-actions">
    <span>最多显示 200 条</span>
    <button id="retry-all-failures" type="button" class="secondary" disabled aria-label="重试全部失败媒体">全部重试</button>
  </div>
</div>
<div id="retry-failures-message" class="failure-message" role="status"></div>
```

保留后面的 `#sync-failures` 容器。

- [ ] **步骤 4：让 API 错误携带 HTTP 状态**

将 `api` 中的错误分支改为：

```javascript
  if (!response.ok) {
    const error = new Error(body.detail || `请求失败 (${response.status})`);
    error.status = response.status;
    throw error;
  }
```

- [ ] **步骤 5：渲染单条按钮并实现控件状态**

增加全局状态：

```javascript
let syncState = {state: 'idle', media_failed: 0};
let retrySubmitting = false;
```

在每个失败行的原文链接后增加：

```javascript
<button type="button" class="secondary retry-media" data-retry-media data-post-id="${esc(item.post_id)}" data-media-index="${esc(item.media_index)}">重试</button>
```

增加：

```javascript
function updateRetryControls() {
  const active = ['starting', 'collecting', 'downloading', 'retrying'].includes(syncState.state);
  const disabled = active || retrySubmitting;
  $('retry-all-failures').disabled = disabled || !(syncState.media_failed > 0);
  document.querySelectorAll('[data-retry-media]').forEach(button => {
    button.disabled = disabled;
  });
}
```

在 `loadSyncFailures()` 成功和失败分支结束前调用 `updateRetryControls()`。

- [ ] **步骤 6：实现单条与全部重试请求**

增加：

```javascript
async function retryMediaFailures(url, button) {
  retrySubmitting = true;
  const originalLabel = button.textContent;
  button.textContent = '正在重试…';
  $('retry-failures-message').textContent = '正在提交媒体重试任务…';
  updateRetryControls();
  try {
    const result = await api(url, {method: 'POST'});
    if (!result.requested) {
      $('retry-failures-message').textContent = '当前没有需要重试的失败媒体';
      await loadSyncFailures();
      return;
    }
    $('retry-failures-message').textContent = `已提交 ${formatNumber(result.requested)} 个失败媒体，正在重试`;
    await poll();
  } catch (error) {
    $('retry-failures-message').textContent = error.message;
    if (error.status === 404) await loadSyncFailures();
  } finally {
    retrySubmitting = false;
    button.textContent = originalLabel;
    updateRetryControls();
  }
}

$('retry-all-failures').addEventListener('click', event => {
  retryMediaFailures('/api/sync/failures/retry', event.currentTarget);
});

$('sync-failures').addEventListener('click', event => {
  const button = event.target.closest('[data-retry-media]');
  if (!button) return;
  const postId = encodeURIComponent(button.dataset.postId);
  const mediaIndex = encodeURIComponent(button.dataset.mediaIndex);
  retryMediaFailures(`/api/sync/failures/${postId}/${mediaIndex}/retry`, button);
});
```

- [ ] **步骤 7：把重试状态接入轮询和完成刷新**

在 `renderSyncState(state)` 开头赋值 `syncState = state`，并在末尾调用 `updateRetryControls()`。将轮询活动状态改为：

```javascript
if (['starting', 'collecting', 'downloading', 'retrying'].includes(state.state)) {
  pollTimer = setTimeout(poll, 1500);
}
```

完成刷新保留并明确为：

```javascript
if (state.state === 'finished') {
  await Promise.all([load(), loadOverview(), loadSyncFailures()]);
}
```

- [ ] **步骤 8：调整失败记录布局**

将桌面失败行调整为五列，并增加：

```css
.failure-heading-actions { display: flex; align-items: center; gap: 10px; }
.failure-message { min-height: 22px; color: var(--muted); font-size: 12px; }
.failure-row { grid-template-columns: minmax(130px, .8fr) 80px minmax(0, 1.6fr) auto auto; }
.retry-media { min-height: 34px; padding: 7px 10px; }
```

在现有 `@media (max-width: 720px)` 中使用：

```css
  .failure-heading { align-items: flex-start; }
  .failure-heading-actions { flex-wrap: wrap; justify-content: flex-end; }
  .failure-row { grid-template-columns: minmax(0, 1fr) auto auto; }
  .failure-row > div:first-child, .failure-row .failure-error { grid-column: 1 / -1; }
```

在 `@media (max-width: 520px)` 中使用：

```css
  .failure-heading { display: grid; }
  .failure-heading-actions { justify-content: space-between; }
  .failure-row { grid-template-columns: minmax(0, 1fr) auto; }
  .failure-row .retry-media { grid-column: 2; }
```

- [ ] **步骤 9：运行前端契约和完整 Web 测试**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_web.py -v
node --check src\local_favorites_archive\static\app.js
```

预期：全部通过，无 JavaScript 语法错误。

- [ ] **步骤 10：提交同步中心界面改动**

```powershell
git add src/local_favorites_archive/static/index.html src/local_favorites_archive/static/app.js src/local_favorites_archive/static/styles.css tests/test_web.py
git commit -m "feat: retry failed media from sync center"
```

### 任务 5：更新 README 和中文长期文档

**文件：**

- 修改：`README.md`
- 修改：`docs/FEATURES.md`
- 修改：`docs/ARCHITECTURE.md`
- 修改：`docs/UI-DESIGN.md`
- 修改：`docs/DEVELOPMENT.md`
- 修改：`docs/DATA-STORAGE.md`
- 修改：`docs/SECURITY-AND-LIMITATIONS.md`
- 测试：`tests/test_project_documentation.py`

- [ ] **步骤 1：增加文档内容测试**

在 `tests/test_project_documentation.py` 追加：

```python
def test_documentation_explains_media_retry_modes() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    documents = {
        filename: (ROOT / "docs" / filename).read_text(encoding="utf-8")
        for filename in EXPECTED_DOCUMENTS
    }

    assert "同步期间的隐式重试" in readme
    assert "服务重启不会自动重试" in readme
    assert "全部重试" in readme and "单条重试" in readme
    assert "failed" in readme and "queued" in readme
    assert "local-favorites retry-media" in readme
    assert "显式重试" in documents["FEATURES.md"]
    assert "/api/sync/failures/retry" in documents["ARCHITECTURE.md"]
    assert "全部重试" in documents["UI-DESIGN.md"]
    assert "failed -> queued -> downloaded/failed" in documents["DATA-STORAGE.md"]
    assert "重试不扩大" in documents["SECURITY-AND-LIMITATIONS.md"]
    assert "重试接口" in documents["DEVELOPMENT.md"]
```

- [ ] **步骤 2：运行测试并确认说明尚不完整**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_project_documentation.py::test_documentation_explains_media_retry_modes -v
```

预期：README 和长期文档缺少显式重试说明，测试失败。

- [ ] **步骤 3：更新 README**

在“同步收藏”下新增“媒体失败与重试”小节，明确写出：

```markdown
### 媒体失败与重试

同步期间，每收到一批 Likes 响应以及采集结束时，程序都会运行媒体下载，因此较早失败的媒体可能在同一次同步的后续阶段被隐式重试。同步完成后不会按时间自动重试，服务重启也不会自动重试。

同步中心提供两种显式重试：

- “重试”只重新下载对应的一条失败媒体；
- “全部重试”重新下载归档中所有 `failed` 媒体，不受页面最多显示 200 条的限制。

网页显式重试不会处理已经处于 `queued` 的媒体。命令行 `local-favorites retry-media` 的范围更广，会处理全部未下载媒体，包括 `failed` 和 `queued`。来源链接过期、访问权限、网络错误或 X 平台变化仍可能导致重试再次失败。
```

将现有“重试失败媒体”命令说明改为引用该小节，并避免描述成只处理失败状态。

- [ ] **步骤 4：更新六份长期维护文档**

按设计文档逐一增加：

- `FEATURES.md`：网页单条和全部显式重试、同步期间隐式重试、无定时重试。
- `ARCHITECTURE.md`：两个 POST 接口、目标集合、下载锁、`retrying` 状态和完成刷新。
- `UI-DESIGN.md`：标题区全部重试、行内重试、禁用和状态消息规则。
- `DATA-STORAGE.md`：原样写出 `failed -> queued -> downloaded/failed`，区分网页与命令行范围。
- `SECURITY-AND-LIMITATIONS.md`：写明“重试不扩大访问权限”，链接失效仍可能失败。
- `DEVELOPMENT.md`：增加重试接口、锁互斥、目标过滤和前端交互测试要求。

- [ ] **步骤 5：运行文档测试并提交**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_project_documentation.py -v
git diff --check
```

预期：全部文档测试通过，差异无空白错误。

提交：

```powershell
git add README.md docs/FEATURES.md docs/ARCHITECTURE.md docs/UI-DESIGN.md docs/DEVELOPMENT.md docs/DATA-STORAGE.md docs/SECURITY-AND-LIMITATIONS.md tests/test_project_documentation.py
git commit -m "docs: explain media retry behavior"
```

### 任务 6：完整验证和浏览器交互检查

**文件：**

- 验证：全部项目文件
- 临时数据：使用项目外或被忽略的测试归档，不修改用户真实归档内容

- [ ] **步骤 1：运行完整 Python 测试**

运行：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

预期：全部测试通过，无失败。

- [ ] **步骤 2：运行全部 JavaScript 语法检查**

运行：

```powershell
node --check extension\background.js
node --check extension\popup.js
node --check src\local_favorites_archive\static\app.js
```

预期：三个命令退出码均为 0。

- [ ] **步骤 3：创建隔离的浏览器验证归档**

先建立一张本地测试图片和三条隔离媒体记录：

```powershell
New-Item -ItemType Directory -Force .\archive-qa-fixtures | Out-Null
$png = [Convert]::FromBase64String('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')
[IO.File]::WriteAllBytes((Join-Path (Resolve-Path .\archive-qa-fixtures) 'media.png'), $png)
@'
from datetime import datetime, timezone
from pathlib import Path

from local_favorites_archive.models import MediaItem, Post
from local_favorites_archive.storage import ArchiveStore

store = ArchiveStore(Path("archive-qa"))
for post_id, source_url in (
    ("success", "http://127.0.0.1:8767/media.png"),
    ("failure", "http://127.0.0.1:9/missing.png"),
    ("queued", "http://127.0.0.1:8767/media.png"),
):
    store.upsert_post(Post(
        post_id=post_id,
        url=f"https://x.com/alice/status/{post_id}",
        text=f"QA {post_id}",
        author_id="qa-author",
        author_handle="alice",
        author_name="Alice",
        published_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
        collected_at=datetime.now(timezone.utc),
        raw={"id": post_id},
        media=[MediaItem(0, "image", source_url)],
    ))
with store._connect() as db:
    db.execute("UPDATE media SET status='failed',error='QA failure' WHERE post_id IN ('success','failure')")
'@ | .\.venv\Scripts\python.exe -
```

在两个独立的长运行终端中启动测试媒体服务和项目服务：

```powershell
.\.venv\Scripts\python.exe -m http.server 8767 --bind 127.0.0.1 --directory .\archive-qa-fixtures
```

```powershell
.\.venv\Scripts\local-favorites.exe serve --archive .\archive-qa --port 8766
```

预期：真实默认 `archive/` 不被修改。

- [ ] **步骤 4：验证桌面交互**

使用 Browser 插件打开 `http://127.0.0.1:8766/#sync`：

1. 确认失败面板显示两条失败记录和“全部重试”按钮。
2. 点击一条记录的“重试”，确认按钮进入“重试中”、全局控件禁用、状态显示正在重试。
3. 完成后确认成功项从失败列表消失，排队项没有被下载。
4. 对剩余失败项点击“全部重试”，确认再次失败时保留最新错误。
5. 在任务活动时确认重复点击被禁用。
6. 检查总览、媒体计数和收藏卡片随完成状态刷新。
7. 检查浏览器控制台没有相关错误。

- [ ] **步骤 5：验证窄屏布局**

将浏览器视口调整到约 390×844，确认标题操作区换行、错误文字可读、原文链接和重试按钮不重叠或溢出。

- [ ] **步骤 6：清理验证归档并检查 Git 状态**

在两个长运行终端中分别按 `Ctrl+C` 停止 8766 和 8767 服务，然后运行：

```powershell
$projectRoot = (Resolve-Path '.').Path
$expectedLeaves = @('archive-qa', 'archive-qa-fixtures')
foreach ($leaf in $expectedLeaves) {
  $candidate = Join-Path $projectRoot $leaf
  if (Test-Path -LiteralPath $candidate) {
    $resolved = (Resolve-Path -LiteralPath $candidate).Path
    if ((Split-Path -Parent $resolved) -ne $projectRoot -or (Split-Path -Leaf $resolved) -ne $leaf) {
      throw "拒绝删除未通过校验的测试目录：$resolved"
    }
    [IO.Directory]::Delete($resolved, $true)
  }
}
if (Get-NetTCPConnection -LocalPort 8766,8767 -State Listen -ErrorAction SilentlyContinue) {
  throw '测试服务仍在运行'
}
git diff --check
git status --short --branch
```

预期：服务停止、临时归档删除、工作区干净，所有功能和文档提交均存在。

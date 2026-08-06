# Deduplicated Sync And Post Deletion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop Likes collection after a configurable run of already archived post IDs, preserve media download deduplication, and permanently delete explicitly selected local posts and their owned files.

**Architecture:** SQLite remains the source of truth for post identity and the new persistent stop threshold. The FastAPI ingest endpoint maintains a run-scoped existing-post streak and returns a latched stop signal to the Chrome extension. ArchiveStore owns transactional record deletion and bounded file cleanup, while the existing sync and favorites workspaces expose settings and selected-post deletion.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLite/FTS5, pytest, Chrome Manifest V3 extension JavaScript, vanilla browser JavaScript and CSS.

---

### Task 1: Persist The Stop Threshold And Lock In Media Deduplication

**Files:**
- Modify: `src/local_favorites_archive/storage.py`
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Write failing storage tests**

Add tests that define the default, persistence, and media-status contract:

```python
def test_stop_after_existing_defaults_to_50_and_persists(tmp_path):
    first = ArchiveStore(tmp_path)
    assert first.get_stop_after_existing() == 50

    assert first.set_stop_after_existing(12) == 12
    assert ArchiveStore(tmp_path).get_stop_after_existing() == 12


def test_repeated_post_keeps_downloaded_media_state(tmp_path):
    store = ArchiveStore(tmp_path)
    store.upsert_post(sample_post(post_id="42"))
    with store._connect() as db:
        db.execute(
            "UPDATE media SET status='downloaded',byte_size=123,checksum='saved' WHERE post_id='42'"
        )

    assert store.upsert_post(sample_post(post_id="42")) is False

    media = store.get_post("42")["media"][0]
    assert media["status"] == "downloaded"
    assert media["byte_size"] == 123
    assert media["checksum"] == "saved"
```

- [ ] **Step 2: Run the focused tests and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_storage.py -k "stop_after_existing or repeated_post_keeps" -v
```

Expected: the settings test fails because the methods and table do not exist; the media regression test passes and documents the current no-redownload behavior.

- [ ] **Step 3: Add settings storage**

Add this table and default row in `_init_db()`:

```sql
CREATE TABLE IF NOT EXISTS archive_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
INSERT OR IGNORE INTO archive_settings(key,value)
VALUES('stop_after_existing','50');
```

Add typed methods:

```python
def get_stop_after_existing(self) -> int:
    with self._connect() as db:
        row = db.execute(
            "SELECT value FROM archive_settings WHERE key='stop_after_existing'"
        ).fetchone()
    return int(row["value"]) if row else 50

def set_stop_after_existing(self, value: int) -> int:
    with self._connect() as db:
        db.execute(
            "INSERT INTO archive_settings(key,value) VALUES('stop_after_existing',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(value),),
        )
    return value
```

Validation remains at the Pydantic API boundary in Task 2.

- [ ] **Step 4: Run storage tests and confirm GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_storage.py -q
```

Expected: all storage tests pass.

- [ ] **Step 5: Commit persistent settings**

```powershell
git add src/local_favorites_archive/storage.py tests/test_storage.py
git commit -m "feat: persist sync stop threshold"
```

### Task 2: Count Consecutive Existing Posts Across Ingest Batches

**Files:**
- Modify: `src/local_favorites_archive/web.py`
- Modify: `tests/test_web.py`

- [ ] **Step 1: Add reusable X-response test builders**

Near the top of `tests/test_web.py`, add:

```python
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
```

- [ ] **Step 2: Write failing settings and streak tests**

Add:

```python
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

    latched = client.post("/api/ingest/x-response", json=x_payload("3")).json()
    assert latched["existing_streak"] == 0
    assert latched["stop_requested"] is True

    client.post("/api/ingest/start")
    status = client.get("/api/sync/status").json()
    assert status["existing_streak"] == 0
    assert status["stop_requested"] is False


def test_zero_threshold_never_requests_stop(tmp_path):
    client = TestClient(create_app(Settings(archive_root=tmp_path)))
    client.patch("/api/settings", json={"stop_after_existing": 0})
    client.post("/api/ingest/x-response", json=x_payload("1", "2", "3"))
    client.post("/api/ingest/start")

    result = client.post("/api/ingest/x-response", json=x_payload("1", "2", "3")).json()

    assert result["existing_streak"] == 3
    assert result["stop_after_existing"] == 0
    assert result["stop_requested"] is False
```

Update `test_ingest_x_response_persists_liked_post` so it checks the existing `discovered` and `new` keys individually and also expects the three new stop fields.

- [ ] **Step 3: Run the focused API tests and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_web.py -k "sync_settings or existing_streak or zero_threshold or ingest_x_response_persists" -v
```

Expected: settings endpoints return 404 and ingest responses lack streak fields.

- [ ] **Step 4: Add the settings model and endpoints**

Add:

```python
class ArchiveSettingsPayload(BaseModel):
    stop_after_existing: int = Field(ge=0, le=100000)
```

Inside `create_app()` add:

```python
@app.get("/api/settings")
def archive_settings():
    return {"stop_after_existing": store.get_stop_after_existing()}

@app.patch("/api/settings")
def update_archive_settings(payload: ArchiveSettingsPayload):
    return {"stop_after_existing": store.set_stop_after_existing(payload.stop_after_existing)}
```

- [ ] **Step 5: Implement ordered run-scoped streak counting**

Initialize `state` with the persistent threshold, zero streak, and false latch. In `ingest_start()`, clear and recreate those fields. Replace the generator expression in `ingest_x_response()` with an ordered loop:

```python
existing_streak = state.get("existing_streak", 0)
added = 0
for value in posts:
    if store.upsert_post(value):
        added += 1
        existing_streak = 0
    else:
        existing_streak += 1

threshold = store.get_stop_after_existing()
stop_requested = state.get("stop_requested", False) or (
    threshold > 0 and existing_streak >= threshold
)
state.update({
    "state": "collecting",
    "discovered": state.get("discovered", 0) + len(posts),
    "new": state.get("new", 0) + added,
    "existing_streak": existing_streak,
    "stop_after_existing": threshold,
    "stop_requested": stop_requested,
    "message": "正在从已登录的 Chrome 接收 Likes",
})
```

Return `discovered`, `new`, `existing_streak`, `stop_after_existing`, and `stop_requested`. Keep scheduling media download through the existing lock.

- [ ] **Step 6: Run web tests and confirm GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_web.py -q
```

Expected: all web tests pass.

- [ ] **Step 7: Commit server-side stopping**

```powershell
git add src/local_favorites_archive/web.py tests/test_web.py
git commit -m "feat: stop sync after existing post streak"
```

### Task 3: Make The Chrome Extension Honor The Stop Signal

**Files:**
- Modify: `extension/background.js`
- Modify: `tests/test_extension.py`

- [ ] **Step 1: Write a failing extension contract test**

Add:

```python
def test_extension_finishes_when_server_requests_threshold_stop():
    source = Path("extension/background.js").read_text(encoding="utf-8")

    assert "result.stop_requested" in source
    assert "async function finish" in source
    assert "finishPromise" in source
    assert "连续" in source
    assert "result.existing_streak" in source
```

- [ ] **Step 2: Run the extension test and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_extension.py -v
```

Expected: the new contract assertions fail because the stop response is ignored.

- [ ] **Step 3: Guard finalization and act on the stop response**

Add a module-level `let finishPromise = null;`. Split finalization into a private operation and an idempotent public wrapper:

```javascript
async function finishOnce(message) {
  const tabId = session.tabId;
  pendingLikes.clear();
  await saveState({running: false, tabId: null, message});
  if (tabId !== null) {
    try {
      await chrome.scripting.executeScript({
        target: {tabId},
        func: () => {
          if (globalThis.__localFavoritesArchiveTimer) clearInterval(globalThis.__localFavoritesArchiveTimer);
          globalThis.__localFavoritesArchiveTimer = null;
        },
      });
    } catch (_) {}
    try { await chrome.debugger.detach({tabId}); } catch (_) {}
  }
  try { await fetch(`${LOCAL_API}/api/ingest/finish`, {method: "POST"}); } catch (_) {}
}

async function finish(message) {
  if (!finishPromise) {
    finishPromise = finishOnce(message).finally(() => { finishPromise = null; });
  }
  return finishPromise;
}
```

At the end of `sendPayload()` update state and stop when requested:

```javascript
if (result.stop_requested && session.running) {
  await finish(`已连续读取 ${result.existing_streak} 条本地已有推文，正在下载媒体`);
}
```

Set `finishPromise = null` when a new run starts before debugger attachment.

- [ ] **Step 4: Run extension tests and JavaScript syntax checks**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_extension.py -q
node --check extension/background.js
node --check extension/popup.js
```

Expected: all commands pass.

- [ ] **Step 5: Commit extension stopping**

```powershell
git add extension/background.js tests/test_extension.py
git commit -m "feat: stop extension on archived post streak"
```

### Task 4: Permanently Delete Post Records And Owned Files

**Files:**
- Modify: `src/local_favorites_archive/storage.py`
- Modify: `src/local_favorites_archive/web.py`
- Modify: `tests/test_storage.py`
- Modify: `tests/test_web.py`

- [ ] **Step 1: Write failing storage deletion tests**

Add `import sqlite3` only if required for direct row checks, then add:

```python
def test_delete_posts_removes_records_search_rows_and_owned_files(tmp_path):
    store = ArchiveStore(tmp_path)
    links = [PostLink(0, "example.com", "https://example.com", "https://t.co/link")]
    store.upsert_post(sample_post(post_id="1", text="delete searchable", links=links))
    store.upsert_post(sample_post(post_id="2", text="keep searchable"))
    tag = store.create_tag("selected", "#2563eb")
    store.assign_tag("1", tag["id"])
    media_path = store.root / store.get_post("1")["media"][0]["local_path"]
    media_path.parent.mkdir(parents=True, exist_ok=True)
    media_path.write_bytes(b"saved-media")

    result = store.delete_posts(["1", "missing"])

    assert result["deleted"] == ["1"]
    assert result["not_found"] == ["missing"]
    assert result["file_cleanup_errors"] == []
    assert store.get_post("1") is None
    assert store.get_post("2") is not None
    assert store.list_posts(query="delete") == []
    assert not (tmp_path / "raw" / "1.json").exists()
    assert not (tmp_path / "media" / "1").exists()
    with store._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM media WHERE post_id='1'").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM post_links WHERE post_id='1'").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM post_tags WHERE post_id='1'").fetchone()[0] == 0


def test_delete_posts_deduplicates_requested_ids(tmp_path):
    store = ArchiveStore(tmp_path)
    store.upsert_post(sample_post(post_id="1"))

    result = store.delete_posts(["1", "1"])

    assert result["deleted"] == ["1"]
    assert result["not_found"] == []


def test_delete_posts_reports_file_cleanup_errors_after_database_commit(tmp_path, monkeypatch):
    store = ArchiveStore(tmp_path)
    store.upsert_post(sample_post(post_id="1"))
    original_unlink = Path.unlink

    def fail_raw_cleanup(path, missing_ok=False):
        if path.name == "1.json":
            raise OSError("file is locked")
        return original_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail_raw_cleanup)

    result = store.delete_posts(["1"])

    assert store.get_post("1") is None
    assert result["deleted"] == ["1"]
    assert result["file_cleanup_errors"][0]["post_id"] == "1"
    assert "file is locked" in result["file_cleanup_errors"][0]["error"]
```

Add `from pathlib import Path` to the test imports for the cleanup-failure test.

- [ ] **Step 2: Run storage deletion tests and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_storage.py -k "delete_posts" -v
```

Expected: failures report that `ArchiveStore.delete_posts` does not exist.

- [ ] **Step 3: Implement bounded transactional deletion**

Import `shutil`. Add private path validation:

```python
def _owned_path(self, relative: str | Path) -> Path:
    target = (self.root / relative).resolve()
    root = self.root.resolve()
    if target == root or root not in target.parents:
        raise ValueError(f"archive path escapes root: {relative}")
    return target
```

Implement `delete_posts()` so it preserves first-seen request order, removes duplicate IDs, gathers `raw_path` before deletion, and uses one connection transaction:

```python
def delete_posts(self, post_ids: list[str]) -> dict[str, list[Any]]:
    requested = list(dict.fromkeys(post_ids))
    deleted: list[str] = []
    not_found: list[str] = []
    owned_paths: dict[str, tuple[Path, Path]] = {}
    with self._connect() as db:
        for post_id in requested:
            row = db.execute("SELECT raw_path FROM posts WHERE post_id=?", (post_id,)).fetchone()
            if not row:
                not_found.append(post_id)
                continue
            owned_paths[post_id] = (
                self._owned_path(row["raw_path"]),
                self._owned_path(self.media_dir.relative_to(self.root) / post_id),
            )
            db.execute("DELETE FROM media WHERE post_id=?", (post_id,))
            db.execute("DELETE FROM post_links WHERE post_id=?", (post_id,))
            db.execute("DELETE FROM post_tags WHERE post_id=?", (post_id,))
            db.execute("DELETE FROM posts_fts WHERE post_id=?", (post_id,))
            db.execute("DELETE FROM posts WHERE post_id=?", (post_id,))
            deleted.append(post_id)

    cleanup_errors: list[dict[str, str]] = []
    for post_id, (raw_path, media_path) in owned_paths.items():
        try:
            raw_path.unlink(missing_ok=True)
        except OSError as exc:
            cleanup_errors.append({"post_id": post_id, "path": str(raw_path), "error": str(exc)})
        try:
            if media_path.exists():
                shutil.rmtree(media_path)
        except OSError as exc:
            cleanup_errors.append({"post_id": post_id, "path": str(media_path), "error": str(exc)})
    return {"deleted": deleted, "not_found": not_found, "file_cleanup_errors": cleanup_errors}
```

- [ ] **Step 4: Run storage tests and confirm GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_storage.py -q
```

Expected: all storage tests pass.

- [ ] **Step 5: Write the failing deletion API test**

Add to `tests/test_web.py`:

```python
def test_delete_posts_api_accepts_selected_ids_and_validates_bounds(tmp_path):
    client = TestClient(create_app(Settings(archive_root=tmp_path)))
    client.post("/api/ingest/x-response", json=x_payload("1", "2"))

    response = client.request("DELETE", "/api/posts", json={"post_ids": ["1", "missing"]})

    assert response.status_code == 200
    assert response.json()["deleted"] == ["1"]
    assert response.json()["not_found"] == ["missing"]
    assert client.get("/api/posts/1").status_code == 404
    assert client.get("/api/posts/2").status_code == 200
    assert client.request("DELETE", "/api/posts", json={"post_ids": []}).status_code == 422
    assert client.request("DELETE", "/api/posts", json={"post_ids": [str(i) for i in range(201)]}).status_code == 422
```

- [ ] **Step 6: Run the API test and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_web.py::test_delete_posts_api_accepts_selected_ids_and_validates_bounds -v
```

Expected: DELETE returns 405 because the route does not exist.

- [ ] **Step 7: Add the deletion request model and endpoint**

Add:

```python
class DeletePostsPayload(BaseModel):
    post_ids: list[str] = Field(min_length=1, max_length=200)

    @field_validator("post_ids")
    @classmethod
    def validate_post_ids(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("post IDs cannot be blank")
        return list(dict.fromkeys(normalized))
```

Register the collection route before `/api/posts/{post_id}`:

```python
@app.delete("/api/posts")
def delete_posts(payload: DeletePostsPayload):
    return store.delete_posts(payload.post_ids)
```

- [ ] **Step 8: Run storage and web tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_storage.py tests/test_web.py -q
```

Expected: all tests pass.

- [ ] **Step 9: Commit permanent deletion support**

```powershell
git add src/local_favorites_archive/storage.py src/local_favorites_archive/web.py tests/test_storage.py tests/test_web.py
git commit -m "feat: permanently delete selected posts"
```

### Task 5: Add Current-Page Selection And Deletion To Favorites

**Files:**
- Modify: `src/local_favorites_archive/static/index.html`
- Modify: `src/local_favorites_archive/static/app.js`
- Modify: `src/local_favorites_archive/static/styles.css`
- Modify: `tests/test_web.py`

- [ ] **Step 1: Write a failing frontend contract test**

Add:

```python
def test_favorites_supports_selected_post_deletion(tmp_path):
    client = TestClient(create_app(Settings(archive_root=tmp_path)))
    html = client.get("/").text
    script = client.get("/assets/app.js").text

    for element_id in ("select-page", "selection-count", "delete-selected", "delete-message"):
        assert f'id="{element_id}"' in html
    assert "selectedPostIds" in script
    assert 'class="post-select"' in script
    assert "function updateSelectionControls" in script
    assert "function clearPostSelection" in script
    assert "永久删除所选" in script
    assert "method: 'DELETE'" in script
    assert "post_ids" in script
```

- [ ] **Step 2: Run the contract test and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_web.py::test_favorites_supports_selected_post_deletion -v
```

Expected: the selection controls and script functions are missing.

- [ ] **Step 3: Add the selection toolbar**

In the collection heading add:

```html
<div class="collection-actions">
  <label class="select-page-control"><input id="select-page" type="checkbox">全选当前页</label>
  <span id="selection-count" class="numeric">已选 0 条</span>
  <button id="delete-selected" class="danger" type="button" disabled>删除所选</button>
  <span id="delete-message" role="status"></span>
</div>
```

Keep the page-size control in the same heading without nesting cards.

- [ ] **Step 4: Render checkboxes and maintain page-scoped selection**

Add `const selectedPostIds = new Set();` and these helpers:

```javascript
function updateSelectionControls() {
  const cards = [...document.querySelectorAll('.post')];
  const selectedOnPage = cards.filter(card => selectedPostIds.has(card.dataset.id));
  $('selection-count').textContent = `已选 ${formatNumber(selectedPostIds.size)} 条`;
  $('delete-selected').disabled = selectedPostIds.size === 0;
  $('select-page').checked = cards.length > 0 && selectedOnPage.length === cards.length;
  $('select-page').indeterminate = selectedOnPage.length > 0 && selectedOnPage.length < cards.length;
}

function clearPostSelection() {
  selectedPostIds.clear();
  $('select-page').checked = false;
  $('select-page').indeterminate = false;
  updateSelectionControls();
}
```

Add a checkbox to each post head:

```html
<label class="post-select-control">
  <input class="post-select" type="checkbox" aria-label="选择 ${esc(post.author_name || post.author_handle)} 的推文 ${esc(post.post_id)}">
</label>
```

Clear selection at the beginning of `load()` and call `updateSelectionControls()` after cards render. Add checkbox change handling that updates `selectedPostIds` without triggering tag or image actions.

- [ ] **Step 5: Implement select-page and confirmed deletion**

Add handlers:

```javascript
$('select-page').addEventListener('change', event => {
  document.querySelectorAll('.post').forEach(card => {
    const checkbox = card.querySelector('.post-select');
    checkbox.checked = event.currentTarget.checked;
    if (checkbox.checked) selectedPostIds.add(card.dataset.id);
    else selectedPostIds.delete(card.dataset.id);
  });
  updateSelectionControls();
});

$('delete-selected').addEventListener('click', async () => {
  const postIds = [...selectedPostIds];
  if (!postIds.length) return;
  const confirmed = window.confirm(
    `永久删除所选 ${postIds.length} 条推文？正文、原始 JSON、标签、图片和视频都将删除，且无法撤销。`
  );
  if (!confirmed) return;
  try {
    const result = await api('/api/posts', {
      method: 'DELETE',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({post_ids: postIds}),
    });
    clearPostSelection();
    $('delete-message').textContent = result.file_cleanup_errors.length
      ? `已删除 ${result.deleted.length} 条，但有 ${result.file_cleanup_errors.length} 项文件清理失败`
      : `已删除 ${result.deleted.length} 条`;
    await Promise.all([loadTags(), load(), loadOverview(), loadSyncFailures()]);
    poll();
  } catch (error) {
    $('delete-message').textContent = `删除失败：${error.message}`;
  }
});
```

- [ ] **Step 6: Style stable desktop and mobile controls**

Add restrained toolbar and checkbox rules. Use a minimum 40px hit area, allow the action row to wrap, and at `max-width: 520px` make the delete button full-width while keeping checkbox labels readable. Do not alter card widths or pagination tracks.

- [ ] **Step 7: Run frontend tests and syntax validation**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_web.py -q
node --check src/local_favorites_archive/static/app.js
```

Expected: both commands pass.

- [ ] **Step 8: Commit favorites deletion UI**

```powershell
git add src/local_favorites_archive/static/index.html src/local_favorites_archive/static/app.js src/local_favorites_archive/static/styles.css tests/test_web.py
git commit -m "feat: delete selected favorite posts"
```

### Task 6: Add Persistent Stop Controls To The Sync Center

**Files:**
- Modify: `src/local_favorites_archive/static/index.html`
- Modify: `src/local_favorites_archive/static/app.js`
- Modify: `src/local_favorites_archive/static/styles.css`
- Modify: `tests/test_web.py`

- [ ] **Step 1: Write a failing sync-settings UI test**

Add:

```python
def test_sync_center_edits_and_displays_existing_post_limit(tmp_path):
    client = TestClient(create_app(Settings(archive_root=tmp_path)))
    html = client.get("/").text
    script = client.get("/assets/app.js").text

    for element_id in ("stop-after-existing", "save-sync-settings", "sync-settings-message", "existing-streak"):
        assert f'id="{element_id}"' in html
    assert "async function loadArchiveSettings" in script
    assert "'/api/settings'" in script
    assert "stop_after_existing" in script
    assert "existing_streak" in script
    assert "stop_requested" in script
    assert "已达到连续已有推文停止条件" in script
```

- [ ] **Step 2: Run the test and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_web.py::test_sync_center_edits_and_displays_existing_post_limit -v
```

Expected: the sync controls are missing.

- [ ] **Step 3: Add the sync setting controls**

Below the sync count grid add an unframed settings row:

```html
<form id="sync-settings-form" class="sync-settings-form">
  <label for="stop-after-existing">连续已有推文停止数</label>
  <input id="stop-after-existing" type="number" min="0" max="100000" step="1" value="50" inputmode="numeric">
  <button id="save-sync-settings" type="submit">保存</button>
  <span>当前连续已有 <strong id="existing-streak" class="numeric">0</strong> 条</span>
  <span id="sync-settings-message" role="status"></span>
</form>
```

The label is operational text; do not add explanatory marketing copy.

- [ ] **Step 4: Load, save, and render settings state**

Add:

```javascript
async function loadArchiveSettings() {
  const settings = await api('/api/settings');
  $('stop-after-existing').value = settings.stop_after_existing;
}
```

In `renderSyncState()` set the streak and keep the limit input synchronized when it is not focused:

```javascript
$('existing-streak').textContent = formatNumber(state.existing_streak || 0);
if (document.activeElement !== $('stop-after-existing')) {
  $('stop-after-existing').value = state.stop_after_existing ?? $('stop-after-existing').value;
}
```

When `state.stop_requested` is true, make the sync status message take precedence over the generic collecting/downloading message:

```javascript
if (state.stop_requested) {
  $('status').textContent = `已达到连续已有推文停止条件（${formatNumber(state.existing_streak)} 条），正在完成媒体下载`;
}
```

Apply this after the existing default status-message assignment so the threshold reason remains visible during download finalization.

Add submit handling that sends an integer to `PATCH /api/settings`, reports success or validation failure, and refreshes sync status. Call `loadArchiveSettings()` during initialization and from the global refresh action.

- [ ] **Step 5: Style responsive sync settings**

Use a compact grid on desktop and a single column below 720px. Give the number input a stable width and preserve existing progress-bar dimensions.

- [ ] **Step 6: Run web tests and JavaScript checks**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_web.py -q
node --check src/local_favorites_archive/static/app.js
```

Expected: all checks pass.

- [ ] **Step 7: Commit sync settings UI**

```powershell
git add src/local_favorites_archive/static/index.html src/local_favorites_archive/static/app.js src/local_favorites_archive/static/styles.css tests/test_web.py
git commit -m "feat: configure existing post stop limit"
```

### Task 7: Full Verification, Browser QA, And Service Activation

**Files:**
- Modify only when a regression is found: files from Tasks 1-6

- [ ] **Step 1: Run the complete automated suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --check extension/background.js
node --check extension/popup.js
node --check src/local_favorites_archive/static/app.js
```

Expected: all tests and syntax checks pass.

- [ ] **Step 2: Start an isolated service**

Create a uniquely named archive directory under the Windows temporary directory, verify it is outside the repository, verify port `8766` is free, and start the existing CLI on `http://127.0.0.1:8766`. Do not point browser QA at the user's `archive` directory.

- [ ] **Step 3: Verify stop settings and streak responses**

Through the isolated API, set the threshold to two, insert two synthetic posts, start a new run, then send the same IDs in separate responses. Confirm the first response reports streak one and no stop, the second reports streak two and a latched stop, and a service restart preserves the threshold.

- [ ] **Step 4: Verify the favorites deletion flow in Browser**

The flow under test is: open `#favorites` with at least three synthetic posts -> select one card and cancel permanent confirmation -> verify nothing is deleted -> select two cards and confirm -> verify exactly those two cards, raw JSON files, and media directories disappear -> verify statistics and pagination update.

Use the in-app Browser plugin first. Check page identity, meaningful DOM, absence of framework overlays, console errors/warnings, and screenshot evidence.

- [ ] **Step 5: Verify responsive controls**

At `1280x720` and `390x844`, confirm selection controls, delete command, threshold input, sync counters, post cards, and pagination have no horizontal overflow or overlap. Capture one desktop and one mobile screenshot outside the repository.

- [ ] **Step 6: Clean up the isolated environment**

Reset the temporary viewport, finalize the Browser tab, stop only the process listening on port `8766`, validate the exact temporary archive path, and delete only that directory. Confirm the port is closed and the directory no longer exists.

- [ ] **Step 7: Run fresh final verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --check extension/background.js
node --check extension/popup.js
node --check src/local_favorites_archive/static/app.js
git diff --check
git status --short --branch
```

Expected: tests pass, syntax checks exit zero, `git diff --check` is clean, and no uncommitted implementation files remain.

- [ ] **Step 8: Restart the idle main service and report extension reload requirement**

Read `/api/sync/status` from port `8765`. Restart the existing Local Favorites process only when its state is idle or finished. Verify the post and media totals are unchanged, the new settings endpoint returns the default or persisted value, and an existing post returns successfully. Tell the user to click Reload for the unpacked extension on `chrome://extensions` so `background.js` uses the new stop signal.

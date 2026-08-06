# Multi-View Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the local X Likes archive into four hash-routed workspaces with a statistics overview, dedicated favorites, sync, and tag-management pages while preserving all existing archive and media behavior.

**Architecture:** Keep the existing FastAPI, SQLite, static HTML, CSS, and vanilla JavaScript stack. Add aggregate queries to `ArchiveStore`, expose them through two read-only endpoints, and reorganize the single static document into semantic workspace sections controlled by a small hash router. Existing post filtering, pagination, media rendering, image viewing, tag mutation, and synchronization polling remain in place and are moved to the workspace that owns them.

**Tech Stack:** Python 3.11, FastAPI, SQLite, pytest, HTML5, CSS, vanilla JavaScript, Browser integration.

---

### Task 1: Preserve And Commit The Confirmed Date Picker Fix

**Files:**
- Modify: `src/local_favorites_archive/static/index.html`
- Modify: `src/local_favorites_archive/static/styles.css`
- Modify: `src/local_favorites_archive/static/app.js`
- Test: `tests/test_web.py`

- [ ] **Step 1: Run the focused date-picker test**

Run: `python -m pytest tests/test_web.py::test_date_filters_have_visible_distinct_labels -v`

Expected: PASS, proving the already-reviewed `年/月/日` placeholder behavior is intact.

- [ ] **Step 2: Run JavaScript syntax validation**

Run: `node --check src/local_favorites_archive/static/app.js`

Expected: exit code 0.

- [ ] **Step 3: Commit only the date-picker fix**

```powershell
git add src/local_favorites_archive/static/index.html src/local_favorites_archive/static/styles.css src/local_favorites_archive/static/app.js tests/test_web.py
git commit -m "fix: unify date picker placeholders"
```

### Task 2: Add Overview Aggregate Queries

**Files:**
- Modify: `tests/test_storage.py`
- Modify: `src/local_favorites_archive/storage.py`

- [ ] **Step 1: Write failing aggregate tests**

Add tests that seed posts, tags, and media statuses directly through the store connection, then assert the complete public result:

```python
def test_overview_stats_reports_archive_aggregates(tmp_path, monkeypatch):
    store = ArchiveStore(tmp_path)
    store.upsert_post(sample_post(post_id="1", handle="alice", published_at=datetime(2024, 1, 1, tzinfo=timezone.utc)))
    store.upsert_post(sample_post(post_id="2", handle="bob", published_at=datetime(2024, 1, 3, tzinfo=timezone.utc), with_media=False))
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
    assert stats["monthly_additions"][-1]["month"] == "2024-02"


def test_overview_stats_handles_empty_media_and_zero_months(tmp_path):
    stats = ArchiveStore(tmp_path).overview_stats(now=datetime(2024, 2, 15, tzinfo=timezone.utc))
    assert stats["media_completion_percent"] == 0.0
    assert stats["tag_coverage_percent"] == 0.0
    assert [item["count"] for item in stats["monthly_additions"]] == [0] * 12
```

- [ ] **Step 2: Run the tests and confirm RED**

Run: `python -m pytest tests/test_storage.py -k overview_stats -v`

Expected: FAIL with `AttributeError: 'ArchiveStore' object has no attribute 'overview_stats'`.

- [ ] **Step 3: Implement the aggregate method**

Add `overview_stats(self, now: datetime | None = None) -> dict[str, Any]` to `ArchiveStore`. Use SQL aggregates for totals, distinct authors, distinct tagged posts, media status counts, post-level image/video/text counts, inclusive publication coverage, and `COALESCE(SUM(byte_size), 0)`. Build exactly 12 UTC month keys in Python and merge the grouped `collected_at` counts into them. Round percentages to one decimal place and return zero when the denominator is zero.

- [ ] **Step 4: Run the focused tests and confirm GREEN**

Run: `python -m pytest tests/test_storage.py -k overview_stats -v`

Expected: PASS.

- [ ] **Step 5: Commit the aggregate**

```powershell
git add src/local_favorites_archive/storage.py tests/test_storage.py
git commit -m "feat: add archive overview statistics"
```

### Task 3: Add Media Failure Query And Read-Only APIs

**Files:**
- Modify: `tests/test_storage.py`
- Modify: `tests/test_web.py`
- Modify: `src/local_favorites_archive/storage.py`
- Modify: `src/local_favorites_archive/web.py`

- [ ] **Step 1: Write failing storage and endpoint tests**

```python
def test_list_media_failures_joins_post_context(tmp_path):
    store = ArchiveStore(tmp_path)
    store.upsert_post(sample_post(post_id="7", handle="alice"))
    with store._connect() as db:
        db.execute("UPDATE media SET status='failed', error='timeout' WHERE post_id='7'")
    assert store.list_media_failures() == [{
        "post_id": "7", "author_name": "Alice", "author_handle": "alice",
        "url": "https://x.com/alice/status/7", "published_at": "2024-01-02T00:00:00+00:00",
        "media_index": 0, "kind": "image", "source_url": "https://pbs.twimg.com/media/a.jpg?name=orig",
        "error": "timeout",
    }]


def test_overview_and_failure_endpoints(tmp_path):
    client = TestClient(create_app(Settings(archive_root=tmp_path)))
    stats = client.get("/api/stats/overview")
    failures = client.get("/api/sync/failures")
    assert stats.status_code == 200
    assert stats.json()["posts_total"] == 0
    assert len(stats.json()["monthly_additions"]) == 12
    assert failures.status_code == 200
    assert failures.json() == []
```

- [ ] **Step 2: Run the tests and confirm RED**

Run: `python -m pytest tests/test_storage.py::test_list_media_failures_joins_post_context tests/test_web.py::test_overview_and_failure_endpoints -v`

Expected: FAIL because the method and routes do not exist.

- [ ] **Step 3: Implement the query and routes**

Add `ArchiveStore.list_media_failures(limit: int = 200)` using a `media JOIN posts`, `WHERE m.status='failed'`, and deterministic newest-first publication/media-index ordering. Add these thin routes before the dynamic `/api/posts/{post_id}` route:

```python
@app.get("/api/stats/overview")
def overview_stats():
    return store.overview_stats()

@app.get("/api/sync/failures")
def sync_failures():
    return store.list_media_failures()
```

- [ ] **Step 4: Run focused and full backend tests**

Run: `python -m pytest tests/test_storage.py tests/test_web.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the API work**

```powershell
git add src/local_favorites_archive/storage.py src/local_favorites_archive/web.py tests/test_storage.py tests/test_web.py
git commit -m "feat: expose overview and sync failure data"
```

### Task 4: Build The Four-Workspace Application Shell

**Files:**
- Modify: `tests/test_web.py`
- Modify: `src/local_favorites_archive/static/index.html`
- Modify: `src/local_favorites_archive/static/styles.css`

- [ ] **Step 1: Replace the old shell expectations with failing workspace-contract tests**

Assert that the HTML contains navigation links for `#overview`, `#favorites`, `#sync`, and `#tags`; semantic sections `workspace-overview`, `workspace-favorites`, `workspace-sync`, and `workspace-tags`; dedicated heading focus targets; sidebar badges; and `back-to-top`. Assert that `tag-dialog` and `tag-manager-open` are absent while `image-viewer` remains present.

- [ ] **Step 2: Run the UI contract tests and confirm RED**

Run: `python -m pytest tests/test_web.py -k "workspace or shell or image_viewer" -v`

Expected: FAIL on missing workspace hooks and remaining tag dialog.

- [ ] **Step 3: Implement the semantic document structure**

Create a persistent `.app-sidebar`, a `.workspace-main`, and four sibling `<section class="workspace" data-workspace="...">` elements. Move existing filters/posts/pagination into favorites, sync progress/path into sync, and the tag form/list into tags. Add overview metric, distribution, monthly chart, storage, and coverage placeholders with stable IDs. Keep only the image viewer as a dialog. Add an icon-only `back-to-top` button with Chinese accessible label and tooltip.

- [ ] **Step 4: Implement the responsive visual system**

Define shared tokens for the dark sidebar, white work surface, neutral borders, green accent, radii no larger than 8px, compact controls, and stable responsive grids. Apply `font-variant-numeric: tabular-nums` and `font-feature-settings: "tnum" 1, "lnum" 1` to metric values, dates, counts, percentages, storage, progress labels, and pagination. At `390px`, convert navigation to a sticky horizontal strip and ensure `overflow-x` is not introduced.

- [ ] **Step 5: Run UI contract tests and commit**

Run: `python -m pytest tests/test_web.py -k "workspace or shell or image_viewer or date_filters" -v`

Expected: PASS.

```powershell
git add src/local_favorites_archive/static/index.html src/local_favorites_archive/static/styles.css tests/test_web.py
git commit -m "feat: add multi-view archive shell"
```

### Task 5: Add Hash Routing And Overview Rendering

**Files:**
- Modify: `tests/test_web.py`
- Modify: `src/local_favorites_archive/static/app.js`

- [ ] **Step 1: Write failing JavaScript contract tests**

Assert the served script contains `WORKSPACES`, `normalizeRoute`, `activateWorkspace`, a `hashchange` listener, `aria-current`, `loadOverview`, `formatBytes`, and render targets for all overview metric IDs. Also assert the old `openTagManager` and `showModal()` call for the tag dialog are absent.

- [ ] **Step 2: Run the script contract test and confirm RED**

Run: `python -m pytest tests/test_web.py -k "routing or overview_script" -v`

Expected: FAIL because routing and overview rendering are missing.

- [ ] **Step 3: Implement routing and overview rendering**

Add a route map that normalizes unknown/empty hashes to `#overview`, toggles each workspace `hidden` state, updates `aria-current`, page title, and heading focus. Load overview data with `Promise.all([api('/api/stats/overview'), api('/api/sync/status')])`; format counts with `Intl.NumberFormat('zh-CN')`, binary storage units with a small `formatBytes` helper, proportional distribution bars, and 12 semantic month bars. Avoid reloading posts when switching between non-favorites workspaces.

- [ ] **Step 4: Run tests and syntax validation**

Run: `python -m pytest tests/test_web.py -k "routing or overview_script" -v`

Run: `node --check src/local_favorites_archive/static/app.js`

Expected: both pass.

- [ ] **Step 5: Commit routing and overview rendering**

```powershell
git add src/local_favorites_archive/static/app.js tests/test_web.py
git commit -m "feat: route and render archive workspaces"
```

### Task 6: Migrate Tag Management From Dialog To Workspace

**Files:**
- Modify: `tests/test_web.py`
- Modify: `src/local_favorites_archive/static/app.js`
- Modify: `src/local_favorites_archive/static/styles.css`

- [ ] **Step 1: Add a failing tag-workspace behavior contract**

Assert that untagged post actions set `window.location.hash = '#tags'`, tag mutations refresh tags, overview data, sidebar counts, filters, and the current favorites list, and no code references `tag-dialog`, `tag-dialog-close`, or `showModal()` for tags.

- [ ] **Step 2: Run the test and confirm RED**

Run: `python -m pytest tests/test_web.py -k tag_workspace -v`

Expected: FAIL on remaining dialog behavior and incomplete refresh targets.

- [ ] **Step 3: Implement workspace-native tag management**

Remove dialog open/close handlers. Keep the existing form, row editing, color selection, usage count, save, delete confirmation, and post assignment APIs. Make `refreshAfterTagChange()` refresh `loadTags()`, `loadOverview()`, sidebar badges, and the visible favorites page. Route the empty-tag call to `#tags` and focus the tag-name field after navigation.

- [ ] **Step 4: Run tag tests and commit**

Run: `python -m pytest tests/test_web.py -k "tag or workspace" -v`

Expected: PASS.

```powershell
git add src/local_favorites_archive/static/app.js src/local_favorites_archive/static/styles.css tests/test_web.py
git commit -m "feat: move tag management into workspace"
```

### Task 7: Add Sync Failure Rendering And Back-To-Top Behavior

**Files:**
- Modify: `tests/test_web.py`
- Modify: `src/local_favorites_archive/static/app.js`
- Modify: `src/local_favorites_archive/static/styles.css`

- [ ] **Step 1: Write failing behavior contracts**

Assert that the script calls `/api/sync/failures`, renders author, media kind, error, and original link into `sync-failures`, uses an explicit empty state, listens for scroll, toggles a visibility class after `480`, and invokes `window.scrollTo({top: 0, behavior: 'smooth'})` from `back-to-top`.

- [ ] **Step 2: Run the tests and confirm RED**

Run: `python -m pytest tests/test_web.py -k "sync_failures or back_to_top" -v`

Expected: FAIL because both behaviors are missing.

- [ ] **Step 3: Implement the behaviors**

Add `loadSyncFailures()` and call it on init, refresh, and when sync finishes. Render at most the endpoint results, preserve escaped text, and link only through the explicit original-post anchor. Add passive scroll handling for the fixed button; keep it below the image-viewer layer and above normal cards, with mobile safe-area offsets.

- [ ] **Step 4: Run tests and syntax validation**

Run: `python -m pytest tests/test_web.py -k "sync_failures or back_to_top" -v`

Run: `node --check src/local_favorites_archive/static/app.js`

Expected: both pass.

- [ ] **Step 5: Commit sync and navigation behavior**

```powershell
git add src/local_favorites_archive/static/app.js src/local_favorites_archive/static/styles.css tests/test_web.py
git commit -m "feat: show sync failures and back-to-top control"
```

### Task 8: Full Verification And Browser QA

**Files:**
- Modify if defects are found: `src/local_favorites_archive/static/index.html`
- Modify if defects are found: `src/local_favorites_archive/static/styles.css`
- Modify if defects are found: `src/local_favorites_archive/static/app.js`
- Modify if regressions need coverage: `tests/test_web.py`

- [ ] **Step 1: Run the full automated suite**

Run: `python -m pytest -q`

Expected: all tests pass.

Run: `node --check src/local_favorites_archive/static/app.js`

Expected: exit code 0.

- [ ] **Step 2: Start or restart the local service**

Run the existing CLI on `127.0.0.1:8765`, first checking whether the previous process is still listening and replacing only that application process when necessary.

- [ ] **Step 3: Verify the target browser flow**

The flow under test is: `#overview` loads -> each sidebar workspace activates through hash navigation and browser history -> favorites filtering and pagination update real posts -> tag creation/editing occurs on `#tags` without a dialog -> sync progress/failure state renders on `#sync` -> scrolling reveals a working return-to-top button -> an archived image opens in the existing centered zoom/rotate viewer.

- [ ] **Step 4: Check desktop and mobile layouts**

Use Browser integration first at `1280x720` and `390x844`. Verify page identity, meaningful DOM, no framework overlay, no relevant console warnings/errors, no horizontal overflow, stable numeric alignment, readable chart labels, non-overlapping controls, and long-image centering. Exercise browser back/forward across all four hashes.

- [ ] **Step 5: Compare visual evidence with the accepted reference**

Use `view_image` on `C:/Users/Bruce/AppData/Local/Temp/codex-clipboard-1e7477d1-0df4-469b-b3a1-ff4283491b68.png` and on the latest desktop implementation screenshot. Record at least five comparisons: sidebar density, current-page hierarchy, metric layout, numeric typography, workspace separation, and mobile navigation. Fix all material discrepancies that conflict with the approved design specification.

- [ ] **Step 6: Commit any QA fixes and rerun verification**

For each browser-discovered defect, first add a failing regression test when practical, then make the smallest fix and rerun the focused test. Finish with `python -m pytest -q` and `node --check src/local_favorites_archive/static/app.js` before the final commit.


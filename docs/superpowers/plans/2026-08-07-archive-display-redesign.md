# Archive Display Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the archive display around the approved editorial library layout while preserving every existing archive, filter, tag, pagination, media, and image-viewer workflow.

**Architecture:** Keep the current server-rendered static shell and vanilla JavaScript application. Add one aggregate field to the existing sync status response, replace the page shell with semantic sidebar/hero/summary sections, bind real values through existing API calls, and implement the approved responsive presentation entirely in the existing stylesheet.

**Tech Stack:** FastAPI, SQLite, static HTML, vanilla JavaScript, CSS, pytest, Browser integration

---

## File Map

- Modify `tests/test_web.py`: specify the new aggregate field and stable redesign hooks before production changes.
- Modify `src/local_favorites_archive/web.py`: return the unique stored-author count from the existing sync status endpoint.
- Modify `src/local_favorites_archive/static/index.html`: provide the semantic sidebar, hero, real-data summary, filter, progress, collection, pagination, and existing dialog structure.
- Modify `src/local_favorites_archive/static/app.js`: bind real summary data, active navigation, and refreshed collection counts without changing archive workflows.
- Modify `src/local_favorites_archive/static/styles.css`: implement the approved desktop and mobile visual system while retaining dialog and long-image behavior.

### Task 1: Unique Author Statistic

**Files:**
- Modify: `tests/test_web.py`
- Modify: `src/local_favorites_archive/web.py`

- [ ] **Step 1: Write the failing API test**

Extend `test_status_reports_archive_path_and_persistent_counts` with a second post from the same author and a third post from another author, then assert the distinct count:

```python
assert status["posts_total"] == 3
assert status["authors_total"] == 2
```

Use the existing ingest endpoint so the test covers real persistence and status serialization.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_web.py::test_status_reports_archive_path_and_persistent_counts -q
```

Expected: FAIL because `authors_total` is missing from the status JSON.

- [ ] **Step 3: Add the minimal aggregate query**

Inside `sync_status`, query non-empty handles and include the result:

```python
authors_total = db.execute(
    "SELECT COUNT(DISTINCT author_handle) FROM posts WHERE author_handle <> ''"
).fetchone()[0]
```

Return it next to `posts_total`:

```python
"authors_total": authors_total,
```

- [ ] **Step 4: Verify GREEN**

Run the same focused test. Expected: PASS.

- [ ] **Step 5: Commit the aggregate behavior**

```powershell
git add tests/test_web.py src/local_favorites_archive/web.py
git commit -m "feat: report archived author count"
```

### Task 2: Semantic Page Shell

**Files:**
- Modify: `tests/test_web.py`
- Modify: `src/local_favorites_archive/static/index.html`

- [ ] **Step 1: Write failing page-structure assertions**

Add a focused test that requires the approved copy and stable hooks:

```python
def test_ui_uses_approved_archive_library_shell(tmp_path):
    html = TestClient(create_app(Settings(archive_root=tmp_path))).get("/").text

    assert 'class="app-sidebar"' in html
    assert 'id="collection"' in html
    assert 'id="sync-section"' in html
    assert 'id="hero-posts-total"' in html
    assert 'id="hero-authors-total"' in html
    assert 'id="hero-sync-state"' in html
    assert "存下你的喜爱" in html
    assert "喜欢过的内容，值得被找回。" in html
    assert "把 X 上稍纵即逝的喜欢" in html
```

- [ ] **Step 2: Run the focused test and verify RED**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_web.py::test_ui_uses_approved_archive_library_shell -q
```

Expected: FAIL because the new shell and copy are absent.

- [ ] **Step 3: Replace the outer document structure**

Keep every existing control ID used by `app.js`, but organize the page as:

```html
<div class="app-shell">
  <aside class="app-sidebar">
    <a class="brand" href="#collection" aria-label="存下你的喜爱，返回我的收藏">
      <span class="brand-mark" aria-hidden="true">✦</span>
      <span><strong>存下你的喜爱</strong><small>LOCAL FAVORITES</small></span>
    </a>
    <nav class="side-nav" aria-label="主要导航">
      <a class="side-nav-item is-active" href="#collection">我的收藏</a>
      <a class="side-nav-item" href="#sync-section">同步状态</a>
      <button id="tag-manager-open" class="side-nav-item" type="button">标签管理</button>
    </nav>
    <div class="library-status"><span aria-hidden="true"></span>本地资料库</div>
  </aside>
  <main class="main-content">
    <header class="hero">
      <div class="hero-copy">
        <h1>喜欢过的内容，值得被找回。</h1>
        <p>把 X 上稍纵即逝的喜欢，沉淀为可搜索、可筛选、可长期保存的本地内容库。</p>
      </div>
      <button id="refresh" type="button">刷新归档</button>
    </header>
    <section class="summary-strip" aria-label="归档概览">
      <div><span>已归档内容</span><strong id="hero-posts-total">0</strong></div>
      <div><span>收藏的作者</span><strong id="hero-authors-total">0</strong></div>
      <div><span>同步状态</span><strong id="hero-sync-state">读取中</strong></div>
    </section>
  </main>
</div>
```

Place the existing filter form immediately after the summary strip. Place the progress panel and `#status` inside `#sync-section`. Place the collection heading, pagination, and `#posts` inside `#collection`. Keep the tag and image dialogs after `.app-shell`. Preserve `#q`, `#author`, `#media`, `#tag-filter`, `#from`, `#to`, `#sort`, `#direction`, `#page-size`, `#page-number`, and all viewer IDs exactly.

- [ ] **Step 4: Verify GREEN and existing shell coverage**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_web.py::test_ui_uses_approved_archive_library_shell tests/test_web.py::test_local_api_and_ui tests/test_web.py::test_date_filters_have_visible_distinct_labels tests/test_web.py::test_ui_has_local_image_viewer_controls -q
```

Expected: PASS.

- [ ] **Step 5: Commit the semantic shell**

```powershell
git add tests/test_web.py src/local_favorites_archive/static/index.html
git commit -m "feat: add editorial archive page shell"
```

### Task 3: Real Summary Data And Navigation Behavior

**Files:**
- Modify: `tests/test_web.py`
- Modify: `src/local_favorites_archive/static/app.js`

- [ ] **Step 1: Write failing script-contract assertions**

Add:

```python
def test_ui_script_binds_real_summary_statistics(tmp_path):
    script = TestClient(create_app(Settings(archive_root=tmp_path))).get("/assets/app.js").text

    assert "hero-posts-total" in script
    assert "hero-authors-total" in script
    assert "hero-sync-state" in script
    assert "syncStateLabel" in script
```

- [ ] **Step 2: Run the focused test and verify RED**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_web.py::test_ui_script_binds_real_summary_statistics -q
```

Expected: FAIL because summary bindings are absent.

- [ ] **Step 3: Bind API values and readable sync labels**

Add one mapping helper:

```javascript
function syncStateLabel(state) {
  return ({
    idle: '等待同步',
    starting: '正在连接',
    collecting: '正在采集',
    downloading: '正在下载媒体',
    finished: '同步完成',
    error: '同步失败',
  })[state] || '状态未知';
}
```

In `load`, update `hero-posts-total` from the filtered count. In `poll`, update all overview values from the status response:

```javascript
$('hero-posts-total').textContent = state.posts_total || 0;
$('hero-authors-total').textContent = state.authors_total || 0;
$('hero-sync-state').textContent = syncStateLabel(state.state);
```

Keep refresh behavior as `loadTags()`, `load()`, and `poll()`. Use native anchor navigation for collection and sync links; the tag item continues to open the existing dialog.

- [ ] **Step 4: Verify GREEN and JavaScript syntax**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_web.py::test_ui_script_binds_real_summary_statistics -q
node --check src/local_favorites_archive/static/app.js
```

Expected: test PASS and Node exit code 0.

- [ ] **Step 5: Commit dynamic bindings**

```powershell
git add tests/test_web.py src/local_favorites_archive/static/app.js
git commit -m "feat: bind archive overview statistics"
```

### Task 4: Approved Visual System And Responsive Layout

**Files:**
- Modify: `src/local_favorites_archive/static/styles.css`

- [ ] **Step 1: Record the visual acceptance constraints**

Before editing, use the supplied reference image and the approved spec as the acceptance oracle. The required observations are: pale-green sidebar, white main canvas, visible Chinese brand and English sub-label, serif editorial hero, three-column summary strip, restrained green actions, compact filter toolbar, two-column real-content card grid, and mobile top-header conversion.

- [ ] **Step 2: Implement design tokens and shell geometry**

Define explicit tokens and stable shell dimensions:

```css
:root {
  --ink: #17231f;
  --muted: #6b7772;
  --line: #dfe6e2;
  --paper: #ffffff;
  --sidebar: #edf5f0;
  --green: #176b53;
  --green-soft: #deeee5;
  --danger: #a12626;
  font-family: Inter, "Segoe UI", "Microsoft YaHei", sans-serif;
}

.app-shell { min-height: 100vh; display: grid; grid-template-columns: 268px minmax(0, 1fr); }
.app-sidebar { position: sticky; top: 0; height: 100vh; }
.main-content { width: min(100%, 1440px); padding: 48px clamp(24px, 5vw, 72px); }
```

Use `letter-spacing: 0` everywhere except the approved uppercase `LOCAL FAVORITES` label, where modest positive tracking is intentional.

- [ ] **Step 3: Style the content hierarchy and controls**

Implement:

- 6-8 px radii for controls and cards.
- A 44-56 px serif hero heading, without viewport-scaled font sizing.
- An unframed three-cell summary strip separated by 1 px rules.
- A compact filter grid with clear start/end date labels.
- A low-emphasis synchronization band with the existing two progress bars and archive path.
- `#posts` as `grid-template-columns: repeat(2, minmax(0, 1fr))` on wide screens and one column below tablet width.
- Natural card heights, media constrained by responsive width, and no nested-card styling.
- Visible `:focus-visible` states and usable disabled states.

- [ ] **Step 4: Implement responsive behavior**

At tablet width, reduce the filter grid and card list to one column. At mobile width:

```css
@media (max-width: 720px) {
  .app-shell { display: block; }
  .app-sidebar { position: sticky; height: auto; display: grid; }
  .side-nav { display: flex; overflow-x: auto; }
  .library-status { display: none; }
  .main-content { padding: 28px 16px; }
  .hero { align-items: flex-start; flex-direction: column; }
  .summary-strip { grid-template-columns: 1fr; }
  #posts { grid-template-columns: 1fr; }
}
```

Preserve the existing absolute-center image-viewer rules and responsive viewer controls.

- [ ] **Step 5: Run automated regression checks**

```powershell
.venv\Scripts\python.exe -m pytest -q
node --check src/local_favorites_archive/static/app.js
```

Expected: all tests PASS and Node exit code 0.

- [ ] **Step 6: Commit the presentation layer**

```powershell
git add src/local_favorites_archive/static/styles.css
git commit -m "feat: style archive as a personal library"
```

### Task 5: Live Browser Fidelity And Interaction QA

**Files:**
- Verify: `src/local_favorites_archive/static/index.html`
- Verify: `src/local_favorites_archive/static/styles.css`
- Verify: `src/local_favorites_archive/static/app.js`
- Verify: `tests/test_web.py`

- [ ] **Step 1: Restart the loopback-only service**

Stop only the process listening on port 8765, then launch the project command hidden and confirm it listens on `127.0.0.1:8765`.

- [ ] **Step 2: Run the Browser verification loop**

The flow under test is: archive loads -> real summary and post cards render -> filter changes results -> tag manager opens -> pagination remains usable -> an archived image opens in the existing viewer.

Using the Browser integration, verify:

- URL and page title.
- Meaningful DOM content with the approved copy.
- No framework overlay.
- No relevant console warnings or errors.
- Desktop screenshot at the reference width when practical.
- Mobile screenshot around 390 x 844.
- No horizontal overflow, clipping, overlap, or stale loading text.
- Filter submission changes rendered results.
- Tag manager opens and closes.
- Sidebar anchors reach the correct sections.
- Image viewer opens, centers a long image, rotates, zooms, and closes.

- [ ] **Step 3: Compare reference and implementation directly**

Use `view_image` on both the supplied reference and latest desktop/mobile screenshots. Record and repair mismatches across at least: brand copy, sidebar structure, hero hierarchy, summary strip, palette, filter density, card columns, media framing, and mobile navigation.

- [ ] **Step 4: Re-run full verification after visual repairs**

```powershell
.venv\Scripts\python.exe -m pytest -q
node --check src/local_favorites_archive/static/app.js
git diff --check
```

Expected: all tests PASS, Node exit code 0, and no whitespace errors.

- [ ] **Step 5: Commit final QA repairs**

```powershell
git add tests/test_web.py src/local_favorites_archive/web.py src/local_favorites_archive/static/index.html src/local_favorites_archive/static/app.js src/local_favorites_archive/static/styles.css
git commit -m "fix: polish archive redesign across viewports"
```

- [ ] **Step 6: Verify preserved archive data**

Read the live SQLite database and filesystem without modifying them. Confirm 240 posts, 364 media records, 364 downloaded media records, 240 raw JSON files, and 364 media files. Confirm `/` and `/api/sync/status` both return HTTP 200.

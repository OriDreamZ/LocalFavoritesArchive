# Dual Pagination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add synchronized full pagination controls above and below the favorites list.

**Architecture:** Keep `currentPage` and `totalPages` as the only pagination state. Mark both pagination blocks with shared `data-page-*` hooks, update them together from `updatePageControls`, and bind their actions through the same setup function. Preserve the existing bottom IDs for compatibility while giving the top controls unique markup without duplicate IDs.

**Tech Stack:** Static HTML, CSS, vanilla JavaScript, pytest, Browser integration.

---

### Task 1: Add Synchronized Pagination Controls

**Files:**
- Modify: `tests/test_web.py`
- Modify: `src/local_favorites_archive/static/index.html`
- Modify: `src/local_favorites_archive/static/app.js`
- Modify: `src/local_favorites_archive/static/styles.css`

- [ ] **Step 1: Write the failing contract test**

Add:

```python
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
```

- [ ] **Step 2: Run the test and confirm RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_web.py::test_favorites_has_synchronized_top_and_bottom_pagination -v`

Expected: FAIL because the top pagination and shared hooks do not exist.

- [ ] **Step 3: Add the top pagination and shared hooks**

Insert a complete `<nav class="pagination pagination-top" aria-label="顶部推文分页">` before `#posts`. Give both top and bottom controls these hooks:

```html
<button data-page-action="prev" ...>‹</button>
<span data-page-info class="numeric">第 1 / 1 页 · 共 0 条</span>
<button data-page-action="next" ...>›</button>
<input data-page-number type="number" ...>
<button data-page-action="jump" ...>跳转</button>
```

Keep the existing bottom IDs and do not add IDs to the top block.

- [ ] **Step 4: Synchronize and bind both components**

Update `updatePageControls(total)` to iterate over all shared hooks:

```javascript
document.querySelectorAll('[data-page-info]').forEach(node => { node.textContent = label; });
document.querySelectorAll('[data-page-action="prev"]').forEach(node => { node.disabled = currentPage <= 1; });
document.querySelectorAll('[data-page-action="next"]').forEach(node => { node.disabled = currentPage >= totalPages; });
document.querySelectorAll('[data-page-number]').forEach(node => { node.max = totalPages; node.value = currentPage; });
```

Implement `setupPagination(pagination)` to bind previous, next, jump, and Enter actions inside each block. Change `jumpToPage(input)` to read the triggering block's input. After page changes call:

```javascript
function scrollToCollectionStart() {
  $('collection').scrollIntoView({behavior: 'smooth', block: 'start'});
}
```

- [ ] **Step 5: Style both placements responsively**

Add `.pagination-top { margin: 0 0 18px; }`. Replace mobile ID-specific grid rules with `[data-page-info]` and `[data-page-action="jump"]` so both blocks use the same narrow-screen layout.

- [ ] **Step 6: Run focused and full tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_web.py::test_favorites_has_synchronized_top_and_bottom_pagination -v`

Expected: PASS.

Run: `.\.venv\Scripts\python.exe -m pytest -q`

Expected: all tests pass.

Run: `node --check src/local_favorites_archive/static/app.js`

Expected: exit code 0.

### Task 2: Browser Verification

**Files:**
- Modify only if a regression is found: `src/local_favorites_archive/static/index.html`
- Modify only if a regression is found: `src/local_favorites_archive/static/app.js`
- Modify only if a regression is found: `src/local_favorites_archive/static/styles.css`
- Modify only if coverage is needed: `tests/test_web.py`

- [ ] **Step 1: Reload the running local app**

Open `http://127.0.0.1:8765/#favorites` and reload after the static file changes.

- [ ] **Step 2: Verify synchronization on desktop**

At `1280x720`, click the top next-page button and confirm both page labels show page 2. Use the bottom page input to jump to page 3 and confirm both inputs and labels show page 3. Confirm the page scrolls to the collection start after each action.

- [ ] **Step 3: Verify mobile layout**

At `390x844`, confirm both pagination blocks fit without horizontal overflow, buttons remain usable, and the top control appears before the first post.

- [ ] **Step 4: Commit**

```powershell
git add src/local_favorites_archive/static/index.html src/local_favorites_archive/static/app.js src/local_favorites_archive/static/styles.css tests/test_web.py docs/superpowers/plans/2026-08-07-dual-pagination.md
git commit -m "feat: add synchronized dual pagination"
```

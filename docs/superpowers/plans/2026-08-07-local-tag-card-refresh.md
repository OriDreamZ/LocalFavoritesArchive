# Local Tag Card Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update a post's local tags without rebuilding the favorites page, so the page number and exact viewport position remain unchanged.

**Architecture:** A dedicated `refreshPostTags()` function will reload global tag metadata and the operated post detail, then re-render only that card's tag region. Removing the active filter tag is the sole post-card exception and will use the existing full list refresh because the post must leave the result set.

**Tech Stack:** FastAPI static assets, vanilla JavaScript, pytest, Chrome-compatible Browser QA.

---

### Task 1: Replace Full Favorites Reload With Local Card Refresh

**Files:**
- Modify: `tests/test_web.py`
- Modify: `src/local_favorites_archive/static/app.js`

- [ ] **Step 1: Replace the scroll-compensation contract with a local-refresh contract**

Update `test_tag_refresh_preserves_current_page` in `tests/test_web.py` so it extracts and verifies a dedicated local card refresh function:

```python
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
```

This contract requires normal post-card tag changes to avoid `load()` while preserving the necessary active-filter exception.

- [ ] **Step 2: Run the focused test and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_web.py::test_tag_refresh_preserves_current_page_and_position -v
```

Expected: FAIL because `refreshPostTags()` does not exist.

- [ ] **Step 3: Simplify the full refresh helper for tag management**

Replace the anchor-based `refreshAfterTagChange()` with the full refresh behavior still needed by the dedicated tag workspace:

```javascript
async function refreshAfterTagChange() {
  await loadTags();
  await Promise.all([loadOverview(), load()]);
}
```

This function must not assign `currentPage = 1`; existing `load()` page clamping remains responsible for invalid pages.

- [ ] **Step 4: Add the local card refresh helper**

Add immediately after `refreshAfterTagChange()`:

```javascript
async function refreshPostTags(article, removedTagId = '') {
  if (removedTagId && $('tag-filter').value === String(removedTagId)) {
    await refreshAfterTagChange();
    return;
  }
  await loadTags();
  const [detail] = await Promise.all([
    api('/api/posts/' + encodeURIComponent(article.dataset.id)),
    loadOverview(),
  ]);
  renderPostTags(article.querySelector('.post-tags'), detail);
}
```

The card and its media/text DOM remain mounted, so neither grid geometry nor scroll position changes during normal tag operations.

- [ ] **Step 5: Route post-card handlers through the local helper**

Replace the two calls inside the `#posts` click handler:

```javascript
if (remove) {
  await api(`/api/posts/${article.dataset.id}/tags/${remove.dataset.tagId}`, {method: 'DELETE'});
  await refreshPostTags(article, remove.dataset.tagId);
  return;
}

const add = event.target.closest('.tag-add');
if (add) {
  const tagId = add.closest('.tag-assignment').querySelector('.tag-select').value;
  if (!tagId) return;
  await api(`/api/posts/${article.dataset.id}/tags/${tagId}`, {method: 'POST'});
  await refreshPostTags(article);
}
```

Leave tag creation, rename, and deletion handlers in the tag management workspace calling `refreshAfterTagChange()`.

- [ ] **Step 6: Run focused and full frontend tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_web.py::test_tag_refresh_preserves_current_page_and_position -q
.\.venv\Scripts\python.exe -m pytest tests/test_web.py -q
node --check src/local_favorites_archive/static/app.js
git diff --check
```

Expected: the focused regression passes, all web tests pass, JavaScript syntax is valid, and the diff has no whitespace errors.

- [ ] **Step 7: Commit the local refresh implementation**

```powershell
git add src/local_favorites_archive/static/app.js tests/test_web.py
git commit -m "fix: update post tags without reloading page"
```

### Task 2: Verify Exact Position And Activate The Updated Script

**Files:**
- Modify only if Browser QA finds a regression: `src/local_favorites_archive/static/app.js`, `tests/test_web.py`

- [ ] **Step 1: Run the complete automated suite**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --check extension/background.js
node --check extension/popup.js
node --check src/local_favorites_archive/static/app.js
git diff --check
```

Expected: all tests and syntax checks pass.

- [ ] **Step 2: Start an isolated QA service**

Create a uniquely named archive directory under the Windows temporary directory, confirm it is outside the repository, confirm port `8766` is free, and start the existing service at `http://127.0.0.1:8766`. Seed at least 40 text posts and one ASCII-named test tag so page two contains multiple rows without modifying the user's archive.

- [ ] **Step 3: Verify normal tag addition does not move the page or card**

The flow under test is: `#favorites` -> page two -> scroll a middle card into view -> add a tag -> the same card and page remain at the same coordinates.

Using the in-app Browser plugin:

1. Record the top pagination label, target card `data-id`, card `getBoundingClientRect().top`, and `window.scrollY` immediately before clicking Add.
2. Add the tag and wait for `.tag-chip` inside the same card.
3. Record the same values after completion.
4. Require identical page labels, card IDs, card top coordinates, and scroll positions.
5. Confirm the DOM snapshot is meaningful, no framework overlay is present, and console error/warning logs are empty.
6. Capture a viewport screenshot in the Windows temporary directory.

- [ ] **Step 4: Verify the active-filter removal exception**

Assign the test tag to a post, select that tag in `#tag-filter`, and remove it from the visible post. Confirm the card leaves the filtered result set and the summary/pagination update, demonstrating that membership-changing removals still use the full list refresh.

- [ ] **Step 5: Clean up the isolated environment**

Finalize the Browser tab, stop only the process listening on `8766`, validate the exact temporary archive path, delete only that directory, and confirm the port is closed and directory absent.

- [ ] **Step 6: Run fresh final verification and inspect the main service**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --check extension/background.js
node --check extension/popup.js
node --check src/local_favorites_archive/static/app.js
git diff --check
git status --short --branch
```

Read `http://127.0.0.1:8765/api/sync/status`. Restart the main service only when its state is `idle` or `finished`; otherwise leave it running. Verify `/assets/app.js` contains `refreshPostTags` and tell the user to perform `Ctrl+F5` so an already-open page executes the updated script.

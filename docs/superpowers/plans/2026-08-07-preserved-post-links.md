# Preserved Post Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve ordinary links in newly synchronized post text as safe clickable links while removing media placeholder links from normalized local content.

**Architecture:** The collector converts X URL entities into normalized display text plus structured `PostLink` records. SQLite stores those records in a non-destructive child table, and the existing post-detail response supplies them to the frontend. The browser renderer escapes all ordinary text and creates anchors only for validated HTTP(S) destinations.

**Tech Stack:** Python 3.11, dataclasses, FastAPI, SQLite, pytest, vanilla JavaScript, Browser integration.

---

### Task 1: Normalize Post Text And Extract Links

**Files:**
- Modify: `src/local_favorites_archive/models.py`
- Modify: `src/local_favorites_archive/collector.py`
- Modify: `tests/test_collector.py`

- [ ] **Step 1: Replace the URL-removal test with failing normalization tests**

Add `PostLink` expectations for ordinary and media URLs:

```python
def test_normalize_post_text_preserves_ordinary_links_and_removes_media_links():
    text, links = normalize_post_text(
        "查看 https://t.co/article https://t.co/photo",
        [{"url": "https://t.co/article", "display_url": "example.com/article", "expanded_url": "https://example.com/article"}],
        [{"url": "https://t.co/photo"}],
    )
    assert text == "查看 example.com/article"
    assert links == [PostLink(0, "example.com/article", "https://example.com/article", "https://t.co/article")]


def test_normalize_post_text_preserves_complete_url_without_entities():
    text, links = normalize_post_text("查看 https://example.com/direct", [], [])
    assert text == "查看 https://example.com/direct"
    assert links == [PostLink(0, "https://example.com/direct", "https://example.com/direct", "https://example.com/direct")]
```

Update the existing long-post test to include `note_tweet_results.result.entity_set.urls`, then assert the normalized display URL and structured link are taken from the note result. Update the media extraction test so `legacy.entities.media[0].url` appears in `full_text`, then assert it is absent from `post.text` while `post.media` remains populated.

- [ ] **Step 2: Run collector tests and confirm RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_collector.py -v`

Expected: FAIL because `PostLink` and `normalize_post_text` do not exist and current code removes every URL.

- [ ] **Step 3: Add the link model**

Add to `models.py`:

```python
@dataclass
class PostLink:
    index: int
    display_url: str
    expanded_url: str
    short_url: str
```

Add `links: list[PostLink] = field(default_factory=list)` to `Post` after `media`.

- [ ] **Step 4: Implement normalized text extraction**

In `collector.py`, replace all-URL removal with:

```python
def normalize_post_text(
    text: str | None,
    url_entities: list[dict[str, Any]],
    media_entities: list[dict[str, Any]],
) -> tuple[str, list[PostLink]]:
    ...
```

Build ordered replacements from entity `url` tokens. Media replacements emit an empty string and no link. Ordinary replacements emit `display_url` with fallbacks to `expanded_url` then `url`, and produce a `PostLink`. Preserve unmatched HTTP(S) URLs as fallback links. Apply replacements by source position, then normalize horizontal whitespace and blank lines without deleting remaining URLs.

In `posts_from_x_response`, choose `note_tweet...result.entity_set.urls` when note text is used; otherwise choose `legacy.entities.urls`. Combine `legacy.entities.media` and `legacy.extended_entities.media` for media token removal. Pass the normalized text and links into `Post`.

- [ ] **Step 5: Run collector tests and confirm GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_collector.py -v`

Expected: PASS.

- [ ] **Step 6: Commit collector behavior**

```powershell
git add src/local_favorites_archive/models.py src/local_favorites_archive/collector.py tests/test_collector.py
git commit -m "feat: preserve ordinary post links"
```

### Task 2: Persist Structured Links In SQLite

**Files:**
- Modify: `src/local_favorites_archive/storage.py`
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Write the failing storage test**

Extend `sample_post` with an optional `links` argument and add:

```python
def test_post_links_are_replaced_and_returned_in_order(tmp_path):
    store = ArchiveStore(tmp_path)
    first = [PostLink(0, "one.example", "https://one.example", "https://t.co/one")]
    second = [
        PostLink(0, "two.example", "https://two.example", "https://t.co/two"),
        PostLink(1, "three.example", "https://three.example", "https://t.co/three"),
    ]
    store.upsert_post(sample_post(post_id="42", links=first))
    store.upsert_post(sample_post(post_id="42", links=second))
    assert store.get_post("42")["links"] == [
        {"link_index": 0, "display_url": "two.example", "expanded_url": "https://two.example", "short_url": "https://t.co/two"},
        {"link_index": 1, "display_url": "three.example", "expanded_url": "https://three.example", "short_url": "https://t.co/three"},
    ]
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_storage.py::test_post_links_are_replaced_and_returned_in_order -v`

Expected: FAIL because `post_links` is not stored or returned.

- [ ] **Step 3: Create and populate the child table**

Add the `CREATE TABLE IF NOT EXISTS post_links` definition from the approved design to `_init_db()`. In `upsert_post`, delete rows for the current post ID and insert each `PostLink` as `(post_id, index, display_url, expanded_url, short_url)` within the existing transaction.

- [ ] **Step 4: Return links from post details**

In `get_post`, add:

```python
data["links"] = [dict(link) for link in db.execute(
    "SELECT link_index,display_url,expanded_url,short_url FROM post_links WHERE post_id=? ORDER BY link_index",
    (post_id,),
).fetchall()]
```

- [ ] **Step 5: Run storage and web tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_storage.py tests/test_web.py -q`

Expected: PASS.

- [ ] **Step 6: Commit storage support**

```powershell
git add src/local_favorites_archive/storage.py tests/test_storage.py
git commit -m "feat: persist structured post links"
```

### Task 3: Render Safe Clickable Links

**Files:**
- Modify: `src/local_favorites_archive/static/app.js`
- Modify: `src/local_favorites_archive/static/styles.css`
- Modify: `tests/test_web.py`

- [ ] **Step 1: Write the failing frontend contract test**

Add:

```python
def test_ui_renders_structured_post_links_safely(tmp_path):
    script = TestClient(create_app(Settings(archive_root=tmp_path))).get("/assets/app.js").text
    assert "function renderPostText" in script
    assert "function safeHttpUrl" in script
    assert 'class="post-link"' in script
    assert 'target="_blank"' in script
    assert 'rel="noreferrer"' in script
    assert "detail.links" in script
```

- [ ] **Step 2: Run the test and confirm RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_web.py::test_ui_renders_structured_post_links_safely -v`

Expected: FAIL because structured link rendering does not exist.

- [ ] **Step 3: Implement safe rendering**

Add `safeHttpUrl(value)` that returns only URLs parsed with an `http:` or `https:` protocol. Add `renderPostText(node, text, links)` that walks links in order, locates each `display_url` after the prior cursor, escapes surrounding text, and emits:

```html
<a class="post-link" href="..." target="_blank" rel="noreferrer">...</a>
```

If the destination is unsafe, render only escaped display text. If a link label cannot be located, skip that record without appending new content.

During each existing post-detail load, call:

```javascript
renderPostText(article.querySelector('.text'), detail.text, detail.links || []);
```

- [ ] **Step 4: Style inline links**

Add a `.post-link` rule that uses the existing green link color, permits long URL wrapping, and underlines on hover/focus without changing the post-card layout.

- [ ] **Step 5: Run frontend tests and syntax validation**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_web.py -q`

Run: `node --check src/local_favorites_archive/static/app.js`

Expected: both pass.

- [ ] **Step 6: Commit frontend rendering**

```powershell
git add src/local_favorites_archive/static/app.js src/local_favorites_archive/static/styles.css tests/test_web.py
git commit -m "feat: render clickable post links"
```

### Task 4: Full Verification And Browser QA

**Files:**
- Modify only if a regression is found: files from Tasks 1-3

- [ ] **Step 1: Run the full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`

Run: `node --check src/local_favorites_archive/static/app.js`

Expected: all tests pass and JavaScript exits 0.

- [ ] **Step 2: Start a temporary isolated archive service**

Create a temporary directory outside the repository and start the existing CLI on `127.0.0.1:8766` with `--archive <temporary-directory>`. Submit a synthetic X response containing one normal URL entity and one media entity token; do not modify the user's current archive.

- [ ] **Step 3: Verify the browser flow**

The flow under test is: open `#favorites` -> synthetic post renders -> ordinary display URL is visible and points to the expanded HTTP(S) URL -> media `t.co` token is absent from the normalized text -> page has no relevant console errors.

- [ ] **Step 4: Verify responsive layout**

At `1280x720` and `390x844`, confirm long display URLs wrap within the card with no horizontal overflow.

- [ ] **Step 5: Stop the temporary service and remove only its validated temporary archive directory**

Resolve the temporary path, confirm it is outside the repository and is the exact directory created in Step 2, stop only the process listening on port 8766, then remove that temporary directory.

- [ ] **Step 6: Final repository verification**

Run `.\.venv\Scripts\python.exe -m pytest -q`, `node --check src/local_favorites_archive/static/app.js`, `git diff --check`, and `git status --short --branch` before reporting completion.

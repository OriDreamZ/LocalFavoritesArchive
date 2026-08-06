# X Likes Local Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Python application that uses a persistent Playwright browser session to collect liked X posts and media into SQLite/files, then browse and filter the archive locally.

**Architecture:** A FastAPI process exposes a small local UI and JSON endpoints. A collector module owns Playwright session/login/scroll extraction; a storage module owns SQLite, raw JSON, deterministic media paths, and idempotent writes; a downloader module owns retries. The UI never talks to X directly and reads only local archive data.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, Playwright Python, SQLite, vanilla HTML/CSS/JS, pytest.

---

### Task 1: Project skeleton and configuration

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/local_favorites_archive/__init__.py`
- Create: `src/local_favorites_archive/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing configuration test**

```python
def test_config_defaults_are_local(tmp_path):
    from local_favorites_archive.config import Settings
    settings = Settings(archive_root=tmp_path)
    assert settings.host == "127.0.0.1"
    assert settings.archive_root == tmp_path
    assert settings.max_media_concurrency == 2
```

- [ ] **Step 2: Run `pytest tests/test_config.py -q` and verify it fails because the package does not exist.**
- [ ] **Step 3: Implement `Settings` with archive-root derived paths, host/port, scroll limits, retry limits, and media concurrency.**
- [ ] **Step 4: Add a `pyproject.toml` with runtime/test dependencies and `pytest` configuration.**
- [ ] **Step 5: Run the test and verify it passes.**

### Task 2: SQLite schema and idempotent storage

**Files:**
- Create: `src/local_favorites_archive/storage.py`
- Create: `tests/test_storage.py`

- [ ] **Step 1: Write tests for schema creation, post upsert by X ID, media upsert by `(post_id, index)`, deterministic paths, and raw JSON persistence.**
- [ ] **Step 2: Run `pytest tests/test_storage.py -q` and verify the tests fail.**
- [ ] **Step 3: Implement `ArchiveStore` with migrations for `posts`, `media`, `sync_runs`, and FTS5 `posts_fts`; use parameterized SQL and transactions.**
- [ ] **Step 4: Implement `upsert_post`, `upsert_media`, `record_sync_run`, `list_posts`, and `get_post`. Exclude engagement fields from the schema.**
- [ ] **Step 5: Run tests and verify duplicate upserts produce one row and stable files.**

### Task 3: Normalization and fixture-based extraction

**Files:**
- Create: `src/local_favorites_archive/models.py`
- Create: `src/local_favorites_archive/normalize.py`
- Create: `tests/fixtures/post-response.json`
- Create: `tests/test_normalize.py`

- [ ] **Step 1: Add a sanitized fixture containing text, author, timestamps, reply/quote metadata, image media, video variants, and unrelated engagement fields.**
- [ ] **Step 2: Write tests asserting complete visible fields are normalized, media variants choose the highest available bitrate, and engagement fields are ignored.**
- [ ] **Step 3: Run `pytest tests/test_normalize.py -q` and verify failure.**
- [ ] **Step 4: Implement typed dataclasses and a tolerant normalizer that accepts either extracted DOM records or X web response fragments.**
- [ ] **Step 5: Run tests and verify the fixture produces deterministic normalized objects.**

### Task 4: Browser session and collector adapter

**Files:**
- Create: `src/local_favorites_archive/collector.py`
- Create: `tests/test_collector_fake_page.py`

- [ ] **Step 1: Write fake-page tests for login wait, Likes URL navigation, batch extraction, consecutive-known stopping, and challenge detection.**
- [ ] **Step 2: Run the tests and verify failure.**
- [ ] **Step 3: Implement `PlaywrightCollector` using `chromium.launch_persistent_context`, a visible browser, human-scale waits, bounded scrolls, and an extraction adapter. Never request or log passwords/cookies.**
- [ ] **Step 4: Persist each normalized batch before scrolling further and emit a sync summary.**
- [ ] **Step 5: Run fake-page tests and verify interruption/resume behavior.**

### Task 5: Media downloader with resumable status

**Files:**
- Create: `src/local_favorites_archive/downloader.py`
- Create: `tests/test_downloader.py`

- [ ] **Step 1: Write tests using a local HTTP fixture for successful image/video downloads, checksum/path generation, retryable 5xx responses, and permanent failures.**
- [ ] **Step 2: Run tests and verify failure.**
- [ ] **Step 3: Implement bounded async downloads with `httpx`, atomic `.part` files, content-type/extension checks, checksum validation, and persisted status/error fields.**
- [ ] **Step 4: Run tests and verify a rerun skips already verified files and retries only failed items.**

### Task 6: Local FastAPI UI and archive queries

**Files:**
- Create: `src/local_favorites_archive/web.py`
- Create: `src/local_favorites_archive/static/index.html`
- Create: `src/local_favorites_archive/static/app.js`
- Create: `src/local_favorites_archive/static/styles.css`
- Create: `tests/test_web.py`

- [ ] **Step 1: Write API tests for search, author/date/media filters, sorting, post detail, local media serving, and original-link preservation.**
- [ ] **Step 2: Run tests and verify failure.**
- [ ] **Step 3: Implement loopback-only FastAPI routes and static UI with query controls, timeline/grid results, media previews, download-state badges, and canonical X links.**
- [ ] **Step 4: Add a sync-status endpoint and a start/stop action that delegates to a background collector job.**
- [ ] **Step 5: Run tests and verify the UI consumes only local APIs.**

### Task 7: CLI, documentation, and integration verification

**Files:**
- Create: `src/local_favorites_archive/cli.py`
- Create: `README.md`
- Create: `tests/test_integration_local.py`

- [ ] **Step 1: Write an integration test that runs a fake timeline and local media server end to end into a temporary archive.**
- [ ] **Step 2: Implement `python -m local_favorites_archive.cli init|sync|serve|retry-media` commands.**
- [ ] **Step 3: Document first-run login, archive location, stop/resume behavior, known limitations, and X terms/rate-limit caveats.**
- [ ] **Step 4: Run `pytest -q` and the CLI smoke commands against a temporary archive.**
- [ ] **Step 5: Manually verify first-login browser behavior and local offline browsing; record any X-side changes as a documented limitation.**

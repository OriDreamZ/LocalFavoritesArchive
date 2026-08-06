# Local Tags And Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove URL tokens from archived post text, add local tag management and filtering, add text-only filtering, and support direct page jumps.

**Architecture:** Extend the existing collector normalization and SQLite store while leaving capture, raw JSON, and media download unchanged. Expose small FastAPI tag endpoints and enhance the vanilla local UI with one tag dialog, per-post assignment controls, and bounded page navigation.

**Tech Stack:** Python, FastAPI, SQLite, vanilla HTML/CSS/JavaScript, pytest

---

### Task 1: Text cleanup

**Files:**
- Modify: `tests/test_collector.py`
- Modify: `src/local_favorites_archive/collector.py`

- [ ] Add a test asserting mixed text keeps words while removing every HTTP/HTTPS URL.
- [ ] Run the focused test and confirm it fails because URL cleanup is absent.
- [ ] Add `clean_post_text()` and apply it to regular and Note Tweet text.
- [ ] Run collector tests and confirm they pass.

### Task 2: Tag storage and text-only filtering

**Files:**
- Modify: `tests/test_storage.py`
- Modify: `src/local_favorites_archive/storage.py`

- [ ] Add tests for tag creation, case-insensitive uniqueness, update, assignment, removal, deletion, post detail tags, tag filtering, and media type `text`.
- [ ] Run storage tests and confirm they fail because the schema and methods are absent.
- [ ] Add non-destructive tag tables, CRUD/assignment methods, tag-aware queries, and `NOT EXISTS` text filtering.
- [ ] Run storage tests and confirm they pass.

### Task 3: API and static controls

**Files:**
- Modify: `tests/test_web.py`
- Modify: `src/local_favorites_archive/web.py`
- Modify: `src/local_favorites_archive/static/index.html`
- Modify: `src/local_favorites_archive/static/app.js`
- Modify: `src/local_favorites_archive/static/styles.css`

- [ ] Add API tests for tag CRUD/assignment and static tests for text filter, tag manager, and page jump controls.
- [ ] Run web tests and confirm they fail because the routes and controls are absent.
- [ ] Add validated tag request models and endpoints, pass `tag_id` through list/count APIs, and return clear 404/409/422 responses.
- [ ] Add the tag filter, manager dialog, per-post tag controls, text filter option, and page input/jump behavior.
- [ ] Run web tests and the full test suite.

### Task 4: Existing archive migration and browser verification

**Files:**
- Reprocess: `archive/raw/*.json`
- Preserve: `archive/archive.sqlite3`, `archive/media/`

- [ ] Stop only the local archive service process if it is running.
- [ ] Back up the SQLite database, then reparse each raw JSON record and upsert the normalized result.
- [ ] Verify post/media counts are unchanged and normalized text contains no HTTP/HTTPS URL tokens.
- [ ] Restart the service on `127.0.0.1:8765`.
- [ ] Verify tag management, tag filtering, text filtering, direct page jump, and responsive layout in Chrome at desktop and 390 x 844 widths.

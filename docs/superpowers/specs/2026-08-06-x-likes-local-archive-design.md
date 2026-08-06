# X Likes Local Archive Design

## Goal

Build a personal, local-first archive that signs in to X through a dedicated browser profile, collects every accessible post liked by the signed-in account, downloads its images and videos, and keeps the archive searchable and viewable without using X's paid API.

## Scope

The first release has two independent subsystems joined by a stable SQLite schema:

1. A collector that opens a dedicated Chromium profile, lets the user sign in manually, traverses the account's Likes timeline, normalizes posts, downloads media, and supports resumable incremental synchronization.
2. A local web application that reads only the archive and provides search, filtering, sorting, media playback, and links back to the original posts.

Bookmarks, lists, engagement counts, posting to X, multi-account support, and remote hosting are out of scope.

## Acquisition Strategy

The primary collector uses Playwright with a persistent Chromium profile. The user completes any login, verification, or challenge directly in the browser. The application never asks for or stores the X password. Collection reads the rendered Likes timeline and its browser-visible network data. A DOM fallback is kept behind the same adapter interface so changes to one extraction method do not affect storage or browsing.

The collector behaves conservatively: one active synchronization job, human-scale scrolling and waits, bounded retries, and immediate stop when X presents a verification or rate-limit screen. It does not attempt to bypass CAPTCHA, access controls, or platform restrictions.

## Archived Data

Each post record stores:

- X post ID and canonical original URL
- complete visible post text
- author ID, handle, display name, and avatar URL
- original publication time
- collection time and last-seen time
- reply, repost, or quote relationship when visible
- language and source JSON when available
- archive status and extraction version

Engagement counts are intentionally excluded. Media records store type, source URL, local relative path, preview path where applicable, MIME type, dimensions, duration when available, byte size, checksum, download status, and error details. Images and video files are downloaded locally; poster images and avatars may also be cached for offline display.

## Storage Layout

SQLite is the source of truth for normalized searchable metadata. Original response fragments are retained as JSON for recovery and reprocessing. Files use deterministic paths based on post ID and media index rather than post text:

```text
archive/
  archive.sqlite3
  raw/<post-id>.json
  media/<post-id>/<index>.<ext>
  previews/<post-id>/<index>.<ext>
  profiles/<author-id>.<ext>
  browser-profile/
  logs/
```

Database writes and media downloads are idempotent. A post can be discovered multiple times without duplicate rows or files. Failed downloads remain queued with their last error and can be retried later.

## Synchronization Flow

1. Launch Chromium with the archive's persistent browser profile.
2. Wait for the user to finish login when authentication is absent.
3. Open the signed-in account's Likes timeline.
4. Extract batches of post data and persist normalized rows plus raw JSON.
5. Queue media downloads independently of timeline scrolling.
6. Stop after reaching a configurable number of consecutive already-known posts, the end of the accessible timeline, a user stop request, or a platform challenge.
7. Download queued media with bounded concurrency and retry transient failures.
8. Record a synchronization summary including new, updated, skipped, failed, and downloaded counts.

The first run performs a historical backfill as far as X makes content accessible. Later runs are incremental. The application must not claim that inaccessible, deleted, unliked, withheld, or platform-truncated content has been archived.

## Local Browser

The local UI is served only on loopback by default. It supports full-text search, author filtering, date ranges, media type, archive/download state, and sorting by publication time, collection time, or author. A timeline view shows text and media; a compact table/grid supports fast scanning. Each post offers an explicit link to its canonical X URL. Video and images are served from local files when available.

## Failure Handling

- Authentication and verification screens pause collection and leave the browser visible for the user.
- Extractor shape changes fail the affected batch with diagnostic raw data rather than writing partial records.
- Media HTTP failures retain the original URL and retry metadata.
- Interrupted runs resume from database state; no destructive cleanup is automatic.
- Missing local files are shown as unavailable while preserving metadata and original links.
- All filesystem paths are relative to an explicitly configured archive root.

## Security And Privacy

The browser profile, database, raw responses, and media may contain sensitive personal data and remain local. The server binds to `127.0.0.1`. Logs exclude cookies, authorization headers, and full browser storage values. Archive export and backup are explicit user actions. The project documents that browser automation and non-official access can be affected by X's terms and interface changes.

## Verification

Unit tests cover normalization, idempotent persistence, deterministic paths, filtering, and retry state transitions. Fixture-based extractor tests use saved, sanitized network/DOM samples. Integration tests use a fake timeline page and local media server so automated tests do not depend on or send traffic to X. A manual smoke test verifies first-login behavior against the user's account.

## Acceptance Criteria

- A user can launch synchronization, manually sign in once, and reuse the dedicated profile later.
- Every accessible collected post retains complete visible text, author, publication time, original URL, and raw source data.
- Images and videos are stored as local files with resumable failure tracking.
- Re-running synchronization does not duplicate posts or media.
- The local UI can search, filter, sort, view media offline, and open the original X post.
- No paid X API is required and no credential is requested by the application.

# Deduplicated Sync And Post Deletion Design

## Goal

Use the existing X post ID primary key to stop collection after a configurable suffix of already archived posts, prevent downloaded media from being downloaded again, and let users permanently delete one or more selected local posts with all owned files and relationships.

## Existing Guarantees

- `posts.post_id` is the SQLite primary key.
- `ArchiveStore.upsert_post()` returns `True` only when a post ID did not already exist.
- Media rows use `(post_id, media_index)` as their primary key.
- Media UPSERT does not overwrite an existing `downloaded` status.
- `MediaDownloader` excludes rows whose status is `downloaded`.

The implementation will add regression coverage for these guarantees instead of replacing them with a second deduplication mechanism.

## Configurable Stop Rule

The archive stores a non-negative integer setting named `stop_after_existing` in SQLite. Its default is `50`. A value of `0` disables the rule and lets collection continue until manual stop or the existing end-of-page detector fires.

The sync center exposes the setting as a numeric input with a minimum of zero and a save command. The value is persistent across service and browser restarts. The local service is the source of truth; the Chrome extension does not keep a separate configurable copy.

At ingest start, the service initializes these run-scoped fields:

- `existing_streak = 0`
- `stop_requested = false`
- the persisted `stop_after_existing` value

For every successfully parsed post in response order, the service calls `upsert_post()`:

- A newly inserted post resets `existing_streak` to zero.
- An already present post increments `existing_streak` by one.

The streak carries across X response batches. The service evaluates the stop rule after processing the complete response so that no post already delivered in that response is discarded. It requests a stop when the final consecutive suffix reaches the configured threshold. If a later post in the same response is new, the final streak is zero and no stop is requested.

The ingest response adds:

```json
{
  "discovered": 20,
  "new": 2,
  "existing_streak": 18,
  "stop_after_existing": 50,
  "stop_requested": false
}
```

When `stop_requested` is true, the extension calls its existing `finish()` path with a threshold-specific message. `finish()` remains idempotent so simultaneous completed network responses cannot detach the debugger or finish ingestion more than once. Manual stop and end-of-page stop continue to use the same media-download finalization path.

The sync status endpoint exposes `existing_streak`, `stop_after_existing`, and `stop_requested`. The sync center shows the configured limit and current streak while collecting, and reports when the threshold caused collection to stop.

## Settings Storage And API

SQLite gains a non-destructive key-value table:

```sql
CREATE TABLE IF NOT EXISTS archive_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
```

ArchiveStore provides typed methods for reading and updating `stop_after_existing`. Invalid, negative, non-integer, or excessively large values are rejected. The maximum accepted value is `100000` to prevent accidental unusable input while remaining effectively unrestricted for normal archives.

The web API provides:

- `GET /api/settings` returning `{ "stop_after_existing": 50 }`
- `PATCH /api/settings` accepting `{ "stop_after_existing": 0 }`

The patch response returns the persisted normalized value.

## No Duplicate Downloads

All collection modes continue through the same storage and downloader path. A repeated post updates normalized metadata and last-seen time without creating a second post row. Existing media rows retain their status, local path, byte size, and checksum. Media already marked `downloaded` remains excluded from downloader queries.

The feature does not interpret failed or queued media as successfully saved. Those rows remain eligible for the existing retry behavior. This distinction prevents a failed partial download from being permanently skipped.

## Permanent Post Deletion

Deletion is limited to explicitly selected posts. The UI supports selecting individual cards and selecting or clearing all posts on the current page. It does not provide a command that deletes every result matching the active filters.

One endpoint handles both single and multiple deletion:

```http
DELETE /api/posts
Content-Type: application/json

{"post_ids":["123","456"]}
```

The request accepts 1 to 200 distinct, non-empty IDs. Unknown IDs are ignored and reported separately, making retries idempotent. The response is:

```json
{
  "deleted": ["123"],
  "not_found": ["456"],
  "file_cleanup_errors": []
}
```

For each existing ID, `ArchiveStore.delete_posts()` first records the owned raw JSON and media paths. In one SQLite transaction it removes:

- media rows
- structured post links
- tag assignments
- the FTS row
- the post row

After the transaction commits, it removes the exact raw JSON file and the exact per-post media directory. Paths are resolved and verified to remain under the configured archive root before removal. A file cleanup failure does not roll back the already committed database deletion; it is returned in `file_cleanup_errors` so the UI can report that local orphan cleanup needs attention. No unrelated file or shared tag definition is deleted.

## Favorites UI

Each rendered post card receives a selection checkbox with an accessible label containing the author and post ID. The collection heading gains:

- a select-current-page checkbox
- a selected-count label
- a delete-selected command that is disabled when nothing is selected

Selection is scoped to the currently loaded page and is cleared after filtering, sorting, changing page size, navigating pages, refreshing, or completing deletion. Before deletion, the browser confirmation states the exact number of selected posts and that post text, original JSON, tags, images, and videos will be permanently removed.

After a successful deletion the UI reloads posts, counts, overview statistics, tag counts, sync failures, and sync status. Existing pagination clamping moves the user to the preceding valid page when the last item on a page is deleted. If any file cleanup error is returned, the deletion result remains successful but a visible status message reports the cleanup warning.

## Failure Handling

- Setting validation errors return HTTP 422 without changing the persisted value.
- An empty deletion request returns HTTP 422.
- Database deletion failure rolls back the transaction and returns HTTP 500 without removing files.
- File cleanup errors are isolated per post and included in the successful response.
- Extension stop finalization is guarded against duplicate calls.
- Ingest errors do not increment the existing streak for unparsed or unsaved items.

## Testing

Automated tests cover:

- post ID primary-key deduplication
- downloaded media status surviving repeated post UPSERT
- default and persisted threshold settings
- consecutive existing counts resetting on a new post
- streaks carrying across response batches
- threshold zero never requesting a stop
- extension response handling and idempotent threshold finish
- deletion of one and multiple posts
- deletion of media, links, tag assignments, FTS rows, raw JSON, and media directories
- idempotent reporting of unknown IDs
- settings controls, current-page selection, permanent confirmation, and UI refresh behavior

Browser QA uses an isolated archive. It verifies threshold setting persistence, a synthetic repeated-post sequence causing extension-compatible stop output, single deletion, multi-selection deletion, pagination clamping, and responsive selection controls at desktop and mobile sizes. The user's existing archive is not used for destructive QA.

# Local Tags And Navigation Design

## Goal

Improve the existing local archive without changing its Chrome capture path or deleting any archived data. Saved post text must omit URL tokens, while canonical post links, media source links, and raw JSON remain available in their dedicated fields.

## Text Normalization

The collector removes HTTP and HTTPS URL tokens from normalized post text, then collapses leftover horizontal whitespace and excess blank lines. This applies to both regular and Note Tweet text. Existing `archive/raw/*.json` files are reprocessed through the same parser so the database and full-text index are updated consistently. Raw JSON is never rewritten during this migration.

## Tags

Tags are local-only metadata stored in `tags` and `post_tags` tables. A tag has a case-insensitively unique name, a color, and a creation timestamp. Users can create, rename, recolor, and delete tags in a separate management dialog. Deleting a tag removes only its assignments. Each post can receive or lose tags from its card, and the archive can be filtered by one tag at a time.

## Filtering And Pagination

The media filter gains a `text` value meaning posts for which no media row exists. Image and video filtering keep their current downloaded-media behavior. Pagination retains previous and next controls and adds a bounded numeric page input plus a jump button. Filter, sort, and page-size changes reset to page 1; page input is clamped to the available range.

## API And Compatibility

Existing post APIs accept an optional `tag_id`. Tag CRUD uses `/api/tags`, and assignment uses `/api/posts/{post_id}/tags/{tag_id}`. Database tables are created with non-destructive `CREATE TABLE IF NOT EXISTS` migrations. Post details include assigned tags; existing sync, media, and raw files remain intact.

## Verification

Unit tests cover URL removal, tag CRUD/assignment/filtering, text-only filtering, and required page-jump controls. Full tests run before archive reprocessing. After migration, the service is restarted and the local UI is checked at desktop and mobile widths.

# Local Favorites Multi-View Dashboard Design

## Goal

Evolve the archive from one long page into four distinct workspaces while preserving the existing local-only acquisition, storage, filtering, tagging, media, pagination, and image-viewer behavior. The visual direction follows the supplied operational dashboard reference: a dark persistent sidebar, quiet work surfaces, compact statistics, and clear current-page identity.

## Navigation Model

The application remains a single static HTML application, but uses URL hash routing so each workspace has its own stable address:

- `#overview`: 总览
- `#favorites`: 我的收藏
- `#sync`: 同步中心
- `#tags`: 标签管理

Only one workspace is visible at a time. Sidebar links update the hash, active state, page title, and visible workspace. Browser back/forward navigation restores the corresponding workspace. An unknown or empty hash redirects to `#overview`.

The sidebar remains persistent on desktop and becomes a compact horizontal navigation header on mobile. It contains real count badges for total archived posts, current media failures, and total tags where space permits.

## Overview Workspace

The overview is a read-only operational summary. It does not contain the full filters, post cards, synchronization controls, or tag-editing forms.

### Primary Metrics

- **归档内容**: total rows in `posts`.
- **收藏作者**: distinct non-empty `author_handle` values.
- **媒体完整率**: downloaded media divided by all media records, rounded to one decimal place; zero media produces `0%`.
- **已标签内容**: distinct posts with at least one `post_tags` row.

All prominent numbers use the system sans-serif UI stack with `font-variant-numeric: tabular-nums` and `font-feature-settings: "tnum" 1, "lnum" 1`. Editorial serif fonts are not used for statistics, dates, page counts, progress counts, storage values, or percentages.

### Secondary Statistics

- Content distribution: posts containing downloaded images, posts containing downloaded videos, and posts with no media records.
- Archive coverage days: inclusive day count between the earliest and latest non-null `published_at` dates.
- Local media storage: sum of `media.byte_size`, formatted with binary units.
- Tag coverage percentage: tagged posts divided by all posts.
- Recent archive additions: 12 calendar-month buckets based on `collected_at`, including zero-value months.

### Overview Layout

- Page heading and compact current-sync summary.
- Four primary metric cards in one responsive row.
- A full-width content-distribution band using proportional bars and exact counts.
- A 12-month additions chart built with semantic HTML bars rather than a new chart dependency.
- A storage and archive-coverage detail section.

## Favorites Workspace

This workspace owns all browsing behavior:

- Search, author, media type, local tag, start date, end date, sort field, and sort direction.
- Existing Chinese empty date placeholder `年/月/日` and native date picker behavior.
- Page-size control, page navigation, page-number jump, post grid, local tag assignment, original X links, image viewer, and video playback.
- The collection heading displays filtered count, while the sidebar count remains the global archive total.

No overview statistics, synchronization progress, archive path, or tag-management form appears in this workspace.

## Sync Workspace

This workspace contains:

- Current synchronization state and explanatory status text.
- Likes collection progress and media download progress.
- Global posts, media downloaded, queued, and failed counts.
- Local archive path.
- Media failure records, each showing post ID, author, media type, error text, and original X link.
- An empty state when no failures exist.

The existing refresh action reloads local data and state; it does not impersonate the Chrome extension or start X collection. No official X API or browser-profile change is introduced.

## Tags Workspace

The existing tag dialog is removed. Tag creation, editing, color selection, usage counts, and deletion move into an always-visible workspace.

- Creation form stays at the top.
- Existing tags render as rows with color, editable name, usage count, save, and delete actions.
- Deleting a tag retains the existing confirmation and never deletes posts.
- Opening tag management from an untagged post changes the hash to `#tags` instead of opening a dialog.
- After tag changes, sidebar counts, overview metrics, filter options, and visible post tag controls refresh.

## Statistics API

Add `GET /api/stats/overview` with this response shape:

```json
{
  "posts_total": 240,
  "authors_total": 187,
  "tagged_posts": 8,
  "tag_coverage_percent": 3.3,
  "media_total": 364,
  "media_downloaded": 364,
  "media_failed": 0,
  "media_completion_percent": 100.0,
  "image_posts": 149,
  "video_posts": 91,
  "text_posts": 37,
  "archive_days": 3654,
  "storage_bytes": 2341375893,
  "monthly_additions": [
    {"month": "2025-09", "count": 0},
    {"month": "2025-10", "count": 0}
  ]
}
```

The exact example values are illustrative; the endpoint returns live SQLite aggregates. The monthly list always contains 12 ordered entries ending with the current UTC calendar month.

Add `GET /api/sync/failures` returning failed media joined with post author and URL. Limit the response to 200 newest failed records ordered by post publication date and media index.

Aggregate SQL belongs in focused `ArchiveStore.overview_stats()` and `ArchiveStore.list_media_failures()` methods rather than the route function.

## Back-To-Top Control

A fixed icon button appears after the document has scrolled more than 480 pixels. It is hidden at the top, uses an accessible `返回页面顶部` label and tooltip, and scrolls smoothly to the top. It remains above cards but below modal image-viewer layers and never overlaps mobile pagination controls.

## Responsive Behavior

- Desktop: dark 240-260 px sidebar, four-column metric row, a two-column overview detail grid, and the existing two-column favorites post grid.
- Tablet: compact sidebar, two-column metric grid, one-column favorites post grid.
- Mobile: horizontal sticky navigation, single-column metric cards and charts, full-width forms, one-column posts, and a smaller back-to-top control inset from the bottom-right safe area.
- Each workspace must fit without horizontal overflow at 390 x 844 and 1280 x 720.

## Accessibility And State

- Workspaces use semantic sections with headings and `hidden` for inactive content.
- Sidebar links expose `aria-current="page"` only on the active workspace.
- Hash changes move focus to the active workspace heading without causing an unexpected scroll jump on initial load.
- The tag form and failure list retain explicit labels and status messages.
- Empty, loading, and API-error states remain visible inside their owning workspace.
- Image viewer keyboard and long-image fitting behavior remains unchanged.

## Testing And Verification

- Add storage tests for every aggregate definition, month bucket ordering, zero-media percentages, storage-byte sum, and failure record joins.
- Add web tests for both new endpoints and the four workspace hooks.
- Add script-contract tests for hash routing, active navigation, back-to-top state, number formatting, and removal of tag-dialog behavior.
- Run the full Python suite and JavaScript syntax check.
- Verify the live app with the Browser integration at desktop and mobile viewports.
- Exercise all four sidebar routes, browser back/forward, favorites filtering, pagination, tag creation/editing without a dialog, sync failure empty state, back-to-top visibility, and the image viewer.
- Compare screenshots with the supplied dashboard reference for sidebar density, current-page hierarchy, statistics layout, numeric alignment, and workspace separation.

## Out Of Scope

- No change to Chrome-extension capture, X GraphQL ingestion, media downloading, official X APIs, SQLite destructive migrations, cloud storage, authentication, or multi-user support.
- No chart framework, frontend framework, external font download, or separate server-rendered HTML pages.
- No retry-failed-media web action unless requested separately.

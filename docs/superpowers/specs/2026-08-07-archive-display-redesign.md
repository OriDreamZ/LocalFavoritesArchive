# Local Favorites Archive Display Redesign

## Goal

Redesign the local archive display page around the supplied editorial knowledge-base reference while preserving every existing archive workflow. The result should feel like a personal library rather than a generic admin page, remain practical for hundreds of posts, and continue to use the existing FastAPI, SQLite, HTML, CSS, and JavaScript stack.

## Visual Direction

- Use a quiet pale-green desktop sidebar and a white main canvas.
- Brand the product as `喜欢归档` with the supporting label `LOCAL FAVORITES`.
- Use the main heading `喜欢过的内容，值得被找回。`
- Use the supporting copy `把 X 上稍纵即逝的喜欢，沉淀为可搜索、可筛选、可长期保存的本地内容库。`
- Keep corners restrained at 6-8 px, borders light, shadows subtle, and green reserved for active navigation and primary actions.
- Use an editorial serif face for the main heading and collection heading. Use the existing system sans-serif stack for controls, metadata, and post content.

## Information Architecture

### Desktop Sidebar

The sidebar remains visible on desktop and contains:

- Brand block.
- `我的收藏`, linked to the collection area and shown as the active item.
- `同步状态`, linked to the synchronization panel.
- `标签管理`, which opens the existing tag dialog.
- A local-library status marker at the bottom.

The sidebar is not a router. Navigation keeps the current single-page behavior and either scrolls to a section or opens the existing dialog.

### Mobile Header

At mobile widths the sidebar becomes a compact top header. The brand remains visible, and the three destinations are exposed as compact controls without creating horizontal overflow.

### Main Content

The first viewport contains:

1. Editorial heading and supporting copy.
2. Primary refresh action.
3. A real-data summary strip showing archived posts, unique authors, and synchronization state.
4. The existing filters in a compact toolbar.
5. A synchronization panel containing both progress bars, status copy, and archive location.
6. The collection heading, pagination controls, and post grid.

## Data And Behavior

- The post count comes from the existing count endpoint.
- The unique author count is returned by the synchronization status endpoint as `authors_total`, computed from stored posts.
- The synchronization summary uses the existing sync state and progress fields.
- Refresh continues to reload tags, posts, and sync status; it does not trigger collection in X.
- All current search, author, media, tag, date, sort, direction, page-size, page-jump, manual tag assignment, original-link, media playback, and image-viewer behavior remains available.
- Text-only filtering remains a first-class media option.

## Post Cards

- Desktop uses a responsive two-column grid, with one column at narrower widths. A three-column grid is avoided because real tweet text and tag controls need more horizontal space than the reference sample cards.
- Cards show author name, `@handle`, publication date, full post text, media, local tags, and the original X link.
- Media retains its natural inspection role: images remain clickable and videos remain playable.
- Cards may have different heights; content must not be clipped to force a masonry appearance.

## Responsive Behavior

- At wide desktop widths, the sidebar is about 250-280 px and the main content is centered with a practical maximum width.
- Below tablet width, filters reflow into fewer columns and post cards become one column.
- At mobile width, the sidebar becomes a top header, summary metrics stack or wrap, controls remain touch-sized, and pagination stays usable without overlap.
- Dialogs and the existing long-image fitting logic remain unchanged except for visual token alignment.

## Accessibility And Error Handling

- Retain semantic form labels, native controls, dialog behavior, keyboard image navigation, and visible focus states.
- Icon-only controls keep accessible labels and tooltips.
- Failed API calls continue to render status text in the page rather than hiding the main archive.
- Empty and loading states remain explicit.

## Verification

- Update focused web tests for the new stable page hooks and `authors_total` status field.
- Run the Python test suite and JavaScript syntax check.
- Verify the live page at desktop and mobile viewports using the Browser integration.
- Check page identity, meaningful content, console health, responsive overflow, filter interaction, tag dialog, pagination visibility, real statistics, and image-viewer behavior.
- Compare the live screenshots directly with the supplied reference for brand copy, hero hierarchy, sidebar structure, palette, spacing, and content density.

## Out Of Scope

- No changes to Chrome-extension capture, X acquisition, media download logic, SQLite schema migrations, or official X APIs.
- No authentication, cloud storage, external font dependency, analytics, or multi-page routing.
- No removal or truncation of stored post text or media.

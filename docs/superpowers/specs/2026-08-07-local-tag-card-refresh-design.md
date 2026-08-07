# Local Tag Card Refresh Design

## Goal

Keep the active favorites page and the operated post at the same viewport position after adding or removing a local tag.

## Root Cause

The current tag workflow calls `load()`, which rebuilds every visible post card. Restoring an anchor after that rebuild is not fully stable because media loading and the two-column grid can change row heights after scroll compensation.

## Design

For tag changes made from a favorite post card:

1. Complete the existing tag assignment or removal API request.
2. Reload the global tag list so filter options, tag counts, navigation counts, and the tag management workspace stay current.
3. Reload only the operated post detail.
4. Re-render only that card's `.post-tags` region with `renderPostTags()`.
5. Refresh overview statistics without rebuilding the favorites list.

Because the post card remains in the DOM, its page, grid row, and viewport position remain unchanged.

## Filter Exception

When removing the same tag that is currently selected in `#tag-filter`, the post no longer belongs in the visible result set. In that case the application will run the existing full `load()` path. The existing page clamping behavior will keep the current page when it remains valid or move to the last valid page when the removal reduces the page count.

Adding another tag while a tag filter is active does not change result membership and therefore uses the local card refresh path.

Tag creation, rename, and deletion in the dedicated tag management workspace keep their existing full refresh behavior because no favorite card is being operated there.

## Error Handling

If the tag API or follow-up detail request fails, the existing inline tag-operation error is shown. The favorites list is not cleared and the user's page and scroll position are not changed.

## Testing

- Add a frontend contract test requiring a dedicated local-card refresh function and ensuring post-card tag handlers do not call the full refresh path for normal operations.
- Keep the existing page-preservation regression test.
- In isolated Browser QA, open page two, scroll to a middle card, add a tag, and verify the page number, card top coordinate, and scroll position are unchanged.
- Verify removing the active filter tag still refreshes result membership.
- Run the complete Python test suite and JavaScript syntax checks.

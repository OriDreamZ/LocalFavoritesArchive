from local_favorites_archive.collector import normalize_post_text, pick_profile_path, posts_from_x_response
from local_favorites_archive.models import PostLink


def test_normalize_post_text_preserves_ordinary_links_and_removes_media_links():
    text, links = normalize_post_text(
        "Read https://t.co/article https://t.co/photo",
        [{
            "url": "https://t.co/article",
            "display_url": "example.com/article",
            "expanded_url": "https://example.com/article",
        }],
        [{"url": "https://t.co/photo"}],
    )

    assert text == "Read example.com/article"
    assert links == [PostLink(0, "example.com/article", "https://example.com/article", "https://t.co/article")]


def test_normalize_post_text_preserves_complete_url_without_entities():
    text, links = normalize_post_text("Read https://example.com/direct", [], [])

    assert text == "Read https://example.com/direct"
    assert links == [PostLink(0, "https://example.com/direct", "https://example.com/direct", "https://example.com/direct")]


def test_extracts_post_and_highest_bitrate_video():
    payload = {"data": {"result": {
        "rest_id": "99",
        "core": {"user_results": {"result": {"rest_id": "7", "legacy": {"screen_name": "alice", "name": "Alice"}}}},
        "legacy": {
            "full_text": "Complete text",
            "created_at": "Tue Jan 02 03:04:05 +0000 2024",
            "lang": "zh",
            "extended_entities": {"media": [{"type": "video", "video_info": {"variants": [
                {"content_type": "video/mp4", "bitrate": 256000, "url": "https://video.twimg.com/low.mp4"},
                {"content_type": "video/mp4", "bitrate": 2176000, "url": "https://video.twimg.com/high.mp4"},
            ]}}]},
        },
    }}}

    posts = posts_from_x_response(payload)

    assert len(posts) == 1
    assert posts[0].text == "Complete text"
    assert posts[0].author_handle == "alice"
    assert posts[0].url == "https://x.com/alice/status/99"
    assert posts[0].media[0].source_url.endswith("high.mp4")


def test_timeline_entry_uses_note_text_links_and_excludes_embedded_quote():
    quote = {
        "rest_id": "2",
        "legacy": {"full_text": "quoted", "created_at": "Tue Jan 02 03:04:05 +0000 2024"},
        "core": {"user_results": {"result": {"rest_id": "8", "legacy": {"screen_name": "bob", "name": "Bob"}}}},
    }
    liked = {
        "rest_id": "1",
        "note_tweet": {"note_tweet_results": {"result": {
            "text": "Long post https://t.co/note",
            "entity_set": {"urls": [{
                "url": "https://t.co/note",
                "display_url": "example.com/note",
                "expanded_url": "https://example.com/note",
            }]},
        }}},
        "legacy": {
            "full_text": "Truncated https://t.co/legacy",
            "created_at": "Tue Jan 02 03:04:05 +0000 2024",
            "entities": {"urls": [{
                "url": "https://t.co/legacy",
                "display_url": "wrong.example",
                "expanded_url": "https://wrong.example",
            }]},
            "quoted_status_result": {"result": quote},
        },
        "core": {"user_results": {"result": {"rest_id": "7", "legacy": {"screen_name": "alice", "name": "Alice"}}}},
    }
    payload = {"data": {"entries": [{"entryId": "tweet-1", "content": {"itemContent": {"tweet_results": {"result": liked}}}}]}}

    posts = posts_from_x_response(payload)

    assert [post.post_id for post in posts] == ["1"]
    assert posts[0].text == "Long post example.com/note"
    assert posts[0].links == [PostLink(0, "example.com/note", "https://example.com/note", "https://t.co/note")]


def test_extracted_post_removes_media_link_but_keeps_media():
    liked = {
        "rest_id": "1",
        "legacy": {
            "full_text": "Keep text https://t.co/media",
            "created_at": "Tue Jan 02 03:04:05 +0000 2024",
            "entities": {"media": [{"url": "https://t.co/media"}]},
            "extended_entities": {"media": [{
                "type": "photo",
                "url": "https://t.co/media",
                "media_url_https": "https://pbs.twimg.com/media/example.jpg",
            }]},
        },
        "core": {"user_results": {"result": {"rest_id": "7", "legacy": {"screen_name": "alice", "name": "Alice"}}}},
    }

    post = posts_from_x_response({"data": {"result": liked}})[0]

    assert post.text == "Keep text"
    assert post.links == []
    assert len(post.media) == 1


def test_profile_path_ignores_x_navigation_routes():
    hrefs = ["/home", "/explore", "/i/notifications", "/messages", "/alice", "/compose/post"]
    assert pick_profile_path(hrefs) == "/alice"


def test_extracts_author_from_new_user_core_shape():
    result = {
        "rest_id": "99",
        "core": {"user_results": {"result": {"rest_id": "7", "core": {"screen_name": "new_handle", "name": "New Name"}}}},
        "legacy": {"full_text": "post", "created_at": "Tue Jan 02 03:04:05 +0000 2024"},
    }
    payload = {"data": {"entries": [{"entryId": "tweet-99", "content": {"itemContent": {"tweet_results": {"result": result}}}}]}}

    post = posts_from_x_response(payload)[0]

    assert post.author_handle == "new_handle"
    assert post.author_name == "New Name"
    assert post.url == "https://x.com/new_handle/status/99"

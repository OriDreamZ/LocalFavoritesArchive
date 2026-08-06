from local_favorites_archive.collector import clean_post_text, pick_profile_path, posts_from_x_response


def test_clean_post_text_removes_urls_and_preserves_readable_text():
    text = "正文 https://t.co/abc\n第二行 https://example.com/a?b=1 结尾"

    assert clean_post_text(text) == "正文\n第二行 结尾"
    assert clean_post_text("https://t.co/only") == ""


def test_extracts_post_and_highest_bitrate_video():
    payload = {"data": {"result": {"rest_id": "99", "core": {"user_results": {"result": {"rest_id": "7", "legacy": {"screen_name": "alice", "name": "Alice"}}}}, "legacy": {"full_text": "完整文本", "created_at": "Tue Jan 02 03:04:05 +0000 2024", "lang": "zh", "extended_entities": {"media": [{"type": "video", "video_info": {"variants": [{"content_type": "video/mp4", "bitrate": 256000, "url": "https://video.twimg.com/low.mp4"}, {"content_type": "video/mp4", "bitrate": 2176000, "url": "https://video.twimg.com/high.mp4"}]}}]}}}}}
    posts = posts_from_x_response(payload)
    assert len(posts) == 1
    assert posts[0].text == "完整文本"
    assert posts[0].author_handle == "alice"
    assert posts[0].url == "https://x.com/alice/status/99"
    assert posts[0].media[0].source_url.endswith("high.mp4")


def test_timeline_entry_uses_note_text_and_excludes_embedded_quote():
    quote = {"rest_id": "2", "legacy": {"full_text": "quoted", "created_at": "Tue Jan 02 03:04:05 +0000 2024"}, "core": {"user_results": {"result": {"rest_id": "8", "legacy": {"screen_name": "bob", "name": "Bob"}}}}}
    liked = {"rest_id": "1", "note_tweet": {"note_tweet_results": {"result": {"text": "完整的长推文正文"}}}, "legacy": {"full_text": "截断正文…", "created_at": "Tue Jan 02 03:04:05 +0000 2024", "quoted_status_result": {"result": quote}}, "core": {"user_results": {"result": {"rest_id": "7", "legacy": {"screen_name": "alice", "name": "Alice"}}}}}
    payload = {"data": {"entries": [{"entryId": "tweet-1", "content": {"itemContent": {"tweet_results": {"result": liked}}}}]}}
    posts = posts_from_x_response(payload)
    assert [post.post_id for post in posts] == ["1"]
    assert posts[0].text == "完整的长推文正文"


def test_extracted_post_text_does_not_include_links():
    liked = {
        "rest_id": "1",
        "legacy": {
            "full_text": "保留正文 https://t.co/media",
            "created_at": "Tue Jan 02 03:04:05 +0000 2024",
        },
        "core": {
            "user_results": {
                "result": {
                    "rest_id": "7",
                    "legacy": {"screen_name": "alice", "name": "Alice"},
                }
            }
        },
    }

    post = posts_from_x_response({"data": {"result": liked}})[0]

    assert post.text == "保留正文"


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

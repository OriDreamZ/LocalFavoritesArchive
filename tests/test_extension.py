import json
from pathlib import Path


def test_extension_manifest_is_scoped_to_x_and_localhost():
    manifest = json.loads(Path("extension/manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3
    assert "debugger" in manifest["permissions"]
    assert "https://x.com/*" in manifest["host_permissions"]
    assert "http://127.0.0.1:8765/*" in manifest["host_permissions"]


def test_extension_waits_for_network_loading_before_reading_body():
    source = Path("extension/background.js").read_text(encoding="utf-8")
    assert 'method === "Network.loadingFinished"' in source
    assert "pendingLikes.set" in source
    assert "pendingLikes.delete" in source


def test_extension_finishes_when_server_requests_threshold_stop():
    source = Path("extension/background.js").read_text(encoding="utf-8")

    assert "result.stop_requested" in source
    assert "async function finish" in source
    assert "finishPromise" in source
    assert "连续" in source
    assert "result.existing_streak" in source


def test_extension_supports_resume_and_restart_collection_modes():
    background = Path("extension/background.js").read_text(encoding="utf-8")
    popup = Path("extension/popup.js").read_text(encoding="utf-8")
    html = Path("extension/popup.html").read_text(encoding="utf-8")

    assert 'start("resume")' in popup
    assert 'start("restart")' in popup
    assert 'id="restart"' in html
    assert "mode === \"restart\"" in background
    assert "if (targetUrl === url && mode === \"restart\")" in background
    assert "/api/ingest/dom-posts" in background
    assert 'article[data-testid="tweet"]' in background
    assert '[data-testid="tweetText"]' in background
    assert 'a[href*="/status/"]' in background
    assert "blob:" in background

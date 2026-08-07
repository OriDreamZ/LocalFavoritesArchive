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


def test_extension_only_uses_refreshed_network_collection():
    background = Path("extension/background.js").read_text(encoding="utf-8")
    popup = Path("extension/popup.js").read_text(encoding="utf-8")
    html = Path("extension/popup.html").read_text(encoding="utf-8")

    assert 'start()' in popup
    assert 'id="start"' in html
    assert 'chrome.tabs.reload(tabId)' in background
    assert 'Network.loadingFinished' in background
    assert "/api/ingest/dom-posts" not in background
    assert "collectRenderedPosts" not in background
    assert "dom-batch" not in background
    assert "window.scrollBy" in background
    assert "auto-finished" in background
    assert "从当前位置继续" not in html
    assert '"X-Local-Favorites-Client": "extension"' in background


def test_cli_exposes_explicit_lan_switch():
    source = Path("src/local_favorites_archive/cli.py").read_text(encoding="utf-8")
    assert '"--lan"' in source
    assert 'host="0.0.0.0" if args.lan else "127.0.0.1"' in source
    assert "无身份验证" in source

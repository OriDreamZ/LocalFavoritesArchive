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

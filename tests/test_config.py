from local_favorites_archive.config import Settings


def test_config_defaults_are_local(tmp_path):
    settings = Settings(archive_root=tmp_path)
    assert settings.host == "127.0.0.1"
    assert settings.lan_enabled is False
    assert settings.db_path == tmp_path / "archive.sqlite3"
    assert settings.max_media_concurrency == 2

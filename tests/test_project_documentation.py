from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]

EXPECTED_DOCUMENTS = {
    "FEATURES.md": ("# 功能说明", "## 非目标"),
    "ARCHITECTURE.md": ("# 系统架构", "## 数据流"),
    "UI-DESIGN.md": ("# 界面设计规范", "## 可访问性"),
    "DEVELOPMENT.md": ("# 开发规范", "## 测试要求"),
    "DATA-STORAGE.md": ("# 数据存储规范", "## 备份与恢复"),
    "SECURITY-AND-LIMITATIONS.md": ("# 安全、隐私与限制", "## 已知限制"),
}
EXPECTED_NEW_DOCUMENTS = ("FILTERING-AND-TAGS.md", "CHROME-EXTENSION.md", "LAN-ACCESS.md")


def test_project_declares_gpl_3_or_later() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = metadata["project"]

    assert project["readme"] == "README.md"
    assert project["license"] == "GPL-3.0-or-later"
    assert not any(
        classifier.startswith("License ::") for classifier in project["classifiers"]
    )


def test_license_contains_complete_gpl_v3_markers() -> None:
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")

    assert license_text.lstrip().startswith("GNU GENERAL PUBLIC LICENSE\n                       Version 3, 29 June 2007")
    assert "TERMS AND CONDITIONS" in license_text
    assert "END OF TERMS AND CONDITIONS" in license_text
    assert "How to Apply These Terms to Your New Programs" in license_text


def test_long_term_documents_are_present_and_chinese() -> None:
    for filename, required_headings in EXPECTED_DOCUMENTS.items():
        content = (ROOT / "docs" / filename).read_text(encoding="utf-8")
        assert all(heading in content for heading in required_headings)
        assert any("\u4e00" <= character <= "\u9fff" for character in content)
    for filename in EXPECTED_NEW_DOCUMENTS:
        content = (ROOT / "docs" / filename).read_text(encoding="utf-8")
        assert any("\u4e00" <= character <= "\u9fff" for character in content)


def test_documents_describe_current_sync_and_lan_modes() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "多个标签" in readme
    assert "刷新并开始同步" in readme
    assert "不读取已渲染推文 DOM" in readme
    assert "--lan" in readme and "无身份验证" in readme


def test_readme_covers_setup_usage_storage_and_license() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    required_sections = (
        "## 功能",
        "## 运行环境",
        "## 安装",
        "## 启动",
        "## 加载 Chrome 扩展",
        "## 同步 Likes",
        "## 本地浏览与管理",
        "## 备份与迁移",
        "## 开发与测试",
        "## 限制",
        "## 许可证",
    )
    assert all(section in readme for section in required_sections)
    assert "GPL-3.0-or-later" in readme
    assert "http://127.0.0.1:8765" in readme


def test_documentation_explains_media_retry_modes() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    documents = {
        filename: (ROOT / "docs" / filename).read_text(encoding="utf-8")
        for filename in EXPECTED_DOCUMENTS
    }
    assert "单条或全部重试" in readme
    assert "failed" in readme and "queued" in readme
    assert "local-favorites retry-media" in readme
    assert "显式重试" in documents["FEATURES.md"]
    assert "/api/sync/failures/retry" in documents["ARCHITECTURE.md"]
    assert "全部重试" in documents["UI-DESIGN.md"]
    assert "failed -> queued -> downloaded/failed" in documents["DATA-STORAGE.md"]
    assert "重试不扩大" in documents["SECURITY-AND-LIMITATIONS.md"]
    assert "重试接口" in documents["DEVELOPMENT.md"]

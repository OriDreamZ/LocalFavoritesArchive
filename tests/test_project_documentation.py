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


def test_readme_covers_setup_usage_storage_and_license() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    required_sections = (
        "## 项目简介",
        "## 功能概览",
        "## 运行环境",
        "## 安装",
        "## 启动与初始化",
        "## 加载 Chrome 扩展",
        "## 同步收藏",
        "## 本地浏览与管理",
        "## 数据存储与备份",
        "## 常见问题",
        "## 开发与测试",
        "## 项目结构",
        "## 使用限制与免责声明",
        "## 开源许可证",
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
    assert "同步期间的隐式重试" in readme
    assert "服务重启不会自动重试" in readme
    assert "全部重试" in readme and "单条重试" in readme
    assert "failed" in readme and "queued" in readme
    assert "local-favorites retry-media" in readme
    assert "显式重试" in documents["FEATURES.md"]
    assert "/api/sync/failures/retry" in documents["ARCHITECTURE.md"]
    assert "全部重试" in documents["UI-DESIGN.md"]
    assert "failed -> queued -> downloaded/failed" in documents["DATA-STORAGE.md"]
    assert "重试不扩大" in documents["SECURITY-AND-LIMITATIONS.md"]
    assert "重试接口" in documents["DEVELOPMENT.md"]

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
    assert (
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)"
        in project["classifiers"]
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

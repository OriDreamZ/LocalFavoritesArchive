from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


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

"""Feature-only development boundaries complement the landed producer tests."""

from pathlib import Path

import tomllib


def test_development_workflow_isolates_pinned_python_from_owner_packages():
    root = Path(__file__).resolve().parents[2]
    source = (root / ".github/workflows/development-profile.yml").read_text(
        encoding="utf-8"
    )
    assert "python.exe -I -m pip install" in source
    assert "python.exe -I scripts/build_windows_broker.py" in source


def test_generic_setuptools_wheel_cannot_ship_native_helpers():
    root = Path(__file__).resolve().parents[2]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    package_data = project["tool"]["setuptools"]["package-data"]
    assert "computer_use.browser.winhost" not in package_data
    assert "computer_use.browser.winbroker" not in package_data

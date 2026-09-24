"""Feature-only development boundaries complement the landed producer tests."""

import subprocess
import sys
from pathlib import Path

import pytest
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_development_profile import require_exact_clean_source


def test_development_workflow_isolates_pinned_python_from_owner_packages():
    root = Path(__file__).resolve().parents[2]
    source = (root / ".github/workflows/development-profile.yml").read_text(encoding="utf-8")
    assert "python.exe -I -m pip install" in source
    assert "python.exe -I scripts/build_windows_broker.py" in source


def test_development_workflow_builds_supported_native_profiles_without_windows_inputs():
    root = Path(__file__).resolve().parents[2]
    source = (root / ".github/workflows/development-profile.yml").read_text(encoding="utf-8")
    for value in (
        "native-development-${{ matrix.platform }}-${{ matrix.architecture }}",
        "ubuntu-24.04",
        "ubuntu-24.04-arm",
        "macos-15-intel",
        "macos-15",
        "build_native_development_profiles.py",
        "check_native_development_profiles.py",
    ):
        assert value in source
    native_job = source.split("native-development:", 1)[1].split("unsigned-development:", 1)[0]
    assert "adoption-rules.json" not in native_job
    assert "build_windows_broker.py" not in native_job
    assert "profile-wheels" not in native_job


def test_development_source_must_be_the_exact_clean_commit(tmp_path):
    repository = tmp_path / "source"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", repository], check=True)
    subprocess.run(
        ["git", "-C", repository, "config", "user.email", "test@example.invalid"], check=True
    )
    subprocess.run(["git", "-C", repository, "config", "user.name", "Test"], check=True)
    tracked = repository / "tracked.txt"
    tracked.write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "-C", repository, "add", "tracked.txt"], check=True)
    subprocess.run(["git", "-C", repository, "commit", "-qm", "fixture"], check=True)
    commit = subprocess.check_output(
        ["git", "-C", repository, "rev-parse", "HEAD"], text=True
    ).strip()
    require_exact_clean_source(repository, commit)
    with pytest.raises(ValueError, match="exact clean committed source"):
        require_exact_clean_source(repository, "0" * 40)
    tracked.write_text("two\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exact clean committed source"):
        require_exact_clean_source(repository, commit)
    tracked.write_text("one\n", encoding="utf-8")
    (repository / "untracked.txt").write_text("drift\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exact clean committed source"):
        require_exact_clean_source(repository, commit)


def test_generic_setuptools_wheel_cannot_ship_native_helpers():
    root = Path(__file__).resolve().parents[2]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    package_data = project["tool"]["setuptools"]["package-data"]
    assert "computer_use.browser.winhost" not in package_data
    assert "computer_use.browser.winbroker" not in package_data

"""Release consistency guardrails (run in normal CI, before any tag).

The publish workflow also enforces these at release time, but catching them in the
regular suite means a mismatch fails a PR, not a tag build.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _pkg_version() -> str:
    text = (ROOT / "pyproject.toml").read_text()
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    assert m, "could not find project version in pyproject.toml"
    return m.group(1)


def test_extension_manifest_version_matches_package():
    manifest = json.loads((ROOT / "extension" / "manifest.json").read_text())
    assert manifest["version"] == _pkg_version(), (
        f"extension/manifest.json version {manifest['version']} != "
        f"pyproject version {_pkg_version()}; bump them together"
    )


def test_source_manifest_keeps_the_pinned_key():
    # The source manifest keeps `key` (stable unpacked/dev id). CD strips it for the
    # store zip only. If this ever disappears from source, the dev id drifts.
    manifest = json.loads((ROOT / "extension" / "manifest.json").read_text())
    assert manifest.get("key"), (
        "extension/manifest.json must keep its pinned public `key` (dev id stability); "
        "the store zip is stripped by CD, not the source"
    )

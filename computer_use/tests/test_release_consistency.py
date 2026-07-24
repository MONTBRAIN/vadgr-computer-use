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


def test_cua_version_matches_package():
    # Issue #36 (minor): server.py shipped a stale CUA_VERSION ("0.6.1" in the
    # 0.6.4 release). The handshake compares only the integer proto, but a stale
    # string misleads debugging — pin it to the package version.
    from computer_use.browser.server import CUA_VERSION

    assert CUA_VERSION == _pkg_version(), (
        f"CUA_VERSION {CUA_VERSION} != pyproject version {_pkg_version()}; "
        "bump computer_use/browser/server.py with the release"
    )


def test_background_version_fallback_matches_package():
    # Same staleness class in the extension: the `?? "x.y.z"` fallback in
    # background.ts (used only when getManifest is unavailable) must track the
    # release, not fossilize.
    src = (ROOT / "extension" / "src" / "background.ts").read_text()
    m = re.search(r'getManifest\?\.\(\)\.version \?\? "([^"]+)"', src)
    assert m, "could not find the EXT_VERSION fallback in background.ts"
    assert m.group(1) == _pkg_version(), (
        f"background.ts version fallback {m.group(1)} != pyproject version "
        f"{_pkg_version()}; bump them together"
    )


def test_extension_manifest_has_the_alarms_permission():
    # Issue #36 (defect 2): the keep-alive alarm is the only guaranteed wake-up
    # that can re-establish the native port after MV3 idle termination. Without
    # the "alarms" permission chrome.alarms is undefined and the reconnect path
    # silently vanishes.
    manifest = json.loads((ROOT / "extension" / "manifest.json").read_text())
    assert "alarms" in manifest.get("permissions", []), (
        "extension/manifest.json must keep the 'alarms' permission — the "
        "periodic keep-alive is what revives the native port after SW idle death"
    )

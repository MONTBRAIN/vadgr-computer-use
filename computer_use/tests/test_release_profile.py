"""Profile tests start with isolated platform probes and no real helper launch."""

from types import SimpleNamespace

import pytest

from computer_use.browser import profile


@pytest.mark.parametrize(
    "os_name,architecture,expected",
    [
        ("win32", "x86_64", "windows-x86_64"),
        ("win32", "aarch64", "windows-aarch64"),
        ("darwin", "x86_64", "macos-x86_64"),
        ("darwin", "aarch64", "macos-aarch64"),
        ("linux", "x86_64", "linux-x86_64"),
        ("linux", "aarch64", "linux-aarch64"),
        ("wsl", "x86_64", "wsl-x86_64"),
        ("wsl", "aarch64", "wsl-aarch64"),
    ],
)
def test_all_eight_native_profiles(monkeypatch, os_name, architecture, expected):
    monkeypatch.setattr(profile.sys, "platform", "linux" if os_name == "wsl" else os_name)
    monkeypatch.setattr(profile.platform, "machine", lambda: architecture)
    monkeypatch.setattr(
        profile.platform, "release", lambda: "microsoft-standard" if os_name == "wsl" else "6.8"
    )
    monkeypatch.setattr(profile, "_windows_architecture", lambda: architecture)
    monkeypatch.setattr(profile, "_wsl_host_architecture", lambda: architecture)
    monkeypatch.setattr(
        profile.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            returncode=0, stdout="1" if architecture == "aarch64" else "0"
        ),
    )
    monkeypatch.setenv("VADGR_CUA_PROFILE", "windows-x86_64")
    assert profile.select_profile().value == expected


def test_windows_uses_native_architecture_under_emulation(monkeypatch):
    monkeypatch.setattr(profile.sys, "platform", "win32")
    monkeypatch.setattr(profile.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(profile, "_windows_architecture", lambda: "aarch64")
    assert profile.select_profile() is profile.ReleaseProfile.WINDOWS_AARCH64


def test_wsl_host_mismatch_refuses_before_deployment(monkeypatch):
    monkeypatch.setattr(profile.sys, "platform", "linux")
    monkeypatch.setattr(profile.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(profile.platform, "release", lambda: "microsoft-standard-WSL2")
    monkeypatch.setattr(profile, "_wsl_host_architecture", lambda: "x86_64")
    with pytest.raises(profile.ProfileRefusal) as error:
        profile.select_profile()
    assert error.value.code == "wsl-host-mismatch"


def test_wsl_interop_disabled_is_distinct(monkeypatch):
    monkeypatch.setattr(profile.Path, "read_text", lambda *a, **k: "disabled\n")
    with pytest.raises(profile.ProfileRefusal) as error:
        profile._wsl_host_architecture()
    assert error.value.code == "wsl-interop-disabled"


def test_linux_environment_marker_does_not_enable_wsl(monkeypatch):
    monkeypatch.setattr(profile.sys, "platform", "linux")
    monkeypatch.setattr(profile.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(profile.platform, "release", lambda: "6.8.0")
    monkeypatch.setenv("WSL_DISTRO_NAME", "ignored")
    assert profile.select_profile() is profile.ReleaseProfile.LINUX_X86_64


def test_package_manifest_is_bound_to_generated_digest(tmp_path, monkeypatch):
    import hashlib
    import json

    root = tmp_path / "profiles" / "linux-x86_64"
    root.mkdir(parents=True)
    raw = json.dumps({"schema": 1, "release_profile": "linux-x86_64"}).encode()
    manifest = root / "cua-profile-manifest.json"
    manifest.write_bytes(raw)
    monkeypatch.setattr(profile, "__file__", str(tmp_path / "profile.py"))
    monkeypatch.setattr(
        profile,
        "load_package_trust",
        lambda: {
            "mode": "managed",
            "release_profile": "linux-x86_64",
            "manifest_sha256": {"linux-x86_64": hashlib.sha256(raw).hexdigest()},
        },
    )
    assert profile.load_input_manifest(profile.ReleaseProfile.LINUX_X86_64)["schema"] == 1
    manifest.write_bytes(raw + b" ")
    with pytest.raises(profile.ProfileRefusal, match="changed"):
        profile.load_input_manifest(profile.ReleaseProfile.LINUX_X86_64)


def _sha(character="a"):
    return character * 64


def test_package_trust_modes_have_closed_schemas():
    managed = {
        "schema": 1,
        "mode": "managed",
        "release_profile": "windows-x86_64",
        "manifest_sha256": {"windows-x86_64": _sha()},
    }
    development = {
        "schema": 1,
        "mode": "standalone-input",
        "development": True,
        "manifest_sha256": {"windows-x86_64": _sha()},
    }
    release = {
        "schema": 1,
        "mode": "standalone-input",
        "manifest_sha256": {"windows-x86_64": _sha()},
        "adoption": {
            architecture: {
                "policy_sha256": _sha("b"),
                "root_sha256": _sha("c"),
                "verifier_sha256": _sha("d"),
            }
            for architecture in ("x86_64", "aarch64")
        },
    }
    assert profile._validate_package_trust(managed) == managed
    assert profile._validate_package_trust(development) == development
    assert profile._validate_package_trust(release) == release


@pytest.mark.parametrize(
    "trust",
    [
        {"schema": 1, "mode": "standalone-input", "manifest_sha256": {"windows-x86_64": "a" * 64}},
        {
            "schema": 1,
            "mode": "standalone-input",
            "development": False,
            "manifest_sha256": {"windows-x86_64": "a" * 64},
        },
        {
            "schema": 1,
            "mode": "standalone-input",
            "development": True,
            "manifest_sha256": {"windows-x86_64": "a" * 64},
            "adoption": {},
        },
        {
            "schema": 1,
            "mode": "managed",
            "release_profile": "windows-x86_64",
            "manifest_sha256": {"windows-x86_64": "a" * 64},
            "development": True,
        },
        {
            "schema": 1,
            "mode": "managed",
            "release_profile": "windows-x86_64",
            "manifest_sha256": {"windows-aarch64": "a" * 64},
        },
    ],
)
def test_package_trust_rejects_ambiguous_or_extra_fields(trust):
    with pytest.raises(profile.ProfileRefusal, match="trust|metadata|profile"):
        profile._validate_package_trust(trust)


def test_development_and_managed_packages_cannot_request_adoption(monkeypatch):
    for trust in (
        {
            "schema": 1,
            "mode": "standalone-input",
            "development": True,
            "manifest_sha256": {"windows-x86_64": _sha()},
        },
        {
            "schema": 1,
            "mode": "managed",
            "release_profile": "windows-x86_64",
            "manifest_sha256": {"windows-x86_64": _sha()},
        },
    ):
        monkeypatch.setattr(profile, "load_package_trust", lambda trust=trust: trust)
        with pytest.raises(profile.ProfileRefusal) as error:
            profile.load_adoption_pins("x86_64")
        assert error.value.code == "adoption-disabled"


@pytest.mark.parametrize("value", ["i386", "armv7l", "", "riscv64"])
def test_unknown_architecture_refuses(value):
    with pytest.raises(profile.ProfileRefusal):
        profile._architecture(value)

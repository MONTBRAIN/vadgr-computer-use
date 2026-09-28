"""Closed release profiles and native execution-environment checks."""

from __future__ import annotations

import ctypes
import hashlib
import importlib
import json
import platform
import subprocess
import sys
from enum import Enum
from pathlib import Path


class ProfileRefusal(RuntimeError):
    """A profile cannot safely run on the observed host."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class ReleaseProfile(str, Enum):
    WINDOWS_X86_64 = "windows-x86_64"
    WINDOWS_AARCH64 = "windows-aarch64"
    MACOS_X86_64 = "macos-x86_64"
    MACOS_AARCH64 = "macos-aarch64"
    LINUX_X86_64 = "linux-x86_64"
    LINUX_AARCH64 = "linux-aarch64"
    WSL_X86_64 = "wsl-x86_64"
    WSL_AARCH64 = "wsl-aarch64"

    @property
    def architecture(self) -> str:
        return self.value.split("-", 1)[1]

    @property
    def execution_os(self) -> str:
        name = self.value.split("-", 1)[0]
        return "linux" if name == "wsl" else name

    @property
    def windows_helpers(self) -> bool:
        return self.value.startswith(("windows-", "wsl-"))


def _architecture(value: str) -> str:
    aliases = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "aarch64", "aarch64": "aarch64"}
    try:
        return aliases[value.lower()]
    except KeyError:
        raise ProfileRefusal(
            "unsupported-architecture", f"Unsupported native architecture: {value}"
        )


def _windows_architecture() -> str:
    # GetNativeSystemInfo reports the host even when Python runs under emulation.
    info = ctypes.create_string_buffer(64)
    ctypes.windll.kernel32.GetNativeSystemInfo(ctypes.byref(info))
    architecture = int.from_bytes(info.raw[:2], "little")
    try:
        return {9: "x86_64", 12: "aarch64"}[architecture]
    except KeyError:
        raise ProfileRefusal("unsupported-architecture", "Unsupported native Windows architecture")


def _wsl_host_architecture() -> str:
    registration = Path("/proc/sys/fs/binfmt_misc/WSLInterop")
    try:
        enabled = registration.read_text(encoding="utf-8").splitlines()[0] == "enabled"
    except (OSError, IndexError):
        enabled = False
    if not enabled:
        raise ProfileRefusal(
            "wsl-interop-disabled", "Windows interoperability is unavailable in WSL"
        )
    executable = Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
    try:
        result = subprocess.run(
            [
                str(executable),
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "[System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProfileRefusal(
            "wsl-host-probe-failed", "Cannot verify the native Windows host"
        ) from exc
    if result.returncode or len(result.stdout) > 128:
        raise ProfileRefusal("wsl-host-probe-failed", "Cannot verify the native Windows host")
    return _architecture(result.stdout.strip())


def select_profile() -> ReleaseProfile:
    """Select from native facts; environment variables cannot select a profile."""
    if sys.platform == "win32":
        return ReleaseProfile("windows-" + _windows_architecture())
    architecture = _architecture(platform.machine())
    if sys.platform == "darwin":
        # Rosetta reports x86_64 to an emulated interpreter. Query the native host.
        try:
            result = subprocess.run(
                ["/usr/sbin/sysctl", "-n", "hw.optional.arm64"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ProfileRefusal(
                "native-host-probe-failed", "Cannot verify the native macOS host"
            ) from exc
        if result.returncode == 0 and result.stdout.strip() == "1":
            architecture = "aarch64"
        return ReleaseProfile("macos-" + architecture)
    if sys.platform != "linux":
        raise ProfileRefusal("unsupported-os", f"Unsupported operating system: {sys.platform}")
    kernel = platform.release().lower()
    if "microsoft" in kernel or "wsl" in kernel:
        host_architecture = _wsl_host_architecture()
        if host_architecture != architecture:
            raise ProfileRefusal("wsl-host-mismatch", "WSL and native Windows architectures differ")
        return ReleaseProfile("wsl-" + architecture)
    return ReleaseProfile("linux-" + architecture)


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProfileRefusal("invalid-manifest", f"Duplicate manifest key: {key}")
        result[key] = value
    return result


def _digest(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ProfileRefusal("invalid-package-trust", "Package manifest digest is invalid")
    return value


def _digest_map(value: object, *, expected_profiles: set[str] | None = None) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise ProfileRefusal("invalid-package-trust", "Package manifest pins are invalid")
    if expected_profiles is not None and set(value) != expected_profiles:
        raise ProfileRefusal("invalid-package-trust", "Package manifest profiles are invalid")
    for key, digest in value.items():
        try:
            ReleaseProfile(key)
        except (TypeError, ValueError) as exc:
            raise ProfileRefusal(
                "invalid-package-trust", "Package manifest profile is invalid"
            ) from exc
        _digest(digest)
    return value


def _validate_package_trust(trust: object) -> dict:
    if not isinstance(trust, dict) or trust.get("schema") != 1:
        raise ProfileRefusal("invalid-package-trust", "Package profile metadata is invalid")
    mode = trust.get("mode")
    if mode == "managed":
        if set(trust) != {"schema", "mode", "release_profile", "manifest_sha256"}:
            raise ProfileRefusal("invalid-package-trust", "Managed package trust is invalid")
        try:
            release_profile = ReleaseProfile(trust["release_profile"])
        except (TypeError, ValueError) as exc:
            raise ProfileRefusal(
                "invalid-package-trust", "Managed package profile is invalid"
            ) from exc
        _digest_map(trust["manifest_sha256"], expected_profiles={release_profile.value})
        return trust
    if mode != "standalone-input":
        raise ProfileRefusal("invalid-package-trust", "Package profile metadata is invalid")
    if trust.get("development") is True:
        if set(trust) != {"schema", "mode", "development", "manifest_sha256"}:
            raise ProfileRefusal("invalid-package-trust", "Development package trust is invalid")
        _digest_map(trust["manifest_sha256"])
        return trust
    if "development" in trust or set(trust) != {
        "schema",
        "mode",
        "manifest_sha256",
        "adoption",
    }:
        raise ProfileRefusal("invalid-package-trust", "Standalone package trust is invalid")
    _digest_map(trust["manifest_sha256"])
    adoption = trust["adoption"]
    if not isinstance(adoption, dict) or set(adoption) != {"x86_64", "aarch64"}:
        raise ProfileRefusal("invalid-package-trust", "Standalone adoption pins are invalid")
    for pins in adoption.values():
        if not isinstance(pins, dict) or set(pins) != {
            "policy_sha256",
            "root_sha256",
            "verifier_sha256",
        }:
            raise ProfileRefusal("invalid-package-trust", "Standalone adoption pins are invalid")
        for value in pins.values():
            _digest(value)
    return trust


def load_package_trust() -> dict:
    """Read build-generated package constants, never an owner-selected path."""
    try:
        module = importlib.import_module("computer_use.browser._profile_trust")
        trust = module.TRUST
    except (ImportError, AttributeError) as exc:
        raise ProfileRefusal(
            "missing-package-trust", "Package profile metadata is missing"
        ) from exc
    return _validate_package_trust(trust)


def load_adoption_pins(architecture: str) -> dict[str, str]:
    """Return release-only offline adoption pins; development can never adopt."""
    if architecture not in {"x86_64", "aarch64"}:
        raise ProfileRefusal("invalid-adoption-architecture", "Adoption architecture is invalid")
    trust = load_package_trust()
    if trust["mode"] != "standalone-input" or trust.get("development") is True:
        raise ProfileRefusal(
            "adoption-disabled",
            "Authenticated adoption is disabled for this package",
        )
    return trust["adoption"][architecture]


def load_input_manifest(profile: ReleaseProfile) -> dict:
    profile = ReleaseProfile(profile)
    trust = load_package_trust()
    if trust["mode"] == "managed" and trust.get("release_profile") != profile.value:
        raise ProfileRefusal(
            "package-profile-mismatch", "The package does not match the release profile"
        )
    expected = trust.get("manifest_sha256", {}).get(profile.value)
    path = Path(__file__).parent / "profiles" / profile.value / "cua-profile-manifest.json"
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ProfileRefusal(
            "missing-manifest", "The packaged profile manifest is missing"
        ) from exc
    if not expected or hashlib.sha256(raw).hexdigest() != expected:
        raise ProfileRefusal("manifest-digest-mismatch", "The packaged profile manifest changed")
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError) as exc:
        raise ProfileRefusal(
            "invalid-manifest", "The packaged profile manifest is invalid"
        ) from exc
    if value.get("schema") != 1 or value.get("release_profile") != profile.value:
        raise ProfileRefusal(
            "invalid-manifest", "The packaged profile manifest has a different profile"
        )
    return value

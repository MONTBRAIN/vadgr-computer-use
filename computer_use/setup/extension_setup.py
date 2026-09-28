# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""First-run: install the native-host manifest so Chrome can spawn the host.

Chrome only spawns ``native_host.py`` if a host manifest is registered. The
manifest is ``com.vadgr.cua.json`` - ``{name, description, path, type:"stdio",
allowed_origins:["chrome-extension://<id>/", ...]}``. Two things bite if
wrong: the per-OS location, and ``allowed_origins`` must contain the installed
extension's ID exactly (a mismatch = Chrome refuses ``connectNative`` before
the host is ever spawned, so nothing is logged anywhere - issue #36).

There are TWO known IDs for the same extension and BOTH must be allowlisted:

- ``EXTENSION_ID`` - the unpacked dev build, fixed by the ``key`` pinned in
  ``extension/manifest.json`` (SHA256-derived; keep the two in sync).
- ``WEBSTORE_EXTENSION_ID`` - the Chrome Web Store build. The store strips the
  ``key`` field and assigns its own ID, so a store install has a DIFFERENT id
  than the dev build. 0.6.4 allowlisted only the dev id, which made every Web
  Store install permanently unable to connect (issue #36, defect 1).

``install_manifests`` also MERGES with any ``allowed_origins`` already present
at the destination instead of clobbering them: ``ensure_registered`` runs on
every server start, and an unconditional rewrite silently reverted any manual
allowlist fix (issue #36).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from computer_use.browser.bridge import manifest_paths

# The stable unpacked-dev extension ID, derived from the public key pinned in
# extension/manifest.json. If the manifest key changes, regenerate this.
EXTENSION_ID = "bcbdnpafilijienocokppgmfianhehll"

# The Chrome Web Store build's ID. The store strips the pinned `key` from the
# uploaded zip and assigns its own ID, so a store install is a DIFFERENT origin
# than the dev build and must be allowlisted too (issue #36).
WEBSTORE_EXTENSION_ID = "bjjpaehedfnjnjmamjhppjnjnikpnfjl"

# Every ID the host manifest must always allow, dev + store. Order matters only
# cosmetically (dev first, matching the historical single-entry manifest).
KNOWN_EXTENSION_IDS = (EXTENSION_ID, WEBSTORE_EXTENSION_ID)

HOST_NAME = "com.vadgr.cua"


def _origin(extension_id: str) -> str:
    return f"chrome-extension://{extension_id}/"


def build_manifest(host_path: str) -> dict:
    """Build the native-host manifest contents (dev + Web Store origins)."""
    return {
        "name": HOST_NAME,
        "description": "vadgr-computer-use browser tier native messaging host",
        "path": host_path,
        "type": "stdio",
        "allowed_origins": [_origin(i) for i in KNOWN_EXTENSION_IDS],
    }


def _merge_allowed_origins(dest: Path, required: list[str]) -> list[str]:
    """Union of ``required`` with any origins already present at ``dest``.

    ``ensure_registered`` rewrites the manifest on every server start; a user's
    manual allowlist addition (an enterprise-forced id, a fork's id, a canary
    build) must survive that rewrite (issue #36). Required origins come first;
    pre-existing extras keep their relative order. An unreadable/invalid
    existing file merges nothing.
    """
    merged = list(required)
    try:
        existing = json.loads(Path(dest).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return merged
    origins = existing.get("allowed_origins") if isinstance(existing, dict) else None
    if isinstance(origins, list):
        for origin in origins:
            if isinstance(origin, str) and origin not in merged:
                merged.append(origin)
    return merged


def install_manifests(
    host_path: str,
    paths: dict[str, Path] | None = None,
) -> list[str]:
    """Write the manifest to each per-OS target. Returns the browsers written.

    Guarantees BOTH known extension origins (dev + Web Store) are present, and
    merges - never drops - extra ``allowed_origins`` found in an existing
    manifest at the destination.
    """
    targets = paths if paths is not None else manifest_paths()
    manifest = build_manifest(host_path)
    written: list[str] = []
    for browser, dest in targets.items():
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        merged = dict(manifest)
        merged["allowed_origins"] = _merge_allowed_origins(
            dest, manifest["allowed_origins"]
        )
        dest.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        written.append(browser)
    return written


def load_steps() -> str:
    """Human-facing instructions for installing the extension."""
    return (
        "Browser tier setup:\n"
        "  Either install from the Chrome Web Store (extension ID\n"
        f"  {WEBSTORE_EXTENSION_ID}), or sideload the dev build:\n"
        "  1. Open chrome://extensions (or edge://extensions).\n"
        "  2. Enable Developer mode.\n"
        "  3. Click 'Load unpacked' and select the built `extension/` dir.\n"
        f"  4. Confirm the extension ID is {EXTENSION_ID}.\n"
        "  5. The native-host manifest has been installed (both IDs are\n"
        "     allowlisted); restart the browser if it was already running,\n"
        "     then run `browser(op='status')`."
    )


# --- self-registration: cua writes its own host wiring (no manual setup) ------

# HKCU registry subkeys Chrome/Edge read native hosts from (Windows only). The
# manifest *file* alone isn't enough on Windows - the key must point at it.
_WIN_REGISTRY_KEYS = {
    "chrome": r"Software\Google\Chrome\NativeMessagingHosts\com.vadgr.cua",
    "edge": r"Software\Microsoft\Edge\NativeMessagingHosts\com.vadgr.cua",
}


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def windows_relay_path(windows_user: str | None = None) -> str:
    """The Windows-form path of the relay shim Chrome spawns on Windows (WSL).

    On WSL the manifest ``path`` cannot point at a Linux launcher - Chrome runs
    on Windows. It points at ``vadgr-cua-host.exe``, a tiny stdio<->TCP
    forwarder placed under the Windows user's ``AppData\\Local\\vadgr-cua``
    (see ``computer_use/browser/winhost/``). Returns the ``C:\\...`` form
    written into the manifest + the registry.
    """

    return _mnt_to_windows_path(relay_exe_dest(windows_user))


def bundled_relay_exe() -> Path:
    """Path to the packaged Windows relay shim (shipped as package data next to
    ``computer_use/browser/winhost/__init__.py``)."""
    from computer_use.browser import winhost
    from computer_use.browser.profile import (
        ProfileRefusal,
        load_input_manifest,
        select_profile,
    )

    # Profile manifests use paths relative to the wheel root, not the browser
    # package.  This is the source root in a checkout and site-packages after
    # installation.
    wheel_root = Path(winhost.__file__).resolve().parents[3]
    try:
        adopted = _adopted_relay()
        if adopted is not None:
            return adopted
        profile = select_profile()
        manifest = load_input_manifest(profile)
        helpers = manifest.get("helpers")
        if not profile.windows_helpers or not isinstance(helpers, dict):
            raise ProfileRefusal(
                "windows-helper-unavailable",
                "This release profile does not carry a Windows browser relay",
            )
        relay = helpers.get("relay")
        if not isinstance(relay, dict) or set(relay) != {"path", "size", "sha256"}:
            raise ProfileRefusal("invalid-manifest", "The relay manifest is invalid")
        source = wheel_root / str(relay["path"])
        if (
            not source.is_file()
            or source.stat().st_size != relay["size"]
            or _file_sha256(source) != relay["sha256"]
        ):
            raise ProfileRefusal(
                "relay-digest-mismatch", "The packaged Windows relay changed"
            )
        return source
    except ProfileRefusal as error:
        # The exact released 0.7.8 binary remains in source only as a predecessor
        # fixture. It keeps existing source tests usable but is never an installed
        # 0.7.9 package fallback.
        repository = Path(__file__).resolve().parents[2]
        legacy = Path(winhost.__file__).resolve().parent / "vadgr-cua-host.exe"
        if error.code == "missing-package-trust" and (repository / ".git").exists():
            return legacy
        raise


def _managed_relay() -> tuple[str, Path]:
    """Verify and return the final relay bound by the inherited parent channel."""
    from computer_use.browser.managed_authorization import managed_launch_authorization
    from computer_use.browser.profile import load_package_trust, select_profile
    from computer_use.browser.windows_broker import _managed_authorization_pipe

    profile = select_profile()
    trust = load_package_trust()
    if trust.get("mode") != "managed" or trust.get("release_profile") != profile.value:
        raise OSError("the managed relay package profile is invalid")
    envelope, _manifest = managed_launch_authorization(
        _managed_authorization_pipe, profile=profile.value
    )
    windows_path = str(envelope["relay"]["path"])
    root_path = str(envelope["installed_root"])
    if sys.platform == "win32":
        local_path = Path(windows_path)
    else:
        from computer_use.platform.wsl2 import win_to_wsl_path

        local_path = Path(win_to_wsl_path(windows_path))
    if (
        not local_path.is_file()
        or local_path.stat().st_size != envelope["relay"]["size"]
        or _file_sha256(local_path) != envelope["relay"]["sha256"]
    ):
        raise OSError("the installed managed relay changed")
    command = (
        "$env:PSModulePath=$PSHOME+'\\Modules';"
        "$v=[Console]::In.ReadToEnd()|ConvertFrom-Json;"
        "$s=Get-AuthenticodeSignature -LiteralPath $v.path;"
        "$a=Get-Acl -LiteralPath $v.root;"
        "$ids=@($a.Access|ForEach-Object {$_.IdentityReference.Translate("
        "[Security.Principal.SecurityIdentifier]).Value}|Sort-Object -Unique);"
        "$ok=$s.Status -eq 'Valid' -and $a.AreAccessRulesProtected -and "
        "@($ids|Where-Object {$_ -notin @('S-1-5-18',"
        "[Security.Principal.WindowsIdentity]::GetCurrent().User.Value)}).Count -eq 0;"
        "@{ok=$ok;status=[string]$s.Status}|ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        input=json.dumps({"path": windows_path, "root": root_path}),
        capture_output=True,
        text=True,
        stdin=None,
        timeout=15,
    )
    try:
        verification = json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError) as error:
        raise OSError("the installed managed relay could not be verified") from error
    if result.returncode != 0 or verification != {"ok": True, "status": "Valid"}:
        raise OSError("the installed managed relay signature or ACL is invalid")
    return windows_path, local_path


def relay_exe_dest(
    windows_user: str | None = None, *, src: Path | None = None
) -> Path:
    """The ``/mnt/c`` destination the relay shim must live at for Windows Chrome
    to spawn it - the WSL view of
    ``%LOCALAPPDATA%\\vadgr-cua\\vadgr-cua-host.exe``."""
    from computer_use.browser.bridge import windows_user_home_mnt

    source = Path(src) if src is not None else bundled_relay_exe()
    return (
        windows_user_home_mnt(windows_user)
        / "AppData"
        / "Local"
        / "vadgr-cua"
        / "native-host"
        / _file_sha256(source)
        / "vadgr-cua-host.exe"
    )


def native_windows_relay_dest(*, src: Path | None = None) -> Path:
    """Content-addressed native-host destination for a Windows installation."""
    source = Path(src) if src is not None else bundled_relay_exe()
    return (
        Path.home()
        / "AppData"
        / "Local"
        / "vadgr-cua"
        / "native-host"
        / _file_sha256(source)
        / "vadgr-cua-host.exe"
    )


def ensure_relay_exe(
    windows_user: str | None = None,
    *,
    src: Path | None = None,
    dest: Path | None = None,
) -> Path:
    """Copy the packaged relay shim to the Windows-readable location the manifest
    points at, so the WSL bridge needs **no manual file placement**. Idempotent:
    copies only when the destination is missing or differs in size. Returns the
    destination path. The normal destination is content-addressed, so a live
    Chrome process can keep its old executable open while registration moves
    atomically to the new payload.
    """
    if src is None and dest is None:
        adopted = _adopted_relay()
        if adopted is not None:
            return adopted
    src = Path(src) if src is not None else bundled_relay_exe()
    explicit_destination = dest is not None
    dest = Path(dest) if dest is not None else relay_exe_dest(windows_user, src=src)
    dest.parent.mkdir(parents=True, exist_ok=True)
    expected = _file_sha256(src)
    if dest.exists() and _file_sha256(dest) == expected:
        return dest
    if dest.exists() and not explicit_destination:
        raise OSError("the content-addressed Windows native host is corrupted")
    temporary = dest.with_name(f".{dest.name}.tmp")
    shutil.copy2(src, temporary)
    if _file_sha256(temporary) != expected:
        temporary.unlink(missing_ok=True)
        raise OSError("the staged Windows native host failed integrity verification")
    temporary.replace(dest)
    return dest


def host_launcher_path(platform: str | None = None) -> Path:
    """Stable path for the generated launcher Chrome executes as the host."""
    plat = platform or sys.platform
    base = Path.home() / ".vadgr-cua"
    return base / ("host.bat" if plat.startswith("win") else "host.sh")


def write_launcher(
    python: str | None = None,
    platform: str | None = None,
    target: Path | None = None,
) -> str:
    """Write the launcher that runs the native-messaging host, return its path.

    Chrome's manifest ``path`` must be an executable, so we generate a tiny
    wrapper that invokes the current interpreter on ``native_host``.
    """
    plat = platform or sys.platform
    py = python or sys.executable
    dest = Path(target) if target is not None else host_launcher_path(plat)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if plat.startswith("win"):
        dest.write_text(
            f'@echo off\r\n"{py}" -m computer_use.browser.native_host %*\r\n',
            encoding="utf-8",
        )
    else:
        dest.write_text(
            f'#!/bin/sh\nexec "{py}" -m computer_use.browser.native_host "$@"\n',
            encoding="utf-8",
        )
        dest.chmod(0o755)
    return str(dest)


def _winreg_writer(subkey: str, value: str) -> None:  # pragma: no cover - Windows only
    import winreg

    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, subkey)
    try:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, value)
    finally:
        winreg.CloseKey(key)


# Resolve reg.exe via the WSL interop path; falls back to PATH.
_REG_EXE = "/mnt/c/Windows/System32/reg.exe"


def reg_exe_writer(subkey: str, value: str, *, runner=None) -> None:
    """Set ``HKCU\\<subkey>`` default value via Windows ``reg.exe`` from WSL.

    This is the WSL analogue of ``_winreg_writer`` - cua-in-Linux cannot use
    ``winreg``, so it shells out to the Windows ``reg.exe`` over interop. The
    ``runner(argv)`` seam is injected in tests; it defaults to ``subprocess``.
    """
    import os

    reg = _REG_EXE if os.path.exists(_REG_EXE) else "reg.exe"
    argv = [
        reg, "ADD", f"HKCU\\{subkey}",
        "/ve", "/t", "REG_SZ", "/d", value, "/f",
    ]
    if runner is None:  # pragma: no cover - real interop
        import subprocess

        subprocess.run(
            argv, check=False, capture_output=True, timeout=10,
            # Never inherit fd 0: this reg.exe runs at startup on WSL (the #19
            # auto-registration path), and a child holding fd 0 (the stdio MCP
            # JSON-RPC pipe) stalls `initialize` - same class as #18.
            stdin=subprocess.DEVNULL,
        )
    else:
        runner(argv)


def register_windows_registry(
    manifest_path, browsers, *, writer=None, value=None
) -> list[str]:
    """Point each browser's HKCU native-host key at the manifest.

    ``writer(subkey, value)`` is injected in tests; defaults to a winreg write.
    ``value`` overrides the registry value (the WSL path uses the Windows-form
    ``C:\\...`` path, not the ``/mnt/c`` view).
    """
    write = writer or _winreg_writer
    val = value if value is not None else str(manifest_path)
    done: list[str] = []
    for browser in browsers:
        subkey = _WIN_REGISTRY_KEYS.get(browser)
        if subkey is None:
            continue
        write(subkey, val)
        done.append(browser)
    return done


def probe_windows_registry(*, reader=None) -> list[str]:
    """Return browsers whose HKCU registration points to a present manifest."""

    def read(subkey: str) -> str | None:  # pragma: no cover - Windows only
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey) as key:
                value, value_type = winreg.QueryValueEx(key, "")
        except OSError:
            return None
        if value_type not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
            return None
        return str(value)

    read_value = reader or read
    registered: list[str] = []
    for browser, subkey in _WIN_REGISTRY_KEYS.items():
        value = read_value(subkey)
        if value and Path(value).is_file():
            registered.append(browser)
    return registered


def _mnt_to_windows_path(p) -> str:
    """``/mnt/c/Users/..`` -> ``C:\\Users\\..`` (WSL view -> Windows form)."""
    from computer_use.platform.wsl2 import wsl_to_win_path

    return wsl_to_win_path(str(p))


def _resolve_platform(platform: str | None) -> str:
    """Effective platform string; WSL2 maps to the ``wsl`` branch.

    ``sys.platform`` is ``linux`` on WSL2, so a raw ``sys.platform`` never selects
    the WSL branch, and the Windows relay + registry (which the Windows Chrome
    actually driven on WSL reads) are never set up (issue #19). Resolve via the
    canonical detector instead.
    """
    if platform is not None:
        return platform
    from computer_use.platform.detect import Platform, detect_platform

    return "wsl" if detect_platform() is Platform.WSL2 else sys.platform


def _managed_package() -> bool:
    from computer_use.browser.profile import ProfileRefusal, load_package_trust

    try:
        return load_package_trust().get("mode") == "managed"
    except ProfileRefusal as error:
        repository = Path(__file__).resolve().parents[2]
        if error.code == "missing-package-trust" and (repository / ".git").exists():
            return False
        raise


def _adopted_relay() -> Path | None:
    from computer_use.browser.profile import ProfileRefusal
    from computer_use.browser.standalone_adoption import resolve

    try:
        result = resolve()
        return result["relay"] if result else None
    except ProfileRefusal as error:
        repository = Path(__file__).resolve().parents[2]
        if error.code == "missing-package-trust" and (repository / ".git").exists():
            return None
        raise


def ensure_registered(
    *,
    paths: dict | None = None,
    host_path: str | None = None,
    platform: str | None = None,
    registry_writer=None,
    relay_installer=None,
    windows_user: str | None = None,
) -> dict:
    """Self-register the native host so Chrome can reach cua - no manual step.

    Writes the launcher, the per-OS manifest, and the registry keys (Windows
    and WSL). On WSL cua-in-Linux targets the *Windows* Chrome it actually
    drives: the manifest is written under ``/mnt/c`` and the registry key is set
    via ``reg.exe`` interop. Idempotent: safe to call on every startup.
    """
    plat = _resolve_platform(platform)
    if plat == "wsl":
        targets = paths if paths is not None else manifest_paths(
            "wsl", windows_user=windows_user
        )
        # On WSL the manifest `path` must point at the Windows relay shim
        # (a .exe Chrome spawns on Windows); the launcher script is irrelevant.
        # Place the packaged relay shim where the manifest points - no manual copy.
        if host_path is None:
            if _managed_package():
                host, _local = _managed_relay()
            else:
                installed = (relay_installer or ensure_relay_exe)(
                    windows_user=windows_user
                )
                host = (
                    _mnt_to_windows_path(installed)
                    if isinstance(installed, Path)
                    else windows_relay_path(windows_user=windows_user)
                )
        else:
            host = host_path
        written = install_manifests(host, targets)
        reg = registry_writer or reg_exe_writer
        for browser, dest in targets.items():
            win_value = _mnt_to_windows_path(dest)
            register_windows_registry(
                dest, [browser], writer=reg, value=win_value
            )
        return {"host_path": host, "browsers": written, "platform": plat}

    targets = paths if paths is not None else manifest_paths(plat)
    if plat.startswith("win"):
        if host_path is None:
            if _managed_package():
                host, _local = _managed_relay()
            else:
                adopted = _adopted_relay()
                if adopted is not None:
                    host = str(adopted)
                else:
                    source = bundled_relay_exe()
                    destination = native_windows_relay_dest(src=source)
                    installed = (relay_installer or ensure_relay_exe)(src=source, dest=destination)
                    host = str(installed if isinstance(installed, Path) else destination)
        else:
            host = host_path
        written = install_manifests(host, targets)
        for browser, dest in targets.items():
            register_windows_registry(dest, [browser], writer=registry_writer)
        return {"host_path": host, "browsers": written, "platform": plat}

    host = host_path or write_launcher(platform=plat)
    written = install_manifests(host, targets)
    return {"host_path": host, "browsers": written, "platform": plat}


if __name__ == "__main__":  # `python -m computer_use.setup.extension_setup`
    result = ensure_registered()
    print(f"native host registered for: {', '.join(result['browsers'])}")
    print(f"host launcher: {result['host_path']}\n")
    print(load_steps())

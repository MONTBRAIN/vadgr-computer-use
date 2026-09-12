import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from computer_use.browser import windows_broker


def _fake_bundle(root: Path) -> tuple[Path, dict[str, object]]:
    package = root / "winbroker"
    package.mkdir()
    archive = package / windows_broker.BUNDLE_ARCHIVE
    archive.write_bytes(b"verified bundle")
    manifest = {
        "version": "0.7.6",
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "files": [{"path": "broker.exe", "sha256": "0" * 64}],
    }
    (package / windows_broker.BUNDLE_MANIFEST).write_text(json.dumps(manifest))
    return archive, manifest


def test_bundle_input_rejects_archive_tampering(tmp_path, monkeypatch):
    archive, _manifest = _fake_bundle(tmp_path)
    monkeypatch.setattr(windows_broker, "_package_root", lambda: tmp_path)
    archive.write_bytes(b"altered bundle")

    with pytest.raises(OSError, match="integrity verification"):
        windows_broker._bundle_inputs()


def test_endpoint_identity_requires_the_exact_packaged_bundle(tmp_path, monkeypatch):
    _archive, manifest = _fake_bundle(tmp_path)
    monkeypatch.setattr(windows_broker, "_package_root", lambda: tmp_path)
    endpoint = {
        "platform": "win32",
        "host": "127.0.0.1",
        "port": 12345,
        "token": "test-token",
        "epoch": "test-epoch",
        "bundle_hash": manifest["archive_sha256"],
        "pid": 123,
        "process_started_ns": "456",
    }
    assert windows_broker.validate_endpoint(endpoint) == manifest["archive_sha256"]

    endpoint["bundle_hash"] = "f" * 64
    with pytest.raises(windows_broker.WindowsBrokerStateError, match="does not match") as caught:
        windows_broker.validate_endpoint(endpoint)
    assert caught.value.code == "browser_broker_bundle_mismatch"

    del endpoint["bundle_hash"]
    with pytest.raises(
        windows_broker.WindowsBrokerStateError, match="identity verification"
    ) as caught:
        windows_broker.validate_endpoint(endpoint)
    assert caught.value.code == "browser_broker_discovery_invalid"


def test_windows_mount_path_is_converted_without_a_shell():
    assert windows_broker._windows_path(Path("/mnt/c/Users/Owner/file.zip")) == (
        "C:\\Users\\Owner\\file.zip"
    )


def test_wsl_proxy_uses_a_windows_accessible_path(tmp_path, monkeypatch):
    proxy = tmp_path / "native-host" / windows_broker.PROXY_EXECUTABLE
    sentinel = object()
    captured = {}

    monkeypatch.setattr("computer_use.setup.extension_setup.ensure_relay_exe", lambda: proxy)

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return sentinel

    monkeypatch.setattr(windows_broker.subprocess, "Popen", fake_popen)

    assert windows_broker.open_windows_proxy() is sentinel
    assert captured["command"] == [str(proxy), "broker-proxy"]
    assert captured["kwargs"] == {
        "stdin": windows_broker.subprocess.PIPE,
        "stdout": windows_broker.subprocess.PIPE,
        "stderr": windows_broker.subprocess.DEVNULL,
        "close_fds": True,
    }


def test_launch_paths_travel_as_data_not_powershell_source(monkeypatch):
    bundle = "C:\\test spaces\\O'Brien $([int]7) `literal` é\\bundle"
    monkeypatch.setattr(windows_broker, "deployed_bundle", lambda: (bundle, {}))
    captured = {}

    def capture(command, **kwargs):
        captured.update(command=command, options=kwargs)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(windows_broker.subprocess, "run", capture)
    windows_broker.launch_windows_broker()
    assert len(captured["command"]) == 5
    assert captured["command"][:4] == [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
    ]
    assert bundle not in captured["command"][-1]
    assert captured["command"][-1].startswith("$env:PSModulePath = $PSHOME + '\\Modules'; ")
    assert json.loads(captured["options"]["input"]) == {
        "executable": bundle + "\\" + windows_broker.BROKER_EXECUTABLE,
        "directory": bundle,
    }
    assert captured["options"]["input"].isascii()
    assert captured["options"]["text"] is True
    assert "stdin" not in captured["options"]


@pytest.mark.skipif(sys.platform != "win32", reason="real native PowerShell parsing")
@pytest.mark.parametrize("start_fails", [False, True])
def test_native_launch_path_roundtrip_without_launching_a_process(monkeypatch, start_fails):
    bundle = "C:\\test spaces\\O'Brien $([int]7) `literal` é\\bundle"
    monkeypatch.setattr(windows_broker, "deployed_bundle", lambda: (bundle, {}))
    real_run = subprocess.run
    observed = {}
    # These in-process functions replace both filesystem probing and launch.
    # The real PowerShell parser still receives the exact product command/data.
    replacements = (
        "[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false); "
        "function Test-Path { [CmdletBinding()] param($LiteralPath,$PathType) return $true }; "
        "function Start-Process { [CmdletBinding()] "
        "param($FilePath,$ArgumentList,$WorkingDirectory,$WindowStyle) "
    )
    replacements += (
        "throw 'fixture launch failure' }; "
        if start_fails
        else "@{executable=$FilePath;directory=$WorkingDirectory;"
        "arguments=@($ArgumentList);window=$WindowStyle}|ConvertTo-Json -Compress }; "
    )

    def probe(command, **kwargs):
        amended = list(command)
        amended[4] = replacements + amended[4]
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
        result = real_run(amended, **kwargs)
        observed["result"] = result
        return result

    monkeypatch.setattr(windows_broker.subprocess, "run", probe)
    if start_fails:
        with pytest.raises(OSError, match="failed to launch"):
            windows_broker.launch_windows_broker()
        assert observed["result"].returncode != 0
    else:
        windows_broker.launch_windows_broker()
        assert observed["result"].returncode == 0
        assert json.loads(observed["result"].stdout) == {
            "executable": bundle + "\\" + windows_broker.BROKER_EXECUTABLE,
            "directory": bundle,
            "arguments": ["serve"],
            "window": "Hidden",
        }

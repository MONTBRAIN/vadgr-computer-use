import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from computer_use.browser import windows_broker
from computer_use.browser.profile import ReleaseProfile


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


def test_profile_bundle_uses_only_the_selected_architecture(tmp_path, monkeypatch):
    archive = tmp_path / "computer_use/browser/winbroker/aarch64/broker.zip"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"arm64 broker")
    member_manifest = tmp_path / "computer_use/browser/winbroker/aarch64/broker.manifest.json"
    member_manifest.write_text(
        json.dumps(
            {
                "architecture": "aarch64",
                "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    manifest = {
        "helpers": {
            "architecture": "aarch64",
            "archive": {
                "path": "computer_use/browser/winbroker/aarch64/broker.zip",
                "size": archive.stat().st_size,
                "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            },
            "member_manifest": {
                "path": "computer_use/browser/winbroker/aarch64/broker.manifest.json",
                "size": member_manifest.stat().st_size,
                "sha256": hashlib.sha256(member_manifest.read_bytes()).hexdigest(),
            },
        }
    }
    monkeypatch.setattr(windows_broker, "_distribution_root", lambda: tmp_path)
    monkeypatch.setattr(
        "computer_use.browser.profile.select_profile",
        lambda: ReleaseProfile.WINDOWS_AARCH64,
    )
    monkeypatch.setattr(
        "computer_use.browser.profile.load_input_manifest", lambda _profile: manifest
    )

    selected_archive, selected_manifest, selected_metadata = (
        windows_broker._profile_bundle_inputs()
    )

    assert selected_archive == archive
    assert selected_manifest == member_manifest
    assert selected_metadata["architecture"] == "aarch64"


def test_managed_deployment_requires_digest_bound_receipt(tmp_path, monkeypatch):
    archive = tmp_path / "broker.zip"
    archive.write_bytes(b"signed broker")
    manifest_path = tmp_path / "broker-final-manifest.json"
    manifest_path.write_bytes(b"manifest bytes")
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    manifest = {
        "mode": "managed-signed",
        "cua_version": "0.7.9",
        "archive": {"path": "broker.zip", "size": archive.stat().st_size, "sha256": archive_hash},
        "files": [{"path": "broker.exe"}],
    }
    reports = tmp_path / "managed-helpers" / "x86_64" / "signature-reports.json"
    reports.parent.mkdir(parents=True)
    reports.write_text("{}")
    monkeypatch.setattr(
        windows_broker, "_bundle_inputs", lambda: (archive, manifest_path, manifest)
    )
    monkeypatch.setattr(
        windows_broker, "_package_root", lambda: Path(__file__).resolve().parents[1] / "browser"
    )
    monkeypatch.setattr(
        "computer_use.browser.profile.load_package_trust",
        lambda: {"mode": "managed", "release_profile": "windows-x86_64"},
    )
    monkeypatch.setattr(
        "computer_use.browser.profile.select_profile",
        lambda: SimpleNamespace(architecture="x86_64"),
    )
    monkeypatch.setattr(
        "computer_use.browser.managed_authorization.managed_launch_authorization",
        lambda *_args, **_kwargs: ({"installed_root": "C:\\installed\\lib\\cua"}, manifest),
    )
    translated = []

    def local_path(value):
        translated.append(value)
        return tmp_path

    monkeypatch.setattr("computer_use.browser.offline_attestation.local_path", local_path)

    def run(_command, **_kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "destination": f"C:\\state\\0.7.9\\{archive_hash}",
                    "archive_sha256": archive_hash,
                    "broker_final_manifest_sha256": manifest_hash,
                    "member_count": 1,
                }
            ),
        )

    monkeypatch.setattr(windows_broker.subprocess, "run", run)

    destination, returned_manifest = windows_broker.deployed_bundle()

    assert destination.endswith(archive_hash)
    assert returned_manifest is manifest
    assert translated == ["C:\\installed\\lib\\cua"]


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
        "process_created_filetime": "789",
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


def test_wsl_windows_children_receive_windows_isolation_paths(monkeypatch):
    monkeypatch.setattr(windows_broker.sys, "platform", "linux")
    monkeypatch.setenv("LOCALAPPDATA", "/mnt/c/test/local")
    monkeypatch.setenv(
        "VADGR_CUA_BROKER_ENDPOINT", "/mnt/c/test/state/browser-broker.json"
    )
    monkeypatch.setenv(
        "VADGR_CUA_BROWSER_DISCOVERY", "/mnt/c/test/state/browser.port"
    )

    environment = windows_broker._windows_child_environment()

    assert environment["VADGR_CUA_WINDOWS_LOCAL_APP_DATA"] == "C:\\test\\local"
    assert environment["VADGR_CUA_BROKER_ENDPOINT"] == (
        "C:\\test\\state\\browser-broker.json"
    )
    assert environment["VADGR_CUA_BROWSER_DISCOVERY"] == (
        "C:\\test\\state\\browser.port"
    )
    forwarded = environment["WSLENV"].split(":")
    assert "VADGR_CUA_WINDOWS_LOCAL_APP_DATA" in forwarded
    assert "VADGR_CUA_BROKER_ENDPOINT" in forwarded
    assert "VADGR_CUA_BROWSER_DISCOVERY" in forwarded


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
    environment = captured["kwargs"].pop("env")
    assert environment == windows_broker._windows_child_environment()
    assert captured["kwargs"] == {
        "stdin": windows_broker.subprocess.PIPE,
        "stdout": windows_broker.subprocess.PIPE,
        "stderr": windows_broker.subprocess.DEVNULL,
        "close_fds": True,
    }


def test_launch_paths_travel_as_data_not_powershell_source(monkeypatch):
    bundle = "C:\\test spaces\\O'Brien $([int]7) `literal` é\\bundle"
    monkeypatch.setattr(windows_broker, "deployed_bundle", lambda: (bundle, {}))
    monkeypatch.setattr(
        windows_broker, "_run_upgrade_handoff", lambda _bundle: {"state": "no_predecessor"}
    )
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


def test_upgrade_handoff_paths_travel_as_data_not_powershell_source(monkeypatch):
    bundle = "C:\\test spaces\\O'Brien $([int]7) `literal` é\\bundle"
    captured = {}

    def capture(command, **kwargs):
        captured.update(command=command, options=kwargs)
        return SimpleNamespace(
            returncode=0,
            stdout='{"state":"replaced","version":"0.7.7"}\n',
        )

    monkeypatch.setattr(windows_broker.subprocess, "run", capture)
    assert windows_broker._run_upgrade_handoff(bundle) == {
        "state": "replaced",
        "version": "0.7.7",
    }
    assert bundle not in captured["command"][-1]
    assert json.loads(captured["options"]["input"]) == {
        "executable": bundle + "\\" + windows_broker.BROKER_EXECUTABLE,
        "authorization": None,
    }


def test_upgrade_handoff_passes_authenticated_transition_as_data(monkeypatch, tmp_path):
    authorization = tmp_path / "helper-closure-authorization.json"
    authorization.write_bytes(b"authorization")
    digest = "a" * 64
    captured = {}
    monkeypatch.setattr(
        windows_broker, "_handoff_authorization", lambda: (authorization, digest)
    )
    monkeypatch.setattr(windows_broker, "_windows_path", lambda path: str(path))

    def capture(command, **kwargs):
        captured.update(command=command, options=kwargs)
        return SimpleNamespace(returncode=0, stdout='{"state":"replaced"}\n')

    monkeypatch.setattr(windows_broker.subprocess, "run", capture)

    assert windows_broker._run_upgrade_handoff("C:\\bundle") == {"state": "replaced"}
    request = json.loads(captured["options"]["input"])
    assert request["authorization"] == {"path": str(authorization), "sha256": digest}
    assert str(authorization) not in captured["command"][-1]


def test_upgrade_handoff_preserves_exact_safe_failure(monkeypatch):
    reply = {
        "state": "refused",
        "code": "browser_broker_upgrade_unsafe",
        "message": "specific proof failure",
        "remediation": "specific safe remedy",
    }
    monkeypatch.setattr(
        windows_broker.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(reply) + "\n"),
    )

    with pytest.raises(windows_broker.WindowsBrokerStateError) as caught:
        windows_broker._run_upgrade_handoff("C:\\bundle")

    assert caught.value.code == "browser_broker_upgrade_unsafe"
    assert caught.value.remediation == "specific safe remedy"


def test_running_candidate_is_not_started_again(monkeypatch):
    monkeypatch.setattr(windows_broker, "deployed_bundle", lambda: ("C:\\bundle", {}))
    monkeypatch.setattr(
        windows_broker, "_run_upgrade_handoff", lambda _bundle: {"state": "candidate_ready"}
    )
    monkeypatch.setattr(
        windows_broker.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("candidate must not be launched again"),
    )

    windows_broker.launch_windows_broker()


@pytest.mark.skipif(sys.platform != "win32", reason="real native PowerShell parsing")
@pytest.mark.parametrize("start_fails", [False, True])
def test_native_launch_path_roundtrip_without_launching_a_process(monkeypatch, start_fails):
    bundle = "C:\\test spaces\\O'Brien $([int]7) `literal` é\\bundle"
    monkeypatch.setattr(windows_broker, "deployed_bundle", lambda: (bundle, {}))
    monkeypatch.setattr(
        windows_broker, "_run_upgrade_handoff", lambda _bundle: {"state": "no_predecessor"}
    )
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

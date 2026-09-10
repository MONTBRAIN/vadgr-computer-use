"""Exercise the real installer publication race without launching a broker."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest


@pytest.fixture
def installer_root():
    # Pytest's descriptive directory plus the content hash can exceed legacy
    # PowerShell's path limit on hosted runners. This test targets publication.
    with tempfile.TemporaryDirectory(prefix="cua-install-") as directory:
        yield Path(directory)


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows installer filesystem")
@pytest.mark.parametrize("winner_valid", [True, False])
@pytest.mark.parametrize("foreign_modules", [False, True])
def test_installer_never_nests_staging_inside_a_concurrent_winner(
    installer_root, winner_valid, foreign_modules,
):
    tmp_path = installer_root
    root = Path(__file__).resolve().parents[2]
    installer = root / "computer_use/browser/winbroker/install.ps1"
    payload = b"installer fixture, never executed"
    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("broker.exe", payload)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "version": "0.7.6", "archive_sha256": digest,
        "files": [{"path": "broker.exe", "sha256": hashlib.sha256(payload).hexdigest()}],
    }), encoding="utf-8")
    # A second installer publishes after the initial existence check but before
    # this installer's rename. The real publication and cleanup code runs intact.
    anchor = '    $owner = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name'
    source = installer.read_text(encoding="utf-8")
    assert source.count(anchor) == 1
    competing_publish = '    Copy-Item -LiteralPath $staging -Destination $destination -Recurse\n'
    if not winner_valid:
        competing_publish += "    Set-Content -LiteralPath (Join-Path $destination 'broker.exe') -Value 'corrupt'\n"
    probe = tmp_path / "installer.ps1"
    probe.write_text(source.replace(anchor, competing_publish + anchor), encoding="utf-8")
    local = tmp_path / "local data"
    env = dict(os.environ, LOCALAPPDATA=str(local))
    if foreign_modules:
        # Model a PowerShell 7 parent passing incompatible modules through Python.
        modules = tmp_path / "foreign modules"
        utility = modules / "Microsoft.PowerShell.Utility"
        utility.mkdir(parents=True)
        (utility / "Microsoft.PowerShell.Utility.psd1").write_text(
            "@{ ModuleVersion = '7.0.0'; RootModule = 'foreign.psm1'; "
            "FunctionsToExport = @('Get-FileHash', 'ConvertFrom-Json') }",
            encoding="utf-8",
        )
        (utility / "foreign.psm1").write_text(
            "function ConvertFrom-Json { throw 'incompatible parent module fixture' }; "
            "function Get-FileHash { throw 'incompatible parent module fixture' }",
            encoding="utf-8",
        )
        system_modules = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/Modules"
        env["PSModulePath"] = str(modules) + os.pathsep + str(system_modules)
    result = subprocess.run([
        "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", str(probe), "-Archive", str(archive), "-Manifest", str(manifest),
    ], env=env, capture_output=True, text=True, timeout=30)
    destination = local / "vadgr-cua/browser-broker/0.7.6" / digest
    assert destination.is_dir(), (result.returncode, result.stdout, result.stderr)
    assert sorted(p.name for p in destination.iterdir()) == ["broker.exe", "bundle-manifest.json"]
    assert not list(destination.parent.glob(".*"))
    if winner_valid:
        assert result.returncode == 0, result.stderr
        assert destination.joinpath("broker.exe").read_bytes() == payload
        assert result.stdout.strip() == str(destination)
    else:
        assert result.returncode != 0
        assert destination.joinpath("broker.exe").read_bytes() != payload

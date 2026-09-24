"""Exercise managed deployment without manufacturing an Authenticode verdict."""

import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _managed_case(tmp_path):
    repository = Path(__file__).resolve().parents[2]
    installer = repository / "computer_use/browser/winbroker/install-managed.ps1"
    payload = b"nonexecutable fixture"
    archive = tmp_path / "broker.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as output:
        output.writestr("NOTICE.txt", payload)
    archive_bytes = archive.read_bytes()
    manifest_value = {
        "schema": 1,
        "mode": "managed-signed",
        "cua_version": "0.7.9",
        "archive": {
            "path": "broker.zip",
            "size": len(archive_bytes),
            "sha256": _sha256(archive_bytes),
        },
        "files": [
            {
                "path": "NOTICE.txt",
                "size": len(payload),
                "sha256": _sha256(payload),
                "trust_class": "data",
                "signature_report_sha256": None,
            }
        ],
    }
    manifest = tmp_path / "broker-final-manifest.json"
    manifest.write_text(json.dumps(manifest_value), encoding="utf-8")
    reports = tmp_path / "reports"
    reports.mkdir()
    local = tmp_path / "local"
    environment = dict(
        os.environ,
        LOCALAPPDATA=str(local),
        VADGR_CUA_RELEASE_PROFILE="windows-x86_64",
    )

    command = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(installer),
            "-Archive",
            str(archive),
            "-Manifest",
            str(manifest),
            "-ExpectedManifestSha256",
            _sha256(manifest.read_bytes()),
            "-SignatureReports",
            str(reports),
        ]
    result = subprocess.run(
        command,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout.strip().splitlines()[-1])
    assert receipt["profile"] == "windows-x86_64"
    assert receipt["archive_sha256"] == _sha256(archive_bytes)
    assert receipt["broker_final_manifest_sha256"] == _sha256(manifest.read_bytes())
    assert Path(receipt["destination"], "NOTICE.txt").read_bytes() == payload
    return command, environment, Path(receipt["destination"])


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows deployment")
def test_data_only_managed_fixture_deploys_and_returns_bound_receipt(tmp_path):
    command, environment, _destination = _managed_case(tmp_path)
    reused = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=30)
    assert reused.returncode == 0, reused.stderr


def _powershell(action, path):
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
         "$ErrorActionPreference='Stop'; $env:PSModulePath=$PSHOME+'\\Modules'; "
         "Import-Module -Name (Join-Path $PSHOME 'Modules\\Microsoft.PowerShell.Security\\Microsoft.PowerShell.Security.psd1') -Force; "
         "$p=[Console]::In.ReadToEnd(); " + action],
        input=str(path), capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows deployment")
@pytest.mark.parametrize("damage", [
    "missing-manifest", "changed-manifest", "nested-manifest", "hidden-extra",
    "hardlink-member", "hardlink-manifest", "extra-principal", "inherited-root", "junction",
])
def test_managed_reuse_refuses_damaged_or_unprotected_closure(tmp_path, damage):
    command, environment, destination = _managed_case(tmp_path)
    manifest = destination / "broker-final-manifest.json"
    if damage == "missing-manifest":
        manifest.unlink()
    elif damage == "changed-manifest":
        manifest.write_bytes(b"{}")
    elif damage == "nested-manifest":
        nested = destination / "nested"
        nested.mkdir()
        (nested / manifest.name).write_bytes(manifest.read_bytes())
    elif damage == "hidden-extra":
        extra = destination / "extra.dll"
        extra.write_bytes(b"unexpected")
        _powershell("(Get-Item -LiteralPath $p).Attributes='Hidden'", extra)
    elif damage.startswith("hardlink"):
        member = manifest if damage == "hardlink-manifest" else destination / "NOTICE.txt"
        os.link(member, tmp_path / "outside-link")
    elif damage == "extra-principal":
        _powershell(
            "$a=Get-Acl -LiteralPath $p; $s=[Security.Principal.SecurityIdentifier]::new('S-1-5-32-545');"
            "$a.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($s,'Read','Allow'));"
            "Set-Acl -LiteralPath $p -AclObject $a", destination / "NOTICE.txt",
        )
    elif damage == "inherited-root":
        _powershell(
            "& icacls.exe $p /inheritance:e | Out-Null; if($LASTEXITCODE -ne 0){throw 'ACL setup failed'}",
            destination,
        )
    else:
        moved = destination.with_name("moved")
        destination.rename(moved)
        _powershell(
            "$target=Join-Path (Split-Path $p) 'moved';"
            "New-Item -ItemType Junction -Path $p -Target $target | Out-Null", destination,
        )
    result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=30)
    assert result.returncode != 0, result.stdout
    assert not result.stdout.strip()


def test_managed_installer_requires_native_signature_and_timestamp_checks():
    repository = Path(__file__).resolve().parents[2]
    source = (
        repository / "computer_use/browser/winbroker/install-managed.ps1"
    ).read_text(encoding="utf-8")
    assert "Get-AuthenticodeSignature" in source
    assert "SignatureStatus]::Valid" in source
    assert "TimeStamperCertificate" in source
    assert "chain_root_sha256" in source
    assert "certificate_sha256" in source
    assert "Assert-NoReparseParent" in source


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows ACL conversion")
@pytest.mark.parametrize("damage", ["none", "extra-principal", "file"])
def test_adoption_converts_only_safe_inherited_parent(tmp_path, damage):
    source = Path(__file__).resolve().parents[2] / "computer_use/browser/winbroker/adopt-native.ps1"
    request = {"source": str(source), "root": str(tmp_path / "private"), "damage": damage}
    script = r"""
$ErrorActionPreference='Stop'
$env:PSModulePath=$PSHOME+'\Modules'
Import-Module -Name (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1') -Force
$v=[Console]::In.ReadToEnd() | ConvertFrom-Json
$owner=[Security.Principal.WindowsIdentity]::GetCurrent().User
$system=[Security.Principal.SecurityIdentifier]::new('S-1-5-18')
$tokens=$null; $errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($v.source,[ref]$tokens,[ref]$errors)
$names=@('Assert-Path','Assert-Private','Protect-Directory')
foreach($f in $ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -in $names},$false)) {
 Invoke-Expression $f.Extent.Text
}
Protect-Directory $v.root
$child=Join-Path $v.root 'existing'
if($v.damage -eq 'file') {[IO.File]::WriteAllText($child,'ordinary file')}
else {[IO.Directory]::CreateDirectory($child) | Out-Null}
if($v.damage -eq 'extra-principal') {
 $a=Get-Acl -LiteralPath $child
 $a.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
  [Security.Principal.SecurityIdentifier]::new('S-1-5-32-545'),'Read','Allow'))
 Set-Acl -LiteralPath $child -AclObject $a
}
$before=(Get-Acl -LiteralPath $child).Sddl
$inherited=-not (Get-Acl -LiteralPath $child).AreAccessRulesProtected
$accepted=$true
try { Protect-Directory $child } catch { $accepted=$false }
$after=Get-Acl -LiteralPath $child
@{accepted=$accepted; inherited=$inherited; protected=$after.AreAccessRulesProtected; unchanged=($before -ceq $after.Sddl)} | ConvertTo-Json -Compress
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        input=json.dumps(request), capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)
    assert observed["inherited"] is True
    if damage == "none":
        assert observed["accepted"] is True and observed["protected"] is True
    else:
        assert observed["accepted"] is False and observed["unchanged"] is True

"""Native closure SBOM tests use isolated bytes, never synthetic trust verdicts."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import broker_sbom as sbom
from build_profile_wheels import make_zip


def test_native_members_must_match_the_exact_pinned_python_distribution(tmp_path):
    bundle, python = tmp_path / "bundle", tmp_path / "python"
    (bundle / "_internal").mkdir(parents=True)
    (python / "DLLs").mkdir(parents=True)
    for name in ("python312.dll", "libcrypto-3-x64.dll", "libffi-8.dll", "vcruntime140.dll"):
        (bundle / "_internal" / name).write_bytes(name.encode())
        (python / "DLLs" / name).write_bytes(name.encode())
    result = sbom.python_origins(bundle, python)
    assert {row["component"] for row in result.values()} == {
        "CPython",
        "OpenSSL",
        "libffi",
        "Microsoft-VC-runtime",
    }
    (bundle / "_internal/libffi-8.dll").write_bytes(b"changed")
    with pytest.raises(ValueError, match="exact pinned Python input"):
        sbom.python_origins(bundle, python)


def test_unknown_native_member_cannot_disappear_into_generic_python_component():
    with pytest.raises(ValueError, match="unclassified"):
        sbom.native_component("unreviewed.dll")


def test_sbom_covers_nested_bytes_bootloader_relay_and_independent_legal_boundary(tmp_path):
    bundle = tmp_path / "bundle"
    (bundle / "_internal").mkdir(parents=True)
    (bundle / "_internal/python312.dll").write_bytes(b"python")
    (bundle / "_internal/vcruntime140.dll").write_bytes(b"vendor")
    (bundle / "_internal/base_library.zip").write_bytes(make_zip({"module.pyc": b"bytecode"}))
    (bundle / "vadgr-cua-browser-broker.exe").write_bytes(b"bootloader")
    relay = tmp_path / "relay.exe"
    relay.write_bytes(b"go relay")
    receipt = {
        "python_members": {
            "_internal/python312.dll": {"component": "CPython"},
            "_internal/vcruntime140.dll": {"component": "Microsoft-VC-runtime"},
        },
        "static_python_components": ["zlib"],
        "runtime_versions": {"CPython": "3.12.14"},
        "pyinstaller": {"version": "6.22.2"},
    }
    result = sbom.build_sbom(
        bundle,
        relay,
        "0.7.9",
        "x86_64",
        "a" * 40,
        {"url": "https://example.test/pinned-python", "sha256": "b" * 64},
        receipt,
    )
    assert len(result["files"]) == 6
    assert any(row["fileName"].endswith("base_library.zip!/module.pyc") for row in result["files"])
    packages = {row["name"]: row for row in result["packages"]}
    assert packages["Microsoft-VC-runtime"]["licenseConcluded"] == "NOASSERTION"
    assert packages["PyInstaller-bootloader-and-CUA"]["versionInfo"] == "6.22.2"
    assert "Go-runtime-and-CUA-relay" in packages
    assert any(row["relationshipType"] == "STATIC_LINK" for row in result["relationships"])

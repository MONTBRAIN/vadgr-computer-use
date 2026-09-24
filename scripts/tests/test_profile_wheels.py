"""Packaging tests start from an isolated source tree and synthetic data-only PE fixtures."""

import io
import struct
import sys
import zipfile
from pathlib import Path

import pytest
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_profile_wheels as build
import check_profile_wheels as check


def test_generic_setuptools_wheel_cannot_ship_native_helpers():
    project = tomllib.loads((Path(__file__).resolve().parents[2] / "pyproject.toml").read_text())
    package_data = project["tool"]["setuptools"]["package-data"]
    assert "computer_use.browser.winhost" not in package_data
    assert "computer_use.browser.winbroker" not in package_data


def pe(architecture):
    data = bytearray(128)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 60, 64)
    data[64:68] = b"PE\0\0"
    struct.pack_into("<H", data, 68, {"x86_64": 0x8664, "aarch64": 0xAA64}[architecture])
    return bytes(data)


@pytest.mark.parametrize(
    "name",
    [
        "../evil",
        "/evil",
        "C:/evil",
        "a\\b",
        "a:stream",
        "a/../b",
        "CON.txt",
        "nul",
        "a/COM1",
        "a.",
        "a ",
        "a//b",
        "./a",
    ],
)
def test_rejects_unsafe_paths(name):
    with pytest.raises(ValueError):
        build.safe_path(name)


@pytest.mark.parametrize("names", [("a", "A"), ("a", "a"), ("a", "a/b"), ("A", "a/b")])
def test_rejects_duplicate_case_and_parent_collisions(names):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name in names:
            archive.writestr(name, b"x")
    with pytest.raises(ValueError):
        build.zip_members(stream.getvalue())


def test_rejects_symlink_and_expansion_budget(monkeypatch):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        info = zipfile.ZipInfo("link")
        info.external_attr = 0o120777 << 16
        archive.writestr(info, b"target")
    with pytest.raises(ValueError, match="non-regular"):
        build.zip_members(stream.getvalue())
    raw = build.make_zip({"one": b"abc"})
    monkeypatch.setattr(build, "MAX_BYTES", 2)
    with pytest.raises(ValueError, match="budget"):
        build.zip_members(raw)


def test_rejects_duplicate_and_noncanonical_json():
    for raw in (b'{"a":1,"a":2}', b'{"a":1}', b'{"z": 1, "a": 2}\n'):
        with pytest.raises(ValueError):
            build.read_json(raw)


def test_nested_pe_is_discovered_without_extension():
    raw = build.make_zip({"opaque": pe("aarch64")})
    executable, archives = build.inventory(
        {build.PREFIX + "winbroker/aarch64/broker.zip": raw}, "wsl-aarch64"
    )
    assert executable[0]["architecture"] == "aarch64"
    assert executable[0]["role"] == "browser-broker"
    assert executable[0]["archive_members"] == ["opaque"]
    assert archives[0]["members"][0]["path"] == "opaque"


@pytest.mark.parametrize("profile", ["linux-x86_64", "macos-x86_64", "wsl-aarch64"])
def test_wrong_native_architecture_or_os_refuses(profile):
    with pytest.raises(ValueError):
        build.inventory({build.PREFIX + "winhost/x86_64/relay.exe": pe("x86_64")}, profile)


@pytest.mark.parametrize(
    "name,data",
    [
        ("catalog.json", b"#!/bin/sh\nexit 0\n"),
        ("hidden.dat", b"\x1f\x8bopaque"),
        ("broken.zip", b"bad"),
    ],
)
def test_unknown_containers_and_disguised_scripts_refuse(name, data):
    with pytest.raises(ValueError):
        build.inventory({name: data}, "linux-x86_64")


def test_freeze_cannot_rewrite_an_existing_object(tmp_path):
    path = tmp_path / "manifest.json"
    build.freeze(path, b"first")
    with pytest.raises(FileExistsError):
        build.freeze(path, b"second")
    assert path.read_bytes() == b"first"


@pytest.fixture
def package_inputs(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "pyproject.toml").write_text("""[project]
name = "vadgr-computer-use"
version = "0.7.9"
requires-python = ">=3.10"
description = "fixture"
dependencies = []
[project.scripts]
vadgr-cua = "computer_use.mcp_server:main"
""")
    (source / "LICENSE").write_text("Apache-2.0")
    code = source / "computer_use"
    code.mkdir()
    (code / "__init__.py").write_text("")
    broker = code / "browser" / "winbroker"
    broker.mkdir(parents=True)
    for name in ("install.ps1", "install-managed.ps1", "adopt-native.ps1"):
        (broker / name).write_text("param()\n")
    (broker / "predecessor-catalog.json").write_bytes(build.canonical({"schema": 1}))
    commit = "a" * 40
    producer = {
        "repository": "MONTBRAIN/vadgr-computer-use",
        "repository_id": 1215350293,
        "owner_id": 165305289,
        "source_commit": commit,
        "tooling_commit": commit,
        "workflow": ".github/workflows/profile-wheels.yml",
        "workflow_id": 3,
        "ref": "refs/heads/master",
        "event": "workflow_dispatch",
        "run_id": 4,
        "attempt": 1,
        "runner_environment": "github-hosted",
    }
    evidence = {
        "build_sha256": "1" * 64,
        "test_sha256": "2" * 64,
        "sbom_sha256": "3" * 64,
        "native_job_ids": [5],
        "artifacts": [{"id": 6, "sha256": "4" * 64}],
    }
    descriptor = {"producer": producer, "profiles": {p: evidence for p in build.PROFILES}}
    helpers, adoption = {}, tmp_path / "adoption"
    for architecture in ("x86_64", "aarch64"):
        directory = tmp_path / architecture
        directory.mkdir()
        helpers[architecture] = directory
        (directory / "vadgr-cua-host.exe").write_bytes(pe(architecture))
        members = {"vadgr-cua-browser-broker.exe": pe(architecture), "LICENSE": b"notice"}
        archive = build.make_zip(members)
        (directory / "broker.zip").write_bytes(archive)
        manifest = {
            "schema": 1,
            "version": "0.7.9",
            "source_commit": commit,
            "target": architecture + "-pc-windows-msvc",
            "archive_sha256": build.digest(archive),
            "archive_size": len(archive),
            "files": [build.identity(p, b) for p, b in sorted(members.items())],
        }
        (directory / "broker.manifest.json").write_bytes(build.canonical(manifest))
        _, helper = build.helper_files(directory, architecture, "0.7.9", commit)
        policy_directory = adoption / architecture
        policy_directory.mkdir(parents=True)
        root = build.canonical({"trusted": "fixture"})
        policy = {
            "schema": 1,
            "architecture": architecture,
            "cua_version": "0.7.9",
            "source_commit": commit,
            "input_closure": {
                "relay_sha256": helper["relay"]["sha256"],
                "archive_sha256": helper["archive"]["sha256"],
                "manifest_sha256": helper["member_manifest"]["sha256"],
            },
            "root_sha256": build.digest(root),
            "verifier_sha256": build.digest(pe(architecture)),
            "repository": "MONTBRAIN/vadgr",
            "repository_id": 1158230114,
            "owner_id": 165305289,
            "certificate_identity": "https://github.com/MONTBRAIN/vadgr/.github/workflows/candidate.yml@refs/heads/master",
            "issuer": "https://token.actions.githubusercontent.com",
            "source_ref": "refs/heads/master",
            "source_sha_allowlist": ["c" * 40],
            "signer_sha_allowlist": ["d" * 40],
            "expires_at": 4102444800,
            "relay_path": "vadgr-cua-browser-broker.exe",
            "files": {"vadgr-cua-browser-broker.exe": {"trust_class": "publisher-sign"}},
        }
        for name, data in {
            "adoption-policy.json": build.canonical(policy),
            "trusted-root.json": root,
            "gh.exe": pe(architecture),
            "LICENSE": b"MIT fixture",
        }.items():
            (policy_directory / name).write_bytes(data)
    return source, helpers, tmp_path / "output", descriptor, adoption


def test_construct_and_validate_all_nine_wheels(package_inputs):
    source, helpers, output, descriptor, adoption = package_inputs
    catalog = build.build(source, helpers, output, descriptor, adoption)
    assert check.check_catalog(output / "cua-profile-catalog.json") == catalog
    assert len(list(output.glob("*.whl"))) == 9
    assert len({e["wheel"]["filename"] for e in catalog["profiles"].values()}) == 8
    for profile, entry in catalog["profiles"].items():
        files = build.zip_members((output / entry["wheel"]["filename"]).read_bytes())
        assert check.package_trust(files)["mode"] == "managed"
        build_tag = "1" + profile.replace("-", "").replace("_", "")
        metadata = files["vadgr_computer_use-0.7.9.dist-info/WHEEL"].decode()
        assert f"Build: {build_tag}\n" in metadata
        if profile.startswith(("linux-", "macos-")):
            assert not any(name.endswith((".exe", ".zip", ".ps1")) for name in files)


@pytest.mark.parametrize(
    "mutation", ["extra-wheel", "missing-marker", "changed-member", "wrong-role"]
)
def test_rejects_rehashed_adversarial_profile(package_inputs, mutation):
    source, helpers, output, descriptor, adoption = package_inputs
    catalog = build.build(source, helpers, output, descriptor, adoption)
    entry = catalog["profiles"]["windows-x86_64"]
    wheel_path = output / entry["wheel"]["filename"]
    files = build.zip_members(wheel_path.read_bytes())
    manifest_path = build.PREFIX + "profiles/windows-x86_64/cua-profile-manifest.json"
    manifest = build.read_json(files[manifest_path])
    if mutation == "extra-wheel":
        files["computer_use/uncataloged.exe"] = pe("x86_64")
    elif mutation == "missing-marker":
        files.pop(build.PREFIX + "_profile_trust.py")
    elif mutation == "changed-member":
        path = manifest["helpers"]["relay"]["path"]
        files[path] += b"changed"
    else:
        manifest["executables"][0]["role"] = "unknown"
        raw = build.canonical(manifest)
        files[manifest_path] = raw
        (output / entry["input_role_manifest"]["filename"]).write_bytes(raw)
        entry["input_role_manifest"] = build.identity(
            entry["input_role_manifest"]["filename"], raw, "filename"
        )
    tag = "py3-none-win_amd64"
    raw = build.wheel_bytes(
        {p: b for p, b in files.items() if not p.endswith(".dist-info/RECORD")},
        {
            "version": "0.7.9",
            "requires-python": ">=3.10",
            "description": "fixture",
            "dependencies": [],
            "scripts": {"vadgr-cua": "computer_use.mcp_server:main"},
        },
        tag,
        build_tag="1windowsx8664",
    )
    wheel_path.write_bytes(raw)
    entry["wheel"] = build.identity(wheel_path.name, raw, "filename")
    (output / "cua-profile-catalog.json").write_bytes(build.canonical(catalog))
    with pytest.raises((ValueError, KeyError)):
        check.check_catalog(output / "cua-profile-catalog.json")


@pytest.mark.parametrize(
    "field,value",
    [
        ("attempt", 2),
        ("runner_environment", "self-hosted"),
        ("ref", "refs/heads/feature"),
        ("workflow_id", "3"),
    ],
)
def test_producer_provenance_is_closed(package_inputs, field, value):
    descriptor = package_inputs[3]
    descriptor["producer"][field] = value
    with pytest.raises(ValueError):
        build.validate_producer(descriptor["producer"])

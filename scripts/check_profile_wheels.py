#!/usr/bin/env python3
"""Validate complete retained profile artifacts without importing their code."""

from __future__ import annotations

import argparse
import ast
import base64
import csv
import io
import re
import sys
from pathlib import Path

from build_profile_wheels import (
    MAX_BYTES,
    PREFIX,
    PROFILES,
    check_adoption_policy,
    digest,
    identity,
    interpreter,
    inventory,
    native_identity,
    read_json,
    safe_path,
    validate_producer,
    zip_members,
)


def exact_keys(value: dict, keys: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} schema differs")


def checked_file(root: Path, record: dict) -> bytes:
    exact_keys(record, {"filename", "size", "sha256"}, "artifact")
    name = safe_path(record["filename"])
    if "/" in name or type(record["size"]) is not int or not 0 < record["size"] <= MAX_BYTES:
        raise ValueError("invalid artifact filename or size")
    path = root / name
    if path.is_symlink() or path.stat().st_size != record["size"]:
        raise ValueError("artifact size or file type differs")
    data = path.read_bytes()
    if digest(data) != record["sha256"]:
        raise ValueError("artifact digest differs")
    return data


def package_trust(files: dict[str, bytes]) -> dict:
    tree = ast.parse(files[PREFIX + "_profile_trust.py"].decode("utf-8"))
    if (
        len(tree.body) != 1
        or not isinstance(tree.body[0], ast.Assign)
        or len(tree.body[0].targets) != 1
        or not isinstance(tree.body[0].targets[0], ast.Name)
        or tree.body[0].targets[0].id != "TRUST"
    ):
        raise ValueError("package trust contains executable statements")
    value = ast.literal_eval(tree.body[0].value)
    if not isinstance(value, dict):
        raise ValueError("package trust must be a literal mapping")
    return value


def check_record(
    files: dict[str, bytes], version: str, tag: str, *, build_tag: str | None = None
) -> set[str]:
    prefix = f"vadgr_computer_use-{version}.dist-info/"
    record_path = prefix + "RECORD"
    rows = list(csv.reader(io.StringIO(files[record_path].decode())))
    expected = {}
    for row in rows:
        if len(row) != 3 or row[0] in expected:
            raise ValueError("invalid or duplicate wheel RECORD row")
        expected[row[0]] = row[1:]
    if set(expected) != set(files) or expected[record_path] != ["", ""]:
        raise ValueError("wheel RECORD does not cover the exact file set")
    for name, data in files.items():
        if name == record_path:
            continue
        encoded = base64.urlsafe_b64encode(bytes.fromhex(digest(data))).rstrip(b"=").decode()
        if expected[name] != ["sha256=" + encoded, str(len(data))]:
            raise ValueError(f"wheel RECORD digest differs: {name}")
    wheel_lines = files[prefix + "WHEEL"].decode().splitlines()
    if (
        wheel_lines.count("Wheel-Version: 1.0") != 1
        or wheel_lines.count("Root-Is-Purelib: true") != 1
        or wheel_lines.count("Tag: " + tag) != 1
    ):
        raise ValueError("wheel compatibility tag differs")
    builds = [line for line in wheel_lines if line.startswith("Build:")]
    if builds != ([] if build_tag is None else ["Build: " + build_tag]):
        raise ValueError("wheel build tag differs")
    metadata = files[prefix + "METADATA"].decode()
    if f"Version: {version}\n" not in metadata or "Name: vadgr-computer-use\n" not in metadata:
        raise ValueError("wheel package identity differs")
    return {prefix + name for name in ("RECORD", "WHEEL", "METADATA", "entry_points.txt")}


def check_evidence(value: dict, needs_native: bool) -> None:
    exact_keys(
        value,
        {"build_sha256", "test_sha256", "sbom_sha256", "native_job_ids", "artifacts"},
        "profile evidence",
    )
    for key in ("build_sha256", "test_sha256", "sbom_sha256"):
        if not isinstance(value[key], str) or not re.fullmatch(r"[0-9a-f]{64}", value[key]):
            raise ValueError("invalid evidence digest")
    if (
        not isinstance(value["native_job_ids"], list)
        or needs_native
        and not value["native_job_ids"]
        or any(type(n) is not int or n <= 0 for n in value["native_job_ids"])
    ):
        raise ValueError("missing native producer job identity")
    if not isinstance(value["artifacts"], list) or not value["artifacts"]:
        raise ValueError("missing immutable producer artifacts")
    for artifact in value["artifacts"]:
        exact_keys(artifact, {"id", "sha256"}, "producer artifact")
        if (
            type(artifact["id"]) is not int
            or artifact["id"] <= 0
            or not re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"])
        ):
            raise ValueError("invalid immutable producer artifact identity")


def check_manifest(
    manifest: dict, files: dict[str, bytes], profile: str, version: str, commit: str
) -> None:
    exact_keys(
        manifest,
        {
            "schema",
            "cua_version",
            "source_commit",
            "release_profile",
            "interpreter",
            "files",
            "executables",
            "archives",
            "helpers",
        },
        "profile manifest",
    )
    if (
        manifest["schema"] != 1
        or manifest["cua_version"] != version
        or manifest["source_commit"] != commit
        or manifest["release_profile"] != profile
        or manifest["interpreter"] != interpreter(profile)
    ):
        raise ValueError("profile manifest identity differs")
    if manifest["files"] != [identity(p, b, "wheel_path") for p, b in sorted(files.items())]:
        raise ValueError("manifest does not cover the exact package input files")
    executables, archives = inventory(files, profile)
    if manifest["executables"] != executables or manifest["archives"] != archives:
        raise ValueError("executable or archive role inventory differs")
    windows = profile.startswith(("windows-", "wsl-"))
    helper = manifest["helpers"]
    if not windows:
        if helper is not None:
            raise ValueError("native Linux/macOS declares Windows helpers")
        for name in files:
            if name.startswith((PREFIX + "winhost/", PREFIX + "winbroker/")) and not name.endswith(
                ".py"
            ):
                raise ValueError("native Linux/macOS contains Windows assets")
        return
    exact_keys(helper, {"architecture", "relay", "archive", "member_manifest"}, "helper closure")
    if (
        PREFIX + "winbroker/install.ps1" in files
        or PREFIX + "winbroker/install-managed.ps1" not in files
    ):
        raise ValueError("managed package installer mode differs")
    architecture = profile.split("-", 1)[1]
    if helper["architecture"] != architecture:
        raise ValueError("helper architecture differs")
    for key in ("relay", "archive", "member_manifest"):
        record = helper[key]
        exact_keys(record, {"path", "size", "sha256"}, "helper identity")
        if record != identity(record["path"], files[record["path"]]):
            raise ValueError("helper digest differs")
    relay = helper["relay"]["path"]
    archive = helper["archive"]["path"]
    member_manifest = helper["member_manifest"]["path"]
    if (
        relay != PREFIX + f"winhost/{architecture}/vadgr-cua-host.exe"
        or not archive.startswith(PREFIX + f"winbroker/{architecture}/")
        or not member_manifest.startswith(PREFIX + f"winbroker/{architecture}/")
    ):
        raise ValueError("helper paths differ from their fixed consumers")
    native_members = [
        e
        for e in executables
        if native_identity(files[e["wheel_path"]]) is not None and not e["archive_members"]
    ]
    if {e["wheel_path"] for e in native_members} != {relay}:
        raise ValueError("unexpected outer native executable")
    for entry in executables:
        if entry["archive_members"] and entry["wheel_path"] != archive:
            raise ValueError("uncataloged nested executable outside broker closure")
    inner = read_json(files[member_manifest])
    if (
        inner.get("version") != version
        or inner.get("source_commit") != commit
        or inner.get("target") != architecture + "-pc-windows-msvc"
        or inner.get("archive_sha256") != digest(files[archive])
        or inner.get("archive_size") != len(files[archive])
        or inner.get("files")
        != [identity(p, b) for p, b in sorted(zip_members(files[archive]).items())]
    ):
        raise ValueError("broker member manifest differs from the exact input archive")
    nested = zip_members(files[archive])
    if "vadgr-cua-browser-broker.exe" not in nested:
        raise ValueError("broker executable is missing")
    if native_identity(nested["vadgr-cua-browser-broker.exe"]) != ("windows", architecture):
        raise ValueError("broker native architecture differs")


def check_catalog(path: Path) -> dict:
    catalog = read_json(path.read_bytes())
    exact_keys(
        catalog,
        {"schema", "cua_version", "source_commit", "producer", "profiles", "standalone"},
        "profile catalog",
    )
    if catalog["schema"] != 1 or set(catalog["profiles"]) != set(PROFILES):
        raise ValueError("catalog must contain the eight closed profiles")
    validate_producer(catalog["producer"])
    if catalog["source_commit"] != catalog["producer"]["source_commit"]:
        raise ValueError("catalog and producer source commits differ")
    root, version, commit = path.parent, catalog["cua_version"], catalog["source_commit"]
    manifests, profile_files = {}, {}
    filenames = set()
    for profile, entry in sorted(catalog["profiles"].items()):
        exact_keys(
            entry, {"interpreter", "wheel", "input_role_manifest", "evidence"}, "catalog profile"
        )
        if entry["interpreter"] != interpreter(profile):
            raise ValueError("catalog interpreter tags differ")
        check_evidence(entry["evidence"], profile.startswith(("windows-", "wsl-")))
        for key in ("wheel", "input_role_manifest"):
            name = entry[key]["filename"]
            if name in filenames:
                raise ValueError("catalog reuses an artifact filename")
            filenames.add(name)
        raw = checked_file(root, entry["input_role_manifest"])
        files = zip_members(checked_file(root, entry["wheel"]))
        tags = interpreter(profile)
        tag = f"{tags['python']}-{tags['abi']}-{tags['platform']}"
        wanted_name = (
            f"vadgr_computer_use-{version}-1{profile.replace('-', '').replace('_', '')}-{tag}.whl"
        )
        if entry["wheel"]["filename"] != wanted_name:
            raise ValueError("profile wheel filename differs")
        build_tag = "1" + profile.replace("-", "").replace("_", "")
        metadata = check_record(files, version, tag, build_tag=build_tag)
        trust = package_trust(files)
        if trust != {
            "schema": 1,
            "mode": "managed",
            "release_profile": profile,
            "manifest_sha256": {profile: digest(raw)},
        }:
            raise ValueError("mandatory managed package marker differs")
        manifest_path = PREFIX + f"profiles/{profile}/cua-profile-manifest.json"
        if files.get(manifest_path) != raw:
            raise ValueError("packaged manifest differs from catalog manifest")
        for name in metadata | {manifest_path, PREFIX + "_profile_trust.py"}:
            files.pop(name)
        manifest = read_json(raw)
        check_manifest(manifest, files, profile, version, commit)
        manifests[profile], profile_files[profile] = manifest, files
    for architecture in ("x86_64", "aarch64"):
        if (
            manifests["windows-" + architecture]["helpers"]
            != manifests["wsl-" + architecture]["helpers"]
        ):
            raise ValueError("Windows and WSL helper input closures differ")
    standalone = catalog["standalone"]
    exact_keys(standalone, {"wheel", "manifest_sha256", "adoption"}, "standalone catalog")
    if standalone["wheel"]["filename"] != f"vadgr_computer_use-{version}-py3-none-any.whl":
        raise ValueError("standalone wheel filename differs")
    files = zip_members(checked_file(root, standalone["wheel"]))
    metadata = check_record(files, version, "py3-none-any")
    trust = package_trust(files)
    hashes = {p: catalog["profiles"][p]["input_role_manifest"]["sha256"] for p in PROFILES}
    if (
        standalone["manifest_sha256"] != hashes
        or trust.get("manifest_sha256") != hashes
        or trust.get("mode") != "standalone-input"
        or trust.get("schema") != 1
        or trust.get("adoption") != standalone["adoption"]
    ):
        raise ValueError("standalone package marker differs")
    exact_keys(trust, {"schema", "mode", "manifest_sha256", "adoption"}, "standalone package trust")
    expected = {}
    for payload in profile_files.values():
        for name, data in payload.items():
            if name in expected and expected[name] != data:
                raise ValueError("profile common source bytes differ")
            expected[name] = data
    for profile in PROFILES:
        name = PREFIX + f"profiles/{profile}/cua-profile-manifest.json"
        expected[name] = checked_file(root, catalog["profiles"][profile]["input_role_manifest"])
    if set(standalone["adoption"]) != {"x86_64", "aarch64"}:
        raise ValueError("standalone adoption must cover both native architectures")
    for architecture in ("x86_64", "aarch64"):
        prefix = PREFIX + f"adoption/{architecture}/"
        policy = read_json(files[prefix + "adoption-policy.json"])
        check_adoption_policy(
            policy,
            files[prefix + "trusted-root.json"],
            files[prefix + "gh.exe"],
            architecture,
            version,
            commit,
            manifests["windows-" + architecture]["helpers"],
        )
        pins = {
            "policy_sha256": digest(files[prefix + "adoption-policy.json"]),
            "root_sha256": digest(files[prefix + "trusted-root.json"]),
            "verifier_sha256": digest(files[prefix + "gh.exe"]),
        }
        if pins != standalone["adoption"][architecture]:
            raise ValueError("standalone adoption metadata differs")
        for name in ("adoption-policy.json", "trusted-root.json", "gh.exe"):
            expected[prefix + name] = files[prefix + name]
        license_name = prefix + "LICENSE"
        if not files[license_name].strip():
            raise ValueError("standalone verifier notice is missing")
        expected[license_name] = files[license_name]
    expected[PREFIX + "_profile_trust.py"] = files[PREFIX + "_profile_trust.py"]
    for name in ("install.ps1", "adopt-native.ps1"):
        input_installer = PREFIX + "winbroker/" + name
        if not files.get(input_installer):
            raise ValueError("standalone input installer or native verifier is missing")
        expected[input_installer] = files[input_installer]
    for name in metadata:
        files.pop(name)
    if expected != files:
        raise ValueError("standalone has missing, changed or extra files")
    return catalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    args = parser.parse_args()
    catalog = check_catalog(args.catalog)
    total = sum(entry["wheel"]["size"] for entry in catalog["profiles"].values())
    total += catalog["standalone"]["wheel"]["size"]
    print(f"Profile catalog passed: eight managed wheels, one standalone wheel, {total} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())

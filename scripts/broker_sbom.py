"""Inventory shipped broker members and linked relay sources from pinned inputs."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import ssl
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from build_profile_wheels import canonical, digest, read_json, zip_members

NOTICE_COMPONENTS = {
    "OpenSSL": ("LICENSE.openssl-3.txt", "Apache-2.0"),
    "libffi": ("LICENSE.libffi.txt", "MIT"),
    "zlib": ("LICENSE.zlib.txt", "Zlib"),
    "bzip2": ("LICENSE.bzip2.txt", "bzip2-1.0.6"),
    "liblzma": ("LICENSE.liblzma.txt", "0BSD"),
    "mpdecimal": ("LICENSE.mpdecimal.txt", "BSD-2-Clause"),
    "expat": ("LICENSE.expat.txt", "MIT"),
    "SQLite": ("LICENSE.sqlite.txt", "NOASSERTION"),
}


def native_component(name: str) -> str:
    name = name.lower()
    if name.startswith(("libcrypto-", "libssl-")):
        return "OpenSSL"
    if name.startswith("libffi-"):
        return "libffi"
    if name.startswith("vcruntime"):
        return "Microsoft-VC-runtime"
    if name == "sqlite3.dll":
        return "SQLite"
    if name.startswith("python") or name.endswith(".pyd"):
        return "CPython"
    raise ValueError("unclassified native broker member: " + name)


def python_origins(bundle: Path, python_root: Path) -> dict:
    """Every collected Python DLL/PYD must match its pinned distribution bytes."""
    origins = {}
    for path in sorted(bundle.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".dll", ".pyd"}:
            continue
        matches = [
            p
            for p in (python_root / path.name, python_root / "DLLs" / path.name)
            if p.is_file() and digest(p.read_bytes()) == digest(path.read_bytes())
        ]
        if len(matches) != 1:
            raise ValueError("native member is not an exact pinned Python input: " + path.name)
        origins[path.relative_to(bundle).as_posix()] = {
            "component": native_component(path.name),
            "source_member": matches[0].relative_to(python_root).as_posix(),
            "sha256": digest(path.read_bytes()),
        }
    return origins


def collect_go_sources(repository: Path, bundle: Path) -> dict:
    relay_root = repository / "computer_use/browser/winhost"
    goroot = Path(subprocess.check_output(["go", "env", "GOROOT"], text=True).strip()).resolve()
    stream = subprocess.check_output(
        ["go", "list", "-deps", "-json", "."],
        cwd=relay_root,
        text=True,
        env={**os.environ, "CGO_ENABLED": "0", "GOOS": "windows"},
    )
    decoder, cursor, packages, notices = json.JSONDecoder(), 0, [], {}
    while cursor < len(stream):
        cursor += len(stream[cursor:]) - len(stream[cursor:].lstrip())
        if cursor == len(stream):
            break
        package, cursor = decoder.raw_decode(stream, cursor)
        directory = Path(package["Dir"]).resolve()
        if package.get("Standard"):
            source_root = goroot
        elif package.get("Module", {}).get("Path") == "vadgr-cua-host":
            source_root = repository.resolve()
        else:
            raise ValueError("unreviewed external Go module: " + package["ImportPath"])
        source_rows = []
        for field in (
            "GoFiles",
            "CgoFiles",
            "CFiles",
            "HFiles",
            "SFiles",
            "SysoFiles",
            "EmbedFiles",
        ):
            for name in package.get(field, []):
                path = (directory / name).resolve()
                relative = path.relative_to(source_root).as_posix()
                source_rows.append({"path": relative, "sha256": digest(path.read_bytes())})
        licenses = []
        walk = directory
        while walk.is_relative_to(source_root):
            for name in ("LICENSE", "COPYING", "NOTICE", "PATENTS"):
                path = walk / name
                if path.is_file():
                    relative = path.relative_to(source_root).as_posix()
                    notice_name = ("go/" if source_root == goroot else "cua/") + relative
                    notices[notice_name] = path.read_bytes()
                    licenses.append(notice_name)
            if licenses or walk == source_root:
                break
            walk = walk.parent
        if not licenses:
            raise ValueError("linked Go package lacks its source license: " + package["ImportPath"])
        packages.append(
            {
                "import_path": package["ImportPath"],
                "standard": bool(package.get("Standard")),
                "sources": sorted(source_rows, key=lambda row: row["path"]),
                "notices": sorted(licenses),
            }
        )
    for name, data in notices.items():
        path = bundle / "THIRD-PARTY-NOTICES" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return {
        "toolchain": subprocess.check_output(["go", "version"], text=True).strip(),
        "packages": sorted(packages, key=lambda row: row["import_path"]),
    }


def prepare_notices(repository: Path, bundle: Path, python_root: Path) -> tuple[dict, dict]:
    origins = python_origins(bundle, python_root)
    components = {row["component"] for row in origins.values()}
    static_components = set()
    # These libraries are compiled into CPython or its selected extensions.
    names = {Path(path).name.lower() for path in origins}
    if any(name.startswith("python") for name in names):
        components.add("zlib")
        static_components.add("zlib")
    for filename, component in (
        ("_bz2.pyd", "bzip2"),
        ("_lzma.pyd", "liblzma"),
        ("_decimal.pyd", "mpdecimal"),
        ("pyexpat.pyd", "expat"),
    ):
        if filename in names:
            components.add(component)
            static_components.add(component)
    pins = read_json((repository / "packaging/profiles/notice-inputs.json").read_bytes())
    for component in sorted(components & NOTICE_COMPONENTS.keys()):
        name, _ = NOTICE_COMPONENTS[component]
        data = (python_root / "notices" / name).read_bytes()
        if digest(data) != pins[name]["sha256"] or len(data) != pins[name]["size"]:
            raise ValueError("bundled dependency notice differs from reviewed input: " + name)
        destination = bundle / "THIRD-PARTY-NOTICES" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    go_sources = collect_go_sources(repository, bundle)
    pyinstaller = importlib.metadata.distribution("pyinstaller")
    bootloaders = []
    for item in pyinstaller.files or ():
        relative = str(item).replace("\\", "/")
        if "/bootloader/Windows-" in relative and relative.endswith("/run.exe"):
            data = Path(pyinstaller.locate_file(item)).read_bytes()
            bootloaders.append({"path": relative, "sha256": digest(data), "size": len(data)})
    if not bootloaders:
        raise ValueError("pinned PyInstaller Windows bootloader is missing")
    # An exact byte inventory is evidence, not an approval of redistribution rights.
    receipt = {
        "schema": 1,
        "python_members": origins,
        "static_python_components": sorted(static_components),
        "go": go_sources,
        "runtime_versions": {"CPython": sys.version.split()[0], "OpenSSL": ssl.OPENSSL_VERSION},
        "pyinstaller": {
            "version": pyinstaller.version,
            "bootloaders": bootloaders,
            "notice": "PYINSTALLER-COPYING.txt",
        },
    }
    (bundle / "THIRD-PARTY-NOTICES/source-inventory.json").write_bytes(canonical(receipt))
    return origins, receipt


def build_sbom(
    bundle: Path,
    relay: Path,
    version: str,
    architecture: str,
    source_commit: str,
    python_pin: dict,
    receipt: dict,
) -> dict:
    files, relationships, grouped = [], [], {}
    all_files = {
        path.relative_to(bundle).as_posix(): path.read_bytes()
        for path in bundle.rglob("*")
        if path.is_file()
    }
    all_files["vadgr-cua-host.exe"] = relay.read_bytes()
    for name, data in list(all_files.items()):
        if name.endswith(".zip"):
            for member, raw in zip_members(data).items():
                all_files[name + "!/" + member] = raw
    for name, data in sorted(all_files.items()):
        component = receipt["python_members"].get(name, {}).get("component", "vadgr-computer-use")
        if name == "vadgr-cua-browser-broker.exe":
            component = "PyInstaller-bootloader-and-CUA"
        elif name == "vadgr-cua-host.exe":
            component = "Go-runtime-and-CUA-relay"
        elif "base_library.zip" in name:
            component = "CPython"
        identifier = "SPDXRef-File-" + digest(name.encode())[:20]
        grouped.setdefault(component, []).append((identifier, hashlib.sha1(data).hexdigest()))
        files.append(
            {
                "fileName": "./" + name,
                "SPDXID": identifier,
                "checksums": [{"algorithm": "SHA256", "checksumValue": digest(data)}],
                "licenseConcluded": "NOASSERTION",
                "copyrightText": "NOASSERTION",
            }
        )
    for component in receipt["static_python_components"]:
        grouped.setdefault(component, [])
    packages = []
    for component, members in sorted(grouped.items()):
        identifier = "SPDXRef-Package-" + component
        declared = NOTICE_COMPONENTS.get(component, (None, "NOASSERTION"))[1]
        package = {
            "name": component,
            "SPDXID": identifier,
            "downloadLocation": python_pin["url"],
            "filesAnalyzed": bool(members),
            "licenseDeclared": declared,
            "licenseConcluded": "NOASSERTION",
            "checksums": [{"algorithm": "SHA256", "checksumValue": python_pin["sha256"]}],
            "comment": "Exact component membership is recorded in THIRD-PARTY-NOTICES/source-inventory.json. Legal approval is separate.",
        }
        if component in {
            "vadgr-computer-use",
            "PyInstaller-bootloader-and-CUA",
            "Go-runtime-and-CUA-relay",
        }:
            package["downloadLocation"] = (
                "https://github.com/MONTBRAIN/vadgr-computer-use/tree/" + source_commit
            )
            package.pop("checksums")
        if members:
            package["packageVerificationCode"] = {
                "packageVerificationCodeValue": hashlib.sha1(
                    "".join(sorted(h for _, h in members)).encode()
                ).hexdigest()
            }
        if component in receipt.get("runtime_versions", {}):
            package["versionInfo"] = receipt["runtime_versions"][component]
        if component == "PyInstaller-bootloader-and-CUA":
            package["versionInfo"] = receipt["pyinstaller"]["version"]
        packages.append(package)
        relationships += [
            {"spdxElementId": identifier, "relationshipType": "CONTAINS", "relatedSpdxElement": fid}
            for fid, _ in members
        ]
        relationships.append(
            {
                "spdxElementId": "SPDXRef-DOCUMENT",
                "relationshipType": "DESCRIBES",
                "relatedSpdxElement": identifier,
            }
        )
    for component in receipt["static_python_components"]:
        relationships.append(
            {
                "spdxElementId": "SPDXRef-Package-CPython",
                "relationshipType": "STATIC_LINK",
                "relatedSpdxElement": "SPDXRef-Package-" + component,
            }
        )
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"vadgr-cua-browser-broker-{version}-windows-{architecture}",
        "documentNamespace": f"https://github.com/MONTBRAIN/vadgr-computer-use/sbom/{source_commit}/{digest(canonical(files))}",
        "creationInfo": {
            "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "creators": ["Tool: scripts/broker_sbom.py"],
        },
        "packages": packages,
        "files": files,
        "relationships": relationships,
    }

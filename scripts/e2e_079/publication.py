"""Publish only reviewed, retained profile bytes; never rebuild release wheels."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from build_profile_wheels import read_json, validate_producer
from check_profile_wheels import check_catalog

REPOSITORY = "MONTBRAIN/vadgr-computer-use"
CATALOG = "cua-profile-catalog.json"
BUNDLE = "cua-profile-catalog.sigstore.json"
MAX_BYTES = 1024 * 1024 * 1024


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def gh(*args: str, binary: bool = False):
    result = subprocess.run(["gh", *args], capture_output=True, check=True, timeout=180)
    return result.stdout if binary else json.loads(result.stdout)


def extract(data: bytes, destination: Path) -> None:
    if len(data) > MAX_BYTES:
        raise ValueError("retained archive exceeds the release bound")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        if not infos or len(infos) > 100 or sum(i.file_size for i in infos) > MAX_BYTES:
            raise ValueError("retained archive member bound exceeded")
        names = set()
        for info in infos:
            name = info.filename
            if (name in ("", ".", "..") or "/" in name or "\\" in name or ":" in name
                    or name.casefold() in names or info.is_dir()
                    or (info.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError("retained archive path is unsafe or duplicated")
            names.add(name.casefold())
        destination.mkdir(parents=True, exist_ok=False)
        for info in infos:
            with (destination / info.filename).open("xb") as output:
                output.write(archive.read(info))


def validate_descriptor(value: dict, version: str) -> None:
    expected = {"schema", "cua_version", "producer", "artifact_id", "artifact_sha256",
                "catalog_sha256", "bundle_sha256"}
    if set(value) != expected or value["schema"] != 1 or value["cua_version"] != version:
        raise ValueError("reviewed release input schema/version differs")
    validate_producer(value["producer"])
    if type(value["artifact_id"]) is not int or value["artifact_id"] <= 0:
        raise ValueError("exact immutable artifact ID required")
    for field in ("artifact_sha256", "catalog_sha256", "bundle_sha256"):
        if not isinstance(value[field], str) or not re.fullmatch(r"[0-9a-f]{64}", value[field]):
            raise ValueError("exact retained artifact digest required")


def prepare(descriptor: Path, destination: Path, version: str) -> dict:
    value = read_json(descriptor.read_bytes())
    validate_descriptor(value, version)
    producer = value["producer"]
    repository = gh("api", f"repos/{REPOSITORY}")
    if repository["id"] != producer["repository_id"] or repository["owner"]["id"] != producer["owner_id"]:
        raise ValueError("repository/owner numeric identity differs")
    run = gh("api", f"repos/{REPOSITORY}/actions/runs/{producer['run_id']}")
    if (run["head_sha"] != producer["source_commit"] or run["run_attempt"] != 1
            or run["workflow_id"] != producer["workflow_id"] or run["event"] != "workflow_dispatch"
            or run["head_branch"] != "master" or run["conclusion"] != "success"):
        raise ValueError("retained producer run identity or success differs")
    workflow = gh("api", f"repos/{REPOSITORY}/actions/workflows/{producer['workflow_id']}")
    if workflow["path"] != producer["workflow"]:
        raise ValueError("producer workflow path differs")
    artifact = gh("api", f"repos/{REPOSITORY}/actions/artifacts/{value['artifact_id']}")
    if (artifact["expired"] or artifact["workflow_run"]["id"] != producer["run_id"]
            or artifact["digest"] != "sha256:" + value["artifact_sha256"]):
        raise ValueError("retained artifact identity differs or expired")
    data = gh("api", f"repos/{REPOSITORY}/actions/artifacts/{value['artifact_id']}/zip", binary=True)
    if sha(data) != value["artifact_sha256"]:
        raise ValueError("downloaded retained archive digest differs")
    extract(data, destination)
    catalog_path, bundle_path = destination / CATALOG, destination / BUNDLE
    if (sha(catalog_path.read_bytes()) != value["catalog_sha256"]
            or sha(bundle_path.read_bytes()) != value["bundle_sha256"]):
        raise ValueError("catalog or verification bundle differs")
    subprocess.run([
        "gh", "attestation", "verify", str(catalog_path), "--bundle", str(bundle_path),
        "--repo", REPOSITORY, "--cert-identity",
        f"https://github.com/{REPOSITORY}/{producer['workflow']}@refs/heads/master",
        "--cert-oidc-issuer", "https://token.actions.githubusercontent.com",
        "--source-ref", "refs/heads/master", "--source-digest", producer["source_commit"],
        "--signer-digest", producer["tooling_commit"], "--deny-self-hosted-runners",
    ], check=True, timeout=180)
    catalog = check_catalog(catalog_path)
    if catalog["producer"] != producer or catalog["cua_version"] != version:
        raise ValueError("attested catalog differs from reviewed producer")
    expected = {CATALOG, BUNDLE, catalog["standalone"]["wheel"]["filename"]}
    for profile in catalog["profiles"].values():
        expected.update(profile[key]["filename"] for key in ("wheel", "input_role_manifest"))
    if {p.name for p in destination.iterdir()} != expected:
        raise ValueError("retained output has extra or missing assets")
    pypi = destination.parent / "pypi-dist"
    pypi.mkdir(exist_ok=False)
    shutil.copyfile(destination / catalog["standalone"]["wheel"]["filename"],
                    pypi / catalog["standalone"]["wheel"]["filename"])
    return {"catalog_sha256": value["catalog_sha256"], "assets": sorted(expected)}


def publication_record(root: Path, release: dict, version: str) -> dict:
    if release["tag_name"] != f"v{version}" or not release["draft"]:
        raise ValueError("publication record requires the exact new draft release")
    expected = {p.name: p for p in root.iterdir() if p.is_file()}
    assets = {a["name"]: a for a in release["assets"]}
    if len(assets) != len(release["assets"]) or set(assets) != set(expected):
        raise ValueError("release asset names differ from retained inputs")
    records = []
    for name, path in sorted(expected.items()):
        asset = assets[name]
        data = path.read_bytes()
        if asset["size"] != len(data) or asset["digest"] != "sha256:" + sha(data):
            raise ValueError("uploaded release asset bytes differ")
        records.append({"filename": name, "id": asset["id"], "size": len(data), "sha256": sha(data)})
    return {"schema": 1, "cua_version": version, "repository": REPOSITORY,
            "release_id": release["id"], "tag": release["tag_name"],
            "catalog_sha256": sha((root / CATALOG).read_bytes()), "assets": records}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    pre = sub.add_parser("prepare")
    pre.add_argument("--descriptor", type=Path, required=True)
    pre.add_argument("--destination", type=Path, required=True)
    pre.add_argument("--version", required=True)
    rec = sub.add_parser("record")
    rec.add_argument("--root", type=Path, required=True)
    rec.add_argument("--version", required=True)
    rec.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.descriptor, args.destination, args.version)
    else:
        release = gh("api", f"repos/{REPOSITORY}/releases/tags/v{args.version}")
        result = publication_record(args.root, release, args.version)
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

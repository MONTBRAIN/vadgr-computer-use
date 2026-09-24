#!/usr/bin/env python3
"""Collect hosted producer identities and enforce reviewed construction inputs."""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from adoption_inputs import checked_download, generate_policies, provision_verifiers, validate_rules
from build_profile_wheels import (
    MAX_BYTES,
    MAX_FILES,
    PROFILES,
    canonical,
    digest,
    freeze,
    read_json,
    safe_path,
    source_files,
    validate_producer,
    zip_members,
)
from check_profile_wheels import check_catalog


def preflight() -> None:
    base = ROOT / "packaging" / "profiles"
    required = [
        base / name for name in ("size-budgets.json", "verifier-inputs.json", "adoption-rules.json")
    ] + [ROOT / "requirements/windows-broker-build.txt"]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        raise ValueError("reviewed producer inputs are missing: " + ", ".join(missing))
    validate_rules(read_json((base / "adoption-rules.json").read_bytes()))
    budgets = read_json((base / "size-budgets.json").read_bytes())
    if set(budgets) != {*PROFILES, "standalone"} or any(
        type(n) is not int or n <= 0 for n in budgets.values()
    ):
        raise ValueError("reviewed size budgets must cover all nine wheels")


def provision_python(architecture: str, output: Path) -> None:
    lock = read_json((ROOT / "packaging/profiles/toolchain.json").read_bytes())
    record = lock["python_inputs"][architecture]
    with urllib.request.urlopen(record["url"], timeout=120) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES or digest(data) != record["sha256"]:
        raise ValueError("native Python distribution differs from the reviewed archive")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        entries = archive.getmembers()
        if len(entries) > MAX_FILES or sum(item.size for item in entries) > MAX_BYTES:
            raise ValueError("native Python archive exceeds the extraction budget")
        seen = set()
        payload = {}
        for item in entries:
            name = safe_path(item.name.rstrip("/"))
            if name.casefold() in seen or not (item.isdir() or item.isfile()):
                raise ValueError("unsafe native Python archive member")
            seen.add(name.casefold())
            if item.isfile():
                payload[name] = archive.extractfile(item).read()
    if output.exists():
        raise ValueError("native Python destination must be new")
    for name, data in payload.items():
        freeze(output / name, data)
    notices = read_json((ROOT / "packaging/profiles/notice-inputs.json").read_bytes())
    for name, pin in notices.items():
        safe_path(name)
        data = checked_download(
            "https://raw.githubusercontent.com/astral-sh/python-build-standalone/"
            "c0aa3bbdc2fff56a77ad1ecec68b1e47794d8779/" + name,
            pin["sha256"],
            pin["size"],
        )
        freeze(output / "python/notices" / name, data)
    print(f"Native Python verified and extracted: {architecture}; {len(payload)} files")


def native_smoke(inputs: Path, output: Path) -> None:
    archives = list(inputs.glob("*.zip"))
    if len(archives) != 1 or output.exists():
        raise ValueError("native smoke requires one archive and a new output root")
    for name, data in zip_members(archives[0].read_bytes()).items():
        freeze(output / name, data)
    result = subprocess.run(
        [str((output / "vadgr-cua-browser-broker.exe").resolve()), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        shell=False,
        check=False,
    )
    if result.returncode or "usage:" not in result.stdout:
        raise ValueError("native broker command-line smoke failed")
    freeze(inputs / "test.log", ("Native broker --help passed\n" + result.stdout).encode())
    print("Native broker command-line smoke passed")


def api(path: str) -> dict:
    result = subprocess.run(
        ["gh", "api", "repos/MONTBRAIN/vadgr-computer-use/" + path],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode:
        raise ValueError("GitHub producer identity query failed")
    return json.loads(result.stdout)


def descriptor(inputs: Path, output: Path) -> None:
    run_id = int(os.environ["GITHUB_RUN_ID"])
    run = api(f"actions/runs/{run_id}")
    jobs = api(f"actions/runs/{run_id}/attempts/1/jobs?per_page=100")["jobs"]
    artifacts = api(f"actions/runs/{run_id}/artifacts?per_page=100")["artifacts"]
    producer = {
        "repository": "MONTBRAIN/vadgr-computer-use",
        "repository_id": int(os.environ["GITHUB_REPOSITORY_ID"]),
        "owner_id": int(os.environ["GITHUB_REPOSITORY_OWNER_ID"]),
        "source_commit": os.environ["GITHUB_SHA"],
        "tooling_commit": os.environ["GITHUB_SHA"],
        "workflow": ".github/workflows/profile-wheels.yml",
        "workflow_id": run["workflow_id"],
        "ref": os.environ["GITHUB_REF"],
        "event": os.environ["GITHUB_EVENT_NAME"],
        "run_id": run_id,
        "attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
        "runner_environment": "github-hosted",
    }
    validate_producer(producer)
    if (
        run["head_sha"] != producer["source_commit"]
        or run["run_attempt"] != 1
        or run["event"] != "workflow_dispatch"
        or run["head_branch"] != "master"
        or run["path"] != producer["workflow"]
        or run["repository"]["id"] != producer["repository_id"]
        or run["repository"]["owner"]["id"] != producer["owner_id"]
    ):
        raise ValueError("GitHub run differs from trusted producer context")
    profiles = {}
    for profile in PROFILES:
        architecture = profile.split("-", 1)[1]
        name = "native-" + architecture
        matching = [
            artifact
            for artifact in artifacts
            if artifact["name"] == name and not artifact["expired"]
        ]
        native_jobs = [
            job
            for job in jobs
            if job["name"] == name
            and job["conclusion"] == "success"
            and "self-hosted" not in job.get("labels", [])
        ]
        if len(matching) != 1 or len(native_jobs) != 1:
            raise ValueError("missing exact hosted native job or retained artifact: " + name)
        artifact = matching[0]
        if (
            artifact["workflow_run"]["id"] != run_id
            or artifact["workflow_run"]["head_sha"] != producer["source_commit"]
        ):
            raise ValueError("native artifact belongs to another source or workflow run")
        root = inputs / name
        manifests = list(root.glob("*.manifest.json"))
        sboms = list(root.glob("*.spdx.json"))
        if len(manifests) != 1 or len(sboms) != 1:
            raise ValueError("native artifact evidence is incomplete")
        profiles[profile] = {
            "build_sha256": digest(manifests[0].read_bytes()),
            "test_sha256": digest((root / "test.log").read_bytes()),
            "sbom_sha256": digest(sboms[0].read_bytes()),
            "native_job_ids": [native_jobs[0]["id"]],
            "artifacts": [
                {"id": artifact["id"], "sha256": artifact["digest"].removeprefix("sha256:")}
            ],
        }
    freeze(output, canonical({"producer": producer, "profiles": profiles}))


def check_size(path: Path) -> None:
    catalog = check_catalog(path)
    budgets = read_json((ROOT / "packaging/profiles/size-budgets.json").read_bytes())
    for name, entry in {**catalog["profiles"], "standalone": catalog["standalone"]}.items():
        size = entry["wheel"]["size"]
        if size > budgets[name]:
            raise ValueError(f"{name} exceeds its reviewed size budget: {size} > {budgets[name]}")
        print(f"{name}: {size} bytes; budget {budgets[name]} bytes")
        components = {}
        for member, data in zip_members(
            (path.parent / entry["wheel"]["filename"]).read_bytes()
        ).items():
            component = member.split("/", 1)[0]
            components[component] = components.get(component, 0) + len(data)
        for component, size in sorted(components.items()):
            print(f"  {component}: {size} uncompressed bytes")


def validate_output(path: Path, inputs: Path, descriptor_path: Path) -> None:
    """Recheck source, policy and API identities on the fresh attesting runner."""
    descriptor(inputs, descriptor_path)
    expected = read_json(descriptor_path.read_bytes())
    catalog = check_catalog(path)
    if catalog["producer"] != expected["producer"]:
        raise ValueError("catalog producer differs from independently observed GitHub run")
    common = source_files(ROOT)
    for profile, row in catalog["profiles"].items():
        if row["evidence"] != expected["profiles"][profile]:
            raise ValueError("catalog native evidence differs from retained artifact")
        files = zip_members((path.parent / row["wheel"]["filename"]).read_bytes())
        if any(files.get(name) != data for name, data in common.items()):
            raise ValueError("wheel source differs from trusted checkout")
    # Regenerate policies from fixed review inputs and independently retained helpers.
    generated = descriptor_path.parent / "validated-adoption"
    provision_verifiers(ROOT / "packaging/profiles", generated)
    generate_policies(ROOT, inputs, generated, expected)
    standalone = zip_members(
        (path.parent / catalog["standalone"]["wheel"]["filename"]).read_bytes()
    )
    if any(standalone.get(name) != data for name, data in common.items()):
        raise ValueError("standalone source differs from trusted checkout")
    for architecture in ("x86_64", "aarch64"):
        for name in ("adoption-policy.json", "trusted-root.json", "gh.exe", "LICENSE"):
            wheel_path = f"computer_use/browser/adoption/{architecture}/{name}"
            if standalone.get(wheel_path) != (generated / architecture / name).read_bytes():
                raise ValueError("standalone adoption inputs differ from independent construction")
    check_size(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "operation",
        choices=(
            "preflight",
            "descriptor",
            "check-size",
            "provision-python",
            "native-smoke",
            "provision-verifiers",
            "generate-adoption",
            "validate-output",
        ),
    )
    parser.add_argument("--architecture", choices=("x86_64", "aarch64"))
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--descriptor", type=Path)
    args = parser.parse_args()
    if args.operation == "preflight":
        preflight()
        print("All reviewed producer inputs are present")
    elif args.operation == "descriptor":
        descriptor(args.inputs, args.output)
        print("Hosted producer identities recorded")
    elif args.operation == "check-size":
        check_size(args.catalog)
    elif args.operation == "provision-python":
        provision_python(args.architecture, args.output)
    elif args.operation == "provision-verifiers":
        provision_verifiers(ROOT / "packaging/profiles", args.output)
        print("Both native offline verifiers, licenses and root verified")
    elif args.operation == "generate-adoption":
        generate_policies(ROOT, args.inputs, args.output, read_json(args.descriptor.read_bytes()))
        print("Both source-bound adoption policies frozen from reviewed rules")
    elif args.operation == "validate-output":
        validate_output(args.catalog, args.inputs, args.descriptor)
        print("Retained outputs match independently observed source, policy and GitHub identities")
    else:
        native_smoke(args.inputs, args.output)


if __name__ == "__main__":
    main()

"""Freeze source-bound adoption policies from reviewed, non-circular inputs."""

from __future__ import annotations

import re
import time
import urllib.request
from pathlib import Path

import tomllib
from build_profile_wheels import (
    canonical,
    check_adoption_policy,
    digest,
    freeze,
    helper_files,
    native_identity,
    read_json,
    safe_path,
    validate_producer,
    zip_members,
)

ARCHITECTURES = ("x86_64", "aarch64")
SIGNATURE_FIELDS = {
    "trust_class",
    "signer_policy_sha256",
    "legal_approval_sha256",
    "signer",
    "certificate_sha256",
    "chain_root_sha256",
    "digest_algorithm",
    "timestamp_algorithm",
}
RULE_FIELDS = SIGNATURE_FIELDS | {"input_sha256"}
# These are verifier capabilities, not defaults or evidence for a vendor file.
# A newly observed vendor scheme needs a reviewed verifier change before admission.
VENDOR_SIGNATURE_ALGORITHMS = {("sha256", "rfc3161-sha256")}


def reviewed_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[0-9a-f]{64}", value) is not None
        and value != "0" * 64
    )


def checked_download(url: str, sha256: str, size: int) -> bytes:
    if not url.startswith("https://") or type(size) is not int or not 0 < size < 100_000_000:
        raise ValueError("invalid pinned download")
    with urllib.request.urlopen(url, timeout=120) as response:
        data = response.read(size + 1)
    if len(data) != size or digest(data) != sha256:
        raise ValueError("download differs from reviewed size or digest")
    return data


def validate_rules(rules: dict) -> None:
    expected = {"schema", "expires_at", "source_sha_allowlist", "signer_sha_allowlist", "files"}
    if set(rules) != expected or rules["schema"] != 1:
        raise ValueError("reviewed adoption rules schema differs")
    if type(rules["expires_at"]) is not int or rules["expires_at"] <= time.time():
        raise ValueError("reviewed adoption rules expired")
    for key in ("source_sha_allowlist", "signer_sha_allowlist"):
        pins = rules[key]
        if not isinstance(pins, list) or not pins or len(pins) != len(set(pins)):
            raise ValueError("exact reviewed Vadgr source and signer allowlists are required")
        if any(
            not isinstance(p, str) or not re.fullmatch(r"[0-9a-f]{40}", p) or p == "0" * 40
            for p in pins
        ):
            raise ValueError("invalid reviewed Vadgr commit")
    if set(rules["files"]) != set(ARCHITECTURES):
        raise ValueError("reviewed signing rules must cover both architectures")
    for rows in rules["files"].values():
        if not isinstance(rows, dict) or not rows:
            raise ValueError("reviewed signing rules are empty")
        if len({p.casefold() for p in rows}) != len(rows):
            raise ValueError("reviewed signing paths collide")
        for name, row in rows.items():
            safe_path(name)
            if set(row) != RULE_FIELDS:
                raise ValueError("reviewed signing class fields differ")
            if not reviewed_digest(row["input_sha256"]):
                raise ValueError("missing exact reviewed input digest")
            if row["trust_class"] == "data":
                if any(row[k] is not None for k in SIGNATURE_FIELDS - {"trust_class"}):
                    raise ValueError("data cannot assert a signature identity")
                continue
            if row["trust_class"] not in {"publisher-sign", "vendor-preserve"}:
                raise ValueError("unknown reviewed signing class")
            for key in (
                "signer_policy_sha256",
                "legal_approval_sha256",
                "certificate_sha256",
                "chain_root_sha256",
            ):
                if not reviewed_digest(row[key]):
                    raise ValueError("missing exact reviewed legal or signature identity")
            if not isinstance(row["signer"], str) or not row["signer"].strip():
                raise ValueError("missing reviewed signer subject")
            algorithms = (row["digest_algorithm"], row["timestamp_algorithm"])
            if row["trust_class"] == "publisher-sign":
                if algorithms != ("sha256", "rfc3161-sha256"):
                    raise ValueError("publisher signature requires SHA-256 and RFC 3161")
            elif not all(isinstance(value, str) for value in algorithms) or (
                algorithms not in VENDOR_SIGNATURE_ALGORITHMS
            ):
                raise ValueError("unsupported reviewed vendor signature algorithms")


def provision_verifiers(base: Path, output: Path) -> None:
    pins = read_json((base / "verifier-inputs.json").read_bytes())
    if (
        pins["schema"] != 1
        or pins["version"] != "2.95.0"
        or set(pins["architectures"]) != set(ARCHITECTURES)
    ):
        raise ValueError("verifier input set differs")
    if output.exists():
        raise ValueError("verifier output must be new")
    root = checked_download(**pins["root"])
    # The pinned file is the GitHub CLI's JSON-lines trusted-root format.
    for line in root.splitlines():
        import json

        if (
            json.loads(line).get("mediaType")
            != "application/vnd.dev.sigstore.trustedroot+json;version=0.1"
        ):
            raise ValueError("invalid offline trusted root")
    payloads = {}
    for architecture, pin in pins["architectures"].items():
        archive = checked_download(pin["url"], pin["archive_sha256"], pin["archive_size"])
        members = zip_members(archive)
        verifier, license_bytes = members["bin/gh.exe"], members["LICENSE"]
        if (
            digest(verifier) != pin["executable_sha256"]
            or len(verifier) != pin["executable_size"]
            or native_identity(verifier) != ("windows", architecture)
        ):
            raise ValueError("offline verifier identity differs")
        if (
            digest(license_bytes) != pins["license_sha256"]
            or len(license_bytes) != pins["license_size"]
        ):
            raise ValueError("offline verifier license differs")
        payloads[architecture] = {
            "gh.exe": verifier,
            "LICENSE": license_bytes,
            "trusted-root.json": root,
        }
    for architecture, files in payloads.items():
        for name, data in files.items():
            freeze(output / architecture / name, data)


def generate_policies(repository: Path, inputs: Path, output: Path, descriptor: dict, *, source_repository: Path | None = None) -> None:
    """Bind derived closure identities only after every member matches its reviewed bytes."""
    validate_producer(descriptor["producer"])
    base = repository / "packaging/profiles"
    rules = read_json((base / "adoption-rules.json").read_bytes())
    validate_rules(rules)
    pins = read_json((base / "verifier-inputs.json").read_bytes())
    source_repository = source_repository or repository
    version = tomllib.loads((source_repository / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    commit = descriptor["producer"]["source_commit"]
    policies = {}
    for architecture in ARCHITECTURES:
        payload, helper = helper_files(
            inputs / ("native-" + architecture), architecture, version, commit
        )
        members = zip_members(payload[helper["archive"]["path"]])
        relay_path = "vadgr-cua-host.exe"
        if relay_path in members:
            raise ValueError("relay collides with a broker member")
        members[relay_path] = payload[helper["relay"]["path"]]
        if set(members) != set(rules["files"][architecture]):
            raise ValueError("helper member set differs from reviewed signing rules")
        files = {}
        for path, data in sorted(members.items()):
            row = rules["files"][architecture][path]
            if digest(data) != row["input_sha256"]:
                raise ValueError(
                    f"member bytes differ from reviewed input: {architecture}/{path}; "
                    "renew the exact review before producing a policy"
                )
            if (native_identity(data) is not None) == (row["trust_class"] == "data"):
                raise ValueError("native member signing class differs")
            files[path] = dict(row)
        directory = output / architecture
        root = (directory / "trusted-root.json").read_bytes()
        verifier = (directory / "gh.exe").read_bytes()
        if (
            digest(root) != pins["root"]["sha256"]
            or digest(verifier) != pins["architectures"][architecture]["executable_sha256"]
            or digest((directory / "LICENSE").read_bytes()) != pins["license_sha256"]
        ):
            raise ValueError("provisioned verifier inputs changed")
        policy = {
            "schema": 1,
            "architecture": architecture,
            "cua_version": version,
            "source_commit": commit,
            "input_closure": {
                "relay_sha256": helper["relay"]["sha256"],
                "archive_sha256": helper["archive"]["sha256"],
                "manifest_sha256": helper["member_manifest"]["sha256"],
            },
            "root_sha256": digest(root),
            "verifier_sha256": digest(verifier),
            "repository": "MONTBRAIN/vadgr",
            "repository_id": 1158230114,
            "owner_id": 165305289,
            "certificate_identity": "https://github.com/MONTBRAIN/vadgr/.github/workflows/candidate.yml@refs/heads/master",
            "issuer": "https://token.actions.githubusercontent.com",
            "source_ref": "refs/heads/master",
            "source_sha_allowlist": rules["source_sha_allowlist"],
            "signer_sha_allowlist": rules["signer_sha_allowlist"],
            "expires_at": rules["expires_at"],
            "relay_path": relay_path,
            "files": files,
        }
        check_adoption_policy(policy, root, verifier, architecture, version, commit, helper)
        policies[architecture] = canonical(policy)
    for architecture, data in policies.items():
        freeze(output / architecture / "adoption-policy.json", data)

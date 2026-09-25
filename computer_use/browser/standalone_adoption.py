# Copyright 2026 Victor Santiago Montano Diaz
# Licensed under the Apache License, Version 2.0.

"""Adopt only an installed, authenticated Windows closure; never an ambient path."""

from __future__ import annotations

import io
import stat
import time
import zipfile
from pathlib import Path

from computer_use.browser import offline_attestation as offline
from computer_use.browser import profile as profiles
from computer_use.browser.adoption import (
    adopt_signed_closure,
    require_signed_after_adoption,
    validate_offline_policy,
)
from computer_use.browser.managed_authorization import (
    canonical_json,
    digest,
    fields,
    member_path,
    require,
    sha256,
    strict_json,
    validate_final_manifest,
)

MAX_PAYLOAD = 256 * 1024 * 1024


def read(root: Path, name: str, *, limit: int = 4 * 1024 * 1024) -> bytes:
    name = member_path(name)
    path = root / name
    for candidate in (path, *path.parents):
        info = candidate.lstat()
        require(
            not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
            "signed helper path contains a link",
        )
    info = path.lstat()
    require(
        stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= limit,
        "signed helper file is not a bounded ordinary file",
    )
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, "signed helper file exceeds its limit")
    return raw


def archive_members(raw: bytes) -> dict[str, bytes]:
    require(len(raw) <= MAX_PAYLOAD, "helper archive exceeds its limit")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        values = {}
        folded = set()
        total = 0
        require(len(archive.infolist()) <= 4096, "helper archive has too many members")
        for record in archive.infolist():
            path = member_path(record.orig_filename)
            require(path == record.filename, "helper archive member name was normalized")
            require(
                path.casefold() not in folded
                and not record.is_dir()
                and not record.flag_bits & 1
                and stat.S_IFMT(record.external_attr >> 16) in {0, stat.S_IFREG},
                "helper archive contains an unsafe member",
            )
            total += record.file_size
            require(total <= MAX_PAYLOAD, "expanded helper archive exceeds its limit")
            folded.add(path.casefold())
            values[path] = archive.read(record)
        return values


def _record(root: Path, record: dict, *, limit: int = MAX_PAYLOAD) -> bytes:
    fields(record, "path size sha256")
    digest(record["sha256"])
    require(
        type(record["size"]) is int and 0 <= record["size"] <= limit,
        "helper record size is invalid",
    )
    raw = read(root, record["path"], limit=limit)
    require(
        len(raw) == record["size"] and sha256(raw) == record["sha256"],
        "helper record differs from installed bytes",
    )
    return raw


def _probe(architecture: str, input_key: str) -> dict:
    value = offline.native_call(
        {"operation": "probe", "architecture": architecture, "input_key": input_key}
    )
    fields(value, "installed_root state")
    require(
        value["state"] is None or isinstance(value["state"], str),
        "native adoption state is invalid",
    )
    return value


def resolve() -> dict | None:
    """Return freshly verified signed paths, or unsigned input only before adoption.

    A damaged or missing installed generation is a repair error after the
    monotonic state exists. No exception is converted into unsigned fallback.
    """
    trust = profiles.load_package_trust()
    profile = profiles.select_profile()
    if trust["mode"] != "standalone-input" or not profile.windows_helpers:
        return None
    architecture = profile.architecture
    input_manifest = profiles.load_input_manifest(profile)
    helpers = input_manifest["helpers"]
    input_closure = {
        "relay_sha256": helpers["relay"]["sha256"],
        "archive_sha256": helpers["archive"]["sha256"],
        "manifest_sha256": helpers["member_manifest"]["sha256"],
    }
    for value in input_closure.values():
        digest(value)
    input_key = sha256(canonical_json(input_closure))
    probe = _probe(architecture, input_key)
    previous = probe["state"].encode("utf-8") if probe["state"] is not None else None
    root = offline.local_path(probe["installed_root"])
    envelope_path = root / "cua-runtime-authorization.json"
    if trust.get("development") is True:
        require_signed_after_adoption(previous, requested_mode="producer-input")
        # Development input has no adoption trust roots and can never adopt.
        return None
    if not envelope_path.exists():
        require_signed_after_adoption(previous, requested_mode="producer-input")
        return None
    pins = profiles.load_adoption_pins(architecture)
    package = Path(__file__).parent
    directory = package / "adoption" / architecture
    policy_raw = read(directory, "adoption-policy.json")
    roots = read(directory, "trusted-root.json")
    verifier = read(directory, "gh.exe", limit=80 * 1024 * 1024)
    require(
        sha256(roots) == pins["root_sha256"] and sha256(verifier) == pins["verifier_sha256"],
        "packaged adoption trust changed",
    )
    now = int(time.time())
    policy = validate_offline_policy(
        policy_raw,
        expected_sha256=pins["policy_sha256"],
        root_bytes=roots,
        verifier_bytes=verifier,
        architecture=architecture,
        now=now,
    )
    require(policy["input_closure"] == input_closure, "packaged adoption input identity changed")

    def verify(subject, bundle, selected_policy, root_bytes, verifier_bytes):
        return offline.verify(
            subject,
            bundle,
            selected_policy,
            root_bytes,
            verifier_bytes,
            verifier_path=directory / "gh.exe",
            root_path=directory / "trusted-root.json",
        )

    envelope_raw = read(root, "cua-runtime-authorization.json")
    verify(
        envelope_raw, read(root, "cua-runtime-authorization.sigstore.json"), policy, roots, verifier
    )
    envelope = strict_json(envelope_raw, canonical=False)
    fields(
        envelope,
        "schema release_profile cua_version generation payload_sha256 "
        "installed_inventory_sha256 broker_final_manifest_sha256 "
        "helper_closure_authorization_sha256 relay",
    )
    # Both standalone consumers adopt the native Windows installation, not a
    # hypothetical Linux-hosted copy of its Windows closure.
    require(
        type(envelope["schema"]) is int
        and envelope["schema"] == 1
        and envelope["release_profile"] == "windows-" + architecture
        and envelope["cua_version"] == policy["cua_version"]
        and isinstance(envelope["generation"], str)
        and bool(envelope["generation"]),
        "installed runtime authorization has a different identity",
    )
    for key in (
        "payload_sha256",
        "installed_inventory_sha256",
        "broker_final_manifest_sha256",
        "helper_closure_authorization_sha256",
    ):
        digest(envelope[key])
    cua_root = root / "lib" / "cua"
    payload_raw = read(cua_root, "payload.json")
    inventory_raw = read(cua_root, "installed-inventory.json")
    require(
        sha256(payload_raw) == envelope["payload_sha256"]
        and sha256(inventory_raw) == envelope["installed_inventory_sha256"],
        "installed runtime inventory or payload changed",
    )
    inventory = strict_json(inventory_raw, canonical=False)
    fields(inventory, "schema target files")
    require(
        type(inventory["schema"]) is int
        and inventory["schema"] == 1
        and inventory["target"] == architecture + "-pc-windows-msvc"
        and isinstance(inventory["files"], dict),
        "installed inventory has a different target",
    )
    relay = envelope["relay"]
    relay_raw = _record(cua_root, relay)
    require(
        inventory["files"].get(relay["path"]) == {"size": relay["size"], "sha256": relay["sha256"]},
        "installed relay is absent from the authenticated inventory",
    )
    helper = cua_root / "managed-helpers" / architecture
    manifest_raw = read(helper, "broker-final-manifest.json")
    authorization_raw = read(helper, "helper-closure-authorization.json")
    require(
        sha256(manifest_raw) == envelope["broker_final_manifest_sha256"]
        and sha256(authorization_raw) == envelope["helper_closure_authorization_sha256"],
        "installed helper authorization changed",
    )
    manifest = validate_final_manifest(manifest_raw)
    archive_raw = _record(cua_root, manifest["archive"])
    final = archive_members(archive_raw)
    require(policy["relay_path"] not in final, "relay collides with a broker member")
    final[policy["relay_path"]] = relay_raw
    package_root = package.parents[1]
    input_archive = _record(package_root, helpers["archive"])
    require(
        sha256(input_archive) == policy["input_closure"]["archive_sha256"]
        and sha256(_record(package_root, helpers["member_manifest"]))
        == policy["input_closure"]["manifest_sha256"],
        "standalone input closure changed",
    )
    inputs = archive_members(input_archive)
    inputs[policy["relay_path"]] = _record(package_root, helpers["relay"])
    reports_value = strict_json(read(helper, "signature-reports.json"))
    reports = {member_path(path): canonical_json(value) for path, value in reports_value.items()}
    native_request = {
        "operation": "deploy",
        "architecture": architecture,
        "input_key": input_key,
        "archive": offline.windows_path(cua_root / member_path(manifest["archive"]["path"])),
        "archive_sha256": manifest["archive"]["sha256"],
        "manifest": manifest,
        "manifest_path": offline.windows_path(helper / "broker-final-manifest.json"),
        "manifest_sha256": sha256(manifest_raw),
        "relay": {**relay, "path": offline.windows_path(cua_root / member_path(relay["path"]))},
        "relay_member": policy["relay_path"],
        "policy": policy["files"],
        "installed_root": probe["installed_root"],
    }
    receipt = {}

    def verify_installed(_authorization, _manifest, _final, _reports):
        receipt.update(offline.native_call(native_request))
        fields(receipt, "destination relay archive_sha256 manifest_sha256")
        require(
            receipt["archive_sha256"] == manifest["archive"]["sha256"]
            and receipt["manifest_sha256"] == sha256(manifest_raw)
            and receipt["relay"] == native_request["relay"]["path"],
            "native installed verification receipt differs",
        )
        return True

    state = adopt_signed_closure(
        policy_bytes=policy_raw,
        policy_sha256=pins["policy_sha256"],
        root_bytes=roots,
        verifier_bytes=verifier,
        architecture=architecture,
        now=now,
        claim_bytes=read(helper, "pre-signing-claim.json"),
        manifest_bytes=manifest_raw,
        authorization_bytes=authorization_raw,
        receipt_bytes=[read(helper, "receipt-windows.json"), read(helper, "receipt-wsl.json")],
        mapping_bytes=read(helper, "input-output.json"),
        bundle_bytes=read(helper, "authorization.sigstore.json"),
        inputs=inputs,
        final=final,
        reports=reports,
        verify_offline=verify,
        verify_installed=verify_installed,
        previous_state=previous,
    )
    state_raw = canonical_json(state)
    published = offline.native_call(
        {
            **native_request,
            "operation": "publish-state",
            "previous": probe["state"],
            "state": state_raw.decode("utf-8"),
            "authorization_sha256": sha256(authorization_raw),
        }
    )
    require(
        published == {"state_sha256": sha256(state_raw)}, "native adoption state was not committed"
    )
    return {
        "archive": cua_root / member_path(manifest["archive"]["path"]),
        "manifest_path": helper / "broker-final-manifest.json",
        "manifest": manifest,
        "destination": receipt["destination"],
        "relay": offline.local_path(receipt["relay"]),
        "authorization_path": helper / "helper-closure-authorization.json",
        "authorization_sha256": sha256(authorization_raw),
    }

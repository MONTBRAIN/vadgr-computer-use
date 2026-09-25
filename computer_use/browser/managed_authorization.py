# Copyright 2026 Victor Santiago Montano Diaz
# Licensed under the Apache License, Version 2.0.

"""Data-only validation of the immutable signed helper authorization chain.

These checks bind already authenticated records. They do not verify a native
signature or an attestation and must not be used as substitutes for either.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import threading
from pathlib import PurePosixPath, PureWindowsPath
from typing import BinaryIO


class AuthorizationError(ValueError):
    """The helper identity cannot be authorized."""


MAX_RECORD_BYTES = 4 * 1024 * 1024
_managed_launch_lock = threading.Lock()
_managed_launch_record: bytes | None = None
_managed_launch_failure: Exception | None = None


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuthorizationError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


def strict_json(data: bytes, *, canonical: bool = True) -> dict:
    require(
        isinstance(data, bytes) and 0 < len(data) <= MAX_RECORD_BYTES,
        "authorization record exceeds its size limit",
    )

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    def constant(_value):
        raise AuthorizationError("non-finite JSON number")

    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
        require(isinstance(value, dict), "authorization must be a JSON object")
        if canonical:
            require(canonical_json(value) == data, "noncanonical authorization JSON")
        return value
    except (UnicodeError, ValueError, TypeError, RecursionError) as error:
        raise AuthorizationError(str(error)) from error


def fields(value: object, names: str) -> dict:
    require(
        isinstance(value, dict) and set(value) == set(names.split()),
        "unknown or missing authorization fields",
    )
    return value


def digest(value: object) -> str:
    require(
        isinstance(value, str)
        and re.fullmatch(r"[0-9a-f]{64}", value) is not None
        and value != "0" * 64,
        "invalid or placeholder SHA-256",
    )
    return value


def positive(value: object, *, zero: bool = False) -> int:
    require(type(value) is int and value >= (0 if zero else 1), "invalid integer")
    return value


def text_value(value: object) -> str:
    require(
        isinstance(value, str) and bool(value) and not any(ord(c) < 32 for c in value),
        "invalid text value",
    )
    return value


def member_path(value: object) -> str:
    text_value(value)
    require(
        not value.startswith("/") and "\\" not in value and ":" not in value, "unsafe archive path"
    )
    for part in value.split("/"):
        require(
            part not in {"", ".", ".."}
            and not part.endswith((".", " "))
            and not any(c in '<>"|?*' for c in part),
            "unsafe archive path",
        )
        require(
            re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])", part.split(".")[0]) is None,
            "reserved Windows path",
        )
    return value


def installed_path(value: object):
    path = text_value(value)
    windows_path = PureWindowsPath(path)
    posix_path = PurePosixPath(path)
    require(
        windows_path.is_absolute() or posix_path.is_absolute(),
        "managed installed path must be absolute",
    )
    require(not path.startswith(("\\\\", "//")), "managed helper must use a local installed path")
    parsed = windows_path if windows_path.is_absolute() else posix_path
    require(len(parsed.parts) > 1, "managed installed path must not be a filesystem root")
    member_path("/".join(parsed.parts[1:]))
    return parsed


def profile_pair(architecture: str) -> list[str]:
    require(architecture in {"x86_64", "aarch64"}, "unsupported helper architecture")
    return [f"windows-{architecture}", f"wsl-{architecture}"]


def consumer_inputs(value: object, architecture: str) -> dict:
    require(
        isinstance(value, dict) and set(value) == set(profile_pair(architecture)),
        "both exact helper consumers are required",
    )
    for binding in value.values():
        fields(binding, "candidate_sha256 catalog_sha256 lock_sha256 wheel_sha256")
        for item in binding.values():
            digest(item)
    return value


def closure_identity(value: object) -> dict:
    fields(value, "relay_sha256 archive_sha256 manifest_sha256")
    for item in value.values():
        digest(item)
    return value


def validate_final_manifest(data: bytes) -> dict:
    value = strict_json(data)
    fields(
        value,
        "schema mode cua_version architecture consumer_profiles helper_closure_id "
        "source_commit tooling_commit input_catalog_sha256 input_manifest_sha256 "
        "input_archive_sha256 consumer_inputs signing_claim_ref pre_signing_claim_sha256 "
        "signing_run_id signing_attempt signing_job_id archive files "
        "publisher_policy_sha256 predecessor_catalog_sha256",
    )
    require(
        type(value["schema"]) is int and value["schema"] == 1 and value["mode"] == "managed-signed",
        "unsupported final manifest",
    )
    require(
        value["consumer_profiles"] == profile_pair(value["architecture"]),
        "invalid consumer profile pair",
    )
    consumer_inputs(value["consumer_inputs"], value["architecture"])
    for key in (
        "cua_version",
        "helper_closure_id",
        "source_commit",
        "tooling_commit",
        "signing_claim_ref",
        "signing_job_id",
    ):
        text_value(value[key])
    for key in ("source_commit", "tooling_commit"):
        require(
            re.fullmatch(r"[0-9a-f]{40}", value[key]) is not None and value[key] != "0" * 40,
            "invalid source or tooling commit",
        )
    for key in (
        "input_catalog_sha256",
        "input_manifest_sha256",
        "input_archive_sha256",
        "pre_signing_claim_sha256",
        "publisher_policy_sha256",
        "predecessor_catalog_sha256",
    ):
        digest(value[key])
    positive(value["signing_run_id"])
    require(
        type(value["signing_attempt"]) is int and value["signing_attempt"] == 1,
        "unexpected signing attempt",
    )
    archive = fields(value["archive"], "path size sha256")
    member_path(archive["path"])
    positive(archive["size"])
    digest(archive["sha256"])
    require(isinstance(value["files"], list) and bool(value["files"]), "empty member list")
    paths = []
    for row in value["files"]:
        fields(
            row,
            "path size input_sha256 sha256 role execution_os architecture trust_class "
            "signer_policy_sha256 legal_approval_sha256 signature_report_sha256",
        )
        paths.append(member_path(row["path"]))
        require(
            row["path"].split("/")[-1].lower() != "broker-final-manifest.json",
            "final manifest cannot contain itself",
        )
        positive(row["size"], zero=True)
        digest(row["input_sha256"])
        digest(row["sha256"])
        require(
            row["role"] == "browser-broker"
            and row["execution_os"] == "windows"
            and row["architecture"] == value["architecture"],
            "invalid member role",
        )
        require(
            row["trust_class"] in {"publisher-sign", "vendor-preserve", "data"},
            "unknown signature trust class",
        )
        for key in ("signer_policy_sha256", "legal_approval_sha256", "signature_report_sha256"):
            if row["trust_class"] == "data":
                require(row[key] is None, "data member cannot assert a signature")
            else:
                digest(row[key])
        if row["trust_class"] != "publisher-sign":
            require(row["input_sha256"] == row["sha256"], "preserved member changed")
    require(
        paths == sorted(paths, key=lambda p: p.encode("utf-8"))
        and len({p.casefold() for p in paths}) == len(paths),
        "unsorted or colliding member paths",
    )
    return value


def validate_chain(
    claim_bytes: bytes,
    manifest_bytes: bytes,
    authorization_bytes: bytes,
    receipt_bytes: list[bytes],
    *,
    observed_consumers: dict,
    signing_ledger: list[dict],
) -> dict:
    """Bind a prior claim, a frozen manifest, authorization, and both receipts.

    observed_consumers and signing_ledger must come from the trusted consumer
    and signer checks, never from fields supplied by an untrusted envelope.
    """
    return _validate_chain(
        claim_bytes,
        manifest_bytes,
        authorization_bytes,
        receipt_bytes,
        observed_consumers=observed_consumers,
        signing_ledger=signing_ledger,
        authenticated=False,
    )


def validate_authenticated_chain(
    claim_bytes: bytes,
    manifest_bytes: bytes,
    authorization_bytes: bytes,
    receipt_bytes: list[bytes],
) -> dict:
    """Check a chain after the fixed trusted workflow authenticated authorization.

    The protected coordinator measures both consumers and its signing ledger
    before issuing authorization. Those observations are not reconstructed by
    the offline consumer, and a GitHub certificate does not assert a job id.
    """
    return _validate_chain(
        claim_bytes,
        manifest_bytes,
        authorization_bytes,
        receipt_bytes,
        observed_consumers=None,
        signing_ledger=None,
        authenticated=True,
    )


def _validate_chain(
    claim_bytes: bytes,
    manifest_bytes: bytes,
    authorization_bytes: bytes,
    receipt_bytes: list[bytes],
    *,
    observed_consumers: dict | None,
    signing_ledger: list[dict] | None,
    authenticated: bool,
) -> dict:
    claim = strict_json(claim_bytes)
    fields(
        claim,
        "schema helper_closure_id architecture cua_version source_commit tooling_commit "
        "input_closure consumer_inputs publisher_policy_sha256 legal_policy_sha256 "
        "signing_claim_ref signing_run_id signing_attempt signing_job_id "
        "publisher_sign_paths signing_operations adoption_inputs",
    )
    require(type(claim["schema"]) is int and claim["schema"] == 1, "invalid signing claim")
    closure_identity(claim["input_closure"])
    manifest = validate_final_manifest(manifest_bytes)
    authorization = strict_json(authorization_bytes)
    fields(
        authorization,
        "schema pre_signing_claim_sha256 helper_closure_id architecture "
        "cua_version source_commit tooling_commit input_closure final_closure consumer_inputs "
        "signing_run_id signing_attempt signing_job_id output_artifact "
        "publisher_policy_sha256 legal_policy_sha256 mapping_sha256 adoption_edges",
    )
    require(
        type(authorization["schema"]) is int and authorization["schema"] == 1,
        "invalid closure authorization",
    )
    claim_hash = sha256(claim_bytes)
    require(
        manifest["pre_signing_claim_sha256"] == claim_hash
        and authorization["pre_signing_claim_sha256"] == claim_hash,
        "signing claim digest mismatch",
    )
    for key in (
        "helper_closure_id",
        "architecture",
        "cua_version",
        "source_commit",
        "tooling_commit",
        "consumer_inputs",
        "signing_run_id",
        "signing_attempt",
        "signing_job_id",
        "publisher_policy_sha256",
    ):
        require(claim[key] == manifest[key] == authorization[key], "claim binding mismatch: " + key)
    require(claim["signing_claim_ref"] == manifest["signing_claim_ref"], "claim reference changed")
    require(
        claim["legal_policy_sha256"] == authorization["legal_policy_sha256"], "legal policy changed"
    )
    digest(claim["legal_policy_sha256"])
    digest(authorization["mapping_sha256"])
    require(authorization["input_closure"] == claim["input_closure"], "input closure changed")
    require(
        manifest["input_manifest_sha256"] == claim["input_closure"]["manifest_sha256"]
        and manifest["input_archive_sha256"] == claim["input_closure"]["archive_sha256"],
        "input manifest/archive changed",
    )
    require(
        all(
            binding["catalog_sha256"] == manifest["input_catalog_sha256"]
            for binding in claim["consumer_inputs"].values()
        ),
        "input catalog changed",
    )
    final = closure_identity(authorization["final_closure"])
    require(
        final["manifest_sha256"] == sha256(manifest_bytes)
        and final["archive_sha256"] == manifest["archive"]["sha256"],
        "final closure digest mismatch",
    )
    artifact = fields(authorization["output_artifact"], "id sha256 subjects")
    positive(artifact["id"])
    digest(artifact["sha256"])
    fields(artifact["subjects"], "relay_sha256 archive_sha256 manifest_sha256 mapping_sha256")
    require(
        artifact["subjects"] == {**final, "mapping_sha256": authorization["mapping_sha256"]},
        "helper artifact must precede its authorization",
    )
    inputs = claim["adoption_inputs"]
    require(
        isinstance(inputs, list) and inputs == [claim["input_closure"]], "unknown adoption input"
    )
    require(
        authorization["adoption_edges"]
        == [
            {
                "direction": "unsigned-to-signed",
                "architecture": claim["architecture"],
                "cua_version": claim["cua_version"],
                "source_commit": claim["source_commit"],
                "input_closure": inputs[0],
                "final_closure": final,
            }
        ],
        "invalid adoption transformation edge",
    )
    paths = claim["publisher_sign_paths"]
    require(isinstance(paths, list) and bool(paths), "missing signing paths")
    require(paths == sorted(set(paths)), "duplicate or unsorted signing path")
    for path in paths:
        member_path(path)
    broker_signing = {
        row["path"] for row in manifest["files"] if row["trust_class"] == "publisher-sign"
    }
    broker_paths = {row["path"] for row in manifest["files"]}
    require(
        set(paths) & broker_paths == broker_signing and len(set(paths) - broker_paths) == 1,
        "signing claim must cover the broker publishers and one relay",
    )
    positive(claim["signing_operations"])
    require(claim["signing_operations"] == len(paths), "signing quota mismatch")
    require(
        authenticated
        or signing_ledger
        == [
            {
                "pre_signing_claim_sha256": claim_hash,
                "helper_closure_id": claim["helper_closure_id"],
                "operations": len(paths),
            }
        ],
        "shared signing quota must be spent exactly once",
    )
    pair = profile_pair(claim["architecture"])
    require(
        authenticated or observed_consumers == {profile: final for profile in pair},
        "managed consumers do not contain identical final helpers",
    )
    require(len(receipt_bytes) == 2, "both consumer receipts are required")
    receipts = {}
    for raw in receipt_bytes:
        receipt = strict_json(raw)
        fields(
            receipt,
            "schema profile input broker_final_manifest_sha256 helper_closure_authorization_sha256",
        )
        require(
            type(receipt["schema"]) is int
            and receipt["schema"] == 1
            and receipt["profile"] in pair
            and receipt["profile"] not in receipts,
            "invalid or duplicate consumption receipt",
        )
        require(
            receipt["input"] == claim["consumer_inputs"][receipt["profile"]]
            and receipt["broker_final_manifest_sha256"] == sha256(manifest_bytes)
            and receipt["helper_closure_authorization_sha256"] == sha256(authorization_bytes),
            "consumption receipt binding mismatch",
        )
        receipts[receipt["profile"]] = receipt
    return authorization


def load_managed_authorization(
    pipe: BinaryIO, *, profile: str, generation: str, inventory_sha256: str, manifest_sha256: str
) -> dict:
    """Read a bounded record from the parent's dedicated inherited pipe.

    The caller supplies pins from authenticated installed metadata. A path,
    environment digest, or adjacent manifest is not an authenticated pin.
    """
    value, manifest = read_managed_authorization(pipe, profile=profile)
    digest(inventory_sha256)
    digest(manifest_sha256)
    require(
        value["profile"] == profile
        and value["generation"] == generation
        and value["inventory_sha256"] == inventory_sha256
        and value["broker_final_manifest_sha256"] == manifest_sha256,
        "managed launch identity mismatch",
    )
    return manifest


def read_managed_authorization(pipe: BinaryIO, *, profile: str) -> tuple[dict, dict]:
    """Read the dedicated parent-authenticated channel, returning envelope and manifest.

    The launcher must supply an inherited read-only anonymous pipe. This API
    does not turn arbitrary file contents into an authenticated parent channel.
    """
    require(pipe is not None, "managed CUA requires its parent authorization pipe")
    raw = pipe.read(MAX_RECORD_BYTES + 1)
    value = strict_json(raw)
    fields(
        value,
        "schema generation profile inventory_sha256 broker_final_manifest_sha256 "
        "helper_closure_authorization_sha256 broker_final_manifest relay installed_root",
    )
    require(
        type(value["schema"]) is int and value["schema"] == 1,
        "unsupported managed launch authorization",
    )
    text_value(value["generation"])
    digest(value["inventory_sha256"])
    digest(value["broker_final_manifest_sha256"])
    digest(value["helper_closure_authorization_sha256"])
    require(value["profile"] == profile, "managed launch profile mismatch")
    manifest_bytes = canonical_json(value["broker_final_manifest"])
    require(
        sha256(manifest_bytes) == value["broker_final_manifest_sha256"],
        "managed manifest digest mismatch",
    )
    manifest = validate_final_manifest(manifest_bytes)
    require(profile in manifest["consumer_profiles"], "managed profile mismatch")
    relay = fields(value["relay"], "path size sha256")
    path = installed_path(relay["path"])
    root = installed_path(value["installed_root"])
    require(
        type(path) is type(root) and path != root and path.is_relative_to(root),
        "managed relay is outside the authenticated installed root",
    )
    positive(relay["size"])
    digest(relay["sha256"])
    return value, manifest


def managed_launch_authorization(pipe_factory, *, profile: str) -> tuple[dict, dict]:
    """Read the parent channel once for registration and broker launch.

    Returned objects are copies. Each consumer must verify the installed relay
    path containment, ACLs and bytes against the returned inventory binding.
    A failed first read remains failed for this process.
    """
    global _managed_launch_record, _managed_launch_failure
    with _managed_launch_lock:
        if _managed_launch_failure is not None:
            raise AuthorizationError("managed parent authorization previously failed") from (
                _managed_launch_failure
            )
        if _managed_launch_record is None:
            try:
                stream = pipe_factory()
                require(stream is not None, "managed CUA requires its parent authorization pipe")
                try:
                    envelope, _ = read_managed_authorization(stream, profile=profile)
                finally:
                    stream.close()
                _managed_launch_record = canonical_json(envelope)
            except Exception as error:
                _managed_launch_failure = error
                raise
        return read_managed_authorization(io.BytesIO(_managed_launch_record), profile=profile)

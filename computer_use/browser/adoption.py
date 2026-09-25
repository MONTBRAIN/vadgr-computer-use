# Copyright 2026 Victor Santiago Montano Diaz
# Licensed under the Apache License, Version 2.0.

"""Offline signed-helper admission using packaged, digest-pinned trust policy.

Native signatures and attestations are checked by a trusted verifier adapter.
No default adapter, PATH lookup, download, or unsigned fallback is provided.
"""

from __future__ import annotations

import struct
from collections.abc import Callable

from computer_use.browser.managed_authorization import (
    closure_identity,
    digest,
    fields,
    member_path,
    positive,
    require,
    sha256,
    strict_json,
    validate_authenticated_chain,
    validate_chain,
    validate_final_manifest,
)


def _pe_content(data: bytes, architecture: str) -> bytes:
    """Remove only the PE certificate table and its two mutable header fields."""
    require(len(data) >= 64 and data[:2] == b"MZ", "invalid native executable")
    offset = struct.unpack_from("<I", data, 60)[0]
    require(
        offset + 24 <= len(data) and data[offset : offset + 4] == b"PE\0\0", "invalid PE header"
    )
    machine, sections = struct.unpack_from("<HH", data, offset + 4)
    require(
        machine == {"x86_64": 0x8664, "aarch64": 0xAA64}.get(architecture),
        "wrong native executable architecture",
    )
    optional_size = struct.unpack_from("<H", data, offset + 20)[0]
    optional = offset + 24
    require(
        optional_size >= 152 and optional + optional_size + sections * 40 <= len(data),
        "truncated PE headers",
    )
    require(struct.unpack_from("<H", data, optional)[0] == 0x20B, "PE32+ is required")
    require(struct.unpack_from("<I", data, optional + 108)[0] >= 5, "missing PE security directory")
    security = optional + 112 + 4 * 8
    cert_offset, cert_size = struct.unpack_from("<II", data, security)
    require((cert_offset == 0) == (cert_size == 0), "invalid certificate range")
    section_end = optional + optional_size + sections * 40
    for index in range(sections):
        start = optional + optional_size + index * 40
        size, pointer = struct.unpack_from("<II", data, start + 16)
        require(pointer + size <= len(data), "truncated PE section")
        section_end = max(section_end, pointer + size)
    if cert_size:
        require(
            cert_offset % 8 == 0
            and cert_size >= 8
            and cert_offset >= section_end
            and cert_offset + cert_size == len(data),
            "unexplained certificate table or overlay",
        )
        cursor = cert_offset
        while cursor < len(data):
            require(cursor + 8 <= len(data), "truncated certificate entry")
            length, revision, kind = struct.unpack_from("<IHH", data, cursor)
            require(
                length >= 8 and cursor + length <= len(data) and revision == 0x200 and kind == 2,
                "invalid certificate entry",
            )
            cursor += (length + 7) & ~7
        require(cursor == len(data), "invalid certificate padding")
    result = bytearray(data[:cert_offset] if cert_size else data)
    result[optional + 64 : optional + 68] = b"\0" * 4
    result[security : security + 8] = b"\0" * 8
    return bytes(result)


def validate_mapping(
    mapping_bytes: bytes,
    *,
    inputs: dict[str, bytes],
    final: dict[str, bytes],
    policy: dict,
    reports: dict[str, bytes],
) -> list[str]:
    """Check all bytes and authenticated native reports against the pinned classes."""
    mapping = strict_json(mapping_bytes)
    fields(mapping, "schema files")
    require(
        type(mapping["schema"]) is int and mapping["schema"] == 1, "invalid transformation mapping"
    )
    require(isinstance(mapping["files"], list), "invalid transformation files")
    expected = policy["files"]
    require(
        isinstance(expected, dict) and set(inputs) == set(final) == set(expected),
        "transformation file set differs from packaged inputs",
    )
    rows = {}
    signing = []
    for row in mapping["files"]:
        fields(row, "path input_sha256 sha256 size trust_class signature_report_sha256")
        path = member_path(row["path"])
        require(path not in rows, "duplicate transformation path")
        rows[path] = row
    require(
        list(rows) == sorted(expected) and len({p.casefold() for p in rows}) == len(rows),
        "missing, unsorted or colliding transformation paths",
    )
    expected_reports = set()
    for path, row in rows.items():
        pinned = fields(
            expected[path],
            "input_sha256 trust_class signer_policy_sha256 "
            "legal_approval_sha256 signer certificate_sha256 chain_root_sha256 "
            "digest_algorithm timestamp_algorithm",
        )
        digest(pinned["input_sha256"])
        require(
            row["input_sha256"] == pinned["input_sha256"] == sha256(inputs[path])
            and row["sha256"] == sha256(final[path])
            and type(row["size"]) is int
            and row["size"] == len(final[path]),
            "transformation member digest mismatch",
        )
        kind = pinned["trust_class"]
        require(
            kind in {"data", "vendor-preserve", "publisher-sign"} and row["trust_class"] == kind,
            "signature trust class substitution",
        )
        if kind != "publisher-sign":
            require(inputs[path] == final[path], "preserved member bytes changed")
        if kind == "data":
            require(
                row["signature_report_sha256"] is None
                and all(
                    pinned[key] is None
                    for key in pinned
                    if key not in {"input_sha256", "trust_class"}
                ),
                "data member cannot assert native trust",
            )
            require(not final[path].startswith(b"MZ"), "executable cannot use data trust class")
            continue
        expected_reports.add(path)
        require(path in reports, "missing native signature report")
        digest(pinned["signer_policy_sha256"])
        digest(pinned["legal_approval_sha256"])
        digest(pinned["certificate_sha256"])
        digest(pinned["chain_root_sha256"])
        report_bytes = reports[path]
        require(row["signature_report_sha256"] == sha256(report_bytes), "signature report changed")
        report = strict_json(report_bytes)
        fields(
            report,
            "schema file_sha256 trust_class signer certificate_sha256 chain_root_sha256 "
            "digest_algorithm timestamp_algorithm signer_policy_sha256 legal_approval_sha256 "
            "signtool_exit authenticode_status chain_valid timestamp_valid",
        )
        require(
            type(report["schema"]) is int
            and report["schema"] == 1
            and type(report["signtool_exit"]) is int
            and report["signtool_exit"] == 0
            and report["authenticode_status"] == "Valid"
            and report["chain_valid"] is True
            and report["timestamp_valid"] is True
            and report["file_sha256"] == row["sha256"],
            "native signature verification failed",
        )
        for key in (
            "trust_class",
            "signer",
            "certificate_sha256",
            "chain_root_sha256",
            "digest_algorithm",
            "timestamp_algorithm",
            "signer_policy_sha256",
            "legal_approval_sha256",
        ):
            require(report[key] == pinned[key], "native signature policy mismatch: " + key)
        _pe_content(final[path], policy["architecture"])
        if kind == "publisher-sign":
            signing.append(path)
            require(
                report["digest_algorithm"] == "sha256"
                and report["timestamp_algorithm"] == "rfc3161-sha256",
                "publisher signature requires SHA-256 and RFC 3161",
            )
            original_content = _pe_content(inputs[path], policy["architecture"])
            final_content = _pe_content(final[path], policy["architecture"])
            padding = b"\0" * ((-len(original_content)) % 8)
            require(
                final_content in (original_content, original_content + padding),
                "signing changed executable content",
            )
    require(set(reports) == expected_reports, "unexpected native signature reports")
    return signing


def validate_offline_policy(
    policy_bytes: bytes,
    *,
    expected_sha256: str,
    root_bytes: bytes,
    verifier_bytes: bytes,
    architecture: str,
    now: int,
) -> dict:
    """The expected digest must come from generated package trust metadata."""
    digest(expected_sha256)
    require(sha256(policy_bytes) == expected_sha256, "packaged adoption policy changed")
    policy = strict_json(policy_bytes, canonical=False)
    fields(
        policy,
        "schema architecture cua_version source_commit input_closure root_sha256 "
        "verifier_sha256 repository repository_id owner_id certificate_identity issuer "
        "source_ref source_sha_allowlist signer_sha_allowlist expires_at relay_path files",
    )
    require(
        type(policy["schema"]) is int
        and policy["schema"] == 1
        and architecture in {"x86_64", "aarch64"}
        and policy["architecture"] == architecture,
        "adoption architecture mismatch",
    )
    require(
        policy["repository"] == "MONTBRAIN/vadgr"
        and type(policy["repository_id"]) is int
        and policy["repository_id"] == 1158230114
        and type(policy["owner_id"]) is int
        and policy["owner_id"] == 165305289
        and policy["certificate_identity"]
        == "https://github.com/MONTBRAIN/vadgr/.github/workflows/candidate.yml@refs/heads/master"
        and policy["issuer"] == "https://token.actions.githubusercontent.com"
        and policy["source_ref"] == "refs/heads/master",
        "unexpected adoption authority",
    )
    positive(now)
    positive(policy["expires_at"])
    require(now < policy["expires_at"], "adoption policy expired; reinstall the standalone package")
    for key in ("root_sha256", "verifier_sha256"):
        digest(policy[key])
    require(
        sha256(root_bytes) == policy["root_sha256"]
        and sha256(verifier_bytes) == policy["verifier_sha256"],
        "offline verifier/root changed",
    )
    _pe_content(verifier_bytes, architecture)
    for key in ("source_sha_allowlist", "signer_sha_allowlist"):
        values = policy[key]
        require(
            isinstance(values, list) and 0 < len(values) <= 4 and len(set(values)) == len(values),
            "missing reviewed workflow/source pins",
        )
        for value in values:
            require(
                isinstance(value, str)
                and len(value) == 40
                and all(c in "0123456789abcdef" for c in value)
                and value != "0" * 40,
                "invalid workflow/source pin",
            )
    closure_identity(policy["input_closure"])
    member_path(policy["relay_path"])
    return policy


def adoption_state(
    *,
    policy: dict,
    authorization_sha256: str,
    final_closure: dict,
    previous: bytes | None,
    retained_available: bool,
) -> dict:
    """Validate monotonic state before an owner-only atomic publication.

    A missing retained generation is a repair error, never permission to use
    the original unsigned closure. Callers must retain this state on uninstall.
    """
    digest(authorization_sha256)
    closure_identity(final_closure)
    value = {
        "schema": 1,
        "architecture": policy["architecture"],
        "input_closure": policy["input_closure"],
        "final_closure": final_closure,
        "authorization_sha256": authorization_sha256,
        "mode": "managed-signed",
    }
    if previous is not None:
        old = strict_json(previous)
        fields(old, "schema architecture input_closure final_closure authorization_sha256 mode")
        require(old == value, "adoption state changed; an exact signed transition is required")
    require(
        retained_available, "retained signed helper is missing; repair or reinstall is required"
    )
    return value


def require_signed_after_adoption(previous: bytes | None, *, requested_mode: str) -> None:
    if previous is not None:
        old = strict_json(previous)
        fields(old, "schema architecture input_closure final_closure authorization_sha256 mode")
        require(
            type(old["schema"]) is int and old["schema"] == 1 and old["mode"] == "managed-signed",
            "invalid retained adoption state",
        )
        closure_identity(old["input_closure"])
        closure_identity(old["final_closure"])
        digest(old["authorization_sha256"])
        require(
            requested_mode == "managed-signed",
            "signed-to-unsigned downgrade is forbidden; repair or reinstall is required",
        )


def adopt_signed_closure(
    *,
    policy_bytes: bytes,
    policy_sha256: str,
    root_bytes: bytes,
    verifier_bytes: bytes,
    architecture: str,
    now: int,
    claim_bytes: bytes,
    manifest_bytes: bytes,
    authorization_bytes: bytes,
    receipt_bytes: list[bytes],
    mapping_bytes: bytes,
    bundle_bytes: bytes,
    inputs: dict[str, bytes],
    final: dict[str, bytes],
    reports: dict[str, bytes],
    observed_consumers: dict | None = None,
    signing_ledger: list[dict] | None = None,
    verify_offline: Callable | None = None,
    verify_installed: Callable | None = None,
    previous_state: bytes | None = None,
) -> dict:
    """Admit one closure only after trusted offline and native verifier callbacks.

    verify_offline returns checked provenance, or raises. verify_installed
    independently verifies all deployed files, archive, signatures and ACLs and
    returns True. Callbacks are installed program code, never envelope values.
    """
    policy = validate_offline_policy(
        policy_bytes,
        expected_sha256=policy_sha256,
        root_bytes=root_bytes,
        verifier_bytes=verifier_bytes,
        architecture=architecture,
        now=now,
    )
    require(
        callable(verify_offline) and callable(verify_installed),
        "offline and native signature verifiers are required",
    )
    proof = verify_offline(authorization_bytes, bundle_bytes, policy, root_bytes, verifier_bytes)
    fields(
        proof,
        "subject_sha256 repository repository_id owner_id certificate_identity issuer "
        "source_ref source_sha signer_sha run_id attempt self_hosted",
    )
    require(
        proof["subject_sha256"] == sha256(authorization_bytes)
        and proof["source_sha"] in policy["source_sha_allowlist"]
        and proof["signer_sha"] in policy["signer_sha_allowlist"]
        and proof["self_hosted"] is False,
        "offline attestation provenance mismatch",
    )
    for key in (
        "repository",
        "repository_id",
        "owner_id",
        "certificate_identity",
        "issuer",
        "source_ref",
    ):
        require(proof[key] == policy[key], "offline attestation policy mismatch: " + key)
    chain_verifier = validate_authenticated_chain
    chain_options = {}
    if observed_consumers is not None or signing_ledger is not None:
        chain_verifier = validate_chain
        chain_options = {"observed_consumers": observed_consumers, "signing_ledger": signing_ledger}
    authorization = chain_verifier(
        claim_bytes,
        manifest_bytes,
        authorization_bytes,
        receipt_bytes,
        **chain_options,
    )
    for key in ("architecture", "cua_version", "source_commit", "input_closure"):
        require(authorization[key] == policy[key], "unapproved standalone input identity")
    for proof_key, auth_key in (
        ("run_id", "signing_run_id"),
        ("attempt", "signing_attempt"),
    ):
        require(proof[proof_key] == authorization[auth_key], "signer execution mismatch")
    require(sha256(mapping_bytes) == authorization["mapping_sha256"], "signed mapping changed")
    signing = validate_mapping(
        mapping_bytes, inputs=inputs, final=final, policy=policy, reports=reports
    )
    claim = strict_json(claim_bytes)
    require(signing == claim["publisher_sign_paths"], "signing quota includes the wrong members")
    manifest = validate_final_manifest(manifest_bytes)
    relay = policy["relay_path"]
    require(
        set(final) == {row["path"] for row in manifest["files"]} | {relay}
        and relay not in {row["path"] for row in manifest["files"]},
        "signed mapping must contain the exact broker members and relay",
    )
    require(
        sha256(inputs[relay]) == policy["input_closure"]["relay_sha256"]
        and sha256(final[relay]) == authorization["final_closure"]["relay_sha256"],
        "relay differs from the authorized closure",
    )
    for row in manifest["files"]:
        path = row["path"]
        require(
            path in final
            and sha256(final[path]) == row["sha256"]
            and len(final[path]) == row["size"]
            and sha256(inputs[path]) == row["input_sha256"]
            and row["trust_class"] == policy["files"][path]["trust_class"],
            "final manifest differs from the signed mapping",
        )
        for key in ("signer_policy_sha256", "legal_approval_sha256"):
            require(row[key] == policy["files"][path][key], "member trust policy changed")
        expected_report = sha256(reports[path]) if path in reports else None
        require(row["signature_report_sha256"] == expected_report, "member report changed")
    require(
        verify_installed(authorization, manifest, final, reports) is True,
        "installed helper verification failed",
    )
    return adoption_state(
        policy=policy,
        authorization_sha256=sha256(authorization_bytes),
        final_closure=authorization["final_closure"],
        previous=previous_state,
        retained_available=True,
    )

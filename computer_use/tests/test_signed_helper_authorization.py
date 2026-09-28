# Copyright 2026 Victor Santiago Montano Diaz
# Licensed under the Apache License, Version 2.0.

"""Data-only trust-chain fixtures; these do not establish native signing trust."""

import copy
import io
import struct
import zipfile
from types import SimpleNamespace

import pytest

from computer_use.browser import windows_broker
from computer_use.browser.adoption import (
    adopt_signed_closure,
    adoption_state,
    require_signed_after_adoption,
    validate_mapping,
    validate_offline_policy,
)
from computer_use.browser.managed_authorization import (
    AuthorizationError,
    canonical_json,
    managed_launch_authorization,
    read_managed_authorization,
    sha256,
    strict_json,
    validate_chain,
    validate_final_manifest,
)
from scripts.finalize_signed_helper import deterministic_zip, verify_final_archive


def h(value):
    return sha256(value.encode())


@pytest.fixture
def chain():
    """Each object is frozen once, in dependency order, without a native signer."""
    inputs = {
        "relay_sha256": h("relay-input"),
        "archive_sha256": h("archive-input"),
        "manifest_sha256": h("manifest-input"),
    }
    consumers = {
        profile: {
            "candidate_sha256": h(profile),
            "catalog_sha256": h("catalog"),
            "lock_sha256": h(profile + "lock"),
            "wheel_sha256": h(profile + "wheel"),
        }
        for profile in ("windows-x86_64", "wsl-x86_64")
    }
    claim = {
        "schema": 1,
        "helper_closure_id": "closure-x86_64",
        "architecture": "x86_64",
        "cua_version": "0.7.9",
        "source_commit": "a" * 40,
        "tooling_commit": "b" * 40,
        "input_closure": inputs,
        "consumer_inputs": consumers,
        "publisher_policy_sha256": h("publisher"),
        "legal_policy_sha256": h("legal"),
        "signing_claim_ref": "claim-1",
        "signing_run_id": 123,
        "signing_attempt": 1,
        "signing_job_id": "job-1",
        "publisher_sign_paths": ["relay.exe"],
        "signing_operations": 1,
        "adoption_inputs": [inputs],
    }
    claim_bytes = canonical_json(claim)
    members = {"license.txt": b"retained license"}
    archive = deterministic_zip(members)
    manifest = {
        key: claim[key]
        for key in (
            "schema",
            "helper_closure_id",
            "architecture",
            "cua_version",
            "source_commit",
            "tooling_commit",
            "consumer_inputs",
            "publisher_policy_sha256",
            "signing_claim_ref",
            "signing_run_id",
            "signing_attempt",
            "signing_job_id",
        )
    }
    manifest.update(
        mode="managed-signed",
        consumer_profiles=list(consumers),
        input_catalog_sha256=h("catalog"),
        input_manifest_sha256=inputs["manifest_sha256"],
        input_archive_sha256=inputs["archive_sha256"],
        pre_signing_claim_sha256=sha256(claim_bytes),
        predecessor_catalog_sha256=h("prior"),
        archive={"path": "broker.zip", "size": len(archive), "sha256": sha256(archive)},
        files=[
            {
                "path": "license.txt",
                "size": len(members["license.txt"]),
                "input_sha256": sha256(members["license.txt"]),
                "sha256": sha256(members["license.txt"]),
                "role": "browser-broker",
                "execution_os": "windows",
                "architecture": "x86_64",
                "trust_class": "data",
                "signer_policy_sha256": None,
                "legal_approval_sha256": None,
                "signature_report_sha256": None,
            }
        ],
    )
    manifest_bytes = canonical_json(manifest)
    final = {
        "relay_sha256": h("relay-final"),
        "archive_sha256": sha256(archive),
        "manifest_sha256": sha256(manifest_bytes),
    }
    authorization = {
        key: claim[key]
        for key in (
            "schema",
            "helper_closure_id",
            "architecture",
            "cua_version",
            "source_commit",
            "tooling_commit",
            "input_closure",
            "consumer_inputs",
            "publisher_policy_sha256",
            "legal_policy_sha256",
            "signing_run_id",
            "signing_attempt",
            "signing_job_id",
        )
    }
    authorization.update(
        pre_signing_claim_sha256=sha256(claim_bytes),
        final_closure=final,
        mapping_sha256=h("mapping"),
        output_artifact={
            "id": 321,
            "sha256": h("artifact"),
            "subjects": {**final, "mapping_sha256": h("mapping")},
        },
        adoption_edges=[
            {
                "direction": "unsigned-to-signed",
                "architecture": "x86_64",
                "cua_version": "0.7.9",
                "source_commit": "a" * 40,
                "input_closure": inputs,
                "final_closure": final,
            }
        ],
    )
    authorization_bytes = canonical_json(authorization)
    receipts = [
        canonical_json(
            {
                "schema": 1,
                "profile": profile,
                "input": consumers[profile],
                "broker_final_manifest_sha256": sha256(manifest_bytes),
                "helper_closure_authorization_sha256": sha256(authorization_bytes),
            }
        )
        for profile in consumers
    ]
    return {
        "claim_bytes": claim_bytes,
        "manifest_bytes": manifest_bytes,
        "authorization_bytes": authorization_bytes,
        "receipt_bytes": receipts,
        "observed_consumers": {profile: final for profile in consumers},
        "signing_ledger": [
            {
                "pre_signing_claim_sha256": sha256(claim_bytes),
                "helper_closure_id": "closure-x86_64",
                "operations": 1,
            }
        ],
        "archive": archive,
    }


def check(chain):
    return validate_chain(**{key: value for key, value in chain.items() if key != "archive"})


def test_forward_only_chain_and_final_archive(chain):
    result = check(chain)
    assert result["architecture"] == "x86_64"
    assert verify_final_archive(chain["archive"], chain["manifest_bytes"]) == {
        "license.txt": b"retained license"
    }


@pytest.mark.parametrize(
    "raw",
    [
        b'{"a":1,"a":2}\n',
        b'{"a":NaN}\n',
        b'{"a":1.0}\r\n',
        b' {"a":1}\n',
        b"[]\n",
        b"\xef\xbb\xbf{}\n",
    ],
)
def test_strict_json_rejects_ambiguous_encodings(raw):
    with pytest.raises(AuthorizationError):
        strict_json(raw)


@pytest.mark.parametrize(
    "key",
    [
        "authorization_sha256",
        "helper_closure_authorization_sha256",
        "receipt_sha256",
        "sha256",
        "outer_inventory_sha256",
    ],
)
def test_inner_manifest_rejects_future_and_self_hashes(chain, key):
    manifest = strict_json(chain["manifest_bytes"])
    manifest[key] = h("future")
    with pytest.raises(AuthorizationError):
        validate_final_manifest(canonical_json(manifest))


@pytest.mark.parametrize(
    "record,key,value",
    [
        ("claim_bytes", "signing_operations", 2),
        ("claim_bytes", "tooling_commit", "c" * 40),
        ("manifest_bytes", "input_archive_sha256", h("different")),
        ("manifest_bytes", "pre_signing_claim_sha256", "0" * 64),
        ("manifest_bytes", "signing_attempt", 2),
        ("authorization_bytes", "legal_policy_sha256", h("different")),
        ("authorization_bytes", "receipt_sha256", h("future")),
    ],
)
def test_mutating_frozen_objects_breaks_downstream_bindings(chain, record, key, value):
    obj = strict_json(chain[record])
    obj[key] = value
    chain[record] = canonical_json(obj)
    with pytest.raises(AuthorizationError):
        check(chain)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "swap-input", "stale-manifest"])
def test_both_receipts_are_bound_to_exact_profiles(chain, mutation):
    if mutation == "missing":
        chain["receipt_bytes"].pop()
    elif mutation == "duplicate":
        chain["receipt_bytes"][1] = chain["receipt_bytes"][0]
    else:
        receipt = strict_json(chain["receipt_bytes"][1])
        if mutation == "swap-input":
            receipt["input"] = strict_json(chain["receipt_bytes"][0])["input"]
        else:
            receipt["broker_final_manifest_sha256"] = h("old")
        chain["receipt_bytes"][1] = canonical_json(receipt)
    with pytest.raises(AuthorizationError):
        check(chain)


def test_separately_resigned_wsl_output_is_not_equal(chain):
    chain["observed_consumers"] = copy.deepcopy(chain["observed_consumers"])
    chain["observed_consumers"]["wsl-x86_64"]["archive_sha256"] = h("equivalent-signature")
    with pytest.raises(AuthorizationError, match="identical"):
        check(chain)


def test_shared_quota_is_once_not_per_consumer(chain):
    chain["signing_ledger"] *= 2
    with pytest.raises(AuthorizationError, match="exactly once"):
        check(chain)


def test_authorization_cannot_appear_in_its_prior_artifact(chain):
    auth = strict_json(chain["authorization_bytes"])
    auth["output_artifact"]["subjects"]["authorization_sha256"] = h("self")
    chain["authorization_bytes"] = canonical_json(auth)
    with pytest.raises(AuthorizationError):
        check(chain)


def test_managed_pipe_requires_exact_parent_profile_and_manifest(chain):
    envelope = {
        "schema": 1,
        "generation": "generation-1",
        "profile": "windows-x86_64",
        "inventory_sha256": h("inventory"),
        "broker_final_manifest_sha256": sha256(chain["manifest_bytes"]),
        "helper_closure_authorization_sha256": h("authorization"),
        "broker_final_manifest": strict_json(chain["manifest_bytes"]),
        "installed_root": "C:/installed",
        "relay": {"path": "C:/installed/relay.exe", "size": 12, "sha256": h("relay")},
    }
    raw = canonical_json(envelope)
    result, manifest = read_managed_authorization(io.BytesIO(raw), profile="windows-x86_64")
    assert result == envelope and manifest["mode"] == "managed-signed"
    with pytest.raises(AuthorizationError):
        read_managed_authorization(io.BytesIO(raw), profile="wsl-x86_64")
    envelope["broker_final_manifest"]["cua_version"] = "0.7.8"
    with pytest.raises(AuthorizationError):
        read_managed_authorization(io.BytesIO(canonical_json(envelope)), profile="windows-x86_64")
    with pytest.raises(AuthorizationError):
        read_managed_authorization(None, profile="windows-x86_64")


@pytest.mark.parametrize("profile", ["windows-x86_64", "wsl-x86_64"])
def test_managed_bundle_uses_authenticated_installed_root(chain, tmp_path, monkeypatch, profile):
    cua_root = tmp_path / "lib" / "cua"
    cua_root.mkdir(parents=True)
    archive = cua_root / "broker.zip"
    archive.write_bytes(chain["archive"])
    manifest_path = cua_root / "broker-final-manifest.json"
    manifest_path.write_bytes(chain["manifest_bytes"])
    envelope = {
        "schema": 1,
        "generation": "generation-1",
        "profile": profile,
        "inventory_sha256": h("inventory"),
        "broker_final_manifest_sha256": sha256(chain["manifest_bytes"]),
        "helper_closure_authorization_sha256": sha256(chain["authorization_bytes"]),
        "broker_final_manifest": strict_json(chain["manifest_bytes"]),
        "installed_root": "C:\\installed\\lib\\cua",
        "relay": {
            "path": "C:\\installed\\lib\\cua\\relay.exe",
            "size": 12,
            "sha256": h("relay"),
        },
    }
    translated = []

    def local_path(value):
        translated.append(value)
        return cua_root.resolve()

    monkeypatch.setattr("computer_use.browser.offline_attestation.local_path", local_path)

    selected_archive, selected_manifest, metadata = windows_broker._managed_bundle_inputs(
        SimpleNamespace(value=profile),
        pipe=io.BytesIO(canonical_json(envelope)),
    )

    assert selected_archive == archive.resolve()
    assert selected_manifest == manifest_path.resolve()
    assert metadata["archive"]["sha256"] == sha256(chain["archive"])
    assert translated == [envelope["installed_root"]]


@pytest.mark.parametrize(
    "path",
    [
        "relative.exe",
        "C:/x/../relay.exe",
        "C:/relay.exe:ads",
        "//server/share/relay.exe",
        "C:/CON.exe",
        "C:/",
        "C:/other/relay.exe",
        "C:/installed-neighbor/relay.exe",
        "C:/installed",
    ],
)
def test_managed_relay_requires_safe_absolute_path(chain, path):
    envelope = {
        "schema": 1,
        "generation": "generation-1",
        "profile": "windows-x86_64",
        "inventory_sha256": h("inventory"),
        "broker_final_manifest_sha256": sha256(chain["manifest_bytes"]),
        "helper_closure_authorization_sha256": h("authorization"),
        "broker_final_manifest": strict_json(chain["manifest_bytes"]),
        "installed_root": "C:/installed",
        "relay": {"path": path, "size": 12, "sha256": h("relay")},
    }
    with pytest.raises(AuthorizationError):
        read_managed_authorization(io.BytesIO(canonical_json(envelope)), profile="windows-x86_64")


def test_registration_and_launch_share_one_parent_channel(chain, monkeypatch):
    import computer_use.browser.managed_authorization as module

    monkeypatch.setattr(module, "_managed_launch_record", None)
    monkeypatch.setattr(module, "_managed_launch_failure", None)
    envelope = {
        "schema": 1,
        "generation": "generation-1",
        "profile": "windows-x86_64",
        "inventory_sha256": h("inventory"),
        "broker_final_manifest_sha256": sha256(chain["manifest_bytes"]),
        "helper_closure_authorization_sha256": h("authorization"),
        "broker_final_manifest": strict_json(chain["manifest_bytes"]),
        "installed_root": "C:/installed",
        "relay": {"path": "C:/installed/relay.exe", "size": 12, "sha256": h("relay")},
    }
    calls = []

    def factory():
        calls.append(True)
        return io.BytesIO(canonical_json(envelope))

    first, _ = managed_launch_authorization(factory, profile="windows-x86_64")
    first["relay"]["sha256"] = h("tampered")
    second, _ = managed_launch_authorization(factory, profile="windows-x86_64")
    assert second == envelope and calls == [True]
    with pytest.raises(AuthorizationError):
        managed_launch_authorization(factory, profile="wsl-x86_64")
    assert calls == [True]


def test_failed_parent_channel_is_not_retried(monkeypatch):
    import computer_use.browser.managed_authorization as module

    monkeypatch.setattr(module, "_managed_launch_record", None)
    monkeypatch.setattr(module, "_managed_launch_failure", None)
    calls = []

    def factory():
        calls.append(True)
        return io.BytesIO(b"{}\n")

    for _ in range(2):
        with pytest.raises(AuthorizationError):
            managed_launch_authorization(factory, profile="windows-x86_64")
    assert calls == [True]


@pytest.mark.parametrize(
    "path",
    [
        "../bad",
        "/absolute",
        "C:/bad",
        "a\\b",
        "a:stream",
        "CON.txt",
        "a/../b",
        "LPT1",
        "a.",
        "a ",
        "a//b",
        "a?b",
        "broker-final-manifest.json",
    ],
)
def test_deterministic_zip_rejects_unsafe_and_self_containing_paths(path):
    with pytest.raises(AuthorizationError):
        deterministic_zip({path: b"data"})


def test_zip_rebuild_is_byte_identical_and_has_fixed_metadata():
    first = deterministic_zip({"z.txt": b"z", "a.txt": b"a"})
    assert first == deterministic_zip({"a.txt": b"a", "z.txt": b"z"})
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        assert archive.namelist() == ["a.txt", "z.txt"]
        for item in archive.infolist():
            assert item.compress_type == zipfile.ZIP_STORED
            assert item.date_time == (1980, 1, 1, 0, 0, 0)
            assert item.extra == item.comment == b""
    with pytest.raises(AuthorizationError):
        deterministic_zip({"A.txt": b"a", "a.txt": b"a"})


def test_archive_mutation_cannot_reuse_manifest(chain):
    with pytest.raises(AuthorizationError, match="digest"):
        verify_final_archive(chain["archive"] + b"overlay", chain["manifest_bytes"])


def pe_fixture(*, signed=False, changed=False):
    """Structural PE fixture only; its certificate payload is not a signature."""
    value = bytearray(512)
    value[:2] = b"MZ"
    struct.pack_into("<I", value, 60, 64)
    value[64:68] = b"PE\0\0"
    struct.pack_into("<HH", value, 68, 0x8664, 1)
    struct.pack_into("<H", value, 84, 240)
    struct.pack_into("<H", value, 88, 0x20B)
    struct.pack_into("<I", value, 196, 16)
    struct.pack_into("<II", value, 344, 128, 384)
    if changed:
        value[400] = 1
    if signed:
        struct.pack_into("<II", value, 232, 512, 16)
        value += struct.pack("<IHH", 16, 0x200, 2) + b"TESTONLY"
    return bytes(value)


@pytest.fixture
def mapping_case():
    inputs = {
        "broker.exe": pe_fixture(),
        "vendor.dll": pe_fixture(signed=True),
        "license": b"license",
    }
    final = {**inputs, "broker.exe": pe_fixture(signed=True)}
    files = {}
    reports = {}
    rows = []
    for path in sorted(inputs):
        kind = {"broker.exe": "publisher-sign", "vendor.dll": "vendor-preserve", "license": "data"}[
            path
        ]
        pinned = {
            "input_sha256": sha256(inputs[path]),
            "trust_class": kind,
            "signer_policy_sha256": h("policy"),
            "legal_approval_sha256": h("legal"),
            "signer": "test-only",
            "certificate_sha256": h("certificate"),
            "chain_root_sha256": h("root"),
            "digest_algorithm": "sha256",
            "timestamp_algorithm": "rfc3161-sha256",
        }
        if kind == "data":
            for key in pinned:
                if key not in {"input_sha256", "trust_class"}:
                    pinned[key] = None
        else:
            report = {key: value for key, value in pinned.items() if key != "input_sha256"}
            report.update(
                schema=1,
                file_sha256=sha256(final[path]),
                signtool_exit=0,
                authenticode_status="Valid",
                chain_valid=True,
                timestamp_valid=True,
            )
            reports[path] = canonical_json(report)
        files[path] = pinned
        rows.append(
            {
                "path": path,
                "input_sha256": sha256(inputs[path]),
                "sha256": sha256(final[path]),
                "size": len(final[path]),
                "trust_class": kind,
                "signature_report_sha256": sha256(reports[path]) if path in reports else None,
            }
        )
    return {
        "mapping_bytes": canonical_json({"schema": 1, "files": rows}),
        "inputs": inputs,
        "final": final,
        "policy": {"architecture": "x86_64", "files": files},
        "reports": reports,
    }


def test_mapping_keeps_vendor_and_data_exact(mapping_case):
    assert validate_mapping(**mapping_case) == ["broker.exe"]


@pytest.mark.parametrize("path", ["broker.exe", "vendor.dll", "license"])
def test_mapping_rejects_code_vendor_and_data_changes(mapping_case, path):
    content = pe_fixture(signed=True, changed=True) if path.endswith(".exe") else b"changed"
    mapping_case["final"][path] = content
    mapping = strict_json(mapping_case["mapping_bytes"])
    row = next(row for row in mapping["files"] if row["path"] == path)
    row["sha256"], row["size"] = sha256(content), len(content)
    if path in mapping_case["reports"]:
        report = strict_json(mapping_case["reports"][path])
        report["file_sha256"] = sha256(content)
        mapping_case["reports"][path] = canonical_json(report)
        row["signature_report_sha256"] = sha256(mapping_case["reports"][path])
    mapping_case["mapping_bytes"] = canonical_json(mapping)
    with pytest.raises(AuthorizationError):
        validate_mapping(**mapping_case)


@pytest.mark.parametrize(
    "key,value",
    [
        ("signtool_exit", 2),
        ("chain_valid", False),
        ("timestamp_valid", False),
        ("authenticode_status", "NotSigned"),
        ("signer", "other"),
        ("trust_class", "publisher-sign"),
    ],
)
def test_vendor_reports_must_pass_independent_trust_checks(mapping_case, key, value):
    report = strict_json(mapping_case["reports"]["vendor.dll"])
    report[key] = value
    mapping_case["reports"]["vendor.dll"] = canonical_json(report)
    mapping = strict_json(mapping_case["mapping_bytes"])
    mapping["files"][-1]["signature_report_sha256"] = sha256(mapping_case["reports"]["vendor.dll"])
    mapping_case["mapping_bytes"] = canonical_json(mapping)
    with pytest.raises(AuthorizationError):
        validate_mapping(**mapping_case)


def policy_fixture(chain):
    claim = strict_json(chain["claim_bytes"])
    return {
        "schema": 1,
        "architecture": "x86_64",
        "cua_version": "0.7.9",
        "source_commit": "a" * 40,
        "input_closure": claim["input_closure"],
        "root_sha256": h("root"),
        "verifier_sha256": sha256(pe_fixture()),
        "repository": "MONTBRAIN/vadgr",
        "repository_id": 1158230114,
        "owner_id": 165305289,
        "certificate_identity": "https://github.com/MONTBRAIN/vadgr/.github/workflows/candidate.yml@refs/heads/master",
        "issuer": "https://token.actions.githubusercontent.com",
        "source_ref": "refs/heads/master",
        "source_sha_allowlist": ["b" * 40],
        "signer_sha_allowlist": ["c" * 40],
        "expires_at": 200,
        "relay_path": "relay.exe",
        "files": {},
    }


def test_offline_policy_requires_pinned_root_verifier_architecture_and_expiry(chain):
    raw = canonical_json(policy_fixture(chain))
    kwargs = {
        "expected_sha256": sha256(raw),
        "root_bytes": b"root",
        "verifier_bytes": pe_fixture(),
        "architecture": "x86_64",
        "now": 100,
    }
    assert validate_offline_policy(raw, **kwargs)["repository_id"] == 1158230114
    for key, value in [
        ("expected_sha256", h("other")),
        ("root_bytes", b"other"),
        ("verifier_bytes", b"other"),
        ("architecture", "aarch64"),
        ("now", 200),
    ]:
        with pytest.raises(AuthorizationError):
            validate_offline_policy(raw, **{**kwargs, key: value})


@pytest.mark.parametrize(
    "key,value",
    [
        ("source_sha_allowlist", ["*"]),
        ("signer_sha_allowlist", []),
        ("repository_id", 1),
        ("issuer", "https://example.invalid"),
        ("source_ref", "refs/heads/feature"),
    ],
)
def test_offline_policy_rejects_unreviewed_authority(chain, key, value):
    policy = policy_fixture(chain)
    policy[key] = value
    raw = canonical_json(policy)
    with pytest.raises(AuthorizationError):
        validate_offline_policy(
            raw,
            expected_sha256=sha256(raw),
            root_bytes=b"root",
            verifier_bytes=pe_fixture(),
            architecture="x86_64",
            now=100,
        )


def test_adoption_never_downgrades_after_restart_or_missing_generation(chain):
    policy = policy_fixture(chain)
    final = strict_json(chain["authorization_bytes"])["final_closure"]
    args = {
        "policy": policy,
        "authorization_sha256": sha256(chain["authorization_bytes"]),
        "final_closure": final,
        "previous": None,
        "retained_available": True,
    }
    state = canonical_json(adoption_state(**args))
    assert adoption_state(**{**args, "previous": state}) == strict_json(state)
    require_signed_after_adoption(state, requested_mode="managed-signed")
    with pytest.raises(AuthorizationError, match="downgrade"):
        require_signed_after_adoption(state, requested_mode="producer-input")
    with pytest.raises(AuthorizationError, match="repair"):
        adoption_state(**{**args, "previous": state, "retained_available": False})
    with pytest.raises(AuthorizationError):
        adoption_state(**{**args, "previous": state, "authorization_sha256": h("new")})
    with pytest.raises(AuthorizationError):
        require_signed_after_adoption(b'{"corrupt":true}\n', requested_mode="producer-input")


def test_adoption_requires_real_verifier_adapters_before_any_trust_change(chain):
    raw = canonical_json(policy_fixture(chain))
    args = {
        "policy_bytes": raw,
        "policy_sha256": sha256(raw),
        "root_bytes": b"root",
        "verifier_bytes": pe_fixture(),
        "architecture": "x86_64",
        "now": 100,
        **{key: value for key, value in chain.items() if key != "archive"},
        "mapping_bytes": b"",
        "bundle_bytes": b"",
        "inputs": {},
        "final": {},
        "reports": {},
    }
    with pytest.raises(AuthorizationError, match="verifiers are required"):
        adopt_signed_closure(**args)
    with pytest.raises(AuthorizationError, match="fields"):
        adopt_signed_closure(
            **args, verify_offline=lambda *args: {}, verify_installed=lambda *args: True
        )


@pytest.mark.parametrize(
    "key,value",
    [
        ("subject_sha256", h("other")),
        ("source_sha", "d" * 40),
        ("signer_sha", "d" * 40),
        ("self_hosted", True),
        ("repository_id", 1),
        ("certificate_identity", "https://example.invalid"),
        ("run_id", 124),
        ("attempt", 2),
        ("job_id", "other"),
    ],
)
def test_adoption_rejects_mutated_verified_provenance(chain, key, value):
    policy = policy_fixture(chain)
    raw = canonical_json(policy)
    proof = {
        key: policy[key]
        for key in (
            "repository",
            "repository_id",
            "owner_id",
            "certificate_identity",
            "issuer",
            "source_ref",
        )
    }
    proof.update(
        subject_sha256=sha256(chain["authorization_bytes"]),
        source_sha="b" * 40,
        signer_sha="c" * 40,
        run_id=123,
        attempt=1,
        job_id="job-1",
        self_hosted=False,
    )
    proof[key] = value
    with pytest.raises(AuthorizationError):
        adopt_signed_closure(
            policy_bytes=raw,
            policy_sha256=sha256(raw),
            root_bytes=b"root",
            verifier_bytes=pe_fixture(),
            architecture="x86_64",
            now=100,
            **{key: value for key, value in chain.items() if key != "archive"},
            mapping_bytes=b"",
            bundle_bytes=b"",
            inputs={},
            final={},
            reports={},
            verify_offline=lambda *args: proof,
            verify_installed=lambda *args: True,
        )

# Copyright 2026 Victor Santiago Montano Diaz
# Licensed under the Apache License, Version 2.0.

"""Synthetic trust tests, not a signed candidate or live adoption qualification."""

import copy
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from computer_use.browser import offline_attestation as offline
from computer_use.browser import standalone_adoption as runtime
from computer_use.browser.adoption import adopt_signed_closure
from computer_use.browser.managed_authorization import (
    AuthorizationError,
    canonical_json,
    sha256,
    strict_json,
    validate_authenticated_chain,
)
from computer_use.browser.profile import ReleaseProfile
from computer_use.tests.test_signed_helper_authorization import chain as _chain_fixture
from computer_use.tests.test_signed_helper_authorization import (
    h,
    pe_fixture,
    policy_fixture,
)


@pytest.fixture
def synthetic_chain():
    return _chain_fixture.__wrapped__()


@pytest.fixture
def admission(synthetic_chain):
    chain = synthetic_chain
    policy = policy_fixture(chain)
    relay_input, relay_final = pe_fixture(), pe_fixture(signed=True)
    claim = strict_json(chain["claim_bytes"])
    claim["input_closure"]["relay_sha256"] = sha256(relay_input)
    claim["input_closure"]["archive_sha256"] = sha256(chain["archive"])
    claim["adoption_inputs"] = [claim["input_closure"]]
    claim_raw = canonical_json(claim)
    manifest = strict_json(chain["manifest_bytes"])
    manifest["pre_signing_claim_sha256"] = sha256(claim_raw)
    manifest["input_archive_sha256"] = sha256(chain["archive"])
    manifest_raw = canonical_json(manifest)
    auth = strict_json(chain["authorization_bytes"])
    auth["pre_signing_claim_sha256"] = sha256(claim_raw)
    auth["input_closure"] = claim["input_closure"]
    auth["final_closure"]["relay_sha256"] = sha256(relay_final)
    auth["final_closure"]["manifest_sha256"] = sha256(manifest_raw)
    auth["adoption_edges"][0].update(
        input_closure=auth["input_closure"], final_closure=auth["final_closure"]
    )
    policy["input_closure"] = claim["input_closure"]
    data_policy = {
        "input_sha256": sha256(b"retained license"),
        "trust_class": "data",
        **{
            key: None
            for key in (
                "signer_policy_sha256",
                "legal_approval_sha256",
                "signer",
                "certificate_sha256",
                "chain_root_sha256",
                "digest_algorithm",
                "timestamp_algorithm",
            )
        },
    }
    relay_policy = {
        "input_sha256": sha256(relay_input),
        "trust_class": "publisher-sign",
        "signer_policy_sha256": h("publisher"),
        "legal_approval_sha256": h("legal"),
        "signer": "synthetic-only",
        "certificate_sha256": h("certificate"),
        "chain_root_sha256": h("root"),
        "digest_algorithm": "sha256",
        "timestamp_algorithm": "rfc3161-sha256",
    }
    policy["files"] = {"license.txt": data_policy, "relay.exe": relay_policy}
    report = {k: v for k, v in relay_policy.items() if k != "input_sha256"}
    report.update(
        schema=1,
        file_sha256=sha256(relay_final),
        signtool_exit=0,
        authenticode_status="Valid",
        chain_valid=True,
        timestamp_valid=True,
    )
    report_raw = canonical_json(report)
    final = {"license.txt": b"retained license", "relay.exe": relay_final}
    mapping = {
        "schema": 1,
        "files": [
            {
                "path": name,
                "input_sha256": pin["input_sha256"],
                "sha256": sha256(final[name]),
                "size": len(final[name]),
                "trust_class": pin["trust_class"],
                "signature_report_sha256": sha256(report_raw) if name == "relay.exe" else None,
            }
            for name, pin in sorted(policy["files"].items())
        ],
    }
    mapping_raw = canonical_json(mapping)
    auth["mapping_sha256"] = sha256(mapping_raw)
    auth["output_artifact"]["subjects"] = {
        **auth["final_closure"],
        "mapping_sha256": sha256(mapping_raw),
    }
    auth_raw = canonical_json(auth)
    receipts = []
    for raw in chain["receipt_bytes"]:
        value = strict_json(raw)
        value.update(
            broker_final_manifest_sha256=sha256(manifest_raw),
            helper_closure_authorization_sha256=sha256(auth_raw),
        )
        receipts.append(canonical_json(value))
    policy_raw = canonical_json(policy)
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
        subject_sha256=sha256(auth_raw),
        source_sha="b" * 40,
        signer_sha="c" * 40,
        run_id=123,
        attempt=1,
        self_hosted=False,
    )
    return {
        "policy_bytes": policy_raw,
        "policy_sha256": sha256(policy_raw),
        "root_bytes": b"root",
        "verifier_bytes": pe_fixture(),
        "architecture": "x86_64",
        "now": 100,
        "claim_bytes": claim_raw,
        "manifest_bytes": manifest_raw,
        "authorization_bytes": auth_raw,
        "receipt_bytes": receipts,
        "mapping_bytes": mapping_raw,
        "bundle_bytes": b"synthetic bundle",
        "inputs": {"license.txt": b"retained license", "relay.exe": relay_input},
        "final": final,
        "reports": {"relay.exe": report_raw},
        "verify_offline": lambda *args: copy.deepcopy(proof),
        "verify_installed": lambda *args: True,
    }


def test_authenticated_admission_has_no_invented_job_or_ledger(admission):
    state = adopt_signed_closure(**admission)
    assert state["mode"] == "managed-signed"
    assert adopt_signed_closure(**admission, previous_state=canonical_json(state)) == state
    assert (
        validate_authenticated_chain(
            *(
                admission[key]
                for key in ("claim_bytes", "manifest_bytes", "authorization_bytes", "receipt_bytes")
            )
        )["signing_job_id"]
        == "job-1"
    )


@pytest.mark.parametrize(
    "mutation", ["job", "run", "native", "mapping", "receipt", "state", "extra-report"]
)
def test_admission_rejects_unproved_or_changed_boundaries(admission, mutation):
    if mutation in {"job", "run"}:
        proof = admission["verify_offline"]()
        proof["job_id" if mutation == "job" else "run_id"] = (
            "invented" if mutation == "job" else 999
        )
        admission["verify_offline"] = lambda *args: proof
    elif mutation == "native":
        admission["verify_installed"] = lambda *args: False
    elif mutation == "mapping":
        admission["mapping_bytes"] += b" "
    elif mutation == "receipt":
        admission["receipt_bytes"].pop()
    elif mutation == "extra-report":
        admission["reports"]["extra.exe"] = b"{}\n"
    else:
        state = adopt_signed_closure(**admission)
        state["authorization_sha256"] = h("other")
        admission["previous_state"] = canonical_json(state)
    with pytest.raises(AuthorizationError):
        adopt_signed_closure(**admission)


def verifier_output(policy, subject):
    cert = {
        "sourceRepositoryURI": "https://github.com/" + policy["repository"],
        "sourceRepositoryIdentifier": str(policy["repository_id"]),
        "sourceRepositoryOwnerIdentifier": str(policy["owner_id"]),
        "subjectAlternativeName": policy["certificate_identity"],
        "buildSignerURI": policy["certificate_identity"],
        "issuer": policy["issuer"],
        "sourceRepositoryRef": policy["source_ref"],
        "sourceRepositoryDigest": "b" * 40,
        "buildSignerDigest": "c" * 40,
        "runnerEnvironment": "github-hosted",
        "runInvocationURI": "https://github.com/MONTBRAIN/vadgr/actions/runs/123/attempts/1",
    }
    return [
        {
            "verificationResult": {
                "signature": {"certificate": cert},
                "statement": {"subject": [{"digest": {"sha256": sha256(subject)}}]},
            }
        }
    ]


def test_real_verifier_schema_uses_certificate_extensions(admission):
    policy = strict_json(admission["policy_bytes"])
    raw = canonical_json({})
    result = offline.parse_verified_proof(
        json.dumps(verifier_output(policy, raw)).encode(), raw, policy
    )
    assert result["run_id"] == 123 and result["attempt"] == 1 and "job_id" not in result


@pytest.mark.parametrize(
    "key,value",
    [
        ("issuer", "wrong"),
        ("sourceRepositoryIdentifier", "1"),
        ("sourceRepositoryOwnerIdentifier", "1"),
        ("sourceRepositoryRef", "refs/heads/feature"),
        ("sourceRepositoryDigest", "e" * 40),
        ("buildSignerDigest", "e" * 40),
        ("runnerEnvironment", "self-hosted"),
        ("subjectAlternativeName", "wrong"),
        ("buildSignerURI", "wrong"),
        ("runInvocationURI", "https://github.com/other/actions/runs/123/attempts/1"),
    ],
)
def test_certificate_identity_substitution_is_rejected(admission, key, value):
    policy = strict_json(admission["policy_bytes"])
    result = verifier_output(policy, b"subject")
    result[0]["verificationResult"]["signature"]["certificate"][key] = value
    with pytest.raises(AuthorizationError):
        offline.parse_verified_proof(json.dumps(result).encode(), b"subject", policy)


def test_bounded_child_and_clean_environment(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "SYNTHETIC-NOT-A-CREDENTIAL")
    assert (
        "GH_TOKEN" not in offline.clean_environment() and "PATH" not in offline.clean_environment()
    )
    assert (
        offline.run_bounded([sys.executable, "-c", "print('bounded')"], environment={}).strip()
        == b"bounded"
    )
    monkeypatch.setattr(offline, "MAX_OUTPUT", 16)
    with pytest.raises(AuthorizationError, match="limit"):
        offline.run_bounded([sys.executable, "-c", "print('x'*1000)"], environment={})
    with pytest.raises(AuthorizationError, match="timed out"):
        offline.run_bounded(
            [sys.executable, "-c", "import time; time.sleep(3)"], environment={}, timeout=0.05
        )


@pytest.mark.parametrize("name", ["../escape", "x/../escape", "C:/escape", "a\\b", "CON", "x:ads"])
def test_archive_rejects_unsafe_paths(name):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        info = zipfile.ZipInfo("safe")
        info.filename = name
        archive.writestr(info, b"payload")
    with pytest.raises(AuthorizationError):
        runtime.archive_members(stream.getvalue())


def _unsigned_runtime(monkeypatch, tmp_path, state=None, development=False):
    monkeypatch.setattr(
        runtime.profiles,
        "load_package_trust",
        lambda: {"mode": "standalone-input", "development": development},
    )
    monkeypatch.setattr(runtime.profiles, "select_profile", lambda: ReleaseProfile.WINDOWS_X86_64)
    helpers = {name: {"sha256": h(name)} for name in ("relay", "archive", "member_manifest")}
    monkeypatch.setattr(runtime.profiles, "load_input_manifest", lambda _: {"helpers": helpers})
    monkeypatch.setattr(runtime.offline, "local_path", lambda _: tmp_path)
    calls = []

    def probe(request):
        calls.append(request)
        return {"installed_root": "C:\\synthetic", "state": state}

    monkeypatch.setattr(runtime.offline, "native_call", probe)
    return calls


@pytest.mark.parametrize("development", [False, True])
def test_absent_install_allows_unsigned_only_before_adoption(
    monkeypatch, tmp_path, admission, development
):
    calls = _unsigned_runtime(monkeypatch, tmp_path, development=development)
    assert runtime.resolve() is None
    assert calls[0]["operation"] == "probe" and len(calls[0]["input_key"]) == 64
    state = canonical_json(adopt_signed_closure(**admission)).decode()
    _unsigned_runtime(monkeypatch, tmp_path, state=state, development=development)
    with pytest.raises(AuthorizationError, match="downgrade"):
        runtime.resolve()


def test_development_does_not_read_or_adopt_installed_authorization(monkeypatch, tmp_path):
    _unsigned_runtime(monkeypatch, tmp_path, development=True)
    (tmp_path / "cua-runtime-authorization.json").write_bytes(b"untrusted")
    monkeypatch.setattr(
        runtime, "read", lambda *args, **kw: pytest.fail("development must not adopt")
    )
    assert runtime.resolve() is None


def test_native_probe_is_read_only_and_uses_fixed_system_executable():
    if sys.platform != "win32":
        pytest.skip("native Windows probe belongs to Windows")
    result = offline.native_call(
        {"operation": "probe", "architecture": "x86_64", "input_key": h("isolated-probe")}
    )
    assert set(result) == {"installed_root", "state"}
    assert result["installed_root"].endswith("\\Programs\\Vadgr") and result["state"] is None


def test_packaged_powershell_has_no_syntax_errors_or_uncompilable_adapters():
    if sys.platform != "win32":
        pytest.skip("native Windows compiler belongs to Windows")
    import re

    script = Path(runtime.__file__).parent / "winbroker" / "adopt-native.ps1"
    source = script.read_text()
    blocks = re.findall("Add-Type -TypeDefinition @'\\n(.*?)\\n'@", source, re.DOTALL)
    assert len(blocks) == 2
    command = "\n".join("Add-Type -TypeDefinition @'\n" + block + "\n'@" for block in blocks)
    result = offline.run_bounded(
        [
            str(offline.powershell()),
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            command + "\n'compiled'",
        ],
        environment=offline.clean_environment(),
        timeout=45,
    )
    assert result.strip() == b"compiled"


def test_wsl_path_and_native_environment_do_not_use_path_or_owner_variables(monkeypatch, tmp_path):
    monkeypatch.setattr(offline, "sys", SimpleNamespace(platform="linux"))
    calls = []

    def run(args, **kw):
        calls.append((args, kw))
        return b"C:\\fixed\\asset\n"

    monkeypatch.setattr(offline, "run_bounded", run)
    assert offline.windows_path(tmp_path) == "C:\\fixed\\asset"
    assert calls[0][0][0] == "/usr/bin/wslpath" and calls[0][1]["environment"] == {}
    assert offline.clean_environment() == {}


@pytest.fixture
def installed_case(monkeypatch, tmp_path, admission, synthetic_chain):
    installed = tmp_path / "installed"
    cua = installed / "lib" / "cua"
    helper = cua / "managed-helpers" / "x86_64"
    package_root = tmp_path / "package"
    browser = package_root / "computer_use" / "browser"
    adoption_dir = browser / "adoption" / "x86_64"
    helper.mkdir(parents=True)
    adoption_dir.mkdir(parents=True)

    def put(path, raw):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    for name, key in (
        ("adoption-policy.json", "policy_bytes"),
        ("trusted-root.json", "root_bytes"),
        ("gh.exe", "verifier_bytes"),
    ):
        put(adoption_dir / name, admission[key])
    for name, key in (
        ("pre-signing-claim.json", "claim_bytes"),
        ("broker-final-manifest.json", "manifest_bytes"),
        ("helper-closure-authorization.json", "authorization_bytes"),
        ("input-output.json", "mapping_bytes"),
        ("authorization.sigstore.json", "bundle_bytes"),
    ):
        put(helper / name, admission[key])
    for name, raw in zip(("receipt-windows.json", "receipt-wsl.json"), admission["receipt_bytes"]):
        put(helper / name, raw)
    put(
        helper / "signature-reports.json",
        canonical_json({key: strict_json(raw) for key, raw in admission["reports"].items()}),
    )
    put(cua / "broker.zip", synthetic_chain["archive"])
    put(cua / "relay.exe", admission["final"]["relay.exe"])
    relay = {
        "path": "relay.exe",
        "size": len(admission["final"]["relay.exe"]),
        "sha256": sha256(admission["final"]["relay.exe"]),
    }
    inventory = canonical_json(
        {
            "schema": 1,
            "target": "x86_64-pc-windows-msvc",
            "files": {"relay.exe": {"size": relay["size"], "sha256": relay["sha256"]}},
        }
    )
    put(cua / "payload.json", b"payload")
    put(cua / "installed-inventory.json", inventory)
    envelope = {
        "schema": 1,
        "release_profile": "windows-x86_64",
        "cua_version": "0.7.9",
        "generation": "candidate-1",
        "payload_sha256": sha256(b"payload"),
        "installed_inventory_sha256": sha256(inventory),
        "broker_final_manifest_sha256": sha256(admission["manifest_bytes"]),
        "helper_closure_authorization_sha256": sha256(admission["authorization_bytes"]),
        "relay": relay,
    }
    put(installed / "cua-runtime-authorization.json", canonical_json(envelope))
    put(installed / "cua-runtime-authorization.sigstore.json", b"synthetic envelope bundle")
    input_bytes = {
        "archive": synthetic_chain["archive"],
        "member_manifest": b"manifest-input",
        "relay": admission["inputs"]["relay.exe"],
    }
    helpers = {}
    for name, raw in input_bytes.items():
        relative = "computer_use/browser/input-" + name
        put(package_root / relative, raw)
        helpers[name] = {"path": relative, "size": len(raw), "sha256": sha256(raw)}
    trust = {
        "mode": "standalone-input",
        "adoption": {
            "x86_64": {
                "policy_sha256": admission["policy_sha256"],
                "root_sha256": sha256(admission["root_bytes"]),
                "verifier_sha256": sha256(admission["verifier_bytes"]),
            }
        },
    }
    monkeypatch.setattr(runtime, "__file__", str(browser / "standalone_adoption.py"))
    monkeypatch.setattr(runtime.time, "time", lambda: 100)
    monkeypatch.setattr(runtime.profiles, "load_package_trust", lambda: trust)
    monkeypatch.setattr(runtime.profiles, "load_input_manifest", lambda _: {"helpers": helpers})
    monkeypatch.setattr(runtime.profiles, "select_profile", lambda: ReleaseProfile.WINDOWS_X86_64)
    calls = []
    state = [None]

    def native(request):
        calls.append(request)
        if request["operation"] == "probe":
            return {"installed_root": str(installed), "state": state[0]}
        if request["operation"] == "deploy":
            return {
                "destination": str(tmp_path / "native-cache"),
                "relay": request["relay"]["path"],
                "archive_sha256": request["archive_sha256"],
                "manifest_sha256": request["manifest_sha256"],
            }
        assert request["operation"] == "publish-state"
        state[0] = request["state"]
        return {"state_sha256": sha256(request["state"].encode())}

    monkeypatch.setattr(runtime.offline, "native_call", native)
    monkeypatch.setattr(runtime.offline, "local_path", lambda value: Path(value))
    attestations = []

    def attest(subject, bundle, *args, **kwargs):
        attestations.append(subject)
        proof = admission["verify_offline"]()
        proof["subject_sha256"] = sha256(subject)
        return proof

    monkeypatch.setattr(runtime.offline, "verify", attest)
    return {
        "installed": installed,
        "helper": helper,
        "calls": calls,
        "state": state,
        "attestations": attestations,
    }


def test_complete_resolver_binds_two_attestations_and_commits_only_verified_state(installed_case):
    result = runtime.resolve()
    assert result["manifest"]["mode"] == "managed-signed"
    assert [call["operation"] for call in installed_case["calls"]] == [
        "probe",
        "deploy",
        "publish-state",
    ]
    assert len(installed_case["attestations"]) == 2
    assert installed_case["state"][0] is not None
    assert result["authorization_sha256"] == sha256(result["authorization_path"].read_bytes())
    assert runtime.resolve()["manifest"] == result["manifest"]


@pytest.mark.parametrize(
    "name",
    [
        "cua-runtime-authorization.json",
        "lib/cua/payload.json",
        "lib/cua/installed-inventory.json",
        "lib/cua/relay.exe",
        "lib/cua/broker.zip",
        "lib/cua/managed-helpers/x86_64/broker-final-manifest.json",
        "lib/cua/managed-helpers/x86_64/helper-closure-authorization.json",
        "lib/cua/managed-helpers/x86_64/signature-reports.json",
    ],
)
def test_resolver_refuses_tampering_before_native_deploy_or_state(installed_case, name):
    path = installed_case["installed"] / name
    path.write_bytes(b"changed")
    with pytest.raises((AuthorizationError, ValueError)):
        runtime.resolve()
    assert [call["operation"] for call in installed_case["calls"]] == ["probe"]
    assert installed_case["state"][0] is None


def test_installed_envelope_null_or_extra_keys_are_not_adoption_authority(installed_case):
    path = installed_case["installed"] / "cua-runtime-authorization.json"
    value = strict_json(path.read_bytes())
    value["relay"] = None
    path.write_bytes(canonical_json(value))
    with pytest.raises(AuthorizationError):
        runtime.resolve()
    value["extra"] = "not-authorized"
    path.write_bytes(canonical_json(value))
    with pytest.raises(AuthorizationError):
        runtime.resolve()


def test_wsl_adopts_the_same_native_windows_installed_closure(installed_case, monkeypatch):
    monkeypatch.setattr(runtime.profiles, "select_profile", lambda: ReleaseProfile.WSL_X86_64)
    assert runtime.resolve()["manifest"]["architecture"] == "x86_64"


def test_managed_uninstall_after_adoption_requires_repair_not_unsigned(installed_case):
    runtime.resolve()
    (installed_case["installed"] / "cua-runtime-authorization.json").unlink()
    with pytest.raises(AuthorizationError, match="downgrade"):
        runtime.resolve()

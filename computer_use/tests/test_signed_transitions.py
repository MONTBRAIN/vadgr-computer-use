# Copyright 2026 Victor Santiago Montano Diaz
# Licensed under the Apache License, Version 2.0.

"""Two synthetic fixtures exercise contracts, never claim actual signature trust."""

import copy
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from computer_use.browser import windows_broker_entry, windows_process
from computer_use.browser.adoption import adoption_state, require_signed_after_adoption
from computer_use.browser.managed_authorization import (
    AuthorizationError,
    canonical_json,
    sha256,
    strict_json,
    validate_authenticated_chain,
)
from computer_use.browser.signed_transitions import closure_key, transition_edges
from computer_use.tests.test_signed_helper_authorization import chain as chain_fixture
from computer_use.tests.test_signed_helper_authorization import h
from computer_use.tests.test_windows_process import FakeProcess
from scripts.finalize_signed_helper import deterministic_zip


def fixture(label):
    result = chain_fixture.__wrapped__()
    claim = strict_json(result["claim_bytes"])
    original = {key: h(label + key) for key in claim["input_closure"]}
    claim.update(input_closure=original, adoption_inputs=[original], source_commit=label * 40,
                 helper_closure_id=closure_key("x86_64", original))
    claim["signing_claim_ref"] = "refs/tags/cua-signing-claims/" + claim["helper_closure_id"]
    result["claim_bytes"] = canonical_json(claim)
    manifest = strict_json(result["manifest_bytes"])
    for key in ("source_commit", "helper_closure_id", "signing_claim_ref"):
        manifest[key] = claim[key]
    contents = ("synthetic broker " + label).encode()
    row = manifest["files"][0]
    row.update(path=windows_process.BROKER_EXECUTABLE, size=len(contents),
               sha256=sha256(contents), input_sha256=sha256(contents))
    result["archive"] = deterministic_zip({row["path"]: contents})
    manifest.update(pre_signing_claim_sha256=sha256(result["claim_bytes"]),
                    input_archive_sha256=original["archive_sha256"],
                    input_manifest_sha256=original["manifest_sha256"])
    manifest["archive"].update(size=len(result["archive"]), sha256=sha256(result["archive"]))
    result["manifest_bytes"] = canonical_json(manifest)
    auth = strict_json(result["authorization_bytes"])
    for key in ("source_commit", "helper_closure_id", "input_closure"):
        auth[key] = claim[key]
    auth["pre_signing_claim_sha256"] = sha256(result["claim_bytes"])
    auth["final_closure"] = {"relay_sha256": h(label + "signed-relay"),
                             "archive_sha256": sha256(result["archive"]),
                             "manifest_sha256": sha256(result["manifest_bytes"])}
    auth["output_artifact"]["subjects"] = {**auth["final_closure"], "mapping_sha256": auth["mapping_sha256"]}
    result["authorization_bytes"] = canonical_json(auth)
    return result


def authorize(current, predecessor):
    auth = strict_json(current["authorization_bytes"])
    prior = strict_json(predecessor["authorization_bytes"])
    auth["schema"] = 2
    auth["signed_predecessors"] = {"schema": 1, "architecture": "x86_64", "entries": [
        {key: prior[key] for key in ("cua_version", "source_commit", "input_closure", "final_closure")}]}
    common = {key: auth[key] for key in ("architecture", "cua_version", "source_commit")}
    auth["adoption_edges"] = [
        {**common, "direction": "unsigned-to-signed", "input_closure": auth["input_closure"], "final_closure": auth["final_closure"]},
        {**common, "direction": "signed-to-signed", "input_closure": prior["final_closure"],
         "final_closure": auth["final_closure"], "predecessor_version": prior["cua_version"],
         "predecessor_source_commit": prior["source_commit"]}]
    rebind(current, auth)
    return auth


def rebind(chain, auth):
    chain["authorization_bytes"] = canonical_json(auth)
    receipts = [strict_json(raw) for raw in chain["receipt_bytes"]]
    for receipt in receipts:
        receipt["broker_final_manifest_sha256"] = sha256(chain["manifest_bytes"])
        receipt["helper_closure_authorization_sha256"] = sha256(chain["authorization_bytes"])
    chain["receipt_bytes"] = [canonical_json(value) for value in receipts]


@pytest.fixture
def pair():
    first, second = fixture("a"), fixture("b")
    authorize(first, second)
    authorize(second, first)
    return first, second


def check(chain):
    return validate_authenticated_chain(**{key: chain[key] for key in (
        "claim_bytes", "manifest_bytes", "authorization_bytes", "receipt_bytes")})


def state(auth, previous=None):
    return adoption_state(policy={key: auth[key] for key in ("architecture", "input_closure")},
                          authorization_sha256=sha256(canonical_json(auth)),
                          final_closure=auth["final_closure"], previous=previous,
                          retained_available=True, authorization=auth)


def test_two_fixtures_forward_reverse_and_restart_preserve_exact_state(pair):
    first, second = map(check, pair)
    assert first["helper_closure_id"] != second["helper_closure_id"]
    a = state(first)
    b = state(second, canonical_json(a))
    assert b["input_closure"] == second["input_closure"]
    assert state(first, canonical_json(b)) == a
    assert state(second, canonical_json(b)) == b
    with pytest.raises(AuthorizationError, match="downgrade"):
        require_signed_after_adoption(canonical_json(b), requested_mode="producer-input")


def test_reviewed_reverse_catalog_refresh_does_not_require_resigning(pair):
    chain = copy.deepcopy(pair[0])
    current = check(chain)
    original = {key: value for key, value in current.items() if key != "signed_predecessors"}
    original.update(schema=1, adoption_edges=current["adoption_edges"][:1])
    rebind(chain, original)
    original = check(chain)
    previous = state(original)
    refreshed = state(current, canonical_json(previous))
    assert refreshed["authorization_sha256"] != previous["authorization_sha256"]
    assert refreshed["input_closure"] == previous["input_closure"]
    assert refreshed["final_closure"] == previous["final_closure"]


@pytest.mark.parametrize("mutation", ["same-input", "metadata-only-input", "same-archive", "wrong-closure", "wrong-manifest",
                                     "unlisted", "unknown", "wrong-arch", "wrong-source", "reverse-forged",
                                     "duplicate", "claim-key", "claim-ref", "unsigned-only"])
def test_transition_catalog_and_claim_refuse_substitution_and_replay(pair, mutation):
    chain, previous = pair
    auth = strict_json(chain["authorization_bytes"])
    entry = auth["signed_predecessors"]["entries"][0]
    if mutation == "same-input":
        entry["input_closure"] = auth["input_closure"]
    elif mutation == "metadata-only-input":
        entry["input_closure"] = {**auth["input_closure"], "manifest_sha256": h("metadata-only")}
    elif mutation == "same-archive":
        entry["final_closure"]["archive_sha256"] = auth["final_closure"]["archive_sha256"]
    elif mutation in ("wrong-closure", "wrong-manifest"):
        entry["final_closure"]["manifest_sha256" if mutation == "wrong-manifest" else "relay_sha256"] = h("other")
    elif mutation == "unlisted":
        auth["signed_predecessors"]["entries"] = []
    elif mutation == "unknown":
        auth["signed_predecessors"]["approved"] = True
    elif mutation == "wrong-arch":
        auth["signed_predecessors"]["architecture"] = "aarch64"
    elif mutation == "wrong-source":
        entry["source_commit"] = "0" * 40
    elif mutation == "reverse-forged":
        auth["adoption_edges"][1]["final_closure"] = entry["final_closure"]
    elif mutation == "duplicate":
        auth["signed_predecessors"]["entries"].append(copy.deepcopy(entry))
    elif mutation == "claim-key":
        auth["helper_closure_id"] = h("candidate-id")
    elif mutation == "claim-ref":
        claim = strict_json(chain["claim_bytes"])
        claim["signing_claim_ref"] = "refs/tags/candidate-id"
        chain["claim_bytes"] = canonical_json(claim)
    else:
        auth["schema"] = 1
        auth.pop("signed_predecessors")
    rebind(chain, auth)
    with pytest.raises(AuthorizationError):
        check(chain)


def test_unlisted_state_and_missing_retained_generation_are_not_transition_authority(pair):
    first, second = map(check, pair)
    old = state(second)
    old["final_closure"] = {**old["final_closure"], "manifest_sha256": h("unlisted")}
    with pytest.raises(AuthorizationError, match="exact signed transition"):
        state(first, canonical_json(old))
    with pytest.raises(AuthorizationError, match="repair"):
        adoption_state(policy=first, authorization_sha256=h("auth"), final_closure=first["final_closure"],
                       previous=None, retained_available=False, authorization=first)


def install_bundle(root, chain):
    auth = check(chain)
    bundle = root / auth["cua_version"] / auth["final_closure"]["archive_sha256"]
    bundle.mkdir(parents=True)
    from scripts.finalize_signed_helper import verify_final_archive

    for name, data in verify_final_archive(chain["archive"], chain["manifest_bytes"]).items():
        (bundle / name).write_bytes(data)
    (bundle / "broker-final-manifest.json").write_bytes(chain["manifest_bytes"])
    return bundle, auth


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("damage", [None, "manifest", "member", "extra", "unlisted", "target", "unsigned-manifest"])
def test_handoff_proves_final_manifest_before_touching_signed_predecessor(pair, tmp_path, monkeypatch, reverse, damage):
    previous, current = pair[::-1] if reverse else pair
    old_bundle, old_auth = install_bundle(tmp_path / "cache", previous)
    new_bundle, auth = install_bundle(tmp_path / "cache", current)
    catalog = new_bundle / "predecessor-catalog.json"
    catalog.write_bytes(canonical_json({"schema": 1, "target": "x86_64-pc-windows-msvc", "releases": []}))
    edges = transition_edges(auth)
    if damage == "manifest":
        (old_bundle / "broker-final-manifest.json").write_bytes(b"changed")
    elif damage == "member":
        (old_bundle / windows_process.BROKER_EXECUTABLE).write_bytes(b"changed")
    elif damage in ("extra", "unsigned-manifest"):
        (old_bundle / ("extra" if damage == "extra" else "bundle-manifest.json")).write_bytes(b"unexpected")
    elif damage == "unlisted":
        edges = edges[:1]
    elif damage == "target":
        edges[1]["final_closure"] = {**edges[1]["final_closure"], "archive_sha256": h("wrong")}
    lock = tmp_path / "state" / "browser-broker.lock"
    lock.parent.mkdir()
    lock.write_text("owned fixture")
    process = FakeProcess(123, old_bundle / windows_process.BROKER_EXECUTABLE)
    monkeypatch.setattr(windows_process, "_verify_owner_and_system", lambda _: None)
    monkeypatch.setattr(windows_process, "_current_user_sid", lambda: "owner")
    monkeypatch.setattr(windows_process, "_open_process", lambda _: process)
    monkeypatch.setattr(windows_process, "_restart_manager_lock_owners", lambda _: ((123, 42),))
    args = {"lock_path": lock, "candidate_bundle": new_bundle, "catalog_path": catalog, "adoption": edges}
    if damage is None:
        assert windows_process.perform_upgrade_handoff(**args)["state"] == "replaced"
        assert process.terminated
    else:
        with pytest.raises(windows_process.UpgradeHandoffError):
            windows_process.perform_upgrade_handoff(**args)
        assert not process.terminated


def test_broker_entry_uses_the_digest_authenticated_transition_catalog(pair, tmp_path):
    chain = pair[0]
    bundle, auth = install_bundle(tmp_path, chain)
    path = tmp_path / "helper-closure-authorization.json"
    path.write_bytes(chain["authorization_bytes"])
    edges, architecture = windows_broker_entry._adoption_edge(bundle, str(path), sha256(path.read_bytes()))
    assert architecture == "x86_64" and edges == auth["adoption_edges"]
    with pytest.raises(RuntimeError, match="digest"):
        windows_broker_entry._adoption_edge(bundle, str(path), h("wrong"))


def test_native_state_has_one_architecture_scope_and_compares_current_state_under_lock():
    path = Path(__file__).resolve().parents[1] / "browser/winbroker/adopt-native.ps1"
    text = path.read_text()
    assert "Join-Path $stateParent 'current'" in text
    assert "Join-Path $stateParent $request.input_key" not in text
    assert "Signed predecessor is not uniquely cataloged" in text
    assert text.index("$previous = Read-State", text.index("$lock =")) < text.index("Assert-SignedTransition ($previous")
    assert text.index("Assert-SignedTransition ($previous") < text.index("[IO.File]::Replace")
    assert "$previous -cne $request.previous" in text


@pytest.mark.skipif(sys.platform != "win32", reason="Native transition validation uses Windows PowerShell")
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("mutation", [None, "unlisted", "authorization-digest", "missing-edge"])
def test_native_transition_validator_accepts_only_the_exact_reviewed_pair(pair, tmp_path, reverse, mutation):
    old, new = map(check, pair[::-1] if reverse else pair)
    if mutation == "missing-edge":
        new["adoption_edges"] = new["adoption_edges"][:1]
    old_state, next_state = state(old), state(new) if mutation != "missing-edge" else {
        "schema": 1, "architecture": "x86_64", "mode": "managed-signed",
        "input_closure": new["input_closure"], "final_closure": new["final_closure"],
        "authorization_sha256": sha256(canonical_json(new))}
    if mutation == "unlisted":
        old_state["final_closure"] = {**old_state["final_closure"], "manifest_sha256": h("unlisted")}
    helper = tmp_path / "lib/cua/managed-helpers/x86_64"
    helper.mkdir(parents=True)
    (helper / "helper-closure-authorization.json").write_bytes(canonical_json(new))
    for name, value in (("old.json", old_state), ("next.json", next_state)):
        (tmp_path / name).write_bytes(canonical_json(value))
    path = Path(__file__).resolve().parents[1] / "browser/winbroker/adopt-native.ps1"
    source = path.read_text()
    functions = "function Assert-Keys" + source.split("function Assert-Keys", 1)[1].split("function Assert-Path", 1)[0]
    quote = lambda path: "'" + str(path).replace("'", "''") + "'"
    command = "$ErrorActionPreference='Stop'\n" + functions + "\n"
    command += "function Within($Root,$Path) { return $Path }\nfunction Assert-Private($Path) {}\n"
    command += "$installed=" + quote(tmp_path) + "\n"
    auth_hash = h("wrong") if mutation == "authorization-digest" else sha256(canonical_json(new))
    command += "$request=[pscustomobject]@{architecture='x86_64';authorization_sha256='" + auth_hash + "'}\n"
    command += "$old=Get-Content -LiteralPath " + quote(tmp_path / "old.json") + " -Raw | ConvertFrom-Json\n"
    command += "$next=Get-Content -LiteralPath " + quote(tmp_path / "next.json") + " -Raw | ConvertFrom-Json\n"
    command += "Assert-SignedTransition $old $next\nWrite-Output 'transition validated'"
    executable = shutil.which("powershell")
    assert executable
    result = subprocess.run([executable, "-NoProfile", "-NonInteractive", "-Command", command],
                            capture_output=True, text=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    if mutation is None:
        assert result.returncode == 0, result.stderr
        assert "transition validated" in result.stdout
    else:
        assert result.returncode != 0 and "transition validated" not in result.stdout

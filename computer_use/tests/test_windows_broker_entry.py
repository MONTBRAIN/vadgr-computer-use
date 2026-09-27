import hashlib
import json

import pytest

from computer_use.browser import windows_broker_entry
from computer_use.browser.managed_authorization import canonical_json


def _authorization(edge, final):
    digest = "1" * 64
    return {
        "schema": 1,
        "pre_signing_claim_sha256": digest,
        "helper_closure_id": "closure",
        "architecture": "x86_64",
        "cua_version": "0.7.9",
        "source_commit": "2" * 40,
        "tooling_commit": "3" * 40,
        "input_closure": edge["input_closure"],
        "final_closure": final,
        "consumer_inputs": {},
        "signing_run_id": 1,
        "signing_attempt": 1,
        "signing_job_id": "sign",
        "output_artifact": {},
        "publisher_policy_sha256": digest,
        "legal_policy_sha256": digest,
        "mapping_sha256": digest,
        "adoption_edges": [edge],
    }


@pytest.mark.parametrize(
    ("target", "architecture"),
    [
        ("x86_64-pc-windows-msvc", "x86_64"),
        ("aarch64-pc-windows-msvc", "aarch64"),
    ],
)
def test_unsigned_candidate_architecture_comes_from_exact_manifest(
    tmp_path, target, architecture
):
    bundle = tmp_path / ("a" * 64)
    bundle.mkdir()
    raw = json.dumps({"target": target, "archive_sha256": bundle.name}).encode()
    (bundle / "bundle-manifest.json").write_bytes(raw)

    manifest, manifest_hash, actual_architecture, managed = windows_broker_entry._candidate(
        bundle
    )

    assert manifest["target"] == target
    assert manifest_hash == hashlib.sha256(raw).hexdigest()
    assert actual_architecture == architecture
    assert managed is False


def test_adoption_edge_is_bound_to_authorization_and_candidate(monkeypatch, tmp_path):
    final = {
        "relay_sha256": "4" * 64,
        "archive_sha256": "5" * 64,
        "manifest_sha256": "6" * 64,
    }
    edge = {
        "direction": "unsigned-to-signed",
        "architecture": "x86_64",
        "cua_version": "0.7.9",
        "source_commit": "2" * 40,
        "input_closure": {
            "relay_sha256": "7" * 64,
            "archive_sha256": "8" * 64,
            "manifest_sha256": "9" * 64,
        },
        "final_closure": final,
    }
    authorization = tmp_path / "helper-closure-authorization.json"
    raw = canonical_json(_authorization(edge, final))
    authorization.write_bytes(raw)
    monkeypatch.setattr(
        windows_broker_entry,
        "_candidate",
        lambda _bundle: (
            {"cua_version": "0.7.9", "archive": {"sha256": final["archive_sha256"]},
             "source_commit": "2" * 40, "pre_signing_claim_sha256": "1" * 64},
            final["manifest_sha256"],
            "x86_64",
            True,
        ),
    )

    actual, architecture = windows_broker_entry._adoption_edge(
        tmp_path, str(authorization.resolve()), hashlib.sha256(raw).hexdigest()
    )

    assert actual == [edge]
    assert architecture == "x86_64"


def test_adoption_edge_refuses_wrong_authorization_digest(monkeypatch, tmp_path):
    authorization = tmp_path / "helper-closure-authorization.json"
    authorization.write_bytes(b"{}\n")
    monkeypatch.setattr(
        windows_broker_entry,
        "_candidate",
        lambda _bundle: ({}, "1" * 64, "x86_64", True),
    )

    with pytest.raises(RuntimeError, match="digest differs"):
        windows_broker_entry._adoption_edge(tmp_path, str(authorization.resolve()), "2" * 64)


def test_main_passes_adoption_arguments_as_values(monkeypatch):
    observed = {}

    def handoff(path, digest):
        observed.update(path=path, digest=digest)
        return 0

    monkeypatch.setattr(windows_broker_entry, "_upgrade_handoff", handoff)

    assert windows_broker_entry.main(
        ["upgrade-handoff", "--authorization", "C:\\safe path\\authorization.json",
         "--authorization-sha256", "a" * 64]
    ) == 0
    assert observed == {
        "path": "C:\\safe path\\authorization.json",
        "digest": "a" * 64,
    }


@pytest.mark.parametrize("damage", ["missing", "digest", "schema", "candidate"])
def test_handoff_returns_safe_refusal_for_invalid_authorization(monkeypatch, tmp_path, capsys, damage):
    from computer_use.browser import windows_process

    authorization = tmp_path / "helper-closure-authorization.json"
    raw = b"{}\n"
    if damage != "missing":
        authorization.write_bytes(raw)
    if damage != "candidate":
        monkeypatch.setattr(windows_broker_entry, "_candidate", lambda _: ({}, "1" * 64, "x86_64", True))
    else:
        monkeypatch.setattr(windows_broker_entry.sys, "executable", str(tmp_path / "broker.exe"))
    called = []
    monkeypatch.setattr(windows_process, "perform_upgrade_handoff", lambda **kwargs: called.append(kwargs))
    digest = "2" * 64 if damage == "digest" else hashlib.sha256(raw).hexdigest()
    assert windows_broker_entry._upgrade_handoff(str(authorization), digest) == 0
    output = capsys.readouterr()
    reply = json.loads(output.out)
    assert reply["state"] == "refused"
    assert reply["code"] == windows_process.UPGRADE_UNSAFE
    assert reply["remediation"]
    assert not called and not output.err
    assert str(tmp_path) not in output.out


@pytest.mark.parametrize("error", [RuntimeError("unexpected"), KeyError("unexpected"), OSError(5, "device fault")])
def test_handoff_does_not_hide_unexpected_verification_faults(monkeypatch, capsys, error):
    def fault(*args):
        raise error

    monkeypatch.setattr(windows_broker_entry, "_adoption_edge", fault)
    with pytest.raises(type(error)) as caught:
        windows_broker_entry._upgrade_handoff()
    assert caught.value is error
    assert capsys.readouterr().out == ""

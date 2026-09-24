"""Review exports are unapproved text packets, never installable artifacts."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import build_profile_review_inputs as review
import build_profile_wheels as build
from test_profile_wheels import package_inputs


@pytest.fixture
def review_inputs(package_inputs, monkeypatch):
    _, helpers, output, descriptor, _ = package_inputs
    commit = descriptor["producer"]["source_commit"]
    monkeypatch.setattr(review, "source_input", lambda: {"source_commit": commit, "version": "0.7.9"})
    monkeypatch.setattr(review, "review_preflight", lambda: None)
    for key, value in {
        "GITHUB_REPOSITORY": "MONTBRAIN/vadgr-computer-use",
        "GITHUB_REPOSITORY_ID": "1215350293", "GITHUB_REPOSITORY_OWNER_ID": "165305289",
        "GITHUB_REF": "refs/heads/master", "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_RUN_ATTEMPT": "1", "GITHUB_RUN_ID": "42", "GITHUB_SHA": "d" * 40,
        "GITHUB_WORKFLOW_REF": "MONTBRAIN/vadgr-computer-use/.github/workflows/profile-review-inputs.yml@refs/heads/master",
    }.items():
        monkeypatch.setenv(key, value)
    for architecture, root in helpers.items():
        members = build.zip_members((root / "broker.zip").read_bytes())
        members["vadgr-cua-host.exe"] = (root / "vadgr-cua-host.exe").read_bytes()
        sbom = {
            "spdxVersion": "SPDX-2.3",
            "name": f"vadgr-cua-browser-broker-0.7.9-windows-{architecture}",
            "files": [{"fileName": "./" + path, "checksums": [{"algorithm": "SHA256", "checksumValue": build.digest(data)}]} for path, data in sorted(members.items())],
        }
        (root / "broker.spdx.json").write_bytes(build.canonical(sbom))
    return helpers, output


@pytest.mark.parametrize("architecture", ["x86_64", "aarch64"])
def test_exports_text_inventory_without_authority_or_binaries(review_inputs, architecture):
    helpers, output = review_inputs
    review.export(helpers[architecture], output, architecture)
    receipt = build.read_json((output / "review-inputs.json").read_bytes())
    assert receipt["mode"] == "review-inputs"
    assert receipt["publishable"] is False
    assert receipt["legal_approval"] is False
    assert receipt["signing_approval"] is False
    assert receipt["source_commit"] != receipt["tooling_commit"]
    inventory = build.read_json((output / "member-inventory.json").read_bytes())
    assert len(inventory["files"]) == 3
    assert all(row["trust_class"] is None for row in inventory["files"])
    for path in output.rglob("*"):
        if path.is_file():
            assert build.native_identity(path.read_bytes()) is None
            assert path.suffix not in {".exe", ".dll", ".pyd", ".zip", ".whl"}
    assert (output / "notices/LICENSE").read_bytes() == b"notice"
    with pytest.raises(FileExistsError):
        review.export(helpers[architecture], output, architecture)


@pytest.mark.parametrize("field,value", [("GITHUB_REF", "refs/heads/feature"), ("GITHUB_RUN_ATTEMPT", "2"), ("GITHUB_REPOSITORY_ID", "1"), ("GITHUB_SHA", "0" * 40)])
def test_refuses_untrusted_producer_identity(review_inputs, monkeypatch, field, value):
    helpers, output = review_inputs
    monkeypatch.setenv(field, value)
    with pytest.raises(ValueError):
        review.export(helpers["x86_64"], output, "x86_64")
    assert not output.exists()


def test_refuses_sbom_member_hash_mismatch(review_inputs):
    helpers, output = review_inputs
    path = helpers["x86_64"] / "broker.spdx.json"
    sbom = json.loads(path.read_bytes())
    sbom["files"][0]["checksums"][0]["checksumValue"] = "e" * 64
    path.write_bytes(build.canonical(sbom))
    with pytest.raises(ValueError, match="SBOM"):
        review.export(helpers["x86_64"], output, "x86_64")
    assert not output.exists()


def test_review_preflight_does_not_replace_final_preflight(tmp_path, monkeypatch):
    review.review_preflight()
    import producer
    monkeypatch.setattr(producer, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="adoption-rules"):
        producer.preflight()


def test_review_workflow_cannot_sign_attest_or_publish():
    workflow = (ROOT / ".github/workflows/profile-review-inputs.yml").read_text()
    for forbidden in ("id-token:", "attestations:", "secrets.", "environment:", "build_profile_wheels.py", "generate-adoption", "attest-build-provenance", "contents: write"):
        assert forbidden not in workflow
    assert "contents: read" in workflow
    assert "persist-credentials: false" in workflow
    assert "path: build/review/output/" in workflow
    assert "--source-repository source" in workflow

"""Draft preparation uses text-only fixtures and never grants signing authority."""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prepare_adoption_review as review
from adoption_inputs import validate_rules
from build_profile_wheels import canonical, digest, read_json


@pytest.fixture
def packets(tmp_path):
    source = review.source_input()
    result = {}
    for architecture in review.ARCHITECTURES:
        directory = tmp_path / architecture
        (directory / "build-inputs").mkdir(parents=True)
        inventory = {"schema": 1, "architecture": architecture, "files": [
            {"path": "LICENSE", "size": 6, "sha256": digest(b"notice"),
             "native_identity": None, "trust_class": None},
            {"path": "vadgr-cua-host.exe", "size": 128, "sha256": digest(b"fixture"),
             "native_identity": ["windows", architecture], "trust_class": None},
        ]}
        files = {
            "member-inventory.json": canonical(inventory),
            "build-inputs/source-input.json": canonical(source),
        }
        receipt = {
            "schema": 1, "mode": "review-inputs", "architecture": architecture,
            "source_commit": source["source_commit"], "version": source["version"],
            "tooling_commit": "d" * 40, "run_id": 42, "attempt": 1,
            "publishable": False, "legal_approval": False, "signing_approval": False,
            "adoption": "disabled", "input_closure": {"fixture": architecture},
            "files": [{"path": name, "size": len(raw), "sha256": digest(raw)}
                      for name, raw in files.items()],
        }
        for name, raw in files.items():
            (directory / name).write_bytes(raw)
        raw = canonical(receipt)
        (directory / "review-inputs.json").write_bytes(raw)
        result[architecture] = (directory, digest(raw))
    return result, tmp_path / "draft"


def test_draft_preserves_hashes_without_manufacturing_authority(packets):
    inputs, output = packets
    binding = review.prepare(inputs, output)
    rules = read_json((output / "adoption-rules.draft.json").read_bytes())
    assert digest(canonical(rules)) == binding["draft_sha256"]
    assert rules["expires_at"] is None
    assert rules["source_sha_allowlist"] == rules["signer_sha_allowlist"] == []
    for rows in rules["files"].values():
        assert rows["LICENSE"]["trust_class"] == "data"
        assert rows["LICENSE"]["input_sha256"] == digest(b"notice")
        native = rows["vadgr-cua-host.exe"]
        assert native["input_sha256"] == digest(b"fixture")
        assert all(native[field] is None for field in review.SIGNATURE_FIELDS)
    with pytest.raises(ValueError):
        validate_rules(rules)
    assert not (output / "adoption-rules.json").exists()
    with pytest.raises(FileExistsError):
        review.prepare(inputs, output)


@pytest.mark.parametrize("mutation", ["receipt", "member", "extra", "missing"])
def test_changed_packet_fails_before_any_draft(packets, mutation):
    inputs, output = packets
    directory, _ = inputs["x86_64"]
    if mutation == "receipt":
        (directory / "review-inputs.json").write_bytes(b"changed")
    elif mutation == "member":
        (directory / "member-inventory.json").write_bytes(b"changed")
    elif mutation == "extra":
        (directory / "extra.txt").write_bytes(b"unrecorded")
    else:
        (directory / "member-inventory.json").unlink()
    with pytest.raises(ValueError):
        review.prepare(inputs, output)
    assert not output.exists()


@pytest.mark.parametrize("field,value", [
    ("source_commit", "e" * 40), ("architecture", "wrong"), ("attempt", 2),
    ("publishable", True), ("signing_approval", True), ("legal_approval", True),
    ("run_id", 43), ("tooling_commit", "e" * 40),
])
def test_incompatible_review_targets_are_not_combined(packets, field, value):
    inputs, output = packets
    directory, _ = inputs["aarch64"]
    path = directory / "review-inputs.json"
    receipt = read_json(path.read_bytes())
    receipt[field] = value
    raw = canonical(receipt)
    path.write_bytes(raw)
    inputs["aarch64"] = (directory, digest(raw))
    with pytest.raises(ValueError):
        review.prepare(inputs, output)
    assert not output.exists()


def test_documented_cli_prepares_only_drafts(packets):
    inputs, output = packets
    arguments = [sys.executable, str(Path(review.__file__).resolve())]
    for architecture, (directory, receipt_hash) in inputs.items():
        prefix = "x86-64" if architecture == "x86_64" else architecture
        arguments += [f"--{prefix}-review", str(directory),
                      f"--{prefix}-receipt-sha256", receipt_hash]
    arguments += ["--output", str(output)]
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "legal, signing, producer authority and expiry remain unset" in result.stdout
    assert sorted(path.name for path in output.iterdir()) == [
        "adoption-rules.draft.json", "review-binding.json"
    ]

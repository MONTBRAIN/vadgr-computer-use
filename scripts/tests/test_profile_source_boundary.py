"""The trusted producer admits reviewed source as data, never as workflow code."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packaging/profiles"))
sys.path.insert(0, str(ROOT / "scripts"))
import producer
from build_profile_wheels import canonical, validate_producer
from test_profile_wheels import package_inputs


def test_source_and_tooling_are_independent_exact_identities(package_inputs):
    descriptor = package_inputs[3]
    descriptor["producer"]["tooling_commit"] = "d" * 40
    validate_producer(descriptor["producer"])


def test_reviewed_source_does_not_accept_an_environment_override(tmp_path, monkeypatch):
    base = tmp_path / "packaging/profiles"
    base.mkdir(parents=True)
    record = {"schema": 1, "source_commit": "b" * 40, "version": "0.7.9"}
    (base / "source-input.json").write_bytes(canonical(record))
    monkeypatch.setattr(producer, "ROOT", tmp_path)
    monkeypatch.setenv("CUA_SOURCE_COMMIT", "e" * 40)
    assert producer.source_input() == record
    record["source_commit"] = "refs/heads/feature"
    (base / "source-input.json").write_bytes(canonical(record))
    with pytest.raises(ValueError, match="source"):
        producer.source_input()


def test_source_checkout_rejects_changed_or_wrong_head(tmp_path, monkeypatch):
    base = tmp_path / "trusted/packaging/profiles"
    base.mkdir(parents=True)
    source = tmp_path / "candidate"
    source.mkdir()
    (source / "pyproject.toml").write_text('[project]\nversion = "0.7.9"\n')
    monkeypatch.setattr(producer, "ROOT", tmp_path / "trusted")
    monkeypatch.setattr(producer, "source_input", lambda: {"source_commit": "b" * 40, "version": "0.7.9"})
    outputs = iter(["b" * 40, "", "100644"])
    monkeypatch.setattr(producer, "git_output", lambda *args: next(outputs))
    assert producer.checked_source(source) == source.resolve()
    monkeypatch.setattr(producer, "git_output", lambda *args: "c" * 40)
    with pytest.raises(ValueError, match="head"):
        producer.checked_source(source)
    outputs = iter(["b" * 40, " M computer_use/browser/broker.py"])
    monkeypatch.setattr(producer, "git_output", lambda *args: next(outputs))
    with pytest.raises(ValueError, match="clean"):
        producer.checked_source(source)
    outputs = iter(["b" * 40, "", "120000"])
    monkeypatch.setattr(producer, "git_output", lambda *args: next(outputs))
    with pytest.raises(ValueError, match="symlink"):
        producer.checked_source(source)


def test_credential_job_never_executes_candidate_source():
    workflow = (ROOT / ".github/workflows/profile-wheels.yml").read_text()
    validator = workflow.split("  validate:", 1)[1]
    assert "--source source" in validator
    assert "persist-credentials: false" in validator
    assert "python source/" not in validator
    assert "pip install" not in validator
    assert "source_commit: ${{ steps.source.outputs.commit }}" in workflow
    assert 'ref: ${{ needs.preflight.outputs.source_commit }}' in workflow
    assert "--source-repository source" in workflow


@pytest.mark.parametrize("mutation", [None, "run", "artifact"])
def test_hosted_provenance_binds_tooling_but_catalog_binds_source(tmp_path, monkeypatch, mutation):
    source_sha, tooling_sha = "b" * 40, "d" * 40
    monkeypatch.setattr(producer, "source_input", lambda: {"source_commit": source_sha})
    for key, value in {
        "GITHUB_RUN_ID": "42", "GITHUB_SHA": tooling_sha,
        "GITHUB_REPOSITORY_ID": "1215350293", "GITHUB_REPOSITORY_OWNER_ID": "165305289",
        "GITHUB_REF": "refs/heads/master", "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_RUN_ATTEMPT": "1",
    }.items():
        monkeypatch.setenv(key, value)
    run = {
        "head_sha": source_sha if mutation == "run" else tooling_sha,
        "workflow_id": 8, "run_attempt": 1, "event": "workflow_dispatch",
        "head_branch": "master", "path": ".github/workflows/profile-wheels.yml",
        "repository": {"id": 1215350293, "owner": {"id": 165305289}},
    }
    jobs, artifacts = [], []
    for index, architecture in enumerate(("x86_64", "aarch64")):
        name = "native-" + architecture
        root = tmp_path / name
        root.mkdir()
        for filename in ("broker.manifest.json", "broker.spdx.json", "test.log"):
            (root / filename).write_bytes(b"retained bytes")
        jobs.append({"id": index + 1, "name": name, "conclusion": "success", "labels": ["windows"]})
        artifacts.append({
            "id": index + 10, "name": name, "expired": False, "digest": "sha256:" + "f" * 64,
            "workflow_run": {"id": 42, "head_sha": source_sha if mutation == "artifact" else tooling_sha},
        })
    monkeypatch.setattr(producer, "api", lambda path: {"jobs": jobs} if "/jobs?" in path else {"artifacts": artifacts} if "/artifacts?" in path else run)
    output = tmp_path / "descriptor.json"
    if mutation:
        with pytest.raises(ValueError):
            producer.descriptor(tmp_path, output)
        assert not output.exists()
    else:
        producer.descriptor(tmp_path, output)
        record = producer.read_json(output.read_bytes())["producer"]
        assert record["source_commit"] == source_sha
        assert record["tooling_commit"] == tooling_sha

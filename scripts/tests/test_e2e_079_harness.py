import importlib.util
import io
import json
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(relative, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def harness():
    return load("E2E/0.7.9/harness/harness.py", "harness079")


@pytest.fixture
def publication():
    return load("scripts/e2e_079/publication.py", "publication079")


def test_runbook_expands_required_cross_products_and_fields(harness):
    cells = harness.cells()
    assert len(cells) == 130
    ids = [cell["id"] for cell in cells]
    assert len([i for i in ids if i.startswith("P06-")]) == 18
    assert len([i for i in ids if i.startswith("P13-")]) == 16
    assert len([i for i in ids if i.startswith("P14-")]) == 2
    allowed_results = ("not run:", "pass", "fail", "blocked", "deferred")
    assert all(cell["Result"].lower().startswith(allowed_results) for cell in cells)
    assert ids[0].startswith("P12-")
    assert ids[4].startswith("P14-")


def test_root_marker_does_not_authorize_another_path(harness, tmp_path):
    root = harness.initialize(tmp_path)
    assert harness.checked_root(root) == root
    (root / harness.MARKER).write_text(json.dumps({"schema": 1, "root": str(tmp_path)}))
    with pytest.raises(ValueError, match="marker"):
        harness.checked_root(root)


def test_cleanup_plan_is_recoverable_and_non_mutating(harness, tmp_path):
    root = harness.initialize(tmp_path)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    plan = harness.cleanup(root, evidence)
    assert plan["executed"] is False
    assert root.is_dir()
    assert Path(plan["destination"]).parent == root.parent


def test_mcp_config_isolates_child_without_importing_login(harness, tmp_path):
    root = harness.initialize(tmp_path)
    entry = root / "venv" / "Scripts" / "vadgr-cua.exe"
    entry.parent.mkdir(parents=True)
    entry.write_bytes(b"entry fixture")
    result = harness.mcp_config(root, entry)
    config = json.loads(Path(result["claude_mcp_config"]).read_text())
    child = config["mcpServers"]["cua"]
    assert child["command"] == str(entry)
    assert child["args"] == ["--transport", "stdio"]
    assert set(child["env"]) == {"HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
                                 "XDG_CONFIG_HOME", "XDG_STATE_HOME"}
    assert all(root in Path(value).parents for value in child["env"].values())
    assert result["codex_override_argv"][0] == "-c"


def test_cleanup_cannot_retire_evidence(harness, tmp_path):
    root = harness.initialize(tmp_path)
    evidence = root / "evidence"
    evidence.mkdir()
    with pytest.raises(ValueError, match="evidence"):
        harness.cleanup(root, evidence)


def test_evidence_is_hash_bound_append_only_and_never_a_pass(harness, tmp_path):
    source = tmp_path / "identity.json"
    source.write_text('{"observed": true}\n')
    cell = harness.cells()[0]["id"]
    value = harness.record(tmp_path, cell, [source])
    assert value["artifacts"][0]["sha256"] == harness.digest(source)
    assert value["verdict"].startswith("unreviewed")
    with pytest.raises(FileExistsError):
        harness.record(tmp_path, cell, [source])


def test_evidence_refuses_external_file_and_credential_filename(harness, tmp_path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    source = tmp_path / "outside"
    source.write_text("not evidence")
    cell = harness.cells()[0]["id"]
    with pytest.raises(ValueError, match="inside"):
        harness.record(evidence, cell, [source])
    secret = evidence / ".env"
    secret.write_text("not-a-real-secret")
    with pytest.raises(ValueError, match="credential"):
        harness.record(evidence, cell, [secret])


@pytest.mark.parametrize("name", ["../escape", "dir/file", "dir\\file", "x:y", ".."])
def test_retained_archive_rejects_unsafe_paths(publication, tmp_path, name):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(name, b"fixture")
    with pytest.raises(ValueError, match="unsafe"):
        publication.extract(stream.getvalue(), tmp_path / "outputs")
    assert not (tmp_path / "outputs").exists()


def test_retained_archive_rejects_case_collision(publication, tmp_path):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("A.whl", b"a")
        archive.writestr("a.whl", b"b")
    with pytest.raises(ValueError, match="duplicated"):
        publication.extract(stream.getvalue(), tmp_path / "outputs")


def test_publication_binds_actual_asset_ids_without_catalog_backfill(publication, tmp_path):
    catalog = tmp_path / publication.CATALOG
    catalog.write_bytes(b"{}\n")
    before = catalog.read_bytes()
    release = {"tag_name": "v0.7.9", "draft": True, "id": 123,
               "assets": [{"name": catalog.name, "id": 456, "size": 3,
                           "digest": "sha256:" + publication.sha(before)}]}
    record = publication.publication_record(tmp_path, release, "0.7.9")
    assert record["assets"][0]["id"] == 456
    assert catalog.read_bytes() == before
    release["assets"][0]["digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="bytes differ"):
        publication.publication_record(tmp_path, release, "0.7.9")


def test_publication_refuses_missing_or_reused_assets(publication, tmp_path):
    (tmp_path / publication.CATALOG).write_bytes(b"{}")
    release = {"tag_name": "v0.7.9", "draft": True, "id": 123, "assets": []}
    with pytest.raises(ValueError, match="names differ"):
        publication.publication_record(tmp_path, release, "0.7.9")
    release["draft"] = False
    with pytest.raises(ValueError, match="draft"):
        publication.publication_record(tmp_path, release, "0.7.9")


def test_release_workflow_does_not_rebuild_or_overwrite_wheels():
    workflow = (ROOT / ".github/workflows/publish.yml").read_text()
    assert "python -m build" not in workflow
    assert "skip-existing: true" not in workflow
    assert "--clobber" not in workflow
    assert "immutable-releases" in workflow
    assert "needs: [build, github-release]" in workflow
    assert "name: standalone-dist" in workflow


def test_profile_contract_job_installs_product_test_dependencies():
    workflow = (ROOT / ".github/workflows/profile-wheels.yml").read_text()
    assert 'python -m pip install ".[dev]"' in workflow

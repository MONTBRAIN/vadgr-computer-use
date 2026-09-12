"""Helpers operate only on fresh synthetic state; no browser or broker is started."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

HARNESS = Path(__file__).resolve().parents[2] / "E2E" / "0.7.6" / "harness"


def load(name):
    spec = importlib.util.spec_from_file_location(name, HARNESS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def isolated():
    with tempfile.TemporaryDirectory(prefix="vadgr-cua-publication-test-") as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        yield root


@pytest.mark.skipif(os.name != "posix", reason="POSIX child audit fixture")
@pytest.mark.parametrize("restoration", ["disarm", "expiry"])
def test_fault_reaches_publication_and_child_exits_then_restores(isolated, restoration):
    _check_fault_and_restoration(isolated, restoration)


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS system temporary aliases")
@pytest.mark.parametrize("alias", ["tmp", "var"])
def test_fault_matches_macos_system_alias(alias):
    if alias == "tmp":
        parent = Path("/tmp")
    else:
        canonical = Path(tempfile.gettempdir()).resolve()
        if not canonical.is_relative_to("/private/var"):
            pytest.skip("the system temporary directory has no /var alias")
        parent = Path("/") / canonical.relative_to("/private")
    with tempfile.TemporaryDirectory(prefix="vadgr-cua-publication-alias-", dir=parent) as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        assert root.absolute() != root.resolve()
        _check_fault_and_restoration(root, "disarm")


def _check_fault_and_restoration(isolated, restoration):
    fixture = load("publication_fault")
    endpoint = isolated / "broker" / "browser-broker.json"
    endpoint.parent.mkdir(mode=0o700)
    endpoint.write_text("old synthetic value")
    endpoint.chmod(0o600)
    directory = isolated / "fault"
    fixture.arm(isolated, directory, endpoint, 60)
    # This acceptance child models setup markers and invokes the real publisher.
    # It is not an installed-product E2E and makes no browser or socket call.
    source = """
import os
from pathlib import Path
from computer_use.browser.private_file import write_private
endpoint = Path(os.environ['TEST_ENDPOINT'])
lock = endpoint.with_name('browser-broker.lock')
lock.write_text(str(os.getpid()))
endpoint.with_name('registration-ready').touch()
try:
    write_private(endpoint, {'generation': 2})
finally:
    lock.unlink()
"""
    environment = dict(os.environ, PYTHONPATH=str(directory), TEST_ENDPOINT=str(endpoint))
    result = subprocess.run([sys.executable, "-c", source], env=environment,
                            cwd=HARNESS.parents[2], capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "isolated endpoint publication fault" in result.stderr
    event = json.loads((directory / "events.jsonl").read_text())
    assert event["event"] == "publication_refused"
    assert event["lock_present"] and event["destination_present"]
    assert event["temporary_mode"] == 0o600 and event["temporary_size"] > 0
    assert endpoint.with_name("registration-ready").exists()
    assert not endpoint.with_name("browser-broker.lock").exists()
    assert endpoint.read_text() == "old synthetic value"
    assert not list(endpoint.parent.glob(".*.tmp"))
    if restoration == "disarm":
        command = [sys.executable, str(HARNESS / "publication_fault.py"), "disarm",
                   "--root", str(isolated), "--directory", str(directory)]
        restored = subprocess.run(command, capture_output=True, text=True, timeout=10)
        assert restored.returncode == 0 and json.loads(restored.stdout)["disarmed"]
    else:
        configuration = json.loads((directory / "configuration.json").read_text())
        configuration["expires"] = 0
        (directory / "configuration.json").write_text(json.dumps(configuration))
    restored = subprocess.run([sys.executable, "-c", source], env=environment,
                              cwd=HARNESS.parents[2], capture_output=True, text=True, timeout=10)
    assert restored.returncode == 0, restored.stderr
    assert json.loads(endpoint.read_text()) == {"generation": 2}
    print(json.dumps({"fault": event, "failure_exit": result.returncode,
                      "restoration": restoration, "restored_exit": restored.returncode}))


def test_observer_reports_metadata_without_reading_contents(isolated, monkeypatch):
    observer = load("observe_publication")
    endpoint = isolated / "broker" / "browser-broker.json"
    endpoint.parent.mkdir()
    endpoint.write_text("synthetic private content")
    endpoint.chmod(0o600)
    observer.validate(isolated, endpoint)

    def forbid(*args, **kwargs):
        raise AssertionError("observer must never open endpoint contents")

    monkeypatch.setattr(Path, "read_text", forbid)
    monkeypatch.setattr(Path, "read_bytes", forbid)
    rows = observer.snapshot(endpoint)
    assert rows[1]["size"] == 25
    assert "synthetic private content" not in json.dumps(rows)


@pytest.mark.skipif(os.name != "nt", reason="native Windows PowerShell module isolation")
@pytest.mark.parametrize("module,command", [
    ("Security", "Get-Acl"), ("Utility", "ConvertTo-Json"),
])
def test_observer_ignores_foreign_parent_modules(isolated, monkeypatch, module, command):
    observer = load("observe_publication")
    modules = isolated / "foreign modules"
    foreign = modules / f"Microsoft.PowerShell.{module}"
    foreign.mkdir(parents=True)
    (foreign / f"Microsoft.PowerShell.{module}.psd1").write_text(
        "@{ ModuleVersion = '7.0.0'; RootModule = 'foreign.psm1'; "
        f"FunctionsToExport = @('{command}') }}", encoding="utf-8",
    )
    (foreign / "foreign.psm1").write_text(
        f"function {command} {{ throw 'incompatible parent module fixture' }}",
        encoding="utf-8",
    )
    builtins = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/Modules"
    inherited = str(modules) + os.pathsep + str(builtins)
    monkeypatch.setenv("PSModulePath", inherited)
    metadata = observer.windows_metadata(isolated)
    assert isinstance(metadata["protected"], bool)
    assert isinstance(metadata["owner_matches"], bool)
    assert "rules" in metadata
    assert os.environ["PSModulePath"] == inherited


@pytest.mark.skipif(os.name != "posix", reason="POSIX ownership validation")
def test_fault_refuses_symlink_root_and_outside_endpoint(isolated):
    fixture = load("publication_fault")
    with pytest.raises(ValueError):
        fixture.checked(isolated, isolated.parent / "outside")
    with pytest.raises(ValueError):
        fixture.checked(isolated, isolated / ".." / "outside")
    link = isolated / "link"
    link.symlink_to(isolated.parent)
    with pytest.raises(ValueError):
        fixture.checked(isolated, link / "endpoint")


@pytest.mark.skipif(os.name != "posix", reason="POSIX temporary path aliases")
def test_fault_accepts_system_temporary_alias_without_following_child_links(isolated, monkeypatch):
    fixture = load("publication_fault")
    alias = isolated / "temporary-alias"
    alias.symlink_to(isolated, target_is_directory=True)
    root = isolated / "vadgr-cua-inner"
    root.mkdir(mode=0o700)
    lexical_root = alias / root.name
    monkeypatch.setattr(fixture.tempfile, "gettempdir", lambda: str(alias))
    endpoint = lexical_root / "broker" / "browser-broker.json"
    endpoint.parent.mkdir(mode=0o700)
    endpoint.write_text("synthetic")
    endpoint.chmod(0o600)
    fixture.arm(lexical_root, lexical_root / "fault", endpoint, 60)
    assert (root / "fault" / "configuration.json").exists()
    child_link = root / "child-link"
    child_link.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError):
        fixture.checked(lexical_root, child_link / "broker" / "browser-broker.json")


def test_observer_cli_runs_from_committed_path(isolated):
    endpoint = isolated / "broker" / "browser-broker.json"
    discovery = isolated / "home" / ".vadgr-cua" / "browser.port"
    result = subprocess.run([sys.executable, str(HARNESS / "observe_publication.py"),
                             "--root", str(isolated), "--endpoint", str(endpoint),
                             "--discovery", str(discovery)],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.splitlines()[0])["metadata"][1]["exists"] is False
    assert {row["surface"] for row in json.loads(result.stdout.splitlines()[0])["metadata"]} == {
        "endpoint", "discovery",
    }
    assert json.loads(result.stdout.splitlines()[-1])["observer_finished"]


@pytest.mark.parametrize("vanishes", [False, True])
def test_acl_observer_accepts_only_confirmed_disappearance(isolated, monkeypatch, vanishes):
    observer = load("observe_publication")
    endpoint = isolated / "broker" / "browser-broker.json"
    endpoint.parent.mkdir()
    endpoint.write_text("synthetic")
    monkeypatch.setattr(observer, "sys", SimpleNamespace(platform="win32"))

    def query(path):
        if path == endpoint:
            if vanishes:
                path.unlink()
            raise OSError("synthetic ACL observation failure")
        return {"protected": True}

    monkeypatch.setattr(observer, "windows_metadata", query)
    if vanishes:
        rows = observer.snapshot(endpoint)
        assert rows[1]["vanished"] is True
        assert "acl" not in rows[1]
    else:
        with pytest.raises(OSError):
            observer.snapshot(endpoint)

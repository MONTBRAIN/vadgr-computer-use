"""Isolated setup helpers must target only their named extension resources."""

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

HARNESS = Path(__file__).resolve().parents[2] / "E2E" / "0.7.6" / "harness"


def helper(name, monkeypatch):
    monkeypatch.syspath_prepend(str(HARNESS))
    spec = importlib.util.spec_from_file_location(name, HARNESS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ToggleDevTools:
    def __init__(self, evaluate):
        self.evaluate = evaluate
        self.closed = []

    def create(self, url):
        assert url == "chrome://extensions/"
        return {"id": "temporary-management-tab"}

    def json(self, path):
        assert path == "/json/version"
        return {"id": "browser"}

    def command(self, browser, method, params):
        assert browser == {"id": "browser"}
        assert method == "Target.closeTarget"
        self.closed.append(params["targetId"])
        return {"success": True}


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("failure", [None, "missing-control", "stuck-control"])
def test_toggle_expression_resolves_requested_state(monkeypatch, enabled, failure):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed to evaluate the real browser expression")
    module = helper("toggle_extension", monkeypatch)

    def evaluate(target, expression):
        assert target == {"id": "temporary-management-tab"}
        setup = """
let elapsed = 0;
global.performance = {now: () => elapsed};
global.requestAnimationFrame = callback => { elapsed += 1000; callback(); };
const control = {checked: INITIAL, click() { this.checked = !this.checked; }};
const item = {shadowRoot: {querySelector(s) {
  if (s !== '#enableToggle') throw Error('wrong control'); return control;
}}};
const list = {shadowRoot: {querySelector(s) {
  if (s !== SELECTOR) throw Error('wrong extension'); return item;
}}};
const manager = {shadowRoot: {querySelector(s) {
  if (s !== 'extensions-item-list') throw Error('wrong list'); return list;
}}};
global.document = {querySelector(s) {
  if (s !== 'extensions-manager') throw Error('wrong page'); return manager;
}};
""".replace("INITIAL", json.dumps(not enabled)).replace(
            "SELECTOR", json.dumps(f'extensions-item[id="{module.EXTENSION_ID}"]')
        )
        if failure == "missing-control":
            setup = setup.replace("return control;", "return null;")
        elif failure == "stuck-control":
            setup = setup.replace("this.checked = !this.checked;", "")
        script = (
            setup
            + "\nPromise.resolve("
            + expression
            + ").then(r => console.log(JSON.stringify(r)), "
            + "e => console.log(JSON.stringify({error: e.message, elapsed})));"
        )
        # Process startup is separate from the expression's 5000 ms deadline,
        # checked with the mock clock. Hosted runners can start Node slowly.
        completed = subprocess.run(
            [node, "-e", script],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert completed.returncode == 0, completed.stderr
        result = json.loads(completed.stdout)
        if failure:
            assert result == {
                "error": "toggle not found" if failure == "missing-control" else "toggle timed out",
                "elapsed": 5000,
            }
            raise module.LifecycleSetupError(result["error"])
        return result

    devtools = ToggleDevTools(evaluate)
    if failure:
        with pytest.raises(module.LifecycleSetupError, match="toggle (not found|timed out)"):
            module.toggle(devtools, enabled)
    else:
        assert module.toggle(devtools, enabled) == {
            "enabled": enabled,
            "temporary_extensions_page_closed": True,
        }
    assert devtools.closed == ["temporary-management-tab"]


@pytest.mark.parametrize("failure", ["exception", "wrong-result"])
def test_toggle_closes_management_tab_on_failure(monkeypatch, failure):
    module = helper("toggle_extension", monkeypatch)

    def evaluate(target, expression):
        if failure == "exception":
            raise module.LifecycleSetupError("evaluation failed")
        return {"enabled": False}

    devtools = ToggleDevTools(evaluate)
    with pytest.raises(module.LifecycleSetupError):
        module.toggle(devtools, True)
    assert devtools.closed == ["temporary-management-tab"]


@pytest.mark.parametrize("error", [False, True])
def test_stop_worker_targets_exact_extension_and_disconnects(monkeypatch, error):
    module = helper("stop_extension_worker", monkeypatch)
    extension = "exact-extension"
    page_url = "http://127.0.0.1/isolated-fixture"

    def update(versions):
        return {"method": "ServiceWorker.workerVersionUpdated", "params": {"versions": versions}}

    def version(identity, status, prefix=extension):
        return {
            "versionId": identity,
            "runningStatus": status,
            "scriptURL": f"chrome-extension://{prefix}/worker.js",
        }

    messages = [
        update(
            [version("unrelated", "running", extension + "-other"), version("owned", "running")]
        ),
        {"error": "fixture failure"} if error else {"id": 2, "result": {}},
        update([version("owned", "stopped")]),
    ]

    class Socket:
        closed = False
        sent = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.closed = True

        def send(self, message):
            self.sent.append(json.loads(message))

        def recv(self, timeout):
            return json.dumps(messages.pop(0))

    socket = Socket()

    def connect(url, **kwargs):
        assert url == "ws://isolated-target"
        return socket

    monkeypatch.setattr(
        module.importlib, "import_module", lambda name: SimpleNamespace(connect=connect)
    )
    devtools = SimpleNamespace(
        targets=lambda: [
            {"type": "page", "url": page_url + "-other", "webSocketDebuggerUrl": "ws://unrelated"},
            {"type": "page", "url": page_url, "webSocketDebuggerUrl": "ws://isolated-target"},
        ]
    )
    if error:
        with pytest.raises(module.LifecycleSetupError, match="fixture failure"):
            module.stop_worker(devtools, page_url, extension)
    else:
        result = module.stop_worker(devtools, page_url, extension)
        assert result["stop_acknowledged"] is True
        assert result["devtools_disconnected"] is True
    assert socket.closed is True
    assert socket.sent == [
        {"id": 1, "method": "ServiceWorker.enable"},
        {"id": 2, "method": "ServiceWorker.stopWorker", "params": {"versionId": "owned"}},
    ]

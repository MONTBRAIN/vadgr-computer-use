# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Launch subscribed Windows B09 and restart cells through installed MCP clients."""

import argparse
import ctypes
import importlib.util
import json
import os
import pathlib
import queue
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from ctypes import wintypes

HARNESS = pathlib.Path(__file__).resolve().parent
PREFIX = "b09"


def checked_root(root):
    root = pathlib.Path(root).absolute()
    if root != root.resolve(strict=True) or not root.is_dir():
        raise ValueError("root must be an existing directory without redirects")
    if not root.name.startswith(("vadgr-cua-", "cua-")):
        raise ValueError("expected a named isolated CUA directory")
    bases = (pathlib.Path(tempfile.gettempdir()).resolve(), HARNESS.parents[3] / ".tmp")
    if not any(root.is_relative_to(base) and root != base for base in bases):
        raise ValueError("root must be below temporary storage")
    return root


def write_json(path, value):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".pending")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def live_test_endpoint(path, root):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        pid, port = value["pid"], value["port"]
        if (type(pid) is not int or pid <= 4 or type(port) is not int
                or not 0 < port < 65536 or value.get("host") != "127.0.0.1"
                or int(value["process_started_ns"]) <= 0):
            return None
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
        ]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        try:
            exit_code, size = wintypes.DWORD(), wintypes.DWORD(32768)
            image = ctypes.create_unicode_buffer(size.value)
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)) or exit_code.value != 259:
                return None
            if not kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)):
                return None
            executable = pathlib.Path(image.value).resolve()
            if (executable.name != "vadgr-cua-browser-broker.exe"
                    or not executable.is_relative_to(root)):
                return None
            with socket.create_connection(("127.0.0.1", port), timeout=.5):
                pass
            # Reject endpoint replacement during validation; existing live
            # installed brokers are valid and must not be restarted for setup.
            if json.loads(path.read_text(encoding="utf-8")) != value:
                return None
            return value
        finally:
            kernel.CloseHandle(handle)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def driver_command(root, gate, runtime, codex):
    environment = {
        "VADGR_CUA_BROKER_ROOT": str(root / "broker"),
        "VADGR_CUA_BROWSER_DISCOVERY": str(root / "discovery.json"),
        "LOCALAPPDATA": str(root / "local"), "APPDATA": str(root / "roaming"),
    }
    command = [codex, "--yolo", "exec", "--json", "--ephemeral", "--ignore-user-config",
               "--skip-git-repo-check", "--model", "gpt-5.6-sol",
               "-c", 'model_reasoning_effort="medium"']
    for name in ("cua_two", "cua_three", "cua_one"):
        executable = str(runtime) if name != "cua_one" else sys.executable
        command += ["-c", f"mcp_servers.{name}.command={json.dumps(executable)}",
                    "-c", f"mcp_servers.{name}.startup_timeout_sec=120",
                    "-c", f"mcp_servers.{name}.tool_timeout_sec=180"]
        selected_env = dict(environment)
        if name == "cua_one":
            command += ["-c", f"mcp_servers.{name}.args=" + json.dumps([
                str(HARNESS / "broker_stdio_gate_windows.py"), str(gate), str(runtime),
            ])]
        else:
            selected_env["VADGR_CUA_BROKER_ENDPOINT"] = str(root / "broker/browser-broker.json")
        for key, value in selected_env.items():
            command += ["-c", f"mcp_servers.{name}.env.{key}={json.dumps(value)}"]
    return command


def main():
    if sys.platform != "win32":
        raise RuntimeError("native Windows required")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=pathlib.Path)
    parser.add_argument("--prompt", required=True, type=pathlib.Path)
    args = parser.parse_args()
    ROOT = checked_root(args.root)
    prompt_path = args.prompt.resolve(strict=True)
    if not prompt_path.is_file() or not prompt_path.is_relative_to(ROOT):
        raise ValueError("prompt must be inside the isolated root")
    GATE = ROOT / f"{PREFIX}-gate-private.json"
    STATE = ROOT / f"{PREFIX}-state.json"
    REQUEST = ROOT / f"{PREFIX}-request.json"
    names = [f"{PREFIX}-{suffix}" for suffix in (
        "gate-private.json", "state.json", "request.json", "relay.jsonl",
        "driver.jsonl", "result.json", "progress.txt", "processes.json",
        "control-1.lock", "control-2.lock",
    )]
    if any((ROOT / name).exists() for name in names):
        raise RuntimeError("retry outputs exist; preserve the previous boundary")
    runtime = ROOT / "runtime/Scripts/vadgr-cua.exe"
    endpoint_path = ROOT / "broker/browser-broker.json"
    if not runtime.is_file():
        raise RuntimeError("installed runtime missing")
    spec = importlib.util.spec_from_file_location("retry_relay", HARNESS / "broker_fault_relay.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    private_root = pathlib.Path(tempfile.mkdtemp(prefix="vadgr-cua-b09-"))
    original, alias = private_root / "original.json", private_root / "client-one.json"
    relay = driver = redactor = None
    events = queue.Queue()
    state = {"event": "waiting_for_normal_broker", "sequence": 0, "connections_opened": 0}
    result = {"driver_exit": None, "redactor_exit": None, "relay_exit": None}
    cleanup_errors = []

    def private_gate(value):
        pending = GATE.with_name(GATE.name + "." + uuid.uuid4().hex + ".pending")
        with os.fdopen(helper.windows_private_fd(pending, retain_on_failure=True),
                       "w", encoding="utf-8") as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        pending.replace(GATE)

    processes = {"coordinator_pid": os.getpid()}
    def record_processes():
        for name, process in (("driver", driver), ("redactor", redactor), ("relay", relay)):
            if process is not None:
                processes[name + "_pid"] = process.pid
                processes[name + "_exit"] = process.poll()
        write_json(ROOT / f"{PREFIX}-processes.json", processes)
    write_json(STATE, state)
    (ROOT / f"{PREFIX}-progress.txt").write_text("Waiting for installed cua_two normal startup.\n")
    relay_log = None
    try:
        codex = shutil.which("codex.cmd")
        if not codex:
            raise RuntimeError("subscription CLI missing")
        command = driver_command(ROOT, GATE, runtime, codex)
        with prompt_path.open("rb") as prompt:
            driver = subprocess.Popen(command + ["-"], stdin=prompt, stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL, cwd=ROOT,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
        redactor = subprocess.Popen(
            [sys.executable, str(HARNESS / "redact_stream.py"),
             "--output", str(ROOT / f"{PREFIX}-driver.jsonl")],
            stdin=driver.stdout, stderr=subprocess.DEVNULL, cwd=ROOT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        driver.stdout.close()
        record_processes()
        deadline = time.monotonic() + 75
        endpoint = None
        while driver.poll() is None and time.monotonic() < deadline:
            endpoint = live_test_endpoint(endpoint_path, ROOT)
            if endpoint is not None:
                break
            time.sleep(.2)
        if endpoint is None:
            raise RuntimeError("live installed broker endpoint not observed")
        result["validated_live_broker_pid"] = endpoint["pid"]
        descriptor = helper.windows_private_fd(original, retain_on_failure=True)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(endpoint, stream)
        endpoint.clear()
        relay = subprocess.Popen(
            [sys.executable, str(HARNESS / "broker_fault_relay.py"), "--root", str(private_root),
             "--endpoint", str(original), "--alias", str(alias), "--retain-alias"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, bufsize=1, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        record_processes()
        relay_log = (ROOT / f"{PREFIX}-relay.jsonl").open("x", encoding="utf-8")

        def read_relay():
            try:
                for line in relay.stdout:
                    try:
                        events.put(json.loads(line))
                    except ValueError:
                        pass
            finally:
                events.put({"event": "relay_eof", "monotonic": time.monotonic()})

        reader = threading.Thread(target=read_relay, daemon=True)
        reader.start()

        def record(item):
            allow = {"event", "monotonic", "utc", "seconds", "connection_count"}
            clean = {key: value for key, value in item.items() if key in allow}
            relay_log.write(json.dumps(clean) + "\n")
            relay_log.flush()
            if clean["event"] == "connection_opened":
                state["connections_opened"] += 1
            if clean["event"] in ("ready", "cut", "restored", "stopped", "relay_eof"):
                state.update(clean)
            if clean["event"] == "cut":
                state["cut"] = clean
            if clean["event"] == "restored":
                state["restored"] = clean
            write_json(STATE, state)

        deadline = time.monotonic() + 15
        while state["event"] != "ready":
            record(events.get(timeout=max(.1, deadline - time.monotonic())))
            if state["event"] == "relay_eof" or time.monotonic() >= deadline:
                raise RuntimeError("relay readiness unavailable")
        # This gate contains a private local path, never an endpoint credential.
        private_gate({"ready": True, "alias": str(alias)})
        while driver.poll() is None:
            while not events.empty():
                record(events.get_nowait())
            if relay.poll() is not None:
                raise RuntimeError("relay exited during driver")
            if REQUEST.exists():
                try:
                    request = json.loads(REQUEST.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    request = {}
                if request and request.get("sequence") != state["sequence"]:
                    expected = {1: 8, 2: 46}.get(state["sequence"] + 1)
                    if (set(request) != {"sequence", "cut_seconds"}
                            or type(request["sequence"]) is not int
                            or type(request["cut_seconds"]) is not int
                            or request["sequence"] != state["sequence"] + 1
                            or request["cut_seconds"] != expected
                            or state["event"] not in ("ready", "restored")
                            or state["connections_opened"] < 1):
                        raise RuntimeError("unexpected or unready fault request")
                    state.update(event="cut_requested", sequence=request["sequence"])
                    state.pop("cut", None)
                    state.pop("restored", None)
                    write_json(STATE, state)
                    relay.stdin.write(json.dumps({"cut_seconds": expected}) + "\n")
                    relay.stdin.flush()
            time.sleep(.1)
        result["driver_exit"] = driver.wait()
        result["redactor_exit"] = redactor.wait(timeout=15)
    except Exception as error:
        result["error_type"] = type(error).__name__
    finally:
        try:
            private_gate({"abort": True, "retained_private_root": str(private_root)})
        except (OSError, ValueError):
            cleanup_errors.append("private_gate_write_failed")
        if relay is not None and relay.poll() is None:
            try:
                relay.stdin.write('{"stop":true}\n')
                relay.stdin.flush()
            except (OSError, ValueError):
                cleanup_errors.append("relay_stop_pipe")
            try:
                relay.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Only this orchestration's relay, never broker/browser/driver.
                relay.terminate()
                try:
                    relay.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    cleanup_errors.append("relay_exit_timeout")
        if relay is not None:
            result["relay_exit"] = relay.poll()
        if relay_log is not None:
            while not events.empty():
                record(events.get_nowait())
            relay_log.close()
        result.update(
            driver_still_running=driver is not None and driver.poll() is None,
            redactor_still_running=redactor is not None and redactor.poll() is None,
            private_files_retained=True, cleanup_errors=cleanup_errors,
        )
        record_processes()
        write_json(ROOT / f"{PREFIX}-result.json", result)
        (ROOT / f"{PREFIX}-progress.txt").write_text("Retry ended; inspect actual stream and result.\n")
    print(json.dumps(result))
    return int(bool(result.get("error_type") or cleanup_errors or result["driver_exit"]
                    or result["redactor_exit"] or result["relay_exit"]
                    or result["driver_still_running"] or result["redactor_still_running"]))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(json.dumps({"event": "retry_setup_failed", "error_type": type(error).__name__}))
        sys.exit(1)

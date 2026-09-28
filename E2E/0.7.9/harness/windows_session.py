"""Record isolated native Windows sessions; the subscription agent drives CUA."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import harness

SAFE_CHILD_ENVIRONMENT = (
    "COMSPEC",
    "NUMBER_OF_PROCESSORS",
    "OS",
    "PATH",
    "PATHEXT",
    "PROCESSOR_ARCHITECTURE",
    "PROCESSOR_IDENTIFIER",
    "PROCESSOR_LEVEL",
    "PROCESSOR_REVISION",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "WINDIR",
)

DRIVER_LOGIN_ENVIRONMENT = (
    "APPDATA",
    "HOME",
    "LOCALAPPDATA",
    "USERPROFILE",
    "USERNAME",
)

# Browser-tier cells are DOM-extension tests.  Prompt instructions are not a
# security boundary: make every native desktop, pixel, host and structured-UI
# CUA tool unavailable to the subscription driver.
BROWSER_ALLOWED_CUA_TOOLS = (
    "mcp__cua__browser",
    "mcp__cua__browser_eval",
    "mcp__cua__tabs",
)

BROWSER_DISALLOWED_CUA_TOOLS = (
    "mcp__cua__screenshot",
    "mcp__cua__screenshot_region",
    "mcp__cua__click",
    "mcp__cua__double_click",
    "mcp__cua__right_click",
    "mcp__cua__move_mouse",
    "mcp__cua__scroll",
    "mcp__cua__drag",
    "mcp__cua__type_text",
    "mcp__cua__key_press",
    "mcp__cua__get_screen_size",
    "mcp__cua__get_platform",
    "mcp__cua__get_platform_info",
    "mcp__cua__fs",
    "mcp__cua__shell",
    "mcp__cua__http",
    "mcp__cua__env",
    "mcp__cua__time",
    "mcp__cua__tempfile",
    "mcp__cua__data",
    "mcp__cua__clipboard",
    "mcp__cua__windows",
    "mcp__cua__profiles",
    "mcp__cua__ui_tree",
    "mcp__cua__ui_find",
    "mcp__cua__ui_windows",
    "mcp__cua__ui_act",
    "mcp__cua__ui_wait",
    "mcp__cua__apps",
    "mcp__cua__app_open",
)


def save(path, value):
    with path.open("x", encoding="utf-8") as output:
        json.dump(value, output, indent=2)
        output.write("\n")


def environment(case, source=None):
    source = os.environ if source is None else source
    value = {name: source[name] for name in SAFE_CHILD_ENVIRONMENT if name in source}
    value.update(
        {
            "HOME": str(case / "home"),
            "USERPROFILE": str(case / "home"),
            "APPDATA": str(case / "roaming"),
            "LOCALAPPDATA": str(case / "appdata"),
            "XDG_CONFIG_HOME": str(case / "home/.config"),
            "XDG_STATE_HOME": str(case / "state"),
            "VADGR_CUA_BROKER_ENDPOINT": str(case / "state/browser-broker.json"),
            "VADGR_CUA_BROWSER_DISCOVERY": str(case / "appdata/vadgr-cua/browser.port"),
        }
    )
    return value


def driver_environment(source=None):
    """Keep subscription login paths while excluding ambient provider secrets."""
    source = os.environ if source is None else source
    names = (*SAFE_CHILD_ENVIRONMENT, *DRIVER_LOGIN_ENVIRONMENT)
    return {name: source[name] for name in names if name in source}


def browser_command(case, chrome, extension, url):
    chrome = chrome.resolve(strict=True)
    if chrome.name != "chrome.exe" or chrome.parent.name != "chrome-win64":
        raise ValueError("use the reviewed official Chrome for Testing executable")
    profile = case / "browser-profile"
    if profile.exists():
        raise ValueError("each browser launch requires a fresh profile")
    extension = extension.resolve(strict=True)
    return [
        str(chrome),
        "--no-first-run",
        "--no-default-browser-check",
        "--remote-debugging-port=0",
        f"--user-data-dir={profile}",
        f"--disable-extensions-except={extension}",
        f"--load-extension={extension}",
        url,
    ]


def public_endpoint(value):
    return {key: item for key, item in value.items() if key != "token"}


def registration_hashes() -> list[dict[str, object]]:
    import winreg

    rows = []
    for vendor in ("Google\\Chrome", "Microsoft\\Edge"):
        key_path = "Software\\" + vendor + "\\NativeMessagingHosts\\com.vadgr.cua"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                value, kind = winreg.QueryValueEx(key, "")
        except FileNotFoundError:
            rows.append({"vendor": vendor, "exists": False})
            continue
        encoded = str(value).encode("utf-8")
        manifest = Path(value)
        rows.append(
            {
                "vendor": vendor,
                "exists": True,
                "value_kind": kind,
                "default_value_sha256": hashlib.sha256(encoded).hexdigest(),
                "manifest_exists": manifest.is_file(),
                "manifest_sha256": harness.digest(manifest) if manifest.is_file() else None,
            }
        )
    return rows


def agent_command(config: Path) -> list[str]:
    return [
        "claude",
        "--dangerously-skip-permissions",
        "--tools",
        "",
        "--allowedTools",
        ",".join(BROWSER_ALLOWED_CUA_TOOLS),
        "--disallowedTools",
        ",".join(BROWSER_DISALLOWED_CUA_TOOLS),
        "--print",
        "--verbose",
        "--output-format",
        "stream-json",
        "--model",
        "claude-sonnet-5",
        "--effort",
        "medium",
        "--strict-mcp-config",
        "--mcp-config",
        str(config),
    ]


def agent_config(case: Path, output: Path, entry: Path | None = None) -> Path:
    if entry is None:
        return (case / "work/.mcp.json").resolve(strict=True)
    entry = entry.resolve(strict=True)
    if entry.name not in ("vadgr-cua", "vadgr-cua.exe") or harness.REPO in entry.parents:
        raise ValueError("use an installed public entry point outside the checkout")
    scoped = environment(case)
    config = output / "mcp.private.json"
    save(
        config,
        {
            "mcpServers": {
                "cua": {
                    "command": str(entry),
                    "args": ["--transport", "stdio"],
                    "env": scoped,
                }
            }
        },
    )
    return config


def windows_process_snapshot(root_pid: int, root_created: str) -> dict[str, object]:
    escaped_created = root_created.replace("'", "''")
    script = (
        f"$RootPid = [int]{int(root_pid)}; $RootCreated = '{escaped_created}';"
        + r"""
$Rows = @(Get-CimInstance Win32_Process)
$Root = Get-Process -Id $RootPid -ErrorAction SilentlyContinue
$RootMatches = $false
if ($Root) { $RootMatches = $Root.StartTime.ToUniversalTime().ToString('o') -eq $RootCreated }
$Wanted = [System.Collections.Generic.HashSet[int]]::new()
[void]$Wanted.Add($RootPid)
$Changed = $true
while ($Changed) {
  $Changed = $false
  foreach ($Row in $Rows) {
    if ($Wanted.Contains([int]$Row.ParentProcessId) -and $Wanted.Add([int]$Row.ProcessId)) { $Changed = $true }
  }
}
$Processes = @()
foreach ($Row in $Rows) {
  if ($Wanted.Contains([int]$Row.ProcessId)) {
    $Process = Get-Process -Id $Row.ProcessId -ErrorAction SilentlyContinue
    if ($Process) {
      $Processes += [pscustomobject]@{pid=[int]$Row.ProcessId;parent_pid=[int]$Row.ParentProcessId;created=$Process.StartTime.ToUniversalTime().ToString('o');executable=[IO.Path]::GetFileName($Row.ExecutablePath)}
    }
  }
}
[pscustomobject]@{root_pid=$RootPid;root_identity_matches=$RootMatches;processes=$Processes} | ConvertTo-Json -Compress -Depth 4
"""
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return json.loads(result.stdout)


def process_start_identity(pid: int) -> str:
    script = (
        "$p=Get-Process -Id "
        + str(pid)
        + " -ErrorAction Stop; $p.StartTime.ToUniversalTime().ToString('o')"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=(
            "config",
            "command",
            "browser",
            "agent",
            "agent-start",
            "agent-observe",
            "agent-stop",
            "observe",
            "stop",
            "registry-save",
            "registry-restore",
        ),
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--case", type=Path)
    parser.add_argument("--entry", type=Path)
    parser.add_argument("--chrome", type=Path)
    parser.add_argument("--extension", type=Path)
    parser.add_argument("--url", default="about:blank")
    parser.add_argument("--goal", type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("args", nargs="*")
    args = parser.parse_args()
    root = harness.checked_root(args.root)
    if sys.platform != "win32":
        raise ValueError("native Windows is required")
    if args.action.startswith("registry-"):
        import winreg

        backup = root / "registry-backup.json"
        rows = []
        if args.action == "registry-save":
            for vendor in ("Google\\Chrome", "Microsoft\\Edge"):
                key_path = "Software\\" + vendor + "\\NativeMessagingHosts\\com.vadgr.cua"
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                        value, kind = winreg.QueryValueEx(key, "")
                        rows.append({"key": key_path, "exists": True, "value": value, "kind": kind})
                except FileNotFoundError:
                    rows.append({"key": key_path, "exists": False})
            save(backup, rows)
        else:
            rows = json.loads(backup.read_text())
            for row in rows:
                if row["exists"]:
                    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, row["key"]) as key:
                        winreg.SetValueEx(key, "", 0, row["kind"], row["value"])
                else:
                    try:
                        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, row["key"])
                    except FileNotFoundError:
                        pass
        print(json.dumps({"action": args.action, "registrations": len(rows)}))
        return 0
    case = args.case.resolve(strict=True)
    if root not in case.parents or not (case / ".vadgr-cua-078-fixture.json").is_file():
        raise ValueError("case must be a marked fixture below the pass root")
    env = environment(case)
    if args.action in ("observe", "stop"):
        escaped = str(case).replace("'", "''")
        query = (
            "$root='"
            + escaped
            + "'; @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like ('*'+$root+'*') -and $_.Name -in @('chrome.exe','vadgr-cua-host.exe','vadgr-cua-browser-broker.exe') } | ForEach-Object { $p=Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue; if($p){[pscustomobject]@{pid=$_.ProcessId;created=$p.StartTime.ToUniversalTime().ToString('o');executable=$_.ExecutablePath}} }) | ConvertTo-Json -Compress"
        )
        run = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", query],
            capture_output=True,
            text=True,
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        processes = json.loads(run.stdout or "[]")
        if isinstance(processes, dict):
            processes = [processes]
        if args.action == "stop":
            for process in processes:
                command = (
                    "$p=Get-Process -Id "
                    + str(int(process["pid"]))
                    + " -ErrorAction SilentlyContinue; if($p -and $p.StartTime.ToUniversalTime().ToString('o') -eq '"
                    + process["created"]
                    + "'){Stop-Process -InputObject $p -Force -ErrorAction Stop}; exit 0"
                )
                subprocess.run(
                    ["powershell.exe", "-NoProfile", "-Command", command],
                    check=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            print(json.dumps({"stopped_owned_processes": len(processes)}))
            return 0
        endpoint_path = case / "state/browser-broker.json"
        endpoint = json.loads(endpoint_path.read_text()) if endpoint_path.is_file() else {}
        endpoint = public_endpoint(endpoint)
        endpoint_sha256 = harness.digest(endpoint_path) if endpoint_path.is_file() else None
        for process in processes:
            process["executable_sha256"] = harness.digest(Path(process["executable"]))
            process["executable"] = Path(process["executable"]).name
        pages = []
        port_file = case / "browser-profile/DevToolsActivePort"
        if port_file.is_file():
            port = int(port_file.read_text().splitlines()[0])
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json/list", timeout=5
            ) as response:
                targets = json.load(response)
            from websockets.sync.client import connect

            for target in targets:
                if target.get("type") != "page" or not target.get("url", "").startswith(
                    "http://127.0.0.1:"
                ):
                    continue
                with connect(
                    target["webSocketDebuggerUrl"], proxy=None, open_timeout=5
                ) as connection:
                    connection.send(
                        json.dumps(
                            {
                                "id": 1,
                                "method": "Runtime.evaluate",
                                "params": {
                                    "expression": "JSON.stringify({heading:document.querySelector('h1')?.textContent,value:document.querySelector('#arena')?.value,mutations:document.querySelector('#mutations')?.textContent})",
                                    "returnByValue": True,
                                },
                            }
                        )
                    )
                    while True:
                        result = json.loads(connection.recv(timeout=5))
                        if result.get("id") == 1:
                            pages.append(
                                {
                                    "target": target["id"],
                                    "readback": json.loads(result["result"]["result"]["value"]),
                                }
                            )
                            break
        save(
            args.output,
            {
                "observed_unix": time.time(),
                "endpoint": endpoint,
                "endpoint_sha256": endpoint_sha256,
                "registrations": registration_hashes(),
                "processes": processes,
                "pages": pages,
            },
        )
        print(json.dumps({"observed": True, "processes": len(processes), "pages": pages}))
        return 0
    if args.action == "config":
        for name in ("home", "roaming", "appdata", "work"):
            (case / name).mkdir(exist_ok=True)
        scoped = {key: value for key, value in env.items() if value != os.environ.get(key)}
        save(
            case / "work/.mcp.json",
            {
                "mcpServers": {
                    "cua": {
                        "command": str(args.entry.resolve(strict=True)),
                        "args": ["--transport", "stdio"],
                        "env": scoped,
                    }
                }
            },
        )
        print(json.dumps({"action": "config", "written": True}))
        return 0
    if args.action == "command":
        result = subprocess.run(
            [str(args.entry.resolve(strict=True)), *args.args],
            cwd=case / "work",
            env=env,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        save(
            args.output,
            {
                "argv": args.args,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
        )
        print(json.dumps({"returncode": result.returncode, "captured": True}))
        return result.returncode
    if args.action == "browser":
        command = browser_command(case, args.chrome, args.extension, args.url)
        chrome = Path(command[0])
        profile = case / "browser-profile"
        process = subprocess.Popen(
            command,
            cwd=case,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        save(
            args.output,
            {
                "pid": process.pid,
                "started_unix": time.time(),
                "executable_sha256": harness.digest(chrome),
                "profile": str(profile),
            },
        )
        print(json.dumps({"pid": process.pid, "started": True}))
        return 0
    if args.action in ("agent-observe", "agent-stop"):
        output = args.output.resolve(strict=True)
        receipt = json.loads((output / "driver.json").read_text(encoding="utf-8"))
        pid = int(receipt["pid"])
        created = str(receipt["created"])
        if args.action == "agent-stop":
            script = (
                "$p=Get-Process -Id "
                + str(pid)
                + " -ErrorAction SilentlyContinue; if(-not $p){exit 3}; if($p.StartTime.ToUniversalTime().ToString('o') -ne '"
                + created
                + "'){exit 4}; Stop-Process -InputObject $p -Force -ErrorAction Stop"
            )
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", script],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            print(
                json.dumps(
                    {
                        "pid": pid,
                        "identity_matched": result.returncode == 0,
                        "stopped": result.returncode == 0,
                    }
                )
            )
            return result.returncode
        if args.snapshot is None:
            parser.error("agent-observe requires --snapshot")
        snapshot = windows_process_snapshot(pid, created)
        save(args.snapshot, snapshot)
        print(
            json.dumps(
                {
                    "pid": pid,
                    "identity_matched": snapshot["root_identity_matches"],
                    "process_count": len(snapshot["processes"]),
                }
            )
        )
        return 0
    goal = args.goal.read_text(encoding="utf-8")
    output = args.output.resolve(strict=True)
    config = agent_config(case, output, args.entry)
    if args.action == "agent-start":
        stdout = (output / "agent.jsonl").open("x", encoding="utf-8")
        stderr = (output / "agent.stderr").open("x", encoding="utf-8")
        try:
            process = subprocess.Popen(
                agent_command(config),
                cwd=case / "work",
                stdin=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                stdout=stdout,
                stderr=stderr,
                env=driver_environment(),
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            created = process_start_identity(process.pid)
            save(output / "driver.json", {"pid": process.pid, "created": created})
            process.stdin.write(goal)
            process.stdin.close()
        finally:
            stdout.close()
            stderr.close()
        print(json.dumps({"pid": process.pid, "created": created, "started": True}))
        return 0
    with (
        (output / "agent.jsonl").open("x", encoding="utf-8") as stdout,
        (output / "agent.stderr").open("x", encoding="utf-8") as stderr,
    ):
        result = subprocess.run(
            agent_command(config),
            cwd=case / "work",
            input=goal,
            text=True,
            encoding="utf-8",
            stdout=stdout,
            stderr=stderr,
            env=driver_environment(),
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    save(output / "exit.json", {"returncode": result.returncode})
    print(json.dumps({"returncode": result.returncode, "captured": True}))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())

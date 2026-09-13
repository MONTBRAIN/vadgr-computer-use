#!/usr/bin/env python3
"""Prepare and control isolated released Windows broker upgrade fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[3]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

EXPECTED = {
    "0.7.6": {
        "wheel": "3b1d431ce2d287ab5c5c5c0cf2b0975e72d4072665b97e85a36cd88586d525b5",
        "archive": "fd2c57b76f57d06d3df3d7c964fa544b798e8f32ec460470bf326a46140696df",
    },
    "0.7.7": {
        "wheel": "e982062875efd5e3e12ca61e1de15d2f5b41c8349f9067330b75136e10172b82",
        "archive": "1745cc86a52413d4802ffda0db07266aa8890e7be447e7b475bbbd4e60ee260c",
    },
}
ARCHIVE_MEMBER = (
    "computer_use/browser/winbroker/vadgr-cua-browser-broker-win-x64.zip"
)
MANIFEST_MEMBER = (
    "computer_use/browser/winbroker/vadgr-cua-browser-broker-win-x64.manifest.json"
)
MARKER = ".vadgr-cua-078-fixture.json"
PROCESS_RECORD = ".fixture-process.json"
EXECUTABLE = "vadgr-cua-browser-broker.exe"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def emit(value: dict[str, object]) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


def checked_root(value: str, *, create: bool = False) -> Path:
    root = Path(value)
    if not root.is_absolute() or not root.name.startswith("vadgr-cua-078-"):
        raise ValueError("root is not an absolute 0.7.8 test root")
    if root.is_symlink():
        raise ValueError("fixture root cannot be a symbolic link")
    if create:
        parent = root.parent.resolve(strict=True)
        root = parent / root.name
        root.mkdir(mode=0o700)
        (root / MARKER).write_text(
            json.dumps({"schema": 1, "root": str(root)}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    root = root.resolve(strict=True)
    marker = root / MARKER
    if root.is_symlink() or not marker.is_file() or marker.is_symlink():
        raise ValueError("root has no valid fixture marker")
    metadata = json.loads(marker.read_text(encoding="utf-8"))
    if metadata != {"root": str(root), "schema": 1}:
        raise ValueError("fixture marker does not match the root")
    return root


def safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.infolist():
        target = (destination / member.filename).resolve()
        if target != root and root not in target.parents:
            raise ValueError("archive member escapes the fixture root")
        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as source, target.open("xb") as output:
            shutil.copyfileobj(source, output)


def prepare(root: Path, release: str, wheel_value: str) -> int:
    expected = EXPECTED[release]
    wheel = Path(wheel_value).resolve(strict=True)
    if not wheel.is_file() or sha256(wheel) != expected["wheel"]:
        raise ValueError("released wheel hash does not match the frozen catalog")
    bundle = root / "released" / release
    bundle.mkdir(parents=True)
    archive_path = root / f"broker-{release}.zip"
    with zipfile.ZipFile(wheel) as package:
        archive_path.write_bytes(package.read(ARCHIVE_MEMBER))
        manifest = json.loads(package.read(MANIFEST_MEMBER))
    if sha256(archive_path) != expected["archive"]:
        raise ValueError("embedded broker archive hash does not match the frozen catalog")
    with zipfile.ZipFile(archive_path) as archive:
        safe_extract(archive, bundle)
    (bundle / "bundle-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    executable = bundle / EXECUTABLE
    if not executable.is_file():
        raise ValueError("released broker executable is missing")
    emit(
        {
            "event": "prepared",
            "release": release,
            "wheel_hash": expected["wheel"],
            "archive_hash": expected["archive"],
            "executable_hash": sha256(executable),
        }
    )
    return 0


def fixture_paths(root: Path, release: str) -> tuple[Path, Path, Path]:
    bundle = (root / "released" / release).resolve(strict=True)
    if root not in bundle.parents:
        raise ValueError("released bundle escaped the fixture root")
    executable = (bundle / EXECUTABLE).resolve(strict=True)
    endpoint = root / "state" / "browser-broker.json"
    return bundle, executable, endpoint


def child_environment(root: Path, endpoint: Path) -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(
        {
            "LOCALAPPDATA": str(root / "appdata"),
            "VADGR_CUA_BROKER_ENDPOINT": str(endpoint),
        }
    )
    return environment


def safe_identity(endpoint: Path) -> dict[str, object]:
    try:
        value = json.loads(endpoint.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"endpoint": "absent"}
    except (OSError, ValueError, json.JSONDecodeError):
        return {"endpoint": "invalid"}
    return {
        "endpoint": "valid",
        "platform": value.get("platform"),
        "host": value.get("host"),
        "port_valid": isinstance(value.get("port"), int)
        and 1 <= int(value["port"]) <= 65535,
        "token_present": isinstance(value.get("token"), str) and bool(value["token"]),
        "pid": value.get("pid"),
        "process_started_ns": value.get("process_started_ns"),
        "process_created_filetime": value.get("process_created_filetime"),
        "epoch": value.get("epoch"),
        "bundle_hash": value.get("bundle_hash"),
    }


def start(root: Path, release: str, *, synthetic: bool) -> int:
    if sys.platform != "win32":
        raise ValueError("start must run under native Windows Python")
    bundle, executable, endpoint = fixture_paths(root, release)
    endpoint.parent.mkdir(mode=0o700)
    if synthetic:
        synthetic_bundle = root / "synthetic" / release
        shutil.copytree(bundle, synthetic_bundle)
        executable = synthetic_bundle / EXECUTABLE
        with executable.open("ab") as file:
            file.write(b"vadgr-078-unknown-payload")
        bundle = synthetic_bundle
    process = subprocess.Popen(
        [str(executable), "serve"],
        cwd=bundle,
        env=child_environment(root, endpoint),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
    )
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        identity = safe_identity(endpoint)
        if identity.get("endpoint") == "valid" and identity.get("pid") == process.pid:
            emit(
                {
                    "event": "started",
                    "release": release,
                    "synthetic": synthetic,
                    "executable_hash": sha256(executable),
                    "identity": identity,
                }
            )
            (root / PROCESS_RECORD).write_text(
                json.dumps(
                    {
                        "executable_hash": sha256(executable),
                        "pid": process.pid,
                        "process_created_filetime": identity.get(
                            "process_created_filetime"
                        ),
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            return 0
        if process.poll() is not None:
            raise RuntimeError("fixture broker exited before readiness")
        time.sleep(0.05)
    raise TimeoutError("fixture broker did not publish readiness")


def fault(root: Path, action: str) -> int:
    endpoint = root / "state" / "browser-broker.json"
    if endpoint.is_symlink():
        raise ValueError("endpoint cannot be a symbolic link")
    if action == "remove":
        endpoint.unlink()
    else:
        endpoint.write_text("{invalid\n", encoding="utf-8")
    emit({"event": "fault_applied", "action": action})
    return 0


def stop(root: Path) -> int:
    if sys.platform != "win32":
        raise ValueError("stop must run under native Windows Python")
    endpoint = root / "state" / "browser-broker.json"
    identity = safe_identity(endpoint)
    pid = identity.get("pid")
    if not isinstance(pid, int) or pid < 1:
        record = json.loads((root / PROCESS_RECORD).read_text(encoding="utf-8"))
        pid = record.get("pid")
    if not isinstance(pid, int) or pid < 1:
        raise ValueError("fixture endpoint has no process identity")
    from computer_use.browser.windows_process import _ProcessExited, _WindowsProcess

    try:
        process = _WindowsProcess(pid)
    except _ProcessExited:
        emit({"event": "already_stopped", "pid": pid})
        return 0
    try:
        executable = process.image_path().resolve(strict=True)
        if root not in executable.parents or executable.name.lower() != EXECUTABLE:
            raise ValueError("fixture process is outside the validated root")
        before = process.creation_filetime()
        process.terminate()
        if not process.wait(10):
            raise TimeoutError("validated fixture process did not stop")
        emit(
            {
                "event": "stopped",
                "pid": pid,
                "process_created_filetime": str(before),
                "executable_hash": sha256(executable),
            }
        )
        return 0
    finally:
        process.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command", choices=("init", "prepare", "start", "observe", "fault", "stop")
    )
    parser.add_argument("--root", required=True)
    parser.add_argument("--release", choices=tuple(EXPECTED))
    parser.add_argument("--wheel")
    parser.add_argument("--action", choices=("remove", "corrupt"))
    parser.add_argument("--synthetic", action="store_true")
    args = parser.parse_args()
    root = checked_root(args.root, create=args.command == "init")
    if args.command == "init":
        emit({"event": "initialized"})
        return 0
    if args.command == "prepare":
        if args.release is None or args.wheel is None:
            parser.error("prepare requires --release and --wheel")
        return prepare(root, args.release, args.wheel)
    if args.command == "start":
        if args.release is None:
            parser.error("start requires --release")
        return start(root, args.release, synthetic=args.synthetic)
    if args.command == "observe":
        emit(safe_identity(root / "state" / "browser-broker.json"))
        return 0
    if args.command == "fault":
        if args.action is None:
            parser.error("fault requires --action")
        return fault(root, args.action)
    return stop(root)


if __name__ == "__main__":
    raise SystemExit(main())

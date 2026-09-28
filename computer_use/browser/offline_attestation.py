# Copyright 2026 Victor Santiago Montano Diaz
# Licensed under the Apache License, Version 2.0.

"""Pinned, offline GitHub attestation verification without ambient credentials."""

from __future__ import annotations

import base64
import ctypes
import json
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from computer_use.browser.managed_authorization import (
    AuthorizationError,
    require,
    sha256,
)

MAX_OUTPUT = 4 * 1024 * 1024


def run_bounded(
    arguments: list[str],
    *,
    environment: dict[str, str],
    data: bytes | None = None,
    timeout: int = 45,
) -> bytes:
    """Bound both output streams while the child runs, not after buffering them."""
    process = subprocess.Popen(
        arguments,
        stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    output: list[bytes] = [b"", b""]
    overflow = threading.Event()

    def drain(index, stream):
        chunks = []
        size = 0
        try:
            while chunk := stream.read(65536):
                size += len(chunk)
                if size > MAX_OUTPUT:
                    overflow.set()
                    process.kill()
                    break
                chunks.append(chunk)
            output[index] = b"".join(chunks)
        finally:
            stream.close()

    threads = [
        threading.Thread(target=drain, args=(i, stream), daemon=True)
        for i, stream in enumerate((process.stdout, process.stderr))
    ]
    for thread in threads:
        thread.start()
    writer = None
    if data is not None:

        def write():
            try:
                process.stdin.write(data)
                process.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        writer = threading.Thread(target=write, daemon=True)
        writer.start()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        process.kill()
        process.wait()
        raise AuthorizationError("offline verifier timed out") from error
    finally:
        for thread in threads:
            thread.join(timeout=2)
        if writer:
            writer.join(timeout=2)
    require(not overflow.is_set(), "offline verifier output exceeded its limit")
    require(process.returncode == 0, "offline signature verification failed")
    return output[0]


def powershell() -> Path:
    if sys.platform != "win32":
        value = Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
        require(value.is_file(), "native Windows PowerShell is unavailable")
        return value
    buffer = ctypes.create_unicode_buffer(32768)
    size = ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer))
    require(0 < size < len(buffer), "native Windows system directory is unavailable")
    return Path(buffer.value) / "WindowsPowerShell" / "v1.0" / "powershell.exe"


def windows_path(path: Path) -> str:
    if sys.platform == "win32":
        return str(path.absolute())
    output = run_bounded(["/usr/bin/wslpath", "-w", str(path.absolute())], environment={})
    value = output.decode("utf-8").strip()
    require(
        bool(re.fullmatch(r"[A-Za-z]:\\[^\r\n]+|\\\\(?:wsl\.localhost|wsl\$)\\[^\r\n]+", value)),
        "offline verifier requires a local Windows-accessible package",
    )
    return value


def local_path(value: str) -> Path:
    require(
        isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z]:\\[^\r\n]+", value)),
        "native Windows path is invalid",
    )
    if sys.platform == "win32":
        return Path(value)
    output = run_bounded(["/usr/bin/wslpath", "-u", value], environment={})
    path = Path(output.decode("utf-8").strip())
    require(path.is_absolute(), "native Windows path translation failed")
    return path


def clean_environment() -> dict[str, str]:
    # No owner environment, PATH, token, proxy, Git or credential configuration.
    if sys.platform == "win32":
        system = powershell().parents[2]
        return {"SystemRoot": str(system.parent), "WINDIR": str(system.parent)}
    return {}


def parse_verified_proof(raw: bytes, subject: bytes, policy: dict) -> dict:
    """Read authenticated certificate extensions, not predicate self-reports."""

    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, "duplicate verifier output key")
            value[key] = item
        return value

    try:
        values = json.loads(raw, object_pairs_hook=unique)
        require(
            isinstance(values, list) and len(values) == 1,
            "exactly one verified attestation is required",
        )
        verified = values[0]["verificationResult"]
        certificate = verified["signature"]["certificate"]
        subjects = verified["statement"]["subject"]
        require(
            len(subjects) == 1 and subjects[0]["digest"] == {"sha256": sha256(subject)},
            "verified attestation subject differs",
        )
        repository = "https://github.com/" + policy["repository"]
        invocation = re.fullmatch(
            re.escape(repository) + r"/actions/runs/([1-9][0-9]*)/attempts/([1-9][0-9]*)",
            certificate["runInvocationURI"],
        )
        require(invocation is not None, "attestation run identity is invalid")
        require(
            certificate["sourceRepositoryURI"] == repository
            and certificate["sourceRepositoryIdentifier"] == str(policy["repository_id"])
            and certificate["sourceRepositoryOwnerIdentifier"] == str(policy["owner_id"])
            and certificate["subjectAlternativeName"] == policy["certificate_identity"]
            and certificate["buildSignerURI"] == policy["certificate_identity"]
            and certificate["issuer"] == policy["issuer"]
            and certificate["sourceRepositoryRef"] == policy["source_ref"]
            and certificate["sourceRepositoryDigest"] in policy["source_sha_allowlist"]
            and certificate["buildSignerDigest"] in policy["signer_sha_allowlist"]
            and certificate["runnerEnvironment"] == "github-hosted",
            "authenticated certificate identity differs from packaged policy",
        )
        return {
            **{
                key: policy[key]
                for key in (
                    "repository",
                    "repository_id",
                    "owner_id",
                    "certificate_identity",
                    "issuer",
                    "source_ref",
                )
            },
            "subject_sha256": sha256(subject),
            "source_sha": certificate["sourceRepositoryDigest"],
            "signer_sha": certificate["buildSignerDigest"],
            "run_id": int(invocation[1]),
            "attempt": int(invocation[2]),
            "self_hosted": False,
        }
    except (KeyError, TypeError, ValueError, IndexError, UnicodeError) as error:
        raise AuthorizationError("offline verifier returned an invalid proof") from error


def verify(
    subject: bytes,
    bundle: bytes,
    policy: dict,
    root: bytes,
    verifier: bytes,
    *,
    verifier_path: Path,
    root_path: Path,
) -> dict:
    """Only bundled roots and a detached bundle are available to the verifier."""
    require(
        sha256(verifier) == policy["verifier_sha256"]
        and sha256(verifier_path.read_bytes()) == policy["verifier_sha256"]
        and sha256(root) == policy["root_sha256"]
        and sha256(root_path.read_bytes()) == policy["root_sha256"],
        "offline verifier inputs changed",
    )
    if sys.platform != "win32":
        # Windows interop can otherwise inherit the Windows parent's credentials
        # despite a clean Linux env. The fixed native adapter clears that env.
        receipt = native_call(
            {
                "operation": "attestation",
                "architecture": policy["architecture"],
                "subject": base64.b64encode(subject).decode("ascii"),
                "bundle": base64.b64encode(bundle).decode("ascii"),
                "policy": policy,
            }
        )
        require(
            set(receipt) == {"proof"} and isinstance(receipt["proof"], str),
            "native offline attestation receipt differs",
        )
        return parse_verified_proof(receipt["proof"].encode(), subject, policy)
    # Native Windows temp location is obtained from a system API, not TEMP.
    # WSL stages on the same Windows filesystem as the verified package.
    staging_parent = verifier_path.parent
    with tempfile.TemporaryDirectory(prefix=".verification-", dir=staging_parent) as temporary:
        directory = Path(temporary)
        from computer_use.browser.private_file import private_directory

        private_directory(directory)
        subject_path = directory / "subject.json"
        bundle_path = directory / "bundle.json"
        subject_path.write_bytes(subject)
        bundle_path.write_bytes(bundle)
        environment = clean_environment()
        environment.update(
            {
                "GH_CONFIG_DIR": windows_path(directory),
                "GH_PROMPT_DISABLED": "1",
                "GH_NO_UPDATE_NOTIFIER": "1",
                "GH_NO_EXTENSION_UPDATE_NOTIFIER": "1",
            }
        )
        arguments = [
            str(verifier_path),
            "attestation",
            "verify",
            windows_path(subject_path),
            "--bundle",
            windows_path(bundle_path),
            "--custom-trusted-root",
            windows_path(root_path),
            "--repo",
            policy["repository"],
            "--cert-identity",
            policy["certificate_identity"],
            "--cert-oidc-issuer",
            policy["issuer"],
            "--source-ref",
            policy["source_ref"],
            "--deny-self-hosted-runners",
            "--format",
            "json",
        ]
        last = None
        for source in policy["source_sha_allowlist"]:
            for signer in policy["signer_sha_allowlist"]:
                try:
                    raw = run_bounded(
                        arguments + ["--source-digest", source, "--signer-digest", signer],
                        environment=environment,
                    )
                    return parse_verified_proof(raw, subject, policy)
                except AuthorizationError as error:
                    last = error
        raise AuthorizationError("no approved offline attestation verified") from last


def native_call(request: dict) -> dict:
    script = Path(__file__).parent / "winbroker" / "adopt-native.ps1"
    require(script.is_file(), "native signed-helper verifier is missing")
    command = [
        str(powershell()),
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        windows_path(script),
    ]
    raw = run_bounded(
        command,
        environment=clean_environment(),
        data=json.dumps(request, separators=(",", ":")).encode(),
        timeout=120,
    )
    try:
        value = json.loads(raw)
        require(isinstance(value, dict), "native verifier returned an invalid receipt")
        return value
    except (UnicodeError, ValueError) as error:
        raise AuthorizationError("native verifier returned an invalid receipt") from error

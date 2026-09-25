# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Self-contained Windows entry point for the shared browser broker.

The frozen executable only serves the broker on Windows loopback. Native
Windows clients connect directly; WSL clients use the separately built Go
stdio proxy so the frozen payload never carries a second transport path.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import time
from pathlib import Path

_REPARSE_POINT = 0x400
_MAX_AUTHORIZATION = 4 * 1024 * 1024


def _ordinary(path: Path) -> bytes:
    for candidate in (path, *path.parents):
        info = candidate.lstat()
        if getattr(info, "st_file_attributes", 0) & _REPARSE_POINT:
            raise RuntimeError("browser broker authorization path contains a reparse point")
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > _MAX_AUTHORIZATION:
        raise RuntimeError("browser broker authorization is not a bounded ordinary file")
    raw = path.read_bytes()
    if not raw or len(raw) > _MAX_AUTHORIZATION:
        raise RuntimeError("browser broker authorization exceeds its limit")
    return raw


def _candidate(bundle: Path) -> tuple[dict, str, str, bool]:
    """Read the one externally installed manifest for this exact candidate."""
    final_path = bundle / "broker-final-manifest.json"
    input_path = bundle / "bundle-manifest.json"
    present = [path for path in (final_path, input_path) if path.is_file()]
    if len(present) != 1:
        raise RuntimeError("browser broker bundle has an ambiguous manifest")
    path = present[0]
    raw = _ordinary(path)
    from computer_use.browser.managed_authorization import (
        sha256,
        validate_final_manifest,
    )

    if path == final_path:
        manifest = validate_final_manifest(raw)
        return manifest, sha256(raw), manifest["architecture"], True
    try:
        manifest = json.loads(raw)
        target = manifest["target"]
        architecture = {
            "x86_64-pc-windows-msvc": "x86_64",
            "aarch64-pc-windows-msvc": "aarch64",
        }[target]
        if manifest["archive_sha256"] != bundle.name:
            raise ValueError("candidate input archive differs")
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError("browser broker input manifest is invalid") from error
    return manifest, sha256(raw), architecture, False


def _adoption_edge(
    bundle: Path, authorization_path: str | None, expected_sha256: str | None
) -> tuple[dict[str, object] | None, str]:
    """Load only a caller-authenticated authorization bound to this candidate."""
    manifest, manifest_sha256, architecture, managed = _candidate(bundle)
    if authorization_path is None and expected_sha256 is None:
        return None, architecture
    if not authorization_path or not expected_sha256:
        raise RuntimeError("both adoption authorization path and digest are required")
    if not managed:
        raise RuntimeError("an unsigned candidate cannot consume adoption authorization")
    path = Path(authorization_path)
    if path.name != "helper-closure-authorization.json" or not path.is_absolute():
        raise RuntimeError("adoption authorization path is invalid")
    raw = _ordinary(path)
    from computer_use.browser.managed_authorization import fields, sha256, strict_json

    if sha256(raw) != expected_sha256:
        raise RuntimeError("adoption authorization digest differs")
    authorization = strict_json(raw)
    fields(
        authorization,
        "schema pre_signing_claim_sha256 helper_closure_id architecture "
        "cua_version source_commit tooling_commit input_closure final_closure consumer_inputs "
        "signing_run_id signing_attempt signing_job_id output_artifact "
        "publisher_policy_sha256 legal_policy_sha256 mapping_sha256 adoption_edges",
    )
    final = authorization["final_closure"]
    if (
        authorization["architecture"] != architecture
        or authorization["cua_version"] != manifest["cua_version"]
        or not isinstance(final, dict)
        or final.get("archive_sha256") != manifest["archive"]["sha256"]
        or final.get("manifest_sha256") != manifest_sha256
    ):
        raise RuntimeError("adoption authorization targets a different candidate")
    edges = authorization["adoption_edges"]
    if not isinstance(edges, list) or len(edges) != 1:
        raise RuntimeError("adoption authorization has an invalid transition set")
    return edges[0], architecture


def _serve() -> int:
    bundle = Path(sys.executable).resolve().parent
    paths = [path for path in (
        bundle / "broker-final-manifest.json",
        bundle / "bundle-manifest.json",
    ) if path.is_file()]
    try:
        if len(paths) != 1:
            raise RuntimeError("browser broker bundle has an ambiguous manifest")
        manifest_path = paths[0]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        bundle_hash = str(
            manifest["archive"]["sha256"]
            if manifest.get("mode") == "managed-signed"
            else manifest["archive_sha256"]
        )
    except (OSError, ValueError, KeyError) as error:
        raise RuntimeError("browser broker bundle manifest is unavailable") from error
    os.environ["VADGR_CUA_BROKER_BUNDLE_HASH"] = bundle_hash
    os.environ["VADGR_CUA_BROKER_STARTED_NS"] = str(time.time_ns())
    from computer_use.browser.windows_process import current_process_creation_filetime

    os.environ["VADGR_CUA_BROKER_CREATED_FILETIME"] = current_process_creation_filetime()
    from computer_use.browser.broker import main

    return main()


def _upgrade_handoff(
    authorization_path: str | None = None, authorization_sha256: str | None = None
) -> int:
    from computer_use.browser.broker import broker_lock_path
    from computer_use.browser.windows_process import (
        UpgradeHandoffError,
        perform_upgrade_handoff,
    )

    bundle = Path(sys.executable).resolve().parent
    packaged = Path(getattr(sys, "_MEIPASS", bundle))
    try:
        adoption, architecture = _adoption_edge(
            bundle, authorization_path, authorization_sha256
        )
        result = perform_upgrade_handoff(
            lock_path=broker_lock_path(),
            candidate_bundle=bundle,
            catalog_path=packaged / "predecessor-catalog.json",
            architecture=architecture,
            adoption=adoption,
        )
    except UpgradeHandoffError as error:
        result = {
            "state": "refused",
            "code": error.code,
            "message": str(error),
            "remediation": error.remediation,
        }
    print(json.dumps(result, separators=(",", ":")), flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vadgr-cua-browser-broker")
    parser.add_argument("mode", nargs="?", choices=("serve", "upgrade-handoff"), default="serve")
    parser.add_argument("--authorization")
    parser.add_argument("--authorization-sha256")
    options = parser.parse_args(argv)
    return (
        _upgrade_handoff(options.authorization, options.authorization_sha256)
        if options.mode == "upgrade-handoff"
        else _serve()
    )


if __name__ == "__main__":
    raise SystemExit(main())

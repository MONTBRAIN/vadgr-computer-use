# Copyright 2026 Victor Santiago Montano Diaz
# Licensed under the Apache License, Version 2.0.

"""Build a deterministic archive from independently verified final members.

This module never signs code and never invokes an input executable.
"""

from __future__ import annotations

import io
import zipfile

from computer_use.browser.managed_authorization import (
    member_path,
    require,
    sha256,
    validate_final_manifest,
)

MAX_MEMBERS = 4096
MAX_EXPANDED_BYTES = 512 * 1024 * 1024


def deterministic_zip(members: dict[str, bytes]) -> bytes:
    require(
        isinstance(members, dict) and 0 < len(members) <= MAX_MEMBERS,
        "invalid archive member count",
    )
    require(
        len({name.casefold() for name in members}) == len(members), "case-colliding archive members"
    )
    total = 0
    for name, content in members.items():
        member_path(name)
        require(
            name.split("/")[-1].lower() != "broker-final-manifest.json",
            "the final manifest must stay outside its archive",
        )
        require(isinstance(content, bytes), "archive members must be immutable bytes")
        total += len(content)
    require(total <= MAX_EXPANDED_BYTES, "archive exceeds its expanded size limit")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        for name in sorted(members, key=lambda item: item.encode("utf-8")):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_STORED
            info.extra = b""
            info.comment = b""
            archive.writestr(info, members[name])
    return buffer.getvalue()


def verify_final_archive(archive_bytes: bytes, manifest_bytes: bytes) -> dict[str, bytes]:
    manifest = validate_final_manifest(manifest_bytes)
    require(
        sha256(archive_bytes) == manifest["archive"]["sha256"]
        and len(archive_bytes) == manifest["archive"]["size"],
        "final archive digest mismatch",
    )
    expected = {row["path"]: row for row in manifest["files"]}
    require(len(expected) <= MAX_MEMBERS, "too many archive members")
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        infos = archive.infolist()
        require(
            len(infos) == len(expected) and {row.filename for row in infos} == set(expected),
            "archive member set differs from final manifest",
        )
        require(
            sum(row.file_size for row in infos) <= MAX_EXPANDED_BYTES,
            "archive exceeds its expanded size limit",
        )
        members = {}
        for info in infos:
            member_path(info.filename)
            require(
                info.file_size == expected[info.filename]["size"]
                and info.compress_type == zipfile.ZIP_STORED,
                "invalid archive member size/type",
            )
            content = archive.read(info)
            require(sha256(content) == expected[info.filename]["sha256"], "archive member changed")
            members[info.filename] = content
    require(deterministic_zip(members) == archive_bytes, "archive metadata is not deterministic")
    return members

import hashlib
import importlib.util
import json
import pathlib
import zipfile

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "build_windows_broker.py"


@pytest.fixture
def builder():
    spec = importlib.util.spec_from_file_location("build_windows_broker", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_zip(path, entries, timestamp, *, reverse_metadata=False):
    with zipfile.ZipFile(path, "w") as output:
        output.comment = b"archive comment" if reverse_metadata else b"other comment"
        for index, (name, data) in enumerate(entries):
            info = zipfile.ZipInfo(name, timestamp)
            info.compress_type = zipfile.ZIP_DEFLATED if name == "a.pyc" else zipfile.ZIP_STORED
            info.comment = b"member comment"
            info.extra = b"\x0a\x00\x00\x00"
            info.create_system = 0 if reverse_metadata else 3
            info.external_attr = index + 1
            output.writestr(info, data, compresslevel=1)


def _content_hashes(path):
    with zipfile.ZipFile(path) as archive:
        return {
            info.filename: hashlib.sha256(archive.read(info)).hexdigest()
            for info in archive.infolist()
        }


def test_system_api_set_contracts_are_not_deployed_as_app_local_dlls(tmp_path, builder):
    internal = tmp_path / "_internal"
    internal.mkdir()
    removable = (
        "api-ms-win-core-console-l1-1-0.dll",
        "API-MS-WIN-CRT-RUNTIME-L1-1-0.DLL",
        "ext-ms-win-shell-shell32-l1-2-0.dll",
        "ucrtbase.dll",
    )
    for name in removable:
        (internal / name).write_bytes(b"system contract")
    retained = internal / "python312.dll"
    retained.write_bytes(b"pinned runtime")

    removed = builder.remove_system_api_set_forwarders(tmp_path)

    assert set(removed) == {f"_internal/{name}" for name in removable}
    assert retained.read_bytes() == b"pinned runtime"
    assert not any((internal / name).exists() for name in removable)


def test_embedded_zip_normalization_is_byte_reproducible(tmp_path, builder):
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    entries = [("b.pyc", b"second"), ("a.pyc", b"first")]
    _write_zip(first, entries, (2026, 9, 3, 1, 2, 4))
    _write_zip(
        second,
        list(reversed(entries)),
        (2026, 9, 3, 5, 6, 8),
        reverse_metadata=True,
    )
    expected_hashes = _content_hashes(first)

    builder.normalize_embedded_zip(first)
    builder.normalize_embedded_zip(second)

    assert first.read_bytes() == second.read_bytes()
    assert _content_hashes(first) == expected_hashes
    with zipfile.ZipFile(first) as normalized:
        assert normalized.namelist() == ["a.pyc", "b.pyc"]
        assert all(info.date_time == builder.FIXED_ZIP_TIME for info in normalized.infolist())
        assert normalized.comment == b""

    first_root = tmp_path / "first-root" / "_internal"
    second_root = tmp_path / "second-root" / "_internal"
    first_root.mkdir(parents=True)
    second_root.mkdir(parents=True)
    (first_root / "base_library.zip").write_bytes(first.read_bytes())
    (second_root / "base_library.zip").write_bytes(second.read_bytes())
    first_bundle = tmp_path / "first-bundle.zip"
    second_bundle = tmp_path / "second-bundle.zip"
    builder.write_zip(first_root.parent, first_bundle)
    builder.write_zip(second_root.parent, second_bundle)
    assert first_bundle.read_bytes() == second_bundle.read_bytes()


@pytest.mark.parametrize(
    ("architecture", "archive", "manifest"),
    [
        (
            "x86_64",
            "vadgr-cua-browser-broker-win-x64.zip",
            "vadgr-cua-browser-broker-win-x64.manifest.json",
        ),
        (
            "aarch64",
            "vadgr-cua-browser-broker-win-arm64.zip",
            "vadgr-cua-browser-broker-win-arm64.manifest.json",
        ),
    ],
)
def test_artifact_names_are_architecture_closed(builder, architecture, archive, manifest):
    actual_archive, actual_manifest, actual_sbom = builder.artifact_names(architecture)
    assert actual_archive == archive
    assert actual_manifest == manifest
    assert actual_sbom.endswith(".spdx.json")


def test_outer_archive_is_stored_reproducible_and_free_of_mutable_metadata(tmp_path, builder):
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    for root in (first_root, second_root):
        root.joinpath("z.dll").write_bytes(b"dll")
        root.joinpath("a.exe").write_bytes(b"exe")
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    builder.write_zip(first_root, first)
    builder.write_zip(second_root, second)

    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == ["a.exe", "z.dll"]
        assert archive.comment == b""
        assert all(item.compress_type == zipfile.ZIP_STORED for item in archive.infolist())
        assert all(item.date_time == (1980, 1, 1, 0, 0, 0) for item in archive.infolist())
        assert all(item.comment == b"" and item.extra == b"" for item in archive.infolist())


def test_cross_architecture_build_is_refused_before_tool_execution(monkeypatch, builder):
    monkeypatch.setattr(builder.platform, "machine", lambda: "AMD64")
    with pytest.raises(SystemExit, match="must be built on native aarch64 Windows"):
        builder.require_native_architecture("aarch64")


@pytest.mark.parametrize(
    ("architecture", "target", "versions"),
    [
        (
            "x86_64",
            "x86_64-pc-windows-msvc",
            ["0.7.6", "0.7.7", "0.7.8"],
        ),
        ("aarch64", "aarch64-pc-windows-msvc", []),
    ],
)
def test_predecessor_catalog_is_native_architecture_closed(
    tmp_path, builder, architecture, target, versions
):
    source = (
        pathlib.Path(__file__).resolve().parents[2]
        / "computer_use/browser/winbroker/predecessor-catalog.json"
    )
    output = tmp_path / "predecessor-catalog.json"

    builder.write_predecessor_catalog(source, output, architecture)

    value = json.loads(output.read_bytes())
    assert value["target"] == target
    assert [row["version"] for row in value["releases"]] == versions
    assert output.read_bytes().endswith(b"\n")


def test_predecessor_catalog_refuses_missing_released_input(tmp_path, builder):
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps(
            {
                "schema": 1,
                "target": "x86_64-pc-windows-msvc",
                "releases": [],
            }
        )
    )

    with pytest.raises(ValueError, match="incomplete"):
        builder.write_predecessor_catalog(source, tmp_path / "output.json", "x86_64")


def test_released_078_predecessor_row_matches_retained_source_bytes():
    root = pathlib.Path(__file__).resolve().parents[2] / "computer_use/browser/winbroker"
    catalog = json.loads((root / "predecessor-catalog.json").read_bytes())
    row = next(item for item in catalog["releases"] if item["version"] == "0.7.8")
    archive = root / "vadgr-cua-browser-broker-win-x64.zip"
    manifest = root / "vadgr-cua-browser-broker-win-x64.manifest.json"

    assert row["archive_sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    manifest_bytes = manifest.read_bytes().replace(b"\r\n", b"\n")
    assert b"\r" not in manifest_bytes
    assert row["manifest_sha256"] == hashlib.sha256(manifest_bytes).hexdigest()
    with zipfile.ZipFile(archive) as payload:
        broker = payload.read(row["broker_relative_path"])
    assert row["broker_sha256"] == hashlib.sha256(broker).hexdigest()

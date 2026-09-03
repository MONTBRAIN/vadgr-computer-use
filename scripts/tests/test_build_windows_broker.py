import hashlib
import importlib.util
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

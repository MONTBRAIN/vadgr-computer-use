# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Native-messaging stdio framing (length-prefixed JSON), no browser."""

import io
import json
import struct

import pytest

from computer_use.browser import native_host as NH


def _framed(obj) -> bytes:
    raw = json.dumps(obj).encode("utf-8")
    return struct.pack("<I", len(raw)) + raw


class TestWriteFrame:
    def test_writes_4_byte_le_length_prefix_then_json(self):
        buf = io.BytesIO()
        NH.write_message(buf, {"a": 1})
        data = buf.getvalue()
        (length,) = struct.unpack("<I", data[:4])
        assert length == len(data) - 4
        assert json.loads(data[4:]) == {"a": 1}


class TestReadFrame:
    def test_reads_one_framed_message(self):
        buf = io.BytesIO(_framed({"type": "hello", "proto": 1}))
        msg = NH.read_message(buf)
        assert msg == {"type": "hello", "proto": 1}

    def test_eof_returns_none(self):
        assert NH.read_message(io.BytesIO(b"")) is None

    def test_truncated_body_raises(self):
        # Declares 50 bytes but supplies fewer.
        bad = struct.pack("<I", 50) + b"{}"
        with pytest.raises(EOFError):
            NH.read_message(io.BytesIO(bad))

    def test_roundtrip_multiple_messages(self):
        buf = io.BytesIO()
        NH.write_message(buf, {"id": 1})
        NH.write_message(buf, {"id": 2})
        buf.seek(0)
        assert NH.read_message(buf) == {"id": 1}
        assert NH.read_message(buf) == {"id": 2}
        assert NH.read_message(buf) is None

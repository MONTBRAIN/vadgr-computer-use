"""Synthetic handshake frames only; each case has no socket or browser."""

import io
from types import SimpleNamespace

import pytest

from computer_use.browser import server
from computer_use.browser.protocol import BrowserError

HELLO = {"type": "hello", "proto": 1, "ext_version": "0.7.6",
         "browser": "chrome", "supported_ops": ["read_text"]}


@pytest.fixture
def handshake(monkeypatch):
    instance = server.BrowserServer.__new__(server.BrowserServer)
    instance.token = "synthetic-token"
    registered, replies = [], []
    instance.bridge = SimpleNamespace(register_session=registered.append)
    monkeypatch.setattr(server, "write_message", lambda _file, message: replies.append(message))
    monkeypatch.setattr(server, "TcpBrowserSession", lambda *args, **kwargs: SimpleNamespace())

    def run(first):
        frames = iter([first, HELLO])
        monkeypatch.setattr(server, "read_message", lambda _file: next(frames))
        instance._handshake(object(), object())

    return run, registered, replies


@pytest.mark.parametrize("first", [
    HELLO, {}, {"type": "auth"}, {"type": "auth", "token": None},
    {"type": "auth", "token": ["synthetic-token"]},
    {"type": "auth", "token": "incorrect"}, {"type": "auth", "token": "\N{SNOWMAN}"},
    {"type": "hello", "token": "synthetic-token"},
    [], 123, "invalid", None,
])
def test_missing_or_invalid_auth_never_replies_or_registers(handshake, first):
    run, registered, replies = handshake
    with pytest.raises((BrowserError, ValueError)) as caught:
        run(first)
    if isinstance(caught.value, BrowserError):
        assert caught.value.code.value == "not_connected"
    assert registered == []
    assert replies == []


def test_authenticated_native_host_frame_still_registers(handshake):
    run, registered, replies = handshake
    run({"type": "auth", "token": "synthetic-token"})
    assert len(registered) == 1
    assert len(replies) == 1 and replies[0]["type"] == "hello"


def test_truncated_auth_frame_closes_connection_without_registering():
    instance = server.BrowserServer.__new__(server.BrowserServer)
    instance.token = "synthetic-token"
    registered, closed = [], []
    instance.bridge = SimpleNamespace(register_session=registered.append)
    stream = io.BytesIO(b"\x20\x00")
    connection = SimpleNamespace(settimeout=lambda value: None, makefile=lambda mode: stream,
                                 close=lambda: closed.append(True))
    instance._handle_conn(connection)
    assert stream.closed
    assert closed == [True] and registered == []

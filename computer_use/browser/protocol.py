# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""The wire contract — the *only* coupling between cua and the extension.

A single versioned message schema, defined here and mirrored in
``extension/src/protocol.ts``. The two builds share no imports; they agree
only on this envelope.

Two version gates, deliberately separate (the extension and cua update on
different clocks):

- ``PROTOCOL_VERSION`` — one integer for the envelope (handshake, framing,
  error schema). Bumped only on a breaking wire change; negotiated on connect;
  mismatch → no ops run.
- ``SUPPORTED_OPS`` — the op-level capability list the extension reports in
  ``hello``. Adding an op in a later MINOR is additive and does NOT bump
  ``PROTOCOL_VERSION``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

# Envelope version. Bump ONLY on a breaking wire change (handshake / framing /
# error schema). Adding ops does not bump this — see SUPPORTED_OPS.
PROTOCOL_VERSION = 1

# The op-level capability list for THIS build. Mirrored in protocol.ts. Later
# MINORs append to this; they do not bump PROTOCOL_VERSION.
SUPPORTED_OPS: tuple[str, ...] = (
    "navigate",
    "back",
    "forward",
    "reload",
    "wait_for",
    "query",
    "read_text",
    "get_attribute",
    "click",
    "type",
    "fill",
    "select",
    "scroll",
    "cookies",
    "status",
    "eval",
    # CDP universal path (chrome.debugger) — additive (no PROTOCOL_VERSION bump).
    "press",
    "accessibility_tree",
    # 0.5.0 — session targeting + the remaining interaction ops (additive).
    "use_target",
    "hover",
    "dialog",
    "upload",
    "element_state",
    "focus",
    "blur",
    "clear",
    "get_value",
    "snapshot",
)


class BrowserErrorCode(str, Enum):
    """Error taxonomy carried to the LLM.

    The non-retryable codes are terminal-until-the-user-acts — they must not
    look transient, or the agent loop-retries and burns turns.
    """

    NOT_SET_UP = "not_set_up"          # no native-host manifest registered
    NOT_CONNECTED = "not_connected"    # manifest on disk, no live session
    OP_UNSUPPORTED = "op_unsupported"  # connected extension too old for this op
    PROTO_MISMATCH = "proto_mismatch"  # envelope versions incompatible
    WAKING = "waking"                  # session existed; SW asleep (retryable)
    OP_FAILED = "op_failed"            # op ran in-page but failed
    TARGET_LOST = "target_lost"        # pinned tab/window closed (terminal)


# Codes that are transient and worth an automatic retry. Everything else is
# terminal-until-the-user-acts.
_RETRYABLE = frozenset({BrowserErrorCode.WAKING})


class BrowserError(Exception):
    """A typed browser-tier failure.

    Carries the taxonomy ``code``, a human ``message``, an optional
    ``remediation`` string (what the user must do) and an optional ``fallback``
    line (the guided pixel path). ``tool.py`` maps it to a ``ToolError`` whose
    text reaches the LLM verbatim.
    """

    def __init__(
        self,
        code: BrowserErrorCode,
        message: str,
        *,
        remediation: str | None = None,
        fallback: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.remediation = remediation
        self.fallback = fallback

    @property
    def retryable(self) -> bool:
        return self.code in _RETRYABLE


@dataclass(frozen=True)
class ServerHello:
    """The extension's half of the handshake."""

    proto: int
    ext_version: str
    browser: str
    supported_ops: list[str]


def client_hello(cua_version: str) -> dict[str, Any]:
    """Build cua's handshake message (sent first, on connect)."""
    return {"type": "hello", "proto": PROTOCOL_VERSION, "cua_version": cua_version}


def parse_server_hello(msg: dict[str, Any]) -> ServerHello:
    """Validate + parse the extension's hello. Raises on type/proto mismatch."""
    if msg.get("type") != "hello":
        raise BrowserError(
            BrowserErrorCode.PROTO_MISMATCH,
            f"expected a hello message, got {msg.get('type')!r}",
        )
    proto = msg.get("proto")
    if proto != PROTOCOL_VERSION:
        raise BrowserError(
            BrowserErrorCode.PROTO_MISMATCH,
            f"extension speaks protocol {proto}, cua speaks {PROTOCOL_VERSION}",
            remediation="update the extension or cua so the protocol versions match",
        )
    return ServerHello(
        proto=proto,
        ext_version=str(msg.get("ext_version", "")),
        browser=str(msg.get("browser", "")),
        supported_ops=list(msg.get("supported_ops", [])),
    )


def op_message(msg_id: int, op: str, params: dict[str, Any]) -> dict[str, Any]:
    """Build a per-op request envelope."""
    return {"type": "op", "id": msg_id, "op": op, "params": params}


# Wire error codes the extension can raise that map to a specific taxonomy code.
# Anything unrecognized degrades to OP_FAILED (an in-page failure).
_WIRE_CODES: dict[str, BrowserErrorCode] = {
    "target_lost": BrowserErrorCode.TARGET_LOST,
    "op_unsupported": BrowserErrorCode.OP_UNSUPPORTED,
}

# Per-code remediation for terminal errors surfaced from the extension.
_WIRE_REMEDIATION: dict[BrowserErrorCode, str] = {
    BrowserErrorCode.TARGET_LOST: (
        "re-run `use_target` to pin a tab, or it will re-open in owned mode"
    ),
}


def parse_result(msg: dict[str, Any]) -> Any:
    """Unwrap a result envelope.

    Returns the ``result`` payload on success; raises ``BrowserError`` on
    failure. A recognized wire ``error.code`` (e.g. ``target_lost``) maps to its
    taxonomy code with remediation; anything else is ``OP_FAILED``.
    """
    if msg.get("ok"):
        return msg.get("result")
    err = msg.get("error") or {}
    code = _WIRE_CODES.get(str(err.get("code", "")), BrowserErrorCode.OP_FAILED)
    raise BrowserError(
        code,
        str(err.get("message", "operation failed")),
        remediation=_WIRE_REMEDIATION.get(code),
    )

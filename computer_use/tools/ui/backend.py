# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""The structured (AT-SPI) tier's backend seam.

The four ui_* tools are thin over a StructuredBackend: they resolve the backend
for the running session, call it, and normalise the result. The backend is
optional at import and optional at runtime - a box with no accessibility bus
must still start and answer ``at_spi_unavailable`` rather than fail, which is the
lesson 0.6.6 shipped. Resolution therefore never raises: it returns None, and the
tools report the remedy.

Errors are named and absence is not one: an empty match is a successful read, not
a failure (conflating them teaches a model to retry a working tool). A stale ref
is ``element_gone`` and never degrades to clicking an old coordinate - re-acting
on where something used to be is the exact failure a structured tier removes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# Named error codes (the contract; the loop and the model read these, not prose).
AT_SPI_UNAVAILABLE = "at_spi_unavailable"
NO_TREE = "no_tree"
ELEMENT_GONE = "element_gone"
TIMEOUT = "timeout"
UNSUPPORTED_ACTION = "unsupported_action"

# The one-line remedy that ships with at_spi_unavailable. It points at the single
# cross-distro provisioner rather than a hand-typed package line, per the family's
# "easy to install is a contract" rule.
UNAVAILABLE_REMEDY = (
    "No accessibility bus reachable. Enable it and install the stack with "
    "`vadgr-cua install-deps` (at-spi2-core plus the toolkit bridges)."
)


@dataclass(frozen=True)
class Bounds:
    """Screen bounds of an element, in the same space the Tier 2 tools take.

    On Wayland the compositor withholds a client's global surface position, so a
    toolkit reports its window origin as (0, 0) and these bounds are
    window-relative rather than true screen pixels. That is why grounding a
    Tier 2 click on them is an X11-only capability: the resolver reports the
    coordinate trust so a caller never aims a pixel click at a Wayland origin.
    """

    x: int
    y: int
    w: int
    h: int

    def as_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}


@dataclass(frozen=True)
class Element:
    """One accessible element: an opaque, session-scoped ref plus what it is."""

    ref: str
    role: str
    name: str
    bounds: Bounds | None = None
    states: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "ref": self.ref,
            "role": self.role,
            "name": self.name,
            "bounds": self.bounds.as_dict() if self.bounds else None,
            "states": list(self.states),
        }


class StructuredError(Exception):
    """A named structured-tier failure, carrying its code and optional extras."""

    def __init__(self, code: str, message: str = "", **extra) -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message
        self.extra = extra

    def as_dict(self) -> dict:
        out = {"ok": False, "error": self.code}
        if self.message:
            out["message"] = self.message
        out.update(self.extra)
        return out


@runtime_checkable
class StructuredBackend(Protocol):
    """What a per-OS structured backend (AT-SPI, later UIA, AX) must provide.

    One provider per OS resolves behind this seam; the tools never branch on the
    OS or the distro. Each method may raise StructuredError with a named code.
    """

    def tree(self, depth: int) -> dict: ...
    def find(self, role: str, name: str) -> list[Element]: ...
    def act(self, ref: str, action: str, text: str) -> dict: ...
    def wait(self, role: str, name: str, timeout_ms: int) -> Element | None: ...
    def capability(self) -> dict: ...


def resolve_backend() -> StructuredBackend | None:
    """Build the structured backend for this session, or None if unavailable.

    Never raises. A missing optional dependency, no accessibility bus, or an OS
    with no structured tier yet all mean the same thing to a caller - "no
    structured tier here" - which the tools translate to at_spi_unavailable with
    its remedy. The import is deferred so the package loads on a box with no
    accessibility stack at all.
    """
    try:
        from computer_use.tools.ui.atspi import build_atspi_backend
    except Exception:
        return None
    try:
        return build_atspi_backend()
    except Exception:
        return None

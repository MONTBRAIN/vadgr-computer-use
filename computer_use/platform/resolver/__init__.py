# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""OS-agnostic backend selection.

Detects the session, holds the capture/input provider seams + registry, and
resolves a session to its highest-priority working backend. OS backend modules
register providers here; the resolver picks among them.
"""

from computer_use.platform.resolver.engine import BackendResolver, Skip
from computer_use.platform.resolver.providers import (
    BackendUnavailable,
    CaptureProvider,
    InputProvider,
)
from computer_use.platform.resolver.registry import (
    CAPTURE_PROVIDERS,
    INPUT_PROVIDERS,
    register_capture,
    register_input,
)
from computer_use.platform.resolver.session import SessionContext

__all__ = [
    "SessionContext",
    "CaptureProvider",
    "InputProvider",
    "BackendUnavailable",
    "CAPTURE_PROVIDERS",
    "INPUT_PROVIDERS",
    "register_capture",
    "register_input",
    "BackendResolver",
    "Skip",
]

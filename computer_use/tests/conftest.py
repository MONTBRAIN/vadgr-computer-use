"""Shared pytest fixtures.

The autouse fixture below blocks tests from opening the real session bus
during a Mutter RemoteDesktop interaction. Any test that needs that path
must patch _open_dbus_connection itself.
"""

import sys
from unittest.mock import patch

import pytest

# These modules import Linux-only bindings at module scope, so they fail at
# collection on Windows and macOS rather than skipping. A collection guard is
# the only thing that runs early enough: a module-level skipif still imports the
# module first. Without this the whole suite is uncollectable off Linux, and a
# suite that cannot be collected cannot enforce the four-platform rule.
collect_ignore = []
if sys.platform != "linux":
    collect_ignore += ["test_linux.py", "test_uinput.py"]


@pytest.fixture(autouse=True)
def _block_real_session_bus():
    """Stop a test from opening the real session bus.

    The guard is for Linux, where the bus exists. It is autouse, so it ran
    before every test on every platform, and on Windows and macOS the patch
    target does not exist: `computer_use.platform.linux` does not import there.
    That raised `AttributeError` in setup and made the whole suite uncollectable
    off Linux, which is how a `fcntl` import at module scope reached a release
    that supervises the Windows bridge. The four-platform rule needs a suite
    that runs on the four platforms.
    """
    try:
        import computer_use.platform.linux
    except (ImportError, AttributeError):
        # No session bus on this platform, so there is nothing to block.
        yield
        return

    blocker = patch(
        "computer_use.platform.linux._open_dbus_connection",
        side_effect=AssertionError(
            "test attempted to open the real session bus; "
            "patch computer_use.platform.linux._open_dbus_connection in the test"
        ),
    )
    blocker.start()
    try:
        yield
    finally:
        blocker.stop()

"""Shared pytest fixtures.

The autouse fixture below blocks tests from opening the real session bus
during a Mutter RemoteDesktop interaction. Any test that needs that path
must patch _open_dbus_connection itself.
"""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _block_real_session_bus():
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

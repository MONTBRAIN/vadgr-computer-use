import io
import threading
import time

import pytest

from computer_use.browser import broker_client
from computer_use.browser.bridge import BridgeStatus
from computer_use.browser.broker import LEASE_GRACE_SECONDS, BrowserBroker
from computer_use.browser.ownership import OwnershipConflict
from computer_use.browser.protocol import BrowserError


class ExtensionBridge:
    def __init__(self):
        self.calls = []
        self.windows = [
            {
                "window_id": 1,
                "focused": False,
                "owned": False,
                "tabs": [
                    {"window_id": 1, "tab_id": 10, "url": "https://one.test", "title": "one"},
                    {"window_id": 1, "tab_id": 11, "url": "https://two.test", "title": "two"},
                ],
            }
        ]
        self.current = None
        self.next_window = 2
        self.next_tab = 100

    def status(self):
        return BridgeStatus(True, ["chrome"], True, None, [])

    def send(self, op, /, **params):
        self.calls.append((op, dict(params)))
        if op == "profiles":
            return {
                "profiles": [
                    {
                        "profile_id": "profile-one",
                        "browser": "chrome",
                        "is_current": True,
                        "window_count": len(self.windows),
                        "tab_count": sum(len(window["tabs"]) for window in self.windows),
                        "sample_tab_titles": ["one"],
                    }
                ]
            }
        if op == "tabs" and params.get("op") == "list":
            return {"windows": self.windows}
        if op == "windows" and params.get("op") == "open":
            window_id = self.next_window
            self.next_window += 1
            tab_id = window_id * 10
            self.windows.append(
                {
                    "window_id": window_id,
                    "focused": False,
                    "owned": True,
                    "tabs": [{"window_id": window_id, "tab_id": tab_id, "url": "", "title": ""}],
                }
            )
            return {"window_id": window_id, "tab_id": tab_id, "created": True}
        if op == "tabs" and params.get("op") == "open":
            window_id = int(params["window_id"])
            window = next(item for item in self.windows if item["window_id"] == window_id)
            tab_id = self.next_tab
            self.next_tab += 1
            window["tabs"].append(
                {"window_id": window_id, "tab_id": tab_id, "url": "", "title": ""}
            )
            return {"window_id": window_id, "tab_id": tab_id, "created": True}
        if op == "use_target":
            self.current = (params.get("window_id"), params.get("tab_id"))
            return {"window_id": self.current[0], "tab_id": self.current[1], "created": False}
        if op == "read_text":
            target = params.get("_target")
            return {"value": f"target-{target['tab_id']}"}
        raise AssertionError((op, params))


def test_two_clients_get_distinct_owned_windows_and_exact_routing():
    extension = ExtensionBridge()
    broker = BrowserBroker(extension)
    one = broker.connect(None, None)
    two = broker.connect(None, None)
    target_one = broker.request(one, "use_target", {"mode": "owned"})
    target_two = broker.request(two, "use_target", {"mode": "owned"})
    assert target_one["window_id"] != target_two["window_id"]
    assert broker.request(one, "read_text", {})["value"] == f"target-{target_one['tab_id']}"
    assert broker.request(two, "read_text", {})["value"] == f"target-{target_two['tab_id']}"


def test_use_target_inline_profile_selects_before_ambiguity_check():
    class TwoProfileBridge(ExtensionBridge):
        def send(self, op, /, **params):
            if op == "profiles":
                self.calls.append((op, dict(params)))
                return {
                    "profiles": [
                        {"profile_id": "profile-one", "browser": "chrome"},
                        {"profile_id": "profile-two", "browser": "chrome"},
                    ]
                }
            return super().send(op, **params)

    extension = TwoProfileBridge()
    broker = BrowserBroker(extension)
    client = broker.connect(None, None)

    target = broker.request(
        client,
        "use_target",
        {"mode": "owned", "profile_id": "profile-two"},
    )

    assert client.profile_id == "profile-two"
    assert target["created"] is True
    assert any(
        operation == "windows" and params.get("profile_id") == "profile-two"
        for operation, params in extension.calls
    )


def test_listings_show_mine_other_and_unowned_without_hiding_targets():
    extension = ExtensionBridge()
    broker = BrowserBroker(extension)
    one = broker.connect(None, None)
    two = broker.connect(None, None)
    broker.request(one, "tabs", {"op": "claim", "tab_id": 10})
    first = broker.request(one, "tabs", {"op": "list"})
    second = broker.request(two, "tabs", {"op": "list"})
    one_tabs = first["windows"][0]["tabs"]
    two_tabs = second["windows"][0]["tabs"]
    assert [tab["ownership"]["state"] for tab in one_tabs] == ["mine", "unowned"]
    assert [tab["ownership"]["state"] for tab in two_tabs] == ["other", "unowned"]


def test_reconnect_secret_restores_client_state_inside_grace():
    broker = BrowserBroker(ExtensionBridge())
    original = broker.connect(None, None)
    broker.request(original, "tabs", {"op": "claim", "tab_id": 10})
    broker.disconnect(original)
    restored = broker.connect(original.client_id, original.secret)
    assert restored is original
    assert restored.tab_id == 10
    assert broker.request(restored, "read_text", {})["value"] == "target-10"


def test_new_broker_epoch_requires_explicit_reclaim_of_rediscovered_targets():
    broker = BrowserBroker(ExtensionBridge(), recovered_epoch=True)
    client = broker.connect(None, None)
    listed = broker.request(client, "tabs", {"op": "list"})
    assert listed["windows"][0]["ownership"]["state"] == "orphaned"
    assert all(tab["ownership"]["state"] == "orphaned" for tab in listed["windows"][0]["tabs"])
    claimed = broker.request(client, "windows", {"op": "claim", "window_id": 1})
    assert claimed["ownership"]["state"] == "mine"


def test_two_clients_racing_for_one_tab_have_one_atomic_winner():
    broker = BrowserBroker(ExtensionBridge())
    clients = [broker.connect(None, None), broker.connect(None, None)]
    start = threading.Barrier(2)
    outcomes = []

    def claim(client):
        start.wait()
        try:
            broker.request(client, "tabs", {"op": "claim", "tab_id": 10})
            outcomes.append("won")
        except OwnershipConflict:
            outcomes.append("lost")

    threads = [threading.Thread(target=claim, args=(client,)) for client in clients]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)
    assert sorted(outcomes) == ["lost", "won"]


def test_expired_disconnected_client_becomes_orphaned_and_reclaimable():
    broker = BrowserBroker(ExtensionBridge())
    old = broker.connect(None, None)
    broker.request(old, "tabs", {"op": "claim", "tab_id": 10})
    broker.disconnect(old)
    old.lost_at = time.monotonic() - LEASE_GRACE_SECONDS - 1
    broker.reap()
    survivor = broker.connect(None, None)
    listed = broker.request(survivor, "tabs", {"op": "list"})
    assert listed["windows"][0]["tabs"][0]["ownership"]["state"] == "orphaned"
    assert (
        broker.request(survivor, "tabs", {"op": "claim", "tab_id": 10})["ownership"]["state"]
        == "mine"
    )


def test_paced_request_does_not_hold_a_profile_wide_lock():
    entered = threading.Event()
    release = threading.Event()

    class ConcurrentBridge(ExtensionBridge):
        def send(self, op, /, **params):
            if op == "slow":
                entered.set()
                assert release.wait(2)
                return {"slow": True}
            return super().send(op, **params)

    broker = BrowserBroker(ConcurrentBridge())
    slow_client = broker.connect(None, None)
    fast_client = broker.connect(None, None)
    broker.request(slow_client, "tabs", {"op": "claim", "tab_id": 10})
    broker.request(fast_client, "tabs", {"op": "claim", "tab_id": 11})
    thread = threading.Thread(target=lambda: broker.request(slow_client, "slow", {}), daemon=True)
    thread.start()
    assert entered.wait(1)
    assert broker.request(fast_client, "read_text", {})["value"] == "target-11"
    release.set()
    thread.join(timeout=2)
    assert not thread.is_alive()


def test_wsl_uses_windows_stdio_proxy_for_a_native_windows_broker(monkeypatch):
    class Proxy:
        stdin = io.BytesIO()
        stdout = io.BytesIO()

        @staticmethod
        def poll():
            return None

        @staticmethod
        def terminate():
            return None

    proxy = Proxy()
    monkeypatch.setattr(broker_client, "_running_under_wsl", lambda: True)
    monkeypatch.setattr(
        "computer_use.browser.windows_broker.open_windows_proxy", lambda: proxy
    )
    transport, file = broker_client.BrokerClient._open_transport(
        {"host": "127.0.0.1", "platform": "win32"}
    )
    assert transport is proxy
    assert file._process is proxy


def test_broker_socket_transport_never_maps_loopback_to_the_wsl_gateway():
    assert (
        broker_client._endpoint_host({"host": "127.0.0.1", "platform": "win32"})
        == "127.0.0.1"
    )


def test_existing_foreign_target_is_rejected_before_extension_dispatch():
    extension = ExtensionBridge()
    broker = BrowserBroker(extension)
    owner = broker.connect(None, None)
    other = broker.connect(None, None)
    broker.request(owner, "tabs", {"op": "claim", "tab_id": 10})
    extension.calls.clear()

    with pytest.raises(OwnershipConflict):
        broker.request(other, "use_target", {"mode": "attach", "tab_id": 10})

    assert not any(op == "use_target" for op, _params in extension.calls)


def test_owned_mode_does_not_reuse_a_tab_only_lease():
    broker = BrowserBroker(ExtensionBridge())
    client = broker.connect(None, None)
    broker.request(client, "tabs", {"op": "claim", "tab_id": 10})

    target = broker.request(client, "use_target", {"mode": "owned"})

    assert target["window_id"] == 2
    assert target["ownership"]["scope"] == "window"


def test_releasing_a_noncurrent_window_preserves_current_target():
    broker = BrowserBroker(ExtensionBridge())
    client = broker.connect(None, None)
    first = broker.request(client, "windows", {"op": "open"})
    second = broker.request(client, "windows", {"op": "open"})

    broker.request(client, "windows", {"op": "release", "window_id": first["window_id"]})

    assert client.window_id == second["window_id"]
    assert client.tab_id == second["tab_id"]


def test_tab_open_uses_the_explicit_owned_window_not_the_current_window():
    extension = ExtensionBridge()
    broker = BrowserBroker(extension)
    client = broker.connect(None, None)
    first = broker.request(client, "windows", {"op": "open"})
    broker.request(client, "windows", {"op": "open"})

    opened = broker.request(
        client,
        "tabs",
        {"op": "open", "window_id": first["window_id"], "background": True},
    )

    assert opened["window_id"] == first["window_id"]
    assert opened["ownership"]["scope"] == "window"


def test_tab_claim_rejects_a_mismatched_window_id():
    broker = BrowserBroker(ExtensionBridge())
    client = broker.connect(None, None)

    with pytest.raises(BrowserError, match="not in window 99"):
        broker.request(client, "tabs", {"op": "claim", "tab_id": 10, "window_id": 99})

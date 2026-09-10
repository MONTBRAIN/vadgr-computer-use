"""Caller-specific status, with no transport or desktop started."""

import copy

import pytest

from computer_use.browser.bridge import BridgeStatus
from computer_use.browser.broker import BrowserBroker


class StatusBridge:
    def __init__(self, profiles, reason=None):
        self.value = BridgeStatus(bool(profiles), ["chrome"], True, reason, profiles)

    def status(self):
        return self.value

    def send(self, op, /, **params):
        assert op == "profiles" and params == {"op": "list"}
        return {"profiles": copy.deepcopy(self.value.profiles)}


def test_distinct_clients_status_matches_each_profile_list_without_global_mutation():
    profiles = [{"profile_id": pid, "is_current": False} for pid in ["p1", "p2"]]
    bridge = StatusBridge(profiles, "profile_ambiguous")
    broker = BrowserBroker(bridge)
    a, b = broker.connect(None, None), broker.connect(None, None)
    for client, pid in [(a, "p1"), (b, "p2")]:
        broker.request(client, "profiles", {"op": "use", "profile_id": pid})
    for _ in range(2):
        for client, pid in [(a, "p1"), (b, "p2")]:
            status = broker.request(client, "status", {})
            listing = broker.request(client, "profiles", {"op": "list"})
            assert status["profiles"] == listing["profiles"]
            assert status["reason"] is None
            assert [p["profile_id"] for p in status["profiles"] if p["is_current"]] == [pid]
    broker.request(a, "profiles", {"op": "use", "profile_id": "p2"})
    assert b.profile_id == "p2"
    assert bridge.value.profiles == profiles
    assert not any(p["is_current"] for p in profiles)
    assert bridge.value.reason == "profile_ambiguous"


@pytest.mark.parametrize("shared_current", [False, True])
def test_unselected_client_does_not_inherit_global_profile_selection(shared_current):
    bridge = StatusBridge([
        {"profile_id": "p1", "is_current": shared_current},
        {"profile_id": "p2", "is_current": False},
    ], None if shared_current else "profile_ambiguous")
    broker = BrowserBroker(bridge)
    client = broker.connect(None, None)
    status = broker.request(client, "status", {})
    assert status["reason"] == "profile_ambiguous"
    assert not any(p["is_current"] for p in status["profiles"])
    assert client.profile_id is None


@pytest.mark.parametrize("reason", ["not_set_up", "extension_disabled", "extension_missing", "waking"])
def test_no_profiles_preserves_setup_or_recovery_reason(reason):
    bridge = StatusBridge([], reason)
    broker = BrowserBroker(bridge)
    client = broker.connect(None, None)
    client.profile_id = "lost-profile"
    assert broker.request(client, "status", {})["reason"] == reason


@pytest.mark.parametrize("selected", [None, "p1", "unavailable"])
def test_single_profile_status_does_not_silently_retarget(selected):
    bridge = StatusBridge([{"profile_id": "p1", "is_current": True}])
    broker = BrowserBroker(bridge)
    client = broker.connect(None, None)
    client.profile_id = selected
    result = broker.request(client, "status", {})
    assert result["profiles"][0]["is_current"] is (selected == "p1")
    assert result["reason"] == ("profile_ambiguous" if selected == "unavailable" else None)
    assert client.profile_id == selected

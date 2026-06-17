# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""BrowserBridge contract: FakeBridge, status probe, session routing."""

import pytest

from computer_use.browser import bridge as B
from computer_use.browser.protocol import BrowserError, BrowserErrorCode


class TestFakeBridge:
    def test_scripted_result_passes_through(self):
        fake = B.FakeBridge(responses={"click": {"clicked": True}})
        assert fake.send("click", selector="#x") == {"clicked": True}

    def test_records_sent_ops(self):
        fake = B.FakeBridge(responses={"navigate": {"url": "u", "title": "t"}})
        fake.send("navigate", url="https://e.com")
        assert fake.calls == [("navigate", {"url": "https://e.com"})]

    def test_scripted_error_raised(self):
        err = BrowserError(BrowserErrorCode.OP_FAILED, "no element")
        fake = B.FakeBridge(responses={"click": err})
        with pytest.raises(BrowserError) as ei:
            fake.send("click", selector="#x")
        assert ei.value.code == BrowserErrorCode.OP_FAILED

    def test_unconnected_fake_raises_not_connected(self):
        fake = B.FakeBridge(connected=False)
        with pytest.raises(BrowserError) as ei:
            fake.send("click", selector="#x")
        assert ei.value.code == BrowserErrorCode.NOT_CONNECTED

    def test_callable_response_gets_params(self):
        fake = B.FakeBridge(
            responses={"read_text": lambda **p: p.get("selector", "BODY")}
        )
        assert fake.send("read_text", selector="#h") == "#h"


class TestBridgeStatus:
    def test_status_shape(self):
        fake = B.FakeBridge(
            connected=True,
            status=B.BridgeStatus(
                connected=True, browsers=["chrome"], setup=True, reason=None
            ),
        )
        st = fake.status()
        assert st.connected is True
        assert st.browsers == ["chrome"]
        assert st.setup is True
        assert st.reason is None

    def test_status_as_dict(self):
        st = B.BridgeStatus(connected=False, browsers=[], setup=False,
                            reason="not_set_up")
        assert st.as_dict() == {
            "connected": False, "browsers": [], "setup": False,
            "reason": "not_set_up",
        }


class TestManifestProbe:
    def test_returns_browsers_with_manifest_present(self, tmp_path, monkeypatch):
        # Lay down a manifest in a fake chrome dir, point the probe at it.
        chrome_dir = tmp_path / "google-chrome" / "NativeMessagingHosts"
        chrome_dir.mkdir(parents=True)
        (chrome_dir / "com.vadgr.cua.json").write_text("{}")
        paths = {"chrome": chrome_dir / "com.vadgr.cua.json",
                 "edge": tmp_path / "edge" / "com.vadgr.cua.json"}
        found = B.probe_manifests(paths)
        assert "chrome" in found
        assert "edge" not in found

    def test_none_present_returns_empty(self, tmp_path):
        paths = {"chrome": tmp_path / "nope.json"}
        assert B.probe_manifests(paths) == []

    def test_default_paths_are_per_os(self):
        # The Linux table from browser.md must be representable.
        paths = B.manifest_paths(platform="linux")
        assert "chrome" in paths
        assert str(paths["chrome"]).endswith(
            "google-chrome/NativeMessagingHosts/com.vadgr.cua.json"
        )


class TestNativeMessagingBridgeStatus:
    def test_not_set_up_when_no_manifest(self, monkeypatch):
        b = B.NativeMessagingBridge()
        monkeypatch.setattr(b, "_probe_setup", lambda: [])
        monkeypatch.setattr(b, "_active_session", lambda: None)
        st = b.status()
        assert st.connected is False
        assert st.setup is False
        assert st.reason == "not_set_up"

    def test_not_connected_when_manifest_but_no_session(self, monkeypatch):
        b = B.NativeMessagingBridge()
        monkeypatch.setattr(b, "_probe_setup", lambda: ["chrome"])
        monkeypatch.setattr(b, "_active_session", lambda: None)
        st = b.status()
        assert st.connected is False
        assert st.setup is True
        assert st.reason == "not_connected"

    def test_connected_when_session_present(self, monkeypatch):
        sess = B.BrowserSession(browser="chrome", ext_version="0.4.0",
                                supported_ops=list(B_SUPPORTED()))
        b = B.NativeMessagingBridge()
        monkeypatch.setattr(b, "_probe_setup", lambda: ["chrome"])
        monkeypatch.setattr(b, "_active_session", lambda: sess)
        st = b.status()
        assert st.connected is True
        assert st.reason is None


class TestNativeMessagingBridgeSend:
    def test_send_without_session_raises_not_connected(self, monkeypatch):
        b = B.NativeMessagingBridge()
        monkeypatch.setattr(b, "_probe_setup", lambda: ["chrome"])
        monkeypatch.setattr(b, "_active_session", lambda: None)
        with pytest.raises(BrowserError) as ei:
            b.send("click", selector="#x")
        assert ei.value.code == BrowserErrorCode.NOT_CONNECTED

    def test_send_without_setup_raises_not_set_up(self, monkeypatch):
        b = B.NativeMessagingBridge()
        monkeypatch.setattr(b, "_probe_setup", lambda: [])
        monkeypatch.setattr(b, "_active_session", lambda: None)
        with pytest.raises(BrowserError) as ei:
            b.send("click", selector="#x")
        assert ei.value.code == BrowserErrorCode.NOT_SET_UP

    def test_op_unsupported_when_session_too_old(self, monkeypatch):
        sess = B.BrowserSession(browser="chrome", ext_version="0.3.0",
                                supported_ops=["navigate"])  # no 'click'
        b = B.NativeMessagingBridge()
        monkeypatch.setattr(b, "_probe_setup", lambda: ["chrome"])
        monkeypatch.setattr(b, "_active_session", lambda: sess)
        with pytest.raises(BrowserError) as ei:
            b.send("click", selector="#x")
        assert ei.value.code == BrowserErrorCode.OP_UNSUPPORTED

    def test_send_routes_to_active_session(self, monkeypatch):
        sent = {}

        class _Sess(B.BrowserSession):
            def request(self, op, params):
                sent["op"] = op
                sent["params"] = params
                return {"clicked": True}

        sess = _Sess(browser="chrome", ext_version="0.4.0",
                     supported_ops=["click"])
        b = B.NativeMessagingBridge()
        monkeypatch.setattr(b, "_probe_setup", lambda: ["chrome"])
        monkeypatch.setattr(b, "_active_session", lambda: sess)
        out = b.send("click", selector="#submit")
        assert out == {"clicked": True}
        assert sent == {"op": "click", "params": {"selector": "#submit"}}


def B_SUPPORTED():
    from computer_use.browser.protocol import SUPPORTED_OPS
    return SUPPORTED_OPS

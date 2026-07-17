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
            "reason": "not_set_up", "profiles": [],
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


class TestSelfRegisterWiring:
    def test_probe_self_registers_once(self, monkeypatch):
        import computer_use.setup.extension_setup as S

        calls: list[int] = []
        monkeypatch.setattr(S, "ensure_registered", lambda: calls.append(1))
        monkeypatch.setattr(B, "manifest_paths", lambda *a, **k: {})
        monkeypatch.setattr(B, "probe_manifests", lambda paths: [])
        b = B.NativeMessagingBridge()  # auto_register default True
        b._probe_setup()
        b._probe_setup()
        assert calls == [1]  # self-registered exactly once

    def test_auto_register_false_skips(self, monkeypatch):
        import computer_use.setup.extension_setup as S

        calls: list[int] = []
        monkeypatch.setattr(S, "ensure_registered", lambda: calls.append(1))
        monkeypatch.setattr(B, "manifest_paths", lambda *a, **k: {})
        monkeypatch.setattr(B, "probe_manifests", lambda paths: [])
        b = B.NativeMessagingBridge(auto_register=False)
        b._probe_setup()
        assert calls == []


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


def _profile_session(profile_id, *, browser="chrome", titles=None, ops=None):
    """A registry record session carrying a profile identity + recognition context."""
    sess = B.BrowserSession(
        browser=browser,
        ext_version="0.6.1",
        supported_ops=list(ops if ops is not None else ["navigate", "click", "profiles"]),
        profile_id=profile_id,
        profile_context={
            "window_count": 1,
            "tab_count": len(titles or []),
            "sample_tab_titles": list(titles or []),
        },
    )
    return sess


class _RoutedSession(B.BrowserSession):
    """A session that records the op routed to it (so we can prove `current`)."""

    def request(self, op, params):
        self.last = (op, params)
        return {"routed_to": self.profile_id, "op": op}


class TestMultiConnectionRegistry:
    def test_keeps_multiple_connections_keyed_by_browser_and_profile(self):
        b = B.NativeMessagingBridge(auto_register=False)
        b.register_session(_profile_session("work"))
        b.register_session(_profile_session("home"))
        # Both connections are retained (not a single-listener bond).
        assert len(b._sessions) == 2
        assert {s.profile_id for s in b._sessions.values()} == {"work", "home"}

    def test_missing_profile_id_registers_as_default(self):
        b = B.NativeMessagingBridge(auto_register=False)
        # A 0.6.0 extension: BrowserSession with no profile_id.
        b.register_session(
            B.BrowserSession(browser="chrome", ext_version="0.6.0",
                             supported_ops=["navigate"])
        )
        assert ("chrome", "default") in b._sessions

    def test_single_connection_auto_uses_it(self, monkeypatch):
        b = B.NativeMessagingBridge(auto_register=False)
        monkeypatch.delenv("CUA_BROWSER_PROFILE", raising=False)
        sess = _RoutedSession(browser="chrome", ext_version="0.6.1",
                              supported_ops=["navigate"], profile_id="only")
        b.register_session(sess)
        out = b.send("navigate", url="https://e.com")
        assert out == {"routed_to": "only", "op": "navigate"}

    def test_two_connections_none_selected_raises_profile_ambiguous(self, monkeypatch):
        b = B.NativeMessagingBridge(auto_register=False)
        monkeypatch.delenv("CUA_BROWSER_PROFILE", raising=False)
        b.register_session(_profile_session("work", titles=["Work Gmail"]))
        b.register_session(_profile_session("home", titles=["Personal Gmail"]))
        with pytest.raises(BrowserError) as ei:
            b.send("navigate", url="https://e.com")
        assert ei.value.code is BrowserErrorCode.PROFILE_AMBIGUOUS
        # The terminal error lists the choices (never a silent guess).
        assert "work" in str(ei.value) and "home" in str(ei.value)
        assert ei.value.retryable is False

    def test_profiles_list_refreshes_stale_context_from_the_live_extension(self):
        # e2e finding: the hello context is a snapshot from connect time, so a
        # window opened/closed afterward left profiles(list) reporting stale counts
        # (a closed profile still showed its old window + tabs). profiles(list) must
        # re-query each extension for a LIVE buildProfileContext().
        b = B.NativeMessagingBridge(auto_register=False)

        class _LiveSession(B.BrowserSession):
            def request(self, op, params):
                assert (op, params) == ("profiles", {"op": "list"})
                # the extension reports the CURRENT state: the window was closed -> 0
                return {"profiles": [{"profile_id": self.profile_id,
                                      "browser": "chrome", "window_count": 0,
                                      "tab_count": 0, "sample_tab_titles": []}]}

        sess = _LiveSession(
            browser="chrome", ext_version="0.6.1",
            supported_ops=["navigate", "profiles"], profile_id="work",
            profile_context={"window_count": 1, "tab_count": 4,
                             "sample_tab_titles": ["Outlier", "Top topics"]},
        )
        b.register_session(sess)
        entry = b._profiles_op({"op": "list"})["profiles"][0]
        assert entry["window_count"] == 0 and entry["tab_count"] == 0
        assert entry["sample_tab_titles"] == []
        # the cached context was refreshed in place, not just the returned view
        assert sess.profile_context["window_count"] == 0

    def test_profiles_list_keeps_cached_context_when_a_session_is_unreachable(self):
        b = B.NativeMessagingBridge(auto_register=False)

        class _DeadSession(B.BrowserSession):
            def request(self, op, params):
                raise RuntimeError("unreachable")

        sess = _DeadSession(
            browser="chrome", ext_version="0.6.1",
            supported_ops=["navigate", "profiles"], profile_id="work",
            profile_context={"window_count": 2, "tab_count": 5,
                             "sample_tab_titles": ["A"]},
        )
        b.register_session(sess)
        entry = b._profiles_op({"op": "list"})["profiles"][0]
        assert entry["window_count"] == 2  # last-known kept; the list never fails

    def test_explicit_selection_routes_current(self, monkeypatch):
        b = B.NativeMessagingBridge(auto_register=False)
        monkeypatch.delenv("CUA_BROWSER_PROFILE", raising=False)
        work = _RoutedSession(browser="chrome", ext_version="0.6.1",
                              supported_ops=["navigate", "profiles"],
                              profile_id="work-uuid")
        home = _RoutedSession(browser="chrome", ext_version="0.6.1",
                              supported_ops=["navigate", "profiles"],
                              profile_id="home-uuid")
        b.register_session(work)
        b.register_session(home)
        b.send("profiles", op="use", profile_id="work-uuid")
        out = b.send("navigate", url="https://e.com")
        assert out["routed_to"] == "work-uuid"

    def test_env_pin_selects_by_profile_id_prefix(self, monkeypatch):
        b = B.NativeMessagingBridge(auto_register=False)
        monkeypatch.setenv("CUA_BROWSER_PROFILE", "home")
        b.register_session(_RoutedSession(
            browser="chrome", ext_version="0.6.1", supported_ops=["navigate"],
            profile_id="work-9f2c"))
        b.register_session(_RoutedSession(
            browser="chrome", ext_version="0.6.1", supported_ops=["navigate"],
            profile_id="home-1a2b"))
        out = b.send("navigate", url="https://e.com")
        assert out["routed_to"] == "home-1a2b"

    def test_env_pin_selects_by_sample_tab_title_substring(self, monkeypatch):
        b = B.NativeMessagingBridge(auto_register=False)
        monkeypatch.setenv("CUA_BROWSER_PROFILE", "figma")
        work = _RoutedSession(browser="chrome", ext_version="0.6.1",
                              supported_ops=["navigate"], profile_id="w",
                              profile_context={"sample_tab_titles": ["Work Gmail", "Figma"]})
        home = _RoutedSession(browser="chrome", ext_version="0.6.1",
                              supported_ops=["navigate"], profile_id="h",
                              profile_context={"sample_tab_titles": ["Personal Gmail"]})
        b.register_session(work)
        b.register_session(home)
        out = b.send("navigate", url="https://e.com")
        assert out["routed_to"] == "w"

    def test_dropped_current_makes_next_op_loud(self, monkeypatch):
        b = B.NativeMessagingBridge(auto_register=False)
        monkeypatch.delenv("CUA_BROWSER_PROFILE", raising=False)
        work = _RoutedSession(browser="chrome", ext_version="0.6.1",
                              supported_ops=["navigate", "profiles"], profile_id="work")
        home = _RoutedSession(browser="chrome", ext_version="0.6.1",
                              supported_ops=["navigate", "profiles"], profile_id="home")
        b.register_session(work)
        b.register_session(home)
        b.send("profiles", op="use", profile_id="work")
        b.unregister_session(work)  # the current connection drops
        with pytest.raises(BrowserError) as ei:
            b.send("navigate", url="https://e.com")
        assert ei.value.code is BrowserErrorCode.PROFILE_AMBIGUOUS


class TestProfilesOp:
    def test_list_enumerates_every_connected_profile(self, monkeypatch):
        b = B.NativeMessagingBridge(auto_register=False)
        monkeypatch.delenv("CUA_BROWSER_PROFILE", raising=False)
        b.register_session(_profile_session("work-uuid", titles=["Work Gmail", "Figma"]))
        b.register_session(_profile_session("home-uuid", titles=["Personal Gmail"]))
        out = b.send("profiles", op="list")
        ids = {p["profile_id"] for p in out["profiles"]}
        assert ids == {"work-uuid", "home-uuid"}
        work = next(p for p in out["profiles"] if p["profile_id"] == "work-uuid")
        assert work["sample_tab_titles"] == ["Work Gmail", "Figma"]
        assert work["browser"] == "chrome"

    def test_use_selects_and_reports_is_current(self, monkeypatch):
        b = B.NativeMessagingBridge(auto_register=False)
        monkeypatch.delenv("CUA_BROWSER_PROFILE", raising=False)
        b.register_session(_profile_session("work-uuid"))
        b.register_session(_profile_session("home-uuid"))
        out = b.send("profiles", op="use", profile_id="work-uuid")
        assert out == {"profile_id": "work-uuid", "browser": "chrome",
                       "is_current": True}
        # And the list now marks it current.
        listed = b.send("profiles", op="list")
        current = [p for p in listed["profiles"] if p["is_current"]]
        assert len(current) == 1 and current[0]["profile_id"] == "work-uuid"

    def test_use_unknown_profile_is_loud(self, monkeypatch):
        b = B.NativeMessagingBridge(auto_register=False)
        monkeypatch.delenv("CUA_BROWSER_PROFILE", raising=False)
        b.register_session(_profile_session("work-uuid"))
        b.register_session(_profile_session("home-uuid"))
        with pytest.raises(BrowserError) as ei:
            b.send("profiles", op="use", profile_id="nope")
        assert ei.value.code is BrowserErrorCode.PROFILE_AMBIGUOUS

    def test_profiles_op_unsupported_on_old_extension(self, monkeypatch):
        # A single, old (pre-0.6.1) extension: `profiles` not advertised.
        b = B.NativeMessagingBridge(auto_register=False)
        monkeypatch.delenv("CUA_BROWSER_PROFILE", raising=False)
        b.register_session(
            B.BrowserSession(browser="chrome", ext_version="0.6.0",
                             supported_ops=["navigate", "click"], profile_id="default")
        )
        with pytest.raises(BrowserError) as ei:
            b.send("profiles", op="list")
        assert ei.value.code is BrowserErrorCode.OP_UNSUPPORTED

    def test_use_target_profile_id_selects_before_routing(self, monkeypatch):
        b = B.NativeMessagingBridge(auto_register=False)
        monkeypatch.delenv("CUA_BROWSER_PROFILE", raising=False)
        work = _RoutedSession(browser="chrome", ext_version="0.6.1",
                              supported_ops=["use_target"], profile_id="work")
        home = _RoutedSession(browser="chrome", ext_version="0.6.1",
                              supported_ops=["use_target"], profile_id="home")
        b.register_session(work)
        b.register_session(home)
        out = b.send("use_target", profile_id="home", window_id=None, tab_id=None,
                     mode="owned")
        assert out["routed_to"] == "home"
        # profile_id is consumed by cua (selection), never forwarded to the extension.
        assert "profile_id" not in home.last[1]


class TestStatusProfiles:
    def test_status_grows_a_profiles_array(self, monkeypatch):
        b = B.NativeMessagingBridge(auto_register=False)
        monkeypatch.setattr(b, "_probe_setup", lambda: ["chrome"])
        monkeypatch.delenv("CUA_BROWSER_PROFILE", raising=False)
        b.register_session(_profile_session("work-uuid", titles=["Work Gmail"]))
        b.register_session(_profile_session("home-uuid", titles=["Personal Gmail"]))
        st = b.status()
        assert st.connected is True
        ids = {p["profile_id"] for p in st.as_dict()["profiles"]}
        assert ids == {"work-uuid", "home-uuid"}


class TestDetectWindowsUser:
    def test_probe_does_not_inherit_stdin(self, monkeypatch):
        # Issue #18: the cmd.exe interop probe must not inherit fd 0 (the MCP
        # server's JSON-RPC stdin), or `initialize` hangs. It must pass
        # stdin=subprocess.DEVNULL.
        import subprocess

        monkeypatch.delenv("WIN_USER", raising=False)
        monkeypatch.delenv("USERNAME", raising=False)
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs

            class _R:
                stdout = "alice\n"

            return _R()

        monkeypatch.setattr(subprocess, "run", fake_run)
        name = B._detect_windows_user()
        assert name == "alice"
        assert captured["kwargs"].get("stdin") is subprocess.DEVNULL

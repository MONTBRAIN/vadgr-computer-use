# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""The browser / browser_eval MCP tools against a FakeBridge (no browser)."""

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from computer_use.browser import tool as T
from computer_use.browser.bridge import BridgeStatus, FakeBridge
from computer_use.browser.protocol import BrowserError, BrowserErrorCode


class TestOpRouting:
    def test_navigate_maps_params(self):
        fake = FakeBridge(responses={"navigate": {"url": "u", "title": "t"}})
        out = T.browser(op="navigate", bridge=fake, url="https://e.com")
        assert out == {"url": "u", "title": "t"}
        assert fake.calls == [("navigate", {"url": "https://e.com", "wait": "load"})]

    def test_click_passes_selector(self):
        fake = FakeBridge(responses={"click": {"clicked": True}})
        out = T.browser(op="click", bridge=fake, selector="#submit")
        assert out == {"clicked": True}
        assert fake.calls[0][0] == "click"
        assert fake.calls[0][1]["selector"] == "#submit"

    def test_fill_forwards_text_and_flags(self):
        fake = FakeBridge(responses={"fill": {"typed": 5}})
        out = T.browser(op="fill", bridge=fake, selector="#n", text="hello",
                        submit=True)
        assert out == {"typed": 5}
        params = fake.calls[0][1]
        assert params["selector"] == "#n"
        assert params["text"] == "hello"
        assert params["submit"] is True

    def test_query_defaults(self):
        fake = FakeBridge(responses={"query": []})
        T.browser(op="query", bridge=fake, selector=".x")
        params = fake.calls[0][1]
        assert params["by"] == "css"
        assert params["all"] is False

    def test_press_forwards_key(self):
        fake = FakeBridge(responses={"press": {"pressed": "Enter"}})
        out = T.browser(op="press", bridge=fake, key="Enter", selector="#x")
        assert out == {"pressed": "Enter"}
        params = fake.calls[0][1]
        assert params["key"] == "Enter"
        assert params["selector"] == "#x"

    def test_accessibility_tree_op(self):
        fake = FakeBridge(responses={"accessibility_tree": {"nodes": []}})
        out = T.browser(op="accessibility_tree", bridge=fake)
        assert out == {"nodes": []}
        assert fake.calls[0][0] == "accessibility_tree"

    def test_unknown_op_raises_tool_error(self):
        fake = FakeBridge()
        with pytest.raises(ToolError):
            T.browser(op="teleport", bridge=fake)

    def test_eval_is_not_a_browser_op(self):
        # `eval` is the separate browser_eval tool, not reachable via browser().
        fake = FakeBridge()
        with pytest.raises(ToolError):
            T.browser(op="eval", bridge=fake, expression="1+1")


class TestStatusOp:
    def test_status_returns_dict(self):
        st = BridgeStatus(connected=True, browsers=["chrome"], setup=True,
                          reason=None)
        fake = FakeBridge(status=st)
        out = T.browser(op="status", bridge=fake)
        assert out == {"connected": True, "browsers": ["chrome"],
                       "setup": True, "reason": None}

    def test_status_never_touches_a_page(self):
        fake = FakeBridge(connected=False)
        out = T.browser(op="status", bridge=fake)
        assert out["connected"] is False
        # status must not have gone through send()
        assert fake.calls == []


class TestErrorMapping:
    def test_browser_error_becomes_tool_error_with_remediation(self):
        err = BrowserError(
            BrowserErrorCode.NOT_CONNECTED, "no session",
            remediation="open Chrome", fallback="use screenshot fallback",
        )
        fake = FakeBridge(responses={"click": err})
        with pytest.raises(ToolError) as ei:
            T.browser(op="click", bridge=fake, selector="#x")
        text = str(ei.value)
        assert "no session" in text
        assert "open Chrome" in text
        assert "use screenshot fallback" in text

    def test_op_failed_carries_page_reason(self):
        err = BrowserError(BrowserErrorCode.OP_FAILED, "no element matches #x")
        fake = FakeBridge(responses={"click": err})
        with pytest.raises(ToolError) as ei:
            T.browser(op="click", bridge=fake, selector="#x")
        assert "no element matches #x" in str(ei.value)


class TestTargetingOps:
    def test_use_target_owned_default(self):
        fake = FakeBridge(
            responses={"use_target": {"browser": "chrome", "window_id": 42,
                                      "tab_id": 137, "created": True}}
        )
        out = T.browser(op="use_target", bridge=fake)
        assert out["created"] is True
        params = fake.calls[0][1]
        assert params == {"window_id": None, "tab_id": None, "mode": "owned"}

    def test_use_target_by_id(self):
        fake = FakeBridge(responses={"use_target": {"window_id": 3, "tab_id": 9}})
        T.browser(op="use_target", bridge=fake, window_id=3, tab_id=9,
                  mode="attach")
        params = fake.calls[0][1]
        assert params["window_id"] == 3
        assert params["tab_id"] == 9
        assert params["mode"] == "attach"

    def test_target_lost_surfaces_as_terminal_tool_error(self):
        # A closed pinned tab/window is terminal + non-retryable, with remediation.
        err = BrowserError(
            BrowserErrorCode.TARGET_LOST,
            "the pinned tab/window was closed",
            remediation="re-run use_target",
        )
        assert err.retryable is False
        fake = FakeBridge(responses={"hover": err})
        with pytest.raises(ToolError) as ei:
            T.browser(op="hover", bridge=fake, selector=".menu")
        assert "closed" in str(ei.value)


class TestInteractionOps:
    def test_hover_forwards_reveals(self):
        fake = FakeBridge(responses={"hover": {"hovered": True, "revealed": True}})
        out = T.browser(op="hover", bridge=fake, selector=".menu",
                        reveals=".submenu")
        assert out == {"hovered": True, "revealed": True}
        params = fake.calls[0][1]
        assert params["selector"] == ".menu"
        assert params["reveals"] == ".submenu"

    def test_dialog_arms_by_default(self):
        fake = FakeBridge(responses={"dialog": {"armed": True}})
        T.browser(op="dialog", bridge=fake, action="accept", text="hi")
        params = fake.calls[0][1]
        assert params == {"action": "accept", "text": "hi", "arm": True}

    def test_element_state_forwards(self):
        fake = FakeBridge(responses={"element_state": {"visible": True}})
        out = T.browser(op="element_state", bridge=fake, selector="#x")
        assert out == {"visible": True}
        assert fake.calls[0][0] == "element_state"

    def test_focus_and_blur(self):
        fake = FakeBridge(responses={"focus": {"focused": True},
                                     "blur": {"focused": False}})
        assert T.browser(op="focus", bridge=fake, selector="#x")["focused"] is True
        assert T.browser(op="blur", bridge=fake, selector="#x")["focused"] is False

    def test_clear_self_verifies(self):
        fake = FakeBridge(responses={"clear": {"value": "", "ok": True}})
        out = T.browser(op="clear", bridge=fake, selector="#x")
        assert out == {"value": "", "ok": True}

    def test_get_value_forwards(self):
        fake = FakeBridge(responses={"get_value": {"value": "hello"}})
        out = T.browser(op="get_value", bridge=fake, selector="#x")
        assert out == {"value": "hello"}

    def test_snapshot_paginates(self):
        fake = FakeBridge(
            responses={"snapshot": {"nodes": [], "next_cursor": 50}}
        )
        T.browser(op="snapshot", bridge=fake, roles=["button"], limit=50)
        params = fake.calls[0][1]
        assert params["roles"] == ["button"]
        assert params["limit"] == 50

    def test_query_forwards_limit_and_cursor(self):
        fake = FakeBridge(responses={"query": {"nodes": []}})
        T.browser(op="query", bridge=fake, selector=".x", limit=25, cursor=25)
        params = fake.calls[0][1]
        assert params["limit"] == 25
        assert params["cursor"] == 25


class TestUploadPathTranslation:
    def test_native_paths_pass_through(self, monkeypatch):
        monkeypatch.setattr(T, "_upload_platform", lambda: "linux")
        fake = FakeBridge(responses={"upload": {"uploaded": 1, "ok": True}})
        T.browser(op="upload", bridge=fake, selector="input",
                  files=["/home/u/cv.pdf"])
        assert fake.calls[0][1]["files"] == ["/home/u/cv.pdf"]

    def test_wsl_paths_rewritten_to_windows_before_the_wire(self, monkeypatch):
        # The WSL boundary: Windows Chrome cannot read a cua-side WSL path.
        monkeypatch.setattr(T, "_upload_platform", lambda: "wsl")
        monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
        fake = FakeBridge(responses={"upload": {"uploaded": 2, "ok": True}})
        T.browser(op="upload", bridge=fake, selector="input",
                  files=["/mnt/c/Users/me/cv.pdf", "/home/u/photo.png"])
        assert fake.calls[0][1]["files"] == [
            "C:\\Users\\me\\cv.pdf",
            "\\\\wsl.localhost\\Ubuntu\\home\\u\\photo.png",
        ]


class TestScreenshotIsAPixelTool:
    def test_browser_screenshot_op_redirects_to_pixel_tool(self):
        fake = FakeBridge()
        with pytest.raises(ToolError) as ei:
            T.browser(op="screenshot", bridge=fake)
        assert "pixel" in str(ei.value).lower()
        # It must not have gone through the bridge.
        assert fake.calls == []


class TestBrowserEval:
    def test_eval_routes_to_eval_op(self):
        fake = FakeBridge(responses={"eval": {"value": 2}})
        out = T.browser_eval(expression="1+1", bridge=fake)
        assert out == {"value": 2}
        assert fake.calls == [("eval", {"expression": "1+1"})]

    def test_eval_error_maps_to_tool_error(self):
        err = BrowserError(BrowserErrorCode.OP_FAILED, "ReferenceError: foo")
        fake = FakeBridge(responses={"eval": err})
        with pytest.raises(ToolError) as ei:
            T.browser_eval(expression="foo", bridge=fake)
        assert "ReferenceError" in str(ei.value)

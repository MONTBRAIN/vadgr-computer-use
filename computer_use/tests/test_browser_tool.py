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

"""Regression checks for the 0.7.6 browser E2E fixture."""

import importlib.util
from pathlib import Path

PAGE = Path(__file__).resolve().parents[2] / "E2E" / "0.7.6" / "harness" / "page.html"
LIFECYCLE = PAGE.with_name("lifecycle_control.py")
FOCUS_WINDOW = PAGE.with_name("focus_window.ps1")


def _lifecycle():
    spec = importlib.util.spec_from_file_location("e2e_076_lifecycle", LIFECYCLE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_overlay_geometry_applies_inside_shadow_roots():
    source = PAGE.read_text(encoding="utf-8")

    assert 'item.style.cssText = "position:absolute;inset:.5rem;z-index:20;' in source
    assert 'overlay(shadow.querySelector(".slot"))' in source


def test_extension_toggle_polling_does_not_require_a_visible_frame(monkeypatch):
    monkeypatch.syspath_prepend(str(PAGE.parent))
    spec = importlib.util.spec_from_file_location("e2e_toggle", PAGE.with_name("toggle_extension.py"))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class HiddenPage:
        closed = False

        def create(self, url):
            assert url == "chrome://extensions/"
            return {"id": "isolated-management-page"}

        def evaluate(self, target, expression):
            assert "requestAnimationFrame" not in expression
            assert "setTimeout(probe, 50)" in expression
            assert "setTimeout(verify, 50)" in expression
            return {"enabled": False}

        def json(self, path):
            assert path == "/json/version"
            return {}

        def command(self, browser, method, params):
            assert method == "Target.closeTarget"
            assert params == {"targetId": "isolated-management-page"}
            self.closed = True
            return {"success": True}

    page = HiddenPage()
    assert module.toggle(page, False) == {
        "enabled": False, "temporary_extensions_page_closed": True,
    }
    assert page.closed


def test_lifecycle_row_matches_only_the_exact_url():
    expression = _lifecycle().row_expression(
        "http://127.0.0.1/page.html?case=exact",
        "return {ok: true};",
    )

    assert "item.querySelector('.tab-url-cell')" in expression
    assert '=== "http://127.0.0.1/page.html?case=exact"' in expression
    assert "await tab.updateTable_()" in expression
    assert "await tab.updateComplete" in expression
    assert "Page.bringToFront" not in LIFECYCLE.read_text(encoding="utf-8")
    assert "Target.activateTarget" not in LIFECYCLE.read_text(encoding="utf-8")


def test_lifecycle_row_waits_for_discard_table_population():
    lifecycle = _lifecycle()

    class DelayedTable:
        attempts = 0

        @staticmethod
        def targets():
            return [
                {
                    "type": "page",
                    "url": "chrome://discards/",
                    "title": "Discards",
                }
            ]

        def evaluate(self, target, expression):
            del target, expression
            self.attempts += 1
            if self.attempts == 1:
                raise lifecycle.LifecycleSetupError(
                    "Error: exact lifecycle target row is unavailable"
                )
            return {"url": "http://127.0.0.1/page.html", "lifecycle": "hidden"}

    devtools = DelayedTable()
    result = lifecycle.lifecycle_row(devtools, "http://127.0.0.1/page.html", timeout=1)

    assert devtools.attempts == 2
    assert result["lifecycle"] == "hidden"


def test_prepare_waits_for_internal_debugging_page_render():
    lifecycle = _lifecycle()

    class DelayedChromeUrls:
        attempts = 0

        @staticmethod
        def targets():
            return [
                {
                    "id": "chrome-urls",
                    "type": "page",
                    "url": "chrome://chrome-urls/",
                },
                {
                    "id": "discards",
                    "type": "page",
                    "url": "chrome://discards/",
                    "title": "Discards",
                },
            ]

        def evaluate(self, target, expression):
            del target, expression
            self.attempts += 1
            if self.attempts == 1:
                raise lifecycle.LifecycleSetupError(
                    "Error: internal debugging page enable control is unavailable"
                )
            return {"enabled": True, "changed": True}

    devtools = DelayedChromeUrls()
    result = lifecycle.prepare_internal_pages(devtools)

    assert devtools.attempts == 2
    assert result == {
        "debug_pages": {"enabled": True, "changed": True},
        "discards_target_id": "discards",
    }


def test_wsl_focus_helper_is_exact_and_refuses_minimized_windows():
    source = FOCUS_WINDOW.read_text(encoding="utf-8")

    assert "ExactVisibleTitle($ExactTitle)" in source
    assert 'title + " - Google Chrome for Testing"' in source
    assert "$matches.Count -ne 1" in source
    assert "IsIconic($target)" in source
    assert "GetForegroundWindow() -ne $target" in source
    assert "ShowWindow" not in source

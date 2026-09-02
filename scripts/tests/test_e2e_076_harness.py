"""Regression checks for the 0.7.6 browser E2E fixture."""

import importlib.util
from pathlib import Path

PAGE = Path(__file__).resolve().parents[2] / "E2E" / "0.7.6" / "harness" / "page.html"
LIFECYCLE = PAGE.with_name("lifecycle_control.py")


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

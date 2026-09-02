"""Regression checks for the 0.7.6 browser E2E fixture."""

from pathlib import Path

PAGE = Path(__file__).resolve().parents[2] / "E2E" / "0.7.6" / "harness" / "page.html"


def test_overlay_geometry_applies_inside_shadow_roots():
    source = PAGE.read_text(encoding="utf-8")

    assert 'item.style.cssText = "position:absolute;inset:.5rem;z-index:20;' in source
    assert 'overlay(shadow.querySelector(".slot"))' in source

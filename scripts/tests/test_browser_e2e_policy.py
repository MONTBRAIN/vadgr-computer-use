from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _text(path):
    return " ".join((ROOT / path).read_text(encoding="utf-8").split())


def test_browser_e2e_policy_never_uses_owner_browser_or_owner_launch():
    policy = _text("AGENTS.md")
    template = _text("E2E/TEMPLATE.md")
    runbook = _text("E2E/0.7.9/e2e.md")

    for text in (policy, template, runbook):
        assert "Chrome for Testing" in text
        assert "Do not ask the owner to launch" in text
        assert "Never" in text and "owner" in text and "browser" in text


def test_browser_e2e_policy_keeps_dom_and_native_accessibility_separate():
    policy = _text("AGENTS.md")
    template = _text("E2E/TEMPLATE.md")
    runbook = _text("E2E/0.7.9/e2e.md")

    for text in (policy, template, runbook):
        assert "DOM" in text
        assert "UIA" in text
        assert "replace Chrome for Testing" in text

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _text(path):
    return " ".join((ROOT / path).read_text(encoding="utf-8").split())


def _matrix_row(path, part):
    prefix = f"| Part {part} |"
    line = next(
        line
        for line in (ROOT / path).read_text(encoding="utf-8").splitlines()
        if line.startswith(prefix)
    )
    return [column.strip() for column in line.strip("|").split("|")]


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


def test_current_runbook_attributes_only_unsigned_windows_results_to_windows():
    runbook = _text("E2E/0.7.9/e2e.md")
    p06 = _matrix_row("E2E/0.7.9/e2e.md", "P06")
    p08 = _matrix_row("E2E/0.7.9/e2e.md", "P08")
    assert p06[2] == (
        "pass: nine unsigned x86_64 cases in each of three passes at 14cb515; "
        "signed/adoption and ARM64 remain owed"
    )
    assert p08[2] == (
        "pass: four unsigned x86_64 cases in each of three passes at 14cb515; "
        "signed/adoption and ARM64 remain owed"
    )
    for row in (p06, p08):
        assert all("pass:" not in row[index] for index in (1, 3, 4))
    assert "42 accepted observations" in runbook
    assert "14cb515ba54ca9346ea931ba46d4c3253164c8b4" in runbook
    assert "937-ms human-stream failure" in runbook
    assert "No complete Windows, Linux, macOS or WSL pass exists" in runbook

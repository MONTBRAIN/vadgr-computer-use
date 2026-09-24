"""Reuse released Windows fixture preparation for unsigned 0.7.9 slices."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "0.7.8/harness/upgrade_fixture.py"
spec = importlib.util.spec_from_file_location("released_fixture", SOURCE)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
fixture.EXPECTED["0.7.8"] = {
    "wheel": "1c905c200d0e2190bb3512ecf0c58f1b683900ad15288cef00c14a732fb10535",
    "archive": "cb8d47ede577c76683576a7bb4f8e5251eaa884b66bd50a2a35ad394966ce39d",
}

if __name__ == "__main__":
    raise SystemExit(fixture.main())

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "select_cua_e2e_driver.py"
SPEC = importlib.util.spec_from_file_location("select_cua_e2e_driver", SCRIPT)
helper = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(helper)


@pytest.mark.parametrize(
    ("used_percent", "driver"),
    [(24, "codex"), (25, "codex"), (26, "claude"), (60, "claude")],
)
def test_weekly_threshold_selects_driver(used_percent, driver):
    result = {
        "rateLimits": {
            "primary": {
                "usedPercent": used_percent,
                "windowDurationMins": 10_080,
                "resetsAt": 1_800_000_000,
            }
        }
    }

    selection = helper.select_driver(result)

    assert selection["selected_driver"] == driver
    assert selection["codex_weekly_remaining_percent"] == 100 - used_percent


def test_ordinary_limit_ignores_separate_model_allowance():
    result = {
        "rateLimits": {
            "primary": {"usedPercent": 60, "windowDurationMins": 10_080},
        },
        "rateLimitsByLimitId": {
            "codex_bengalfox": {
                "primary": {"usedPercent": 0, "windowDurationMins": 300},
                "secondary": {"usedPercent": 0, "windowDurationMins": 10_080},
            }
        },
    }

    selection = helper.select_driver(result)

    assert selection["selected_driver"] == "claude"
    assert selection["codex_weekly_remaining_percent"] == 40


def test_codex_limit_id_is_used_only_when_default_is_absent():
    result = {
        "rateLimits": None,
        "rateLimitsByLimitId": {
            "codex": {
                "primary": {"usedPercent": 10, "windowDurationMins": 10_080},
            }
        },
    }

    assert helper.select_driver(result)["selected_driver"] == "codex"


def test_missing_weekly_window_is_not_inferred_from_five_hour_window():
    result = {
        "rateLimits": {
            "primary": {"usedPercent": 0, "windowDurationMins": 300},
        }
    }

    with pytest.raises(ValueError, match="weekly window"):
        helper.select_driver(result)

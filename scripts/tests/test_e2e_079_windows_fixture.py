import importlib.util
from pathlib import Path


def test_predecessor_fixture_retains_released_hashes():
    path = Path(__file__).resolve().parents[2] / "E2E/0.7.9/harness/windows_fixture.py"
    spec = importlib.util.spec_from_file_location("fixture079", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert set(module.fixture.EXPECTED) == {"0.7.6", "0.7.7", "0.7.8"}
    assert module.fixture.EXPECTED["0.7.8"]["wheel"] == "1c905c200d0e2190bb3512ecf0c58f1b683900ad15288cef00c14a732fb10535"
    assert module.fixture.EXPECTED["0.7.6"]["archive"] == "fd2c57b76f57d06d3df3d7c964fa544b798e8f32ec460470bf326a46140696df"

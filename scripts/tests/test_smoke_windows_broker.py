import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "smoke_windows_broker.py"
SPEC = importlib.util.spec_from_file_location("smoke_windows_broker", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


def test_listening_addresses_selects_only_owned_tcp_listeners():
    output = """
      Proto  Local Address          Foreign Address        State           PID
      TCP    127.0.0.1:49152        0.0.0.0:0              LISTENING       760
      TCP    127.0.0.1:49152        127.0.0.1:50000        ESTABLISHED     760
      TCP    0.0.0.0:80             0.0.0.0:0              LISTENING       761
      TCP    [::1]:49153            [::]:0                 LISTENING       760
      UDP    127.0.0.1:5353         *:*                                    760
    """

    assert smoke.listening_addresses(output, 760) == {"127.0.0.1", "::1"}


def test_listening_addresses_returns_empty_for_no_owned_listener():
    output = "TCP    127.0.0.1:49152    0.0.0.0:0    LISTENING    761"

    assert smoke.listening_addresses(output, 760) == set()

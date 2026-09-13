# 0.7.8 E2E harness

This directory contains the released-wheel transition fixtures and safe
lifecycle recorder for the 0.7.8 pass. Each helper validates an isolated test
root before it changes state. Helpers prepare faults and record safe metadata.
They never drive the product goal, stop an unknown process, or read a token.

The implementation adds each helper before its first use. Run every helper from
this committed directory. Do not replace a helper with a temporary host script.

`upgrade_fixture.py` runs under native Windows Python. It creates only an
absolute root whose final name starts with `vadgr-cua-078-`, records a marker,
verifies an immutable `0.7.6` or `0.7.7` wheel, extracts its exact broker into
the released content-addressed layout, and starts it with isolated
application-data and endpoint paths. Its `observe`
output reports whether a token exists but never prints the token.

Use the lifecycle in this order for each fresh case:

```text
python upgrade_fixture.py init --root <absolute-new-root>
python upgrade_fixture.py prepare --root <root> --release 0.7.6 --wheel <wheel>
python upgrade_fixture.py start --root <root> --release 0.7.6
python upgrade_fixture.py observe --root <root>
python upgrade_fixture.py fault --root <root> --action remove
python upgrade_fixture.py stop --root <root>
```

Use `--synthetic` only with `start` for the unknown-payload refusal cell. The
helper changes that isolated copy, not the published wheel or candidate. `stop`
opens the recorded PID, verifies its live executable is below the marked root,
and terminates that same process handle. It refuses any uncertain target.

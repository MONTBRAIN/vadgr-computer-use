# 0.7.7 broker lifecycle helpers

`lifecycle_probe.py` prepares and observes the isolated broker states in W1-W6
and S1-S4. It imports the installed candidate only for a client connection. It
never emits endpoint tokens or reads owner broker state.

Every invocation requires a fresh root whose name begins `vadgr-cua-077-` and
an endpoint below that root. `fault` changes only that endpoint. `stop` is
Windows-only and terminates a PID only after its executable path is proven to
be the candidate broker below the same isolated root.

```text
python lifecycle_probe.py observe --root ROOT --endpoint ENDPOINT
python lifecycle_probe.py connect --root ROOT --endpoint ENDPOINT
python lifecycle_probe.py fault --root ROOT --endpoint ENDPOINT --action remove
python lifecycle_probe.py fault --root ROOT --endpoint ENDPOINT --action corrupt
python lifecycle_probe.py fault --root ROOT --endpoint ENDPOINT --action mismatch
python lifecycle_probe.py stop --root ROOT --endpoint ENDPOINT
python lifecycle_probe.py proxy --root ROOT --endpoint ENDPOINT --proxy PROXY
```

`connect` uses `BrokerClient` from the interpreter's installed wheel, requests
broker status, and reports only public identity fields. `proxy` sends one
credential-free readiness frame through the packaged Windows proxy and reports
its public error. These helpers prepare fixtures and observations; they do not
assign cell verdicts.

`browser_fixture.html` is the local instrumented R1 page. Serve it from the
validated root over loopback, open `?agent=one` and `?agent=two` in separate
Chrome for Testing windows, and keep a decoy tab selected in each window. Each
agent leases only its named inactive fixture and writes its public marker.
`browser_oracle.py` prepares those two windows through the isolated DevTools
port and independently records target/window identity, page value, visibility,
focus and decoy state before and after the product operations.

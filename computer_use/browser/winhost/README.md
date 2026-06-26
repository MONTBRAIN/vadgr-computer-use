# vadgr-cua-host.exe — Windows relay shim (WSL browser tier)

A tiny stdio↔TCP forwarder Chrome spawns (via `connectNative`) **on Windows**
when cua runs in **WSL**. There is no Python on the Windows side, so this relay
is a single static Go binary.

## What it does
1. Reads cua's discovery file `%LOCALAPPDATA%\vadgr-cua\browser.port`
   (`{port, token}`), which cua-in-WSL writes to the Windows-readable path.
2. Connects to cua's loopback-TCP listener on `127.0.0.1:<port>`
   (WSL2 mirrored networking shares `127.0.0.1` Windows↔WSL).
3. Sends the auth frame `{"type":"auth","token":...}`.
4. Pumps length-prefixed native-messaging frames both ways between Chrome's
   stdio and cua — identical framing to `computer_use/browser/native_host.py`
   (4-byte little-endian length prefix + UTF-8 JSON).

The WSL manifest's `path` points at this `.exe`; `ensure_registered()` on WSL
writes the manifest under `/mnt/c` and sets the HKCU native-host key via
`reg.exe` (see `computer_use/setup/extension_setup.py`).

## Build
From this directory, with Go installed (any host OS):

```sh
GOOS=windows GOARCH=amd64 go build -o vadgr-cua-host.exe .
```

The committed `vadgr-cua-host.exe` is a `PE32+ x86-64` Windows console binary
built from `main.go` with `go1.24`. It is shipped as package data.

## Verification status
The framing / auth / handshake / op round-trip is unit-validated by building
the **same source** for Linux and driving it against the real Python listener
(`computer_use/browser/server.BrowserServer`). The Windows `.exe` is the
identical code cross-compiled. The live Windows-Chrome ↔ WSL-cua path is part
of the human's e2e (the `.exe` running under real Windows Chrome).

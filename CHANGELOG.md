# Changelog

All notable changes to this project are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org/).

## [0.4.0] - 2026-06-17

### Added
- Browser tier (Tier 1): an MV3 browser extension bridged to cua over native
  messaging, acting DOM-first (content scripts + `chrome.tabs`/`chrome.cookies`;
  no `chrome.debugger`). Drives the user's own logged-in browser by selector.
- `browser` MCP tool (Tier ONE, MEDIUM) op-routed via `OperationGroup`:
  `navigate`/`back`/`forward`/`reload`, `wait_for`, `query`, `read_text`,
  `get_attribute`, `click`, `type`/`fill`, `select`, `scroll`, `cookies`, and
  the `status` pre-flight op.
- `browser_eval` MCP tool (Tier ONE, HIGH): arbitrary JS in the page, kept
  separate so the common ops keep a lower risk ceiling.
- Availability & failure model: a typed `BrowserError` taxonomy (`not_set_up`,
  `not_connected`, `op_unsupported`, `proto_mismatch`, `waking`, `op_failed`)
  mapped to a `ToolError` carrying remediation + a guided pixel fallback;
  `status` reports `{connected, browsers, setup, reason}`.
- `computer_use.browser`: the wire protocol (`PROTOCOL_VERSION=1`, the `hello`
  handshake, `supported_ops`), `BrowserBridge` (`NativeMessagingBridge` +
  `FakeBridge`, session registry, per-OS manifest probe), and the native-host
  stdio framing.
- `computer_use.setup.extension_setup`: installs the `com.vadgr.cua.json`
  native-host manifest to the per-OS paths with `allowed_origins` pinned to the
  extension's stable dev ID.
- `extension/`: the MV3 extension (manifest with a pinned `key` for a stable
  unpacked ID, service worker, op router, content DOM ops, the ported native
  value-setter fill, Offscreen keep-alive), with vitest + happy-dom unit tests.

### Changed
- Tool catalog grows from 21 to 23 (adds the two Tier ONE browser tools).
  `tier_breakdown` now reports `{"0": 8, "0.5": 0, "1": 2, "2": 13}`.

### Notes
- cua and `extension/` are independent builds that share no imports — only the
  versioned wire protocol (`protocol.py` / `protocol.ts`).
- The live native-messaging round-trip (Chrome → native host → running cua) and
  the MV3 service-worker keep-alive are wired but exercised by a manual spike;
  the framing, routing, error model, DOM ops and fill are unit-tested headlessly.

## [0.3.1] - 2026-06-12

### Fixed
- `clipboard` copy op no longer hangs forever on Wayland. `wl-copy` forks a
  background daemon that keeps serving the clipboard and inherits the parent's
  captured stdout/stderr pipes, so the previous `subprocess.run(..., capture_output=True)`
  blocked on the pipe read indefinitely. The `wl-copy` backend now launches
  detached (stdout/stderr to `DEVNULL`, text written to stdin, bounded wait), so
  the call returns immediately while the daemon keeps the clipboard available for
  later pastes. (#11)
- All clipboard copy backends now run with a defensive timeout, so a stuck copy
  surfaces as an error instead of an indefinite hang.

## [0.3.0] - 2026-05-29

### Added
- 8 first-party Tier 0 MCP tools: `fs` (read/write/list/stat/delete), `shell` (run/which), `http` (get/post), `env` (get/set), `time` (now/sleep), `tempfile` (temp_path), `data` (parse/serialize JSON/CSV/YAML), `clipboard` (copy/paste). Each tool dispatches sub-operations via an `op` argument; signatures and risk levels documented in each tool's docstring.
- `computer_use.tools.system` package with one module per tool. Implementations live next to their tests; the MCP wire wrappers in `computer_use.mcp_server` apply `@mcp.tool()` + `@tool(...)` exactly like the existing pixel tools.
- Optional `data-yaml` extra: `pip install vadgr-computer-use[data-yaml]` enables YAML parsing/serialization. Without it, `data` raises a clear RuntimeError on `parse_yaml` / `serialize_yaml` and still serves the JSON/CSV ops.

### Changed
- Tool catalog grows from 13 to 21. `vadgr-cua doctor` JSON now reports `tool_count: 21` and `tier_breakdown: {"0": 8, "0.5": 0, "1": 0, "2": 13}`.
- `shell.run` defaults to `shell_mode=False` and treats a string `command` as a single argv element when the caller didn't ask for shell parsing. Set `shell_mode=True` explicitly to interpret a shell string.
- `time.sleep` is capped at 60 seconds and `shell.run` timeout is capped at 600 seconds so a stuck call cannot stall the MCP session.

### Notes
- `env.set` is process-scoped: the value is applied to `os.environ` of the running MCP server and is NOT persisted to the user's shell init.
- `clipboard` tries `clip.exe` + `powershell.exe Get-Clipboard` (Windows / WSL2), then `pbcopy` / `pbpaste` (macOS), then `wl-copy` / `wl-paste` (Wayland), then `xclip` (X11). When no backend is on PATH the tool raises a RuntimeError listing the supported backends instead of silently no-op'ing.
- The 13 existing pixel-layer tools (Tier 2) are unchanged; this release only adds new tools.

## [0.2.0] - 2026-05-21

### Added
- `computer_use.core` framework: `@tool(name, tier, risk)` decorator, `ToolRegistry` (import-time auto-registration, introspection by name / tier / risk, count, tier breakdown), `Tier` enum (ZERO, HALF, ONE, TWO) and `Risk` enum (READ_ONLY, LOW, MEDIUM, HIGH).
- `computer_use.core.middleware` chain: lightweight `MiddlewareChain` + `TelemetryMiddleware` for structured event emission around tool calls. No policy decisions; no filtering.
- `vadgr-cua doctor` JSON output gains `registry_loaded`, `tool_count`, `tier_breakdown` so users can verify the new registry loads correctly.

### Changed
- All 13 existing pixel-layer MCP tools (`screenshot`, `screenshot_region`, `click`, `double_click`, `right_click`, `move_mouse`, `drag`, `scroll`, `type_text`, `key_press`, `get_screen_size`, `get_platform`, `get_platform_info`) are now registered through `@tool` in addition to `@mcp.tool()`. Tier 2 for all; read-only risk for query tools, medium risk for input-mutating tools.

### Notes
- Pure refactor — no functional change to any MCP tool. The wire surface is identical to 0.1.5.
- Scope is strict: `vadgr-computer-use` drives the local machine, exposes `tier` + `risk` metadata, and emits telemetry. Authorization, denylist, log redaction, approval prompts, and auth-mode policy are not cua concerns and live in the host's agent loop.

## [0.1.5] - 2026-04-26

### Changed
- Default screenshot encoding switched from PNG to JPEG quality 70. On a real desktop this drops a single full-screen capture from ~564 KB to ~100 KB (5-6x). Aspect ratio and coordinate space are preserved across formats so existing click flows work unchanged.
- `screenshot()` and `screenshot_region()` accept a new `format` argument: `"jpeg"` (default), `"png"` (lossless, opt-in), or `"thumbnail"` (~640 px wide JPEG q40, ~15 KB for sanity-check shots in long flows).
- Tool description gains a sixth rule reminding agents that screenshots are point-in-time and older ones should not be referenced.

### Fixed
- Hard dimension ceiling at 1600 px applied inside `_downscale` so a single screenshot can no longer trip the Anthropic 2000 px many-image limit (anthropics/claude-code#37461, #46656). User-set `CU_MAX_WIDTH` below the ceiling still wins; values above it are clamped.
- `get_screen_size()` applies the same ceiling pre-screenshot so its answer matches what the first screenshot will actually return.

### Notes
- Combined with the smaller per-image bytes, the 32 MB request-size cap now fits ~320 default JPEG screenshots (vs ~58 with PNG) and ~2,200 thumbnails. The 2000 px dimension error is structurally eliminated for any vadgr-cua screenshot.

## [0.1.4] - 2026-04-26

### Added
- macOS backend is now functional out of the box. `pip install vadgr-computer-use` pulls `pyobjc-framework-Quartz` and `pyobjc-framework-ApplicationServices` on macOS (wheel install, no compilation, no Homebrew packages).
- `vadgr-cua doctor` now reports `macos_accessibility_granted`, `macos_screen_recording_granted`, and `python_executable` on macOS, so users can verify permission state without launching the agent.
- Backend construction proactively triggers the Accessibility and Screen Recording prompts on first run; macOS opens System Settings to the right pane instead of the user having to find it.
- Every macOS capture and input call now preflights its permission. If denied, System Settings is deep-linked to the matching Privacy pane via the `x-apple.systempreferences:` URL scheme and the call returns a structured error to the agent. This eliminates the silent wallpaper-only screenshot when Screen Recording is revoked, and the silent input no-op when Accessibility is revoked.
- `vadgr-cua setup` subcommand: fires the Accessibility and Screen Recording prompts on demand and prints permission state as JSON. Useful as a one-time post-install step so the user can grant permissions before wiring up an agent.

### Changed
- macOS screen capture switched from the `screencapture` subprocess to `mss` (already a runtime dep). `mss` returns logical-point images that share CGEvent's coordinate space, eliminating the Retina coordinate mismatch that was causing 2x click offsets.
- macOS input switched from optional `cliclick` plus AppleScript fallbacks to `Quartz.CGEvent*` APIs (mouse, keyboard, scroll, drag). `cliclick` is no longer used.
- macOS `type_text` uses `CGEventKeyboardSetUnicodeString`, so any Unicode character types correctly without per-layout keymap maintenance.
- macOS executor now plugs into `core.smooth_move` (WindMouse + Fitts) like the Linux and Windows executors.

### Fixed
- macOS `key_press` correctly handles chords with multiple non-modifier keys (e.g. `ctrl+shift+t`) instead of silently dropping the second non-modifier.
- macOS `scroll` now uses `CGEventCreateScrollWheelEvent` with line units instead of an AppleScript form that did not actually scroll.
- macOS `drag` no longer collapses to a single click in the absence of `cliclick`; it emits the full down/dragged/up event sequence.
- macOS `get_screen_size` and `get_scale_factor` no longer shell out to a system `python3` that lacks `AppKit`; they read directly from Quartz.

## [0.1.3] - 2026-04-25

### Fixed
- `import computer_use.mcp_server` no longer fails on native Windows. The bridge supervisor (which imports `fcntl`) is now loaded lazily inside the daemon CLI subcommands, so the stdio MCP server starts cleanly on Windows where `fcntl` does not exist.

### Changed
- Test suite is green on native Windows: WSL2/Linux/daemon-only test files (`test_supervisor.py`, `test_wsl2.py`) skip cleanly on `win32`, and the two D-Bus tests in `test_linux.py` use `pytest.importorskip("jeepney")`.

## [0.1.2] - 2026-04-24

### Fixed
- `pip install vadgr-computer-use` now works on Linux Wayland (including GNOME) with no manual setup. `jeepney` and `evdev` are added to runtime dependencies under `sys_platform == 'linux'`; both are pure-Python or shipped as wheels, so there is no `libdbus-1-dev` or compilation step.
- Mutter RemoteDesktop client switched from `dbus-python` to `jeepney` (no C build at install time).
- Engine error on backend unavailability now names the missing component and the exact remediation, instead of a generic "required system tools" message.
- Unit tests no longer move the real cursor or keyboard. A new `conftest.py` blocks platform side-effects during `pytest`.

### Added
- `availability_report()` on `PlatformBackend` returning `(available, missing, remediation)`. `is_available()` is kept as a thin wrapper for back-compat.
- Optional `linux-atspi` extra (`pip install vadgr-computer-use[linux-atspi]`) for AT-SPI2 foreground-window detection on Wayland. Pulls `PyGObject` only if requested.
- README rows for Linux / Wayland (GNOME) and Linux / Wayland (Sway, Hyprland, wlroots) with concrete install notes per row.

### Changed
- Linux backend probes screen capture at construct time, so a missing `grim` fails with a clear message instead of on the first `screenshot()` call.

## [0.1.1] - 2026-04-22

### Removed
- Autonomous mode and the entire `computer_use/providers/` package (Anthropic, OpenAI, base, registry). The package is now MCP-only; external clients (Claude Code, Codex CLI, Gemini CLI) drive the server over stdio.
- `ComputerUseEngine.run_task()` and the associated in-process agent loop.

### Changed
- README rewritten: new "Try it" section with runnable one-shot commands per client (Claude interactive + headless, Codex exec, Gemini with explicit `-m gemini-3.1-pro-preview`); real YouTube Music Codex transcript replaces the trivial `get_platform_info` demo.
- Platform support table reordered (Linux, Windows, WSL2, macOS) and macOS flagged as WIP up front.
- Collapsed "How it works" to its tagline; removed duplicate WSL2 auto-launch notes.

### Fixed
- Environment table: `VADGR_DATA` was documented but never existed; removed. `VADGR_DEBUG` now correctly documents the actual debug-screenshot path (`<package>/.debug/`).

### Added
- `.env` and `.env.*` to `.gitignore`.

## [0.1.0] - 2026-04-21

- Initial public release.
- 13 MCP tools: `screenshot`, `screenshot_region`, `click`, `double_click`, `right_click`, `move_mouse`, `drag`, `scroll`, `type_text`, `key_press`, `get_platform`, `get_platform_info`, `get_screen_size`.
- WSL2 bridge daemon with auto-launch, self-heal, and management CLI (`vadgr-cua doctor|install-daemon|stop-daemon|restart-daemon`).
- Backends: `mss` + `xdotool` (Linux/X11), Win32 GDI + SendInput (Windows), TCP bridge to Windows host (WSL2). macOS backend is present but not functional.

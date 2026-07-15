# Changelog

All notable changes to this project are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org/).

## [0.6.1] - 2026-07-13

Browser round 3.1: multi-profile targeting. When the extension is installed in
more than one Chrome profile (personal, work, several Google accounts), cua now
knows which profile each connection is and the agent can choose one, instead of
binding to whichever connected first. No protocol version bump: the handshake
gains additive profile fields and the capability list grows one op.

### Added
- `profiles(op, ...)` op-group (a new Tier 1 tool): `list` returns every
  connected browser profile with recognition context (`profile_id`, `browser`,
  `is_current`, `window_count`, `tab_count`, `sample_tab_titles`) so you can tell
  them apart by what is open in each ("the one with work Gmail and Figma");
  `use(profile_id)` pins which profile the browser / tabs / windows / DOM ops act
  within.
- `use_target` gains an optional `profile_id` that selects the connected profile
  and (optionally) a target within it in one call.
- The extension mints a stable per-profile id (a UUID in `chrome.storage.local`,
  which is isolated per profile) once and reports it plus the recognition context
  in the `hello` handshake. No new permission (storage was already granted).
- `CUA_BROWSER_PROFILE` env var pins a default profile when more than one is
  connected: it matches a `profile_id` prefix or a `sample_tab_title` substring.
- `browser(op="status")` grows a `profiles` array listing every connected
  profile, so the pre-flight shows the choices.

### Changed
- The browser transport keeps every accepted connection concurrently, keyed by
  `(browser, profile_id)`, with a `current` pointer selecting which one ops route
  to. This replaces the single-listener bond (one connection owned the pipe).
  Selection follows a ladder: an explicit `profiles(use)` / `use_target` choice,
  then the `CUA_BROWSER_PROFILE` pin, then the sole connection if there is exactly
  one.

### Fixed
- Never silently wrong on multiple profiles: with more than one connected and none
  selected, the next op raises a terminal `profile_ambiguous` error that lists the
  choices, rather than guessing (the same doctrine as 0.6.0 `target_lost`). If an
  explicitly-selected profile disconnects, the next op is loud too, instead of
  silently falling through to another profile.

### Notes
- Back-compat: a connection whose `hello` carries no `profile_id` (an older
  extension) is registered under a synthetic `default` profile, so single-profile
  setups are unchanged and need no new step.
- Extension version and package version bump to 0.6.1 in lockstep; the
  `PROTOCOL_VERSION` stays 1 (the hello profile fields and the `profiles` op are
  additive).
- The multi-connection registry and the profile handshake are pure Python + a
  pure extension handshake with no path boundary, so Linux / Windows / macOS / WSL
  behave identically; WSL is the parity boundary that proves the multiplexed
  connections round-trip over the bridge. Validated on the automated gate
  (`pytest` / `vitest` / `npm run build` / `npm run typecheck`); the live
  two-profile run is the hardware verification round. This entry is re-checked
  against the final diff at release.

## [0.6.0] - 2026-07-09

Browser round 3: window/tab management (the multi-context session model). The
0.5.0 single pinned target becomes an enumerable, switchable registry, and the
three ways the agent used to get lost in the browser are closed. No protocol
version bump: the new ops grow the capability list only.

### Added
- `tabs(op, ...)` op-group: `list` returns the full `window -> tabs ->
  {tab_id, url, title, active, owned, is_current}` map across the agent's own
  window and yours (tagged by provenance); `open` / `switch` / `close` manage
  tabs. The agent sees every tab but acts only on the pinned target. `switch`
  moves the target and activates the tab within its window without raising that
  window over your foreground; closing one of your tabs requires `force=True`.
- `windows(op, ...)` op-group: `list` (the thin, per-window variant), `open` (a
  new owned window, unfocused by default), `focus` (the explicit, agent-intended
  raise), and `close` (owned only unless `force=True`).
- Every browser op result now carries a `target: {window_id, tab_id, url}`
  field, so the agent always sees which tab it just acted on and a surprise
  `chrome://newtab` is visible immediately (additive; older clients tolerate it).
- `use_target` now also reports the resolved `url` and `provenance`
  (owned / attached / user) and switches the registry's current target.

### Changed
- The target model generalizes from a single pin to a registry of known contexts
  plus a `current` pointer and an `established` flag, all persisted in
  `chrome.storage.session`. Every op still resolves and acts by id (focus-proof,
  unchanged).
- The `target_lost` remediation now points at `tabs(op='list')` then
  `use_target` to re-pin, or `use_target(mode='owned')` to open a fresh window.

### Fixed
- Loud loss: a mid-task target loss (the pinned tab/window closed after a target
  was established) now raises `target_lost` instead of silently re-opening a
  blank `chrome://newtab` window under the agent. A cold start (no target ever
  set this session) still auto-opens the owned window. The split rides on the
  persisted `established` flag, so it survives service-worker idle-termination.
- Content-script self-heal now covers mutating ops (`click` / `fill` / `type`):
  an "unreachable" reply means the message never arrived and the op never ran, so
  re-injecting the content script and delivering once is a safe first delivery,
  not a retry. This closes the "reads self-heal, writes fail on a fresh
  navigation" split. A channel torn down mid-message is still reported as a
  navigation, never redelivered.

### Notes
- Extension version and package version bump to 0.6.0 in lockstep; the
  `PROTOCOL_VERSION` stays 1 (the new ops are additive via `supported_ops`).
- The window/tab/registry/storage surfaces are pure `chrome.windows` /
  `chrome.tabs` extension APIs with no path boundary, so Linux / Windows / macOS /
  WSL behave identically (unlike `upload`). Validated on the Linux + xvfb gating
  harness; per-OS live runs on Windows native / macOS / WSL are done in the
  hardware verification round. This entry is re-checked against the final diff at
  release.

## [0.5.0] - 2026-07-08

### Added
- Session-target model for the browser tier: the extension pins an explicit
  `{browser, window_id, tab_id}` target resolved once and used by every op by id,
  instead of resolving each op against the last-focused window. By default the
  agent opens its own dedicated window in your real Chrome profile (real
  cookies/logins), kept separate so it never fights your foreground tab. The
  pinned target survives service-worker idle-termination (`chrome.storage.session`)
  and follows tabs the agent itself spawns (OAuth popups, `target=_blank`).
- `use_target(mode="owned"|"attach", window_id=None, tab_id=None)` browser op —
  explicitly pin the session target. Attach mode snapshots the tab you are
  currently looking at once, then pins it by id.
- New browser ops on the `chrome.debugger` path: `hover` (with an optional
  `reveals` check), `dialog` (one-shot arm for JS `alert`/`confirm`/`prompt`/
  `beforeunload`), `upload` (file inputs via `DOM.setFileInputFiles`),
  `element_state` (visible / receives_events / enabled / focused / editable /
  checked / value / bbox), `focus`/`blur`, `clear`, `get_value`, and `snapshot`
  (paginated accessibility tree that pierces shadow DOM and frames; supersedes
  `accessibility_tree`, which stays for back-compat).
- `upload` translates each file path to the browser process's OS before the op
  crosses the wire, so a WSL path (`/home/...` or `/mnt/c/...`) reaches Windows
  Chrome as a path it can actually read. Native Chrome paths pass through
  unchanged.

### Changed
- `query` now caps the node count and per-node text and paginates (`limit` +
  `cursor` -> `next_cursor`), so a large page degrades to pages instead of a
  single oversized result.
- The `browser` tool docstring documents that `screenshot` is a pixel tool, not a
  browser op; `browser(op="screenshot")` now returns that guidance instead of an
  opaque error.
- The extension requires the `storage` permission (for `chrome.storage.session`).

### Fixed
- The browser tier no longer acts on whatever window the user last focused. Every
  op targets the pinned window/tab by id, so a focus change (or a popup stealing
  focus) can no longer move the target mid-task. When the pinned tab/window is
  closed the op fails with a terminal `target_lost` error and remediation; the
  tier never silently retargets the user's active tab.
- WSL: the MCP server no longer hangs on `initialize`. The startup subprocess
  probes (the `reg.exe` native-host registration and the `cmd.exe`/`powershell.exe`
  interop probes) inherited the JSON-RPC stdio pipe on fd 0; they now run with a
  null stdin, so `initialize` returns immediately instead of blocking. (#18)
- WSL: the native messaging host now auto-registers against the Windows registry
  on first run. Platform detection resolves WSL2 through `detect_platform()`
  instead of `sys.platform` (which reports `linux` under WSL), so registration
  targets Windows Chrome and the extension bonds with no manual step. (#19)
- The owned automation window opens at a real, hit-testable size (`state:"normal"`,
  1200x900, still unfocused) instead of minimized. On WSL driving Windows Chrome a
  `focused:false` window could open minimized (about 0px viewport), which made the
  actionability hit-test fail and forced `force` on every mutation. A null
  `elementFromPoint` result (a throttled or occluded window that is not composited)
  is also no longer treated as covered, so a CDP-driven owned window is never
  falsely gated.
- Native replies are correlated by request id instead of arrival order, and
  navigation/read ops are time-bounded. A stray frame (a reconnect `hello`, or a
  late reply from a timed-out op) can no longer shift every following reply by one,
  and a page that never reports load-complete can no longer hang the pipe.
- The browser session tears down on an op timeout so the extension can reconnect.
  A socket read-timeout previously left the buffered reader unrecoverable and
  wedged the session; cua now closes the connection on timeout, the native-host
  relay hits EOF, and the extension reconnects with a fresh session.

### Notes
- No `PROTOCOL_VERSION` bump — every new op is additive and gated on the
  extension's `supported_ops`; an older extension returns a precise
  `op_unsupported` for a 0.5.0 op.

## [0.4.1] - 2026-06-29

### Fixed
- Restore the desktop screenshot tier on GNOME 49/50 (Ubuntu 25.10/26.04): add an
  XDG Desktop Portal screenshot backend as the portable Wayland capture path. It
  is tried after the no-dialog CLI tools, so GNOME 46 / Ubuntu 24.04 keeps using
  `gnome-screenshot` unchanged (no new consent dialog) while GNOME 49+ — where the
  CLI tools no longer work — transparently falls through to the portal.

### Added
- Provider/resolver backend abstraction (`SessionContext` + `CaptureProvider` /
  `InputProvider` + `BackendResolver`) so adding a desktop is one provider, not a
  factory edit. `vadgr-cua doctor` now reports the resolved capture/input backend
  and candidate applicability under `platform_backends`.
- Pure-python uinput input fallback (no `evdev`, no C compiler) and an X11 XTEST
  executor via `python-xlib` (no `xdotool`).
- `vadgr-cua install-deps`: distro-aware provisioning (apt/dnf/pacman/zypper) for
  `wl-clipboard` and the `/dev/uinput` udev rule. Prints the plan; `--yes` runs the
  whole plan under a single privilege prompt — `pkexec` (graphical polkit auth, no
  terminal sudo) when a display is present, falling back to `sudo`. This is the
  second of the two install commands: `pip install` then `vadgr-cua install-deps`.

### Changed
- `evdev` moved to the optional `[linux-uinput]` extra; `python-xlib` added as a
  Linux dependency. A plain `pip install` no longer needs a C compiler.

## [0.4.0] - 2026-06-26

### Added
- Browser tier (Tier 1): an MV3 browser extension bridged to cua over native
  messaging. Acts DOM-first (content scripts + `chrome.tabs`/`chrome.cookies`)
  and escalates to a `chrome.debugger` CDP path only when a DOM op cannot
  complete. Drives the user's own logged-in browser by selector.
- `browser` MCP tool (Tier ONE, MEDIUM) op-routed via `OperationGroup`:
  `navigate`/`back`/`forward`/`reload`, `wait_for`, `query`, `read_text`,
  `get_attribute`, `click`, `type`/`fill`, `select`, `scroll`, `cookies`,
  `press`, `accessibility_tree`, and the `status` pre-flight op.
- `browser_eval` MCP tool (Tier ONE, HIGH): arbitrary JS in the page, kept
  separate so the common ops keep a lower risk ceiling.
- Actionability gate (Playwright-style): before a mutating op (`type`/`fill`/
  `click`/`select`) the target is checked for visible / receives-events
  (hit-test) / enabled; a non-actionable target raises `op_failed` instead of
  silently acting on a hidden or wrong node. A `force` param bypasses the gate.
- Self-verifying ops: `type`/`fill` return `{value, ok}`, `select` returns
  `{selected, value, ok}`, and a checkbox `click` returns `{checked}`, so the
  agent confirms an action landed from structured read-back rather than a
  screenshot; the tool descriptions instruct it to. contenteditable editors are
  filled via `execCommand('insertText')`, the only path that drives rich-editor
  state.
- Executor seam + escalation: a DOM executor and a `chrome.debugger` CDP
  executor behind one interface; on a DOM `ok:false` the escalation policy
  retries over CDP (trusted `Input` events, `Accessibility.getFullAXTree`).
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
  extension's stable dev ID. On WSL it also auto-places the Windows-side relay
  executable under `%LOCALAPPDATA%\vadgr-cua\`, so no manual copy step is needed.
- `extension/`: the MV3 extension (manifest with a pinned `key` for a stable
  unpacked ID, service worker, op router, content DOM ops, the ported native
  value-setter fill, the actionability checks, contenteditable fill, the
  executor/escalation seam and `chrome.debugger` CDP executor, Offscreen
  keep-alive), with vitest + happy-dom unit tests.

### Changed
- Tool catalog grows from 21 to 23 (adds the two Tier ONE browser tools).
  `tier_breakdown` now reports `{"0": 8, "0.5": 0, "1": 2, "2": 13}`.

### Notes
- cua and `extension/` are independent builds that share no imports — only the
  versioned wire protocol (`protocol.py` / `protocol.ts`).
- Validated end-to-end on real logged-in sites via the agent-driven runbook in
  `E2E/0.4.0/` (see its per-OS results table); the framing, routing, error
  model, DOM ops, fill, and actionability checks are also unit-tested headlessly.

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

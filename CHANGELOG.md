# Changelog

All notable changes to this project are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org/).

## [0.1.3] - 2026-04-26

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
- Test suite is green on native Windows: WSL2/Linux/daemon-only test files (`test_supervisor.py`, `test_wsl2.py`) skip cleanly on `win32`, and the two D-Bus tests in `test_linux.py` use `pytest.importorskip("jeepney")`.

### Fixed
- `import computer_use.mcp_server` no longer fails on native Windows. The bridge supervisor (which imports `fcntl`) is now loaded lazily inside the daemon CLI subcommands, so the stdio MCP server starts cleanly on Windows where `fcntl` does not exist.
- macOS `key_press` correctly handles chords with multiple non-modifier keys (e.g. `ctrl+shift+t`) instead of silently dropping the second non-modifier.
- macOS `scroll` now uses `CGEventCreateScrollWheelEvent` with line units instead of an AppleScript form that did not actually scroll.
- macOS `drag` no longer collapses to a single click in the absence of `cliclick`; it emits the full down/dragged/up event sequence.
- macOS `get_screen_size` and `get_scale_factor` no longer shell out to a system `python3` that lacks `AppKit`; they read directly from Quartz.

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

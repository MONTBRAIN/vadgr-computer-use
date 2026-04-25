# Changelog

All notable changes to this project are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org/).

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

# Changelog

All notable changes to this project are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org/).

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

# computer_use (package internals)

This is the Python package shipped as `vadgr-computer-use` on PyPI.

For user-facing docs (install, CLI, MCP wiring), see the top-level
[README.md](../README.md).

## Layout

```
computer_use/
├── core/               # Engine facade, types, screenshot/action abstractions
├── platform/           # OS backends (linux.py, wsl2.py, windows.py, macos.py) + detect.py
├── bridge/             # WSL2 -> Windows TCP daemon: client, deployer, supervisor
├── tests/              # pytest suite
└── mcp_server.py       # FastMCP server entry point (`vadgr-cua` console script)
```

## Architecture contract

- `mcp_server.py` exposes 13 MCP tools. Each tool calls straight into
  `ComputerUseEngine`.
- `core/engine.py` is the public Python API. It does not call any LLM.
- `platform/*.py` each implement `PlatformBackend` with `get_screen_capture()`
  and `get_action_executor()` for their OS.
- `bridge/supervisor.py` (WSL2 only) probes, launches, and self-heals the
  Windows-side daemon. The backend delegates to it; callers do not touch
  the daemon directly.

## Running the tests

```bash
pip install -e ".[dev]"
pytest computer_use/tests -q
```

Baseline: Linux CI runs 3.10 / 3.11 / 3.12 (`.github/workflows/test.yml`).

# E2E verification — read the JSON, not the agent's words

This applies to **every** runbook in this directory (`E2E/<version>/e2e.md`).

An e2e is driven by a real Claude agent given a goal-level task. The agent's prose
summary ("I logged in and saw the banner") is **self-report and is not evidence**.
The only trustworthy verdict comes from the **structured JSON of what the agent
actually did** — the `tool_use` calls it issued and the `tool_result` payloads cua
sent back (cua's real read-backs). A claimed success with no confirming
`tool_result` read-back is a **fail**. Always judge from the JSON.

## Where the JSON is

1. **The captured run stream (preferred).** Run the subagent with
   `--output-format stream-json --verbose` and tee it to a file:
   ```bash
   <prompt> | claude --dangerously-skip-permissions --mcp-config .mcp.json \
     --output-format stream-json --verbose -p | tee /tmp/e2e-run.jsonl
   ```
   Each line is one event; the `tool_use` / `tool_result` entries are the ground
   truth.

2. **The Claude session transcript (the fallback — use this if the stream is not
   in your context).** Claude Code persists every session, including subagent
   ("sidechain") turns, as JSONL here:
   ```
   ~/.claude/projects/<sanitized-cwd>/<session-id>.jsonl
   ```
   For this repo the directory is
   `~/.claude/projects/-home-vboxuser-vadgr-computer-use/`. One JSON object per
   line; the newest file is the current session. **This is the unique way to
   verify the agent's actions when the run stream did not land in your context** —
   the transcript cannot be edited by the agent's summary, so it is the
   ground-truth record of the tool calls and their results.

## How to read it

Each line is a JSON object; tool activity lives under `message.content[]` with
`type` `tool_use` (the call + its `input`) or `tool_result` (the returned payload,
plus `is_error`). Subagent turns carry `isSidechain: true`.

```bash
# tool calls + results from a transcript (or a teed stream)
f=~/.claude/projects/-home-vboxuser-vadgr-computer-use/<session-id>.jsonl
python - "$f" <<'PY'
import json, sys
for line in open(sys.argv[1]):
    try: o = json.loads(line)
    except ValueError: continue
    for c in (o.get("message", {}) or {}).get("content", []) or []:
        if not isinstance(c, dict): continue
        if c.get("type") == "tool_use":
            print("CALL", c.get("name"), json.dumps(c.get("input", {}))[:200])
        if c.get("type") == "tool_result":
            err = c.get("is_error", False)
            body = json.dumps(c.get("content"))[:200]
            print("RSLT", "ERROR" if err else "ok", body)
PY
```

## The verdict rules (every runbook)

- A mutating action (`click`/`type`/`scroll`/...) counts only if a **read-back**
  `tool_result` confirms its effect (a follow-up `screenshot`/`query`/`read_text`,
  or an independent ground-truth like a file written to disk or `wl-paste`).
- The **negative test** must show a `tool_result` with `is_error: true` — a failure
  that raises, never a silent success.
- If the run stream is gone, reconstruct the verdict from the `~/.claude`
  transcript. Do not accept the agent's written summary in its place.
- If neither the stream nor a transcript is available, the test is **not verified**
  — say so; do not infer a pass.

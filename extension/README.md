# vadgr-computer-use — browser tier (MV3 extension)

The DOM-first browser half of the 0.4.0 browser tier. It connects to the
running cua over native messaging and runs selector-based ops in the user's own
logged-in browser. Shares no code with the Python side — only the wire protocol
(`src/protocol.ts` mirrors `computer_use/browser/protocol.py`).

## Build

```
npm install
npm run build        # bundles src/ -> dist/ (background.js, content.js, offscreen.js + assets)
```

## Test

```
npm test             # vitest + happy-dom (fill, DOM ops, router)
npm run typecheck    # tsc --noEmit
```

## Install (Chrome Web Store)

The published build's ID is `bjjpaehedfnjnjmamjhppjnjnikpnfjl` (the store
strips the pinned `key` and assigns its own ID). The native-host manifest cua
writes allowlists BOTH the store ID and the dev ID, so a store install and an
unpacked build can each connect.

## Load (unpacked, dev)

1. Run `vadgr-cua` native-host setup so `com.vadgr.cua.json` is installed
   (writes `allowed_origins` covering the dev + Web Store extension IDs).
2. Open `chrome://extensions` (or `edge://extensions`), enable Developer mode.
3. "Load unpacked" → select the `dist/` directory.
4. Confirm the extension ID is `bcbdnpafilijienocokppgmfianhehll` (fixed by the
   `key` pinned in `manifest.json`, so it stays stable across loads and matches
   the native-host manifest's `allowed_origins`).
5. Restart the browser if it was already running, then from cua call
   `browser(op="status")` to confirm the session is connected.

## Layout

- `src/background.ts` — service worker: native port, `hello` handshake, op
  router, Offscreen-Document keep-alive (MV3 ~30s idle termination).
- `src/ops.ts` — service-worker op handlers (navigate→`chrome.tabs`,
  cookies→`chrome.cookies`) + registration; DOM ops forwarded to the content
  script.
- `src/router.ts` — the op router (mirrors cua's `OperationGroup`).
- `src/content/ops.ts` — DOM op handlers (click/query/read_text/get_attribute/
  scroll/select/wait_for/type).
- `src/content/fill.ts` — native value-setter + input/change/blur (ported from
  task-extractor).
- `src/content/index.ts` — content-script entry; answers forwarded op messages.

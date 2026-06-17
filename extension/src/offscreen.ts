// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// Offscreen-document keep-alive. Its mere existence keeps the extension
// resident past the service worker's ~30s idle termination. A heartbeat pings
// the service worker so the native port stays warm across a long agent session.
// Validated in the manual spike (multi-minute session survival is the #1 open
// question in 0.4.0/browser.md).

const HEARTBEAT_MS = 20_000;

setInterval(() => {
  chrome.runtime?.sendMessage?.({ type: "keepalive" }).catch(() => {
    // The SW may be mid-restart; the next tick re-pings. Swallow the error.
  });
}, HEARTBEAT_MS);

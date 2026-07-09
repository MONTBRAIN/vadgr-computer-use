// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// Service worker: connect the native port, perform the `hello` handshake
// (reporting browser + supported_ops), route each op through the command
// router, and keep the MV3 worker alive past its ~30s idle termination via an
// Offscreen Document holding the port.
//
// The pure router + op handlers are unit-tested (router.test / ops.test). This
// wiring (native port, offscreen, handshake) is exercised in the manual spike
// against a real Chrome — it touches chrome.* APIs that have no headless stand-in.

import { buildRouter, sharedResolver } from "./ops";
import {
  PROTOCOL_VERSION,
  ServerHello,
  OpMessage,
  serverHello,
} from "./protocol";
import { ReconnectController } from "./reconnect";
import { Lifecycle } from "./target/lifecycle";

const HOST_NAME = "com.vadgr.cua";
const EXT_VERSION = chrome.runtime.getManifest?.().version ?? "0.6.0";

let port: chrome.runtime.Port | null = null;
const router = buildRouter();

// Auto-reconnect: MV3 service workers idle-terminate and the native host can
// drop, so load order must never matter. On disconnect we back off and retry;
// the backoff resets once a connection succeeds. (Logic unit-tested in
// reconnect.test.ts.)
const reconnect = new ReconnectController(
  () => connect(),
  (fn, delay) => setTimeout(fn, delay),
);

function detectBrowser(): string {
  const ua = navigator.userAgent;
  if (ua.includes("Edg/")) return "edge";
  return "chrome";
}

function connect(): void {
  port = chrome.runtime.connectNative(HOST_NAME);
  port.onMessage.addListener(onMessage);
  port.onDisconnect.addListener(() => {
    port = null;
    // Schedule a backed-off reconnect so the session self-heals.
    reconnect.onDisconnect();
  });
  // The port is connected; reset the backoff so the next drop starts at base.
  reconnect.onConnected();
  // cua sends its hello first; we reply with ours. Send ours proactively too,
  // so a cua that listens-first still negotiates.
  const hello: ServerHello = serverHello(EXT_VERSION, detectBrowser());
  port.postMessage(hello);
}

async function onMessage(msg: any): Promise<void> {
  if (!port) return;
  if (msg?.type === "hello") {
    if (msg.proto !== PROTOCOL_VERSION) {
      port.postMessage({
        type: "result",
        id: msg.id ?? 0,
        ok: false,
        error: {
          code: "proto_mismatch",
          message: `extension proto ${PROTOCOL_VERSION} != cua proto ${msg.proto}`,
        },
      });
    }
    return;
  }
  if (msg?.type === "op") {
    const result = await router.handle(msg as OpMessage);
    port.postMessage(result);
  }
}

// --- MV3 keep-alive: an Offscreen Document holds the long-lived work so the
// service worker can idle-terminate without dropping the session. The #1 spike
// item; proven against a real Chrome over a multi-minute session.
async function ensureOffscreen(): Promise<void> {
  // @ts-ignore - offscreen is present at runtime under the "offscreen" perm.
  const has = await chrome.offscreen?.hasDocument?.();
  if (has) return;
  // @ts-ignore
  await chrome.offscreen?.createDocument?.({
    url: "offscreen.html",
    reasons: ["BLOBS" as chrome.offscreen.Reason],
    justification: "hold the native-messaging port alive across SW idle cycles",
  });
}

// --- session-target lifecycle: follow agent-spawned tabs, drop closed ones.
// A tab spawned FROM the pinned tab (OAuth popup, target=_blank) re-pins so the
// agent follows its own flow; a user-opened tab is left alone. Closing the pinned
// tab clears it (the next resolve re-establishes in owned mode / raises in attach)
// — we NEVER silently grab the user's active tab. Shares the resolver instance the
// op router uses, so re-pins take effect for subsequent ops.
const lifecycle = new Lifecycle(sharedResolver());
chrome.tabs?.onCreated?.addListener((tab) => {
  void lifecycle.onTabCreated(tab);
});
chrome.tabs?.onRemoved?.addListener((tabId) => {
  void lifecycle.onTabRemoved(tabId);
});

chrome.runtime.onStartup?.addListener(() => {
  ensureOffscreen();
  connect();
});
chrome.runtime.onInstalled?.addListener(() => {
  ensureOffscreen();
  connect();
});

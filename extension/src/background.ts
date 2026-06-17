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

import { buildRouter } from "./ops";
import {
  PROTOCOL_VERSION,
  ServerHello,
  OpMessage,
  serverHello,
} from "./protocol";

const HOST_NAME = "com.vadgr.cua";
const EXT_VERSION = chrome.runtime.getManifest?.().version ?? "0.4.0";

let port: chrome.runtime.Port | null = null;
const router = buildRouter();

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
  });
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

chrome.runtime.onStartup?.addListener(() => {
  ensureOffscreen();
  connect();
});
chrome.runtime.onInstalled?.addListener(() => {
  ensureOffscreen();
  connect();
});

// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// Service worker: connect the native port, perform the `hello` handshake
// (reporting browser + supported_ops), and route each op through the command
// router.
//
// MV3 lifetime model (issue #36): Chrome kills this worker after ~30s idle. A
// later wake re-runs this module's top level but fires NEITHER onStartup NOR
// onInstalled, so the top level itself must (re)establish the native port - 
// connect() is idempotent and is called unconditionally below, plus from a
// periodic chrome.alarms keep-alive and the offscreen heartbeat, so the port
// self-heals no matter which event wakes the worker. While a native-messaging
// port is open, Chrome >=116 extends the worker's lifetime; once the port is
// gone, the alarm is the guaranteed wake-up.
//
// The pure router + op handlers are unit-tested (router.test / ops.test); the
// connect wiring is unit-tested in background.test.ts with a chrome.* stub.

import { buildRouter, sharedResolver } from "./ops";
import {
  PROTOCOL_VERSION,
  OpMessage,
  serverHello,
} from "./protocol";
import { ReconnectController } from "./reconnect";
import { Lifecycle } from "./target/lifecycle";
import { ensureProfileId, buildProfileContext } from "./target/profile";
import type { WindowsEnumApi } from "./target/enumeration";

const HOST_NAME = "com.vadgr.cua";
const EXT_VERSION = chrome.runtime.getManifest?.().version ?? "0.7.3";

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

export function connect(): void {
  // IDEMPOTENT: the module top level, onStartup/onInstalled, the reconnect
  // controller, the keep-alive alarm, and the offscreen heartbeat all funnel
  // here - if a port is already open there is nothing to do (issue #36).
  if (port !== null) return;
  let p: chrome.runtime.Port;
  try {
    p = chrome.runtime.connectNative(HOST_NAME);
  } catch {
    // connectNative can throw synchronously (missing permission/manifest); a
    // top-level throw would kill the whole SW start, so back off and retry.
    reconnect.onDisconnect();
    return;
  }
  port = p;
  p.onMessage.addListener(onMessage);
  p.onDisconnect.addListener(() => {
    port = null;
    // Schedule a backed-off reconnect so the session self-heals.
    reconnect.onDisconnect();
  });
  // The port is connected; reset the backoff so the next drop starts at base.
  reconnect.onConnected();
  // cua sends its hello first; we reply with ours. Send ours proactively too,
  // so a cua that listens-first still negotiates. The hello carries this
  // profile's stable id + recognition context (0.6.1) so cua can tell profiles
  // apart; building it is async (storage.local + tab enumeration).
  void sendHello(p);
}

function profileStorage() {
  return {
    // @ts-ignore - chrome.storage.local is present at runtime (storage perm).
    get: (keys: string) => chrome.storage.local.get(keys),
    // @ts-ignore
    set: (items: Record<string, unknown>) => chrome.storage.local.set(items),
  };
}

async function sendHello(p: chrome.runtime.Port): Promise<void> {
  const windowsApi: WindowsEnumApi = {
    getAll: (opts) => chrome.windows.getAll(opts) as Promise<any>,
  };
  let profileId: string | undefined;
  let profile;
  try {
    [profileId, profile] = await Promise.all([
      ensureProfileId(profileStorage()),
      buildProfileContext(windowsApi),
    ]);
  } catch {
    // Identity is best-effort: if storage/enumeration is briefly unavailable,
    // still send a valid hello (cua registers it under the `default` profile).
  }
  // The port may have dropped while we awaited; guard before posting.
  if (port !== p) return;
  p.postMessage(serverHello(EXT_VERSION, detectBrowser(), profileId, profile));
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

// --- MV3 keep-alive helper: the Offscreen Document. It CANNOT hold the native
// port (the port belongs to the service worker, and dies with it); what it does
// do is send a heartbeat message every ~20s, which wakes the SW so the
// top-level / onMessage reconnect paths below run promptly. The thing that
// actually keeps a LIVE port alive is Chrome >=116 extending SW lifetime while
// a native-messaging port is open - which only helps after a successful
// connect; the alarm + heartbeat revive the port after idle death (issue #36).
export async function ensureOffscreen(): Promise<void> {
  // @ts-ignore - offscreen is present at runtime under the "offscreen" perm.
  const has = await chrome.offscreen?.hasDocument?.();
  if (has) return;
  // @ts-ignore
  await chrome.offscreen?.createDocument?.({
    url: "offscreen.html",
    reasons: ["BLOBS" as chrome.offscreen.Reason],
    justification:
      "heartbeat that wakes the service worker so it can re-establish " +
      "the native-messaging port after idle termination",
  });
}

// --- session-target lifecycle: follow agent-spawned tabs, drop closed ones.
// A tab spawned FROM the pinned tab (OAuth popup, target=_blank) re-pins so the
// agent follows its own flow; a user-opened tab is left alone. Closing the pinned
// tab clears it (the next resolve re-establishes in owned mode / raises in attach)
// - we NEVER silently grab the user's active tab. Shares the resolver instance the
// op router uses, so re-pins take effect for subsequent ops.
const lifecycle = new Lifecycle(sharedResolver());
chrome.tabs?.onCreated?.addListener((tab) => {
  void lifecycle.onTabCreated(tab);
});
chrome.tabs?.onRemoved?.addListener((tabId) => {
  void lifecycle.onTabRemoved(tabId);
});

// --- (re)connect wiring (issue #36) ------------------------------------------
// onStartup fires only at browser launch and onInstalled only at
// install/update - NOT when an idle-killed worker is woken by some other event.
// They stay registered (synchronously, as MV3 requires) for those two cases,
// but the paths below are what make reconnection actually happen in steady
// state. connect() is idempotent, so the overlapping paths are safe.
chrome.runtime.onStartup?.addListener(() => {
  void ensureOffscreen();
  connect();
});
chrome.runtime.onInstalled?.addListener(() => {
  void ensureOffscreen();
  connect();
});

// Periodic keep-alive/reconnect. Once the port is gone and the worker is dead,
// NOTHING else is guaranteed to wake the SW - the alarm is what revives the
// port after idle death. 1 minute is Chrome's minimum periodInMinutes.
export const KEEPALIVE_ALARM = "vadgr-cua-keepalive";
chrome.alarms?.create?.(KEEPALIVE_ALARM, { periodInMinutes: 1 });
chrome.alarms?.onAlarm?.addListener((alarm) => {
  if (alarm?.name !== KEEPALIVE_ALARM) return;
  void ensureOffscreen();
  connect();
});

// The offscreen document's ~20s heartbeat lands here; merely dispatching it
// wakes the SW (re-running this module), and answering it gives a faster
// reconnect cadence than the 1-minute alarm while the offscreen page lives.
chrome.runtime.onMessage?.addListener((msg) => {
  if (msg?.type === "keepalive") {
    void ensureOffscreen();
    connect();
  }
});

// EVERY service-worker start - including idle-death wake-ups that fire neither
// onStartup nor onInstalled - re-creates the offscreen document and
// re-establishes the native port. This is the primary fix for issue #36.
void ensureOffscreen();
connect();

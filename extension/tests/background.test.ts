// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// Service-worker (re)connect wiring - issue #36 defect 2. The MV3 worker is
// idle-terminated (~30s); a later wake re-runs the module top level but fires
// neither onStartup nor onInstalled, so the module top level itself, a periodic
// chrome.alarms keep-alive, and the offscreen heartbeat message must all reach
// an IDEMPOTENT connect(). These tests drive src/background.ts against a
// chrome.* stub: importing the module IS a service-worker start.

import { describe, it, expect, vi, beforeEach } from "vitest";

type Listener = (...args: any[]) => void;

function fakePort() {
  const disconnectListeners: Listener[] = [];
  return {
    onMessage: { addListener: vi.fn() },
    onDisconnect: {
      addListener: (fn: Listener) => disconnectListeners.push(fn),
    },
    postMessage: vi.fn(),
    fireDisconnect: () => disconnectListeners.forEach((fn) => fn()),
  };
}

function chromeStub() {
  const ports: ReturnType<typeof fakePort>[] = [];
  const alarmListeners: Listener[] = [];
  const messageListeners: Listener[] = [];
  const startupListeners: Listener[] = [];
  const installedListeners: Listener[] = [];
  const connectNative = vi.fn(() => {
    const p = fakePort();
    ports.push(p);
    return p;
  });
  const alarmsCreate = vi.fn();
  const hasDocument = vi.fn(async () => true); // offscreen already exists
  const stub = {
    runtime: {
      getManifest: () => ({ version: "0.6.5" }),
      connectNative,
      onStartup: { addListener: (fn: Listener) => startupListeners.push(fn) },
      onInstalled: { addListener: (fn: Listener) => installedListeners.push(fn) },
      onMessage: { addListener: (fn: Listener) => messageListeners.push(fn) },
    },
    alarms: {
      create: alarmsCreate,
      onAlarm: { addListener: (fn: Listener) => alarmListeners.push(fn) },
    },
    offscreen: { hasDocument, createDocument: vi.fn(async () => {}) },
    tabs: {
      onCreated: { addListener: vi.fn() },
      onRemoved: { addListener: vi.fn() },
    },
    storage: {
      local: { get: vi.fn(async () => ({})), set: vi.fn(async () => {}) },
    },
    windows: { getAll: vi.fn(async () => []) },
  };
  return {
    stub,
    ports,
    connectNative,
    alarmsCreate,
    hasDocument,
    alarmListeners,
    messageListeners,
    startupListeners,
    installedListeners,
  };
}

async function importBackground(env = chromeStub()) {
  vi.resetModules();
  vi.stubGlobal("chrome", env.stub);
  const mod = await import("../src/background");
  return { ...env, mod };
}

beforeEach(() => {
  vi.unstubAllGlobals();
});

describe("service-worker start (module top level)", () => {
  it("calls connect() unconditionally - not just from onStartup/onInstalled", async () => {
    const { connectNative } = await importBackground();
    // The import itself (any SW start, including an idle-death wake) connects.
    expect(connectNative).toHaveBeenCalledTimes(1);
    expect(connectNative).toHaveBeenCalledWith("com.vadgr.cua");
  });

  it("calls ensureOffscreen() at top level", async () => {
    const { hasDocument } = await importBackground();
    expect(hasDocument).toHaveBeenCalled();
  });

  it("still registers onStartup and onInstalled listeners", async () => {
    const { startupListeners, installedListeners } = await importBackground();
    expect(startupListeners).toHaveLength(1);
    expect(installedListeners).toHaveLength(1);
  });

  it("registers the keep-alive alarm with a 1-minute period", async () => {
    const { alarmsCreate, mod } = await importBackground();
    expect(alarmsCreate).toHaveBeenCalledWith(mod.KEEPALIVE_ALARM, {
      periodInMinutes: 1,
    });
  });
});

describe("connect() idempotency", () => {
  it("is a no-op while a port is already open", async () => {
    const { connectNative, mod } = await importBackground();
    expect(connectNative).toHaveBeenCalledTimes(1);
    mod.connect();
    mod.connect();
    expect(connectNative).toHaveBeenCalledTimes(1); // still just the first port
  });

  it("reconnects once the port has dropped", async () => {
    const { connectNative, ports, mod } = await importBackground();
    ports[0].fireDisconnect(); // Chrome refused / host died -> port = null
    mod.connect();
    expect(connectNative).toHaveBeenCalledTimes(2);
  });

  it("survives a synchronous connectNative throw (schedules a retry instead)", async () => {
    const env = chromeStub();
    env.connectNative.mockImplementationOnce(() => {
      throw new Error("Specified native messaging host not found.");
    });
    const { mod, connectNative } = await importBackground(env);
    // The top-level call threw inside connect(); the module still loaded and
    // a later call can succeed.
    mod.connect();
    expect(connectNative).toHaveBeenCalledTimes(2);
  });
});

describe("keep-alive alarm", () => {
  it("re-establishes the port after idle death", async () => {
    const { connectNative, ports, alarmListeners, mod } = await importBackground();
    expect(alarmListeners).toHaveLength(1);
    ports[0].fireDisconnect(); // the port died with the idle SW
    alarmListeners[0]({ name: mod.KEEPALIVE_ALARM });
    expect(connectNative).toHaveBeenCalledTimes(2);
  });

  it("ignores alarms that are not the keep-alive", async () => {
    const { connectNative, ports, alarmListeners } = await importBackground();
    ports[0].fireDisconnect();
    alarmListeners[0]({ name: "some-other-alarm" });
    expect(connectNative).toHaveBeenCalledTimes(1);
  });

  it("is a no-op while the port is healthy (idempotent connect)", async () => {
    const { connectNative, alarmListeners, mod } = await importBackground();
    alarmListeners[0]({ name: mod.KEEPALIVE_ALARM });
    alarmListeners[0]({ name: mod.KEEPALIVE_ALARM });
    expect(connectNative).toHaveBeenCalledTimes(1);
  });
});

describe("offscreen heartbeat message", () => {
  it("reconnects on a keepalive message when the port is gone", async () => {
    const { connectNative, ports, messageListeners } = await importBackground();
    expect(messageListeners.length).toBeGreaterThan(0);
    ports[0].fireDisconnect();
    messageListeners.forEach((fn) => fn({ type: "keepalive" }));
    expect(connectNative).toHaveBeenCalledTimes(2);
  });

  it("ignores unrelated messages", async () => {
    const { connectNative, ports, messageListeners } = await importBackground();
    ports[0].fireDisconnect();
    messageListeners.forEach((fn) => fn({ type: "something-else" }));
    expect(connectNative).toHaveBeenCalledTimes(1);
  });
});

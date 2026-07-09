// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// TDD for TargetResolver — the single target authority, generalized in 0.6.0
// from one pin to a registry + `current`. resolve() keeps its signature (every
// op acts BY ID). The headline regression guard still holds: no code path
// resolves an op target via query({active,currentWindow}). Owned mode opens a
// dedicated window once; attach mode snapshots the active tab of the LAST-FOCUSED
// window exactly once; use_target reports {url, provenance}; state survives an SW
// idle-termination. (Cold-start / mid-task loud loss lives in loud_loss.test.ts.)

import { describe, it, expect, vi } from "vitest";
import { TargetResolver, TargetLost, type TabsLike } from "../src/target/resolver";
import { OwnedWindowManager } from "../src/target/owned_window";
import type { PersistedState, TargetStore } from "../src/target/store";
import type { WindowsEnumApi } from "../src/target/enumeration";

function memStore(initial: PersistedState | null = null): TargetStore {
  let state = initial;
  return {
    async load() {
      return state;
    },
    async save(s) {
      state = s;
    },
  };
}

// A tabs fake that tracks which live tab ids exist and records query calls.
function fakeTabs(opts: {
  live?: Set<number>;
  windowOf?: (id: number) => number;
  active?: { id: number; windowId: number; url?: string };
  urlOf?: (id: number) => string;
}) {
  const live = opts.live ?? new Set<number>();
  const queryCalls: any[] = [];
  const tabs: TabsLike = {
    async get(tabId) {
      if (!live.has(tabId)) throw new Error("No tab with id");
      return {
        id: tabId,
        windowId: opts.windowOf ? opts.windowOf(tabId) : 1,
        url: opts.urlOf ? opts.urlOf(tabId) : "https://x",
      };
    },
    async query(q) {
      queryCalls.push(q);
      return opts.active ? [opts.active] : [];
    },
  };
  return { tabs, queryCalls, live };
}

const noWindows: WindowsEnumApi = { getAll: async () => [] };

function ownedManager(win: any) {
  const create = vi.fn(async () => ({ windowId: win.id, tabId: win.tabs[0].id }));
  const owm = new OwnedWindowManager({} as any);
  (owm as any).create = create;
  return { owm, create };
}

function makeResolver(opts: {
  tabs: TabsLike;
  owm: OwnedWindowManager;
  store?: TargetStore;
}) {
  return new TargetResolver({
    tabs: opts.tabs,
    owned: opts.owm,
    windowsApi: noWindows,
    store: opts.store ?? memStore(),
  });
}

describe("TargetResolver — owned mode (default)", () => {
  it("opens a dedicated window ONCE when there is no live target and pins it", async () => {
    const { tabs } = fakeTabs({ live: new Set([137]) });
    const { owm, create } = ownedManager({ id: 42, tabs: [{ id: 137 }] });
    const r = makeResolver({ tabs, owm });

    expect(await r.resolve()).toEqual({ windowId: 42, tabId: 137 });
    expect(await r.resolve()).toEqual({ windowId: 42, tabId: 137 });
    expect(create).toHaveBeenCalledTimes(1);
  });

  it("NEVER queries {active, currentWindow} for op targeting (the headline bug)", async () => {
    const { tabs, queryCalls } = fakeTabs({ live: new Set([137]) });
    const { owm } = ownedManager({ id: 42, tabs: [{ id: 137 }] });
    const r = makeResolver({ tabs, owm });
    await r.resolve();
    await r.resolve();
    expect(queryCalls).toHaveLength(0);
  });
});

describe("TargetResolver — attach mode", () => {
  it("snapshots the active tab of the LAST-FOCUSED window exactly once, then pins by id", async () => {
    const { tabs, queryCalls } = fakeTabs({
      live: new Set([9]),
      active: { id: 9, windowId: 3, url: "https://page" },
    });
    const { owm } = ownedManager({ id: 0, tabs: [{ id: 0 }] });
    const r = makeResolver({ tabs, owm });

    const pinned = await r.useTarget({ mode: "attach" });
    expect(pinned).toMatchObject({
      windowId: 3,
      tabId: 9,
      created: false,
      provenance: "attached",
      url: "https://page",
    });
    expect(queryCalls).toEqual([{ active: true, lastFocusedWindow: true }]);

    await r.resolve();
    expect(queryCalls).toHaveLength(1); // ops resolve by id — no further active query
  });

  it("raises target_lost when there is no active tab to attach to", async () => {
    const { tabs } = fakeTabs({ live: new Set() });
    const { owm, create } = ownedManager({ id: 0, tabs: [{ id: 0 }] });
    const r = makeResolver({ tabs, owm });
    await expect(r.useTarget({ mode: "attach" })).rejects.toBeInstanceOf(TargetLost);
    expect(create).not.toHaveBeenCalled();
  });
});

describe("TargetResolver — use_target by id + provenance", () => {
  it("pins an explicit {window_id, tab_id} as attached, reporting url, without opening a window", async () => {
    const { tabs } = fakeTabs({ live: new Set([9]), windowOf: () => 3, urlOf: () => "https://p" });
    const { owm, create } = ownedManager({ id: 0, tabs: [{ id: 0 }] });
    const r = makeResolver({ tabs, owm });
    const out = await r.useTarget({ windowId: 3, tabId: 9 });
    expect(out).toMatchObject({
      windowId: 3,
      tabId: 9,
      created: false,
      provenance: "attached",
      url: "https://p",
    });
    expect(create).not.toHaveBeenCalled();
  });

  it("owned use_target with no ids opens a window and reports created:true, provenance owned", async () => {
    const { tabs } = fakeTabs({ live: new Set([137]), windowOf: () => 42 });
    const { owm } = ownedManager({ id: 42, tabs: [{ id: 137 }] });
    const r = makeResolver({ tabs, owm });
    const out = await r.useTarget({ mode: "owned" });
    expect(out).toMatchObject({ windowId: 42, tabId: 137, created: true, provenance: "owned" });
  });
});

describe("TargetResolver — persistence", () => {
  it("survives a simulated SW idle-termination: re-hydrates the pinned target from the store", async () => {
    const { tabs } = fakeTabs({ live: new Set([137]), windowOf: () => 42 });
    const { owm, create } = ownedManager({ id: 42, tabs: [{ id: 137 }] });
    const store = memStore();
    const r1 = makeResolver({ tabs, owm, store });
    await r1.resolve();
    expect(create).toHaveBeenCalledTimes(1);

    const r2 = makeResolver({ tabs, owm, store });
    expect(await r2.resolve()).toEqual({ windowId: 42, tabId: 137 });
    expect(create).toHaveBeenCalledTimes(1); // no second window opened
  });
});

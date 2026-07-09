// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// TDD for TargetResolver — the single target authority. It pins a {windowId,
// tabId} and every op resolves through it BY ID. The headline regression guard:
// no code path resolves an op target via query({active,currentWindow}). Owned
// mode opens a dedicated window once; attach mode snapshots the active tab of the
// LAST-FOCUSED window exactly once; loss is loud (target_lost), never a silent
// grab of the user's active tab.

import { describe, it, expect, vi } from "vitest";
import { TargetResolver, TargetLost, type TabsLike } from "../src/target/resolver";
import { OwnedWindowManager } from "../src/target/owned_window";
import type { PersistedState, TargetStore } from "../src/target/store";

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
  active?: { id: number; windowId: number };
}) {
  const live = opts.live ?? new Set<number>();
  const queryCalls: any[] = [];
  const tabs: TabsLike = {
    async get(tabId) {
      if (!live.has(tabId)) throw new Error("No tab with id");
      return { id: tabId, windowId: opts.windowOf ? opts.windowOf(tabId) : 1 };
    },
    async query(q) {
      queryCalls.push(q);
      return opts.active ? [opts.active] : [];
    },
  };
  return { tabs, queryCalls, live };
}

function ownedManager(win: any) {
  const create = vi.fn(async () => win);
  const owm = new OwnedWindowManager({ create } as any);
  return { owm, create };
}

describe("TargetResolver — owned mode (default)", () => {
  it("opens a dedicated window ONCE when there is no live target and pins it", async () => {
    const { tabs } = fakeTabs({ live: new Set([137]) });
    const { owm, create } = ownedManager({ id: 42, tabs: [{ id: 137 }] });
    const r = new TargetResolver({ tabs, owned: owm, store: memStore() });

    const a = await r.resolve();
    expect(a).toEqual({ windowId: 42, tabId: 137 });
    // A second resolve reuses the pinned target — no second window.
    const b = await r.resolve();
    expect(b).toEqual({ windowId: 42, tabId: 137 });
    expect(create).toHaveBeenCalledTimes(1);
  });

  it("NEVER queries {active, currentWindow} for op targeting (the headline bug)", async () => {
    const { tabs, queryCalls } = fakeTabs({ live: new Set([137]) });
    const { owm } = ownedManager({ id: 42, tabs: [{ id: 137 }] });
    const r = new TargetResolver({ tabs, owned: owm, store: memStore() });
    await r.resolve();
    await r.resolve();
    // No active-tab query at all in owned mode.
    expect(queryCalls).toHaveLength(0);
  });

  it("re-establishes a fresh owned window when the pinned tab was closed", async () => {
    const { tabs, live } = fakeTabs({ live: new Set([137]) });
    const { owm, create } = ownedManager({ id: 43, tabs: [{ id: 200 }] });
    // Start already pinned to a now-dead tab.
    const store = memStore({ target: { windowId: 42, tabId: 137 }, mode: "owned" });
    const r = new TargetResolver({ tabs, owned: owm, store });
    live.delete(137); // user closed it
    const t = await r.resolve();
    expect(t).toEqual({ windowId: 43, tabId: 200 });
    expect(create).toHaveBeenCalledTimes(1);
  });
});

describe("TargetResolver — attach mode", () => {
  it("snapshots the active tab of the LAST-FOCUSED window exactly once, then pins by id", async () => {
    const { tabs, queryCalls } = fakeTabs({
      live: new Set([9]),
      active: { id: 9, windowId: 3 },
    });
    const { owm } = ownedManager({ id: 0, tabs: [{ id: 0 }] });
    const r = new TargetResolver({ tabs, owned: owm, store: memStore() });

    const pinned = await r.useTarget({ mode: "attach" });
    expect(pinned).toEqual({ windowId: 3, tabId: 9, created: false });
    // Exactly one active-tab query, scoped to lastFocusedWindow (never bare active).
    expect(queryCalls).toEqual([{ active: true, lastFocusedWindow: true }]);

    // Subsequent ops resolve by id — NO further active query.
    await r.resolve();
    expect(queryCalls).toHaveLength(1);
  });

  it("raises target_lost when the attached tab is closed — never grabs the user's active tab", async () => {
    const { tabs, live } = fakeTabs({
      live: new Set([9]),
      active: { id: 9, windowId: 3 },
    });
    const { owm, create } = ownedManager({ id: 0, tabs: [{ id: 0 }] });
    const r = new TargetResolver({ tabs, owned: owm, store: memStore() });
    await r.useTarget({ mode: "attach" });
    live.delete(9); // user closed the attached tab
    await expect(r.resolve()).rejects.toBeInstanceOf(TargetLost);
    // It must NOT have opened an owned window as a silent fallback.
    expect(create).not.toHaveBeenCalled();
  });
});

describe("TargetResolver — use_target by id + persistence", () => {
  it("pins an explicit {window_id, tab_id} without opening a window", async () => {
    const { tabs } = fakeTabs({ live: new Set([9]), windowOf: () => 3 });
    const { owm, create } = ownedManager({ id: 0, tabs: [{ id: 0 }] });
    const r = new TargetResolver({ tabs, owned: owm, store: memStore() });
    const out = await r.useTarget({ windowId: 3, tabId: 9 });
    expect(out).toEqual({ windowId: 3, tabId: 9, created: false });
    expect(create).not.toHaveBeenCalled();
  });

  it("owned use_target with no ids opens a window and reports created:true", async () => {
    const { tabs } = fakeTabs({ live: new Set([137]) });
    const { owm } = ownedManager({ id: 42, tabs: [{ id: 137 }] });
    const r = new TargetResolver({ tabs, owned: owm, store: memStore() });
    const out = await r.useTarget({ mode: "owned" });
    expect(out).toEqual({ windowId: 42, tabId: 137, created: true });
  });

  it("survives a simulated SW idle-termination: re-hydrates the pinned target from the store", async () => {
    const { tabs } = fakeTabs({ live: new Set([137]) });
    const { owm, create } = ownedManager({ id: 42, tabs: [{ id: 137 }] });
    const store = memStore();
    // First worker instance pins the owned window.
    const r1 = new TargetResolver({ tabs, owned: owm, store });
    await r1.resolve();
    expect(create).toHaveBeenCalledTimes(1);
    // A fresh resolver (SW was terminated + restarted) re-hydrates from the store.
    const r2 = new TargetResolver({ tabs, owned: owm, store });
    const t = await r2.resolve();
    expect(t).toEqual({ windowId: 42, tabId: 137 });
    expect(create).toHaveBeenCalledTimes(1); // no second window opened
  });
});

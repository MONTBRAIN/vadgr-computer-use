// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// TDD for the 0.6.0 headline: LOUD LOSS. resolve() splits a COLD start (never
// established -> auto-open the owned window ONCE) from a MID-TASK loss
// (established, current gone -> raise target_lost, NEVER a silent blank re-open).
// The split rides on the persisted `established` flag, so it survives a simulated
// SW idle-termination (persist + re-hydrate) and still raises loud.

import { describe, it, expect, vi } from "vitest";
import { TargetResolver, TargetLost, type TabsLike } from "../src/target/resolver";
import { OwnedWindowManager } from "../src/target/owned_window";
import type { PersistedState, TargetStore } from "../src/target/store";
import type { WindowsEnumApi } from "../src/target/enumeration";

function memStore(initial: PersistedState | null = null): {
  store: TargetStore;
  peek: () => PersistedState | null;
} {
  let state = initial;
  return {
    store: {
      async load() {
        return state;
      },
      async save(s) {
        state = s;
      },
    },
    peek: () => state,
  };
}

function fakeTabs(live: Set<number>, windowOf: (id: number) => number = () => 42): TabsLike {
  return {
    async get(tabId) {
      if (!live.has(tabId)) throw new Error("No tab with id");
      return { id: tabId, windowId: windowOf(tabId), url: "https://x" };
    },
    async query() {
      return [];
    },
  };
}

const noWindows: WindowsEnumApi = { getAll: async () => [] };

function ownedManager(win: any) {
  const create = vi.fn(async () => ({ windowId: win.id, tabId: win.tabs[0].id }));
  const owned = new OwnedWindowManager({} as any);
  (owned as any).create = create;
  return { owned, create };
}

describe("loud loss — cold start vs mid-task", () => {
  it("cold start (never established) auto-opens the owned window exactly once", async () => {
    const { owned, create } = ownedManager({ id: 42, tabs: [{ id: 137 }] });
    const r = new TargetResolver({
      tabs: fakeTabs(new Set([137])),
      owned,
      windowsApi: noWindows,
      store: memStore().store,
    });
    const a = await r.resolve();
    expect(a).toEqual({ windowId: 42, tabId: 137 });
    const b = await r.resolve();
    expect(b).toEqual({ windowId: 42, tabId: 137 });
    expect(create).toHaveBeenCalledTimes(1); // reused, never re-opened
  });

  it("a closed current tab makes the next resolve() raise target_lost — NEVER re-opens", async () => {
    const live = new Set([137]);
    const { owned, create } = ownedManager({ id: 42, tabs: [{ id: 137 }] });
    const r = new TargetResolver({
      tabs: fakeTabs(live),
      owned,
      windowsApi: noWindows,
      store: memStore().store,
    });
    await r.resolve(); // establish the owned target
    expect(create).toHaveBeenCalledTimes(1);

    live.delete(137); // the current tab is closed mid-task
    await expect(r.resolve()).rejects.toBeInstanceOf(TargetLost);
    // The loud path must NOT have opened a fresh blank owned window.
    expect(create).toHaveBeenCalledTimes(1);
  });

  it("the cold/mid-task split survives an SW idle-termination (persist + re-hydrate)", async () => {
    const live = new Set([137]);
    const mem = memStore();
    const { owned, create } = ownedManager({ id: 42, tabs: [{ id: 137 }] });
    const r1 = new TargetResolver({
      tabs: fakeTabs(live),
      owned,
      windowsApi: noWindows,
      store: mem.store,
    });
    await r1.resolve(); // establish + persist established:true + current:137
    expect(mem.peek()?.registry.established).toBe(true);

    // The SW idle-terminates; the current tab is closed while it slept.
    live.delete(137);
    // A fresh resolver wakes, re-hydrates from the store, and must STILL raise
    // loud — the persisted `established` proves this is not a cold start.
    const r2 = new TargetResolver({
      tabs: fakeTabs(live),
      owned,
      windowsApi: noWindows,
      store: mem.store,
    });
    await expect(r2.resolve()).rejects.toBeInstanceOf(TargetLost);
    expect(create).toHaveBeenCalledTimes(1); // r2 never opened a second window
  });

  it("after a loud loss, use_target re-pins a real tab and resume works", async () => {
    const live = new Set([137, 500]);
    const { owned } = ownedManager({ id: 42, tabs: [{ id: 137 }] });
    const r = new TargetResolver({
      tabs: fakeTabs(live, (id) => (id === 500 ? 61 : 42)),
      owned,
      windowsApi: noWindows,
      store: memStore().store,
    });
    await r.resolve();
    live.delete(137);
    await expect(r.resolve()).rejects.toBeInstanceOf(TargetLost);
    // Re-orient onto the real tab (from tabs.list), then resume.
    const out = await r.useTarget({ windowId: 61, tabId: 500 });
    expect(out).toMatchObject({ windowId: 61, tabId: 500, provenance: "attached" });
    expect(await r.resolve()).toEqual({ windowId: 61, tabId: 500 });
  });
});

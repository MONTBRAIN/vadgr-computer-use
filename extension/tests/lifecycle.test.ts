// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// TDD for the target lifecycle listeners (0.6.0 registry model). A tab spawned
// FROM an OWNED tab (openerTabId is owned: _blank, OAuth popup) re-pins so the
// agent follows its own flow; a tab whose opener we do NOT own is left alone
// (stays a `user` context). A closed tab is forgotten — if it was `current`, the
// next resolve() raises target_lost (established stays true), never a silent
// re-open. We NEVER silently grab the user's active tab here.

import { describe, it, expect, vi } from "vitest";
import { Lifecycle } from "../src/target/lifecycle";

function fakeResolver(ownedTabs: Set<number>) {
  return {
    isOwnedTab: vi.fn(async (id: number) => ownedTabs.has(id)),
    pin: vi.fn(async () => {}),
    onTabClosed: vi.fn(async () => {}),
  };
}

describe("Lifecycle.onTabCreated", () => {
  it("re-pins a tab spawned FROM an owned tab (our own action)", async () => {
    const resolver = fakeResolver(new Set([10]));
    const life = new Lifecycle(resolver as any);
    await life.onTabCreated({ id: 11, windowId: 1, openerTabId: 10 });
    expect(resolver.pin).toHaveBeenCalledWith({ windowId: 1, tabId: 11 });
  });

  it("ignores a tab whose opener we do not own (a user-driven spawn)", async () => {
    const resolver = fakeResolver(new Set([10]));
    const life = new Lifecycle(resolver as any);
    await life.onTabCreated({ id: 99, windowId: 5, openerTabId: 55 });
    expect(resolver.pin).not.toHaveBeenCalled();
  });

  it("ignores a tab with no opener link at all", async () => {
    const resolver = fakeResolver(new Set([10]));
    const life = new Lifecycle(resolver as any);
    await life.onTabCreated({ id: 11, windowId: 1 });
    expect(resolver.pin).not.toHaveBeenCalled();
  });
});

describe("Lifecycle.onTabRemoved", () => {
  it("forgets the closed tab (the registry decides if it was current)", async () => {
    const resolver = fakeResolver(new Set([10]));
    const life = new Lifecycle(resolver as any);
    await life.onTabRemoved(10);
    expect(resolver.onTabClosed).toHaveBeenCalledWith(10);
  });
});

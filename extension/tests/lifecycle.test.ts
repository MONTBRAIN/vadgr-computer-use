// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// TDD for the target lifecycle listeners. A tab spawned BY our own action
// (openerTabId === the pinned tab: _blank, OAuth popup) re-pins so the agent
// follows the flow; a user-opened tab does NOT. When the pinned tab is closed we
// clear it (the next resolve re-establishes in owned mode / raises in attach) —
// we NEVER silently grab the user's active tab here.

import { describe, it, expect, vi } from "vitest";
import { Lifecycle } from "../src/target/lifecycle";

function fakeResolver(pinned: { windowId: number; tabId: number } | null) {
  return {
    current: () => pinned,
    pin: vi.fn(async () => {}),
    markLost: vi.fn(async () => {}),
  };
}

describe("Lifecycle.onTabCreated", () => {
  it("re-pins to a tab spawned FROM the pinned tab (our own action)", async () => {
    const resolver = fakeResolver({ windowId: 1, tabId: 10 });
    const life = new Lifecycle(resolver as any);
    await life.onTabCreated({ id: 11, windowId: 1, openerTabId: 10 });
    expect(resolver.pin).toHaveBeenCalledWith({ windowId: 1, tabId: 11 });
  });

  it("ignores a user-opened tab (no opener link to the pinned tab)", async () => {
    const resolver = fakeResolver({ windowId: 1, tabId: 10 });
    const life = new Lifecycle(resolver as any);
    await life.onTabCreated({ id: 99, windowId: 5 });
    expect(resolver.pin).not.toHaveBeenCalled();
  });

  it("does nothing when there is no pinned target yet", async () => {
    const resolver = fakeResolver(null);
    const life = new Lifecycle(resolver as any);
    await life.onTabCreated({ id: 11, windowId: 1, openerTabId: 10 });
    expect(resolver.pin).not.toHaveBeenCalled();
  });
});

describe("Lifecycle.onTabRemoved", () => {
  it("marks the target lost when the pinned tab is closed", async () => {
    const resolver = fakeResolver({ windowId: 1, tabId: 10 });
    const life = new Lifecycle(resolver as any);
    await life.onTabRemoved(10);
    expect(resolver.markLost).toHaveBeenCalledTimes(1);
  });

  it("ignores closure of an unrelated tab", async () => {
    const resolver = fakeResolver({ windowId: 1, tabId: 10 });
    const life = new Lifecycle(resolver as any);
    await life.onTabRemoved(77);
    expect(resolver.markLost).not.toHaveBeenCalled();
  });
});

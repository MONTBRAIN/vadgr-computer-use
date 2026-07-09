// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// TDD for the tabs / windows op-groups + the per-op target wrap. Sub-ops
// dispatch to chrome.tabs.* / chrome.windows.* by id; `switch` sets current and
// activates the tab but issues NO window focus (routing attention never steals
// the user's screen); `close` refuses a `user` context without force; every op
// result is wrapped with the resolved target context.

import { describe, it, expect, vi } from "vitest";
import {
  tabsGroupOp,
  windowsGroupOp,
  wrapWithTarget,
  type TabsMutApi,
  type WindowsMutApi,
  type TargetControl,
} from "../src/ops";
import type { Provenance } from "../src/target/registry";

function fakeControl(over: Partial<TargetControl> = {}): TargetControl {
  return {
    resolve: vi.fn(async () => ({ windowId: 42, tabId: 137 })),
    adoptCurrent: vi.fn(async (t, provenance) => ({ ...t, provenance })),
    provenanceOf: vi.fn(async () => "user" as Provenance),
    isOwnedWindow: vi.fn(async () => false),
    onTabClosed: vi.fn(async () => {}),
    onWindowClosed: vi.fn(async () => {}),
    enumerate: vi.fn(async () => ({ windows: [] })),
    listWindows: vi.fn(async () => ({ windows: [] })),
    ...over,
  };
}

describe("tabsGroupOp", () => {
  it("list delegates to the registry enumeration", async () => {
    const tree = { windows: [{ window_id: 42, focused: false, owned: true, tabs: [] }] };
    const resolver = fakeControl({ enumerate: vi.fn(async () => tree) });
    const tabs = {} as TabsMutApi;
    expect(await tabsGroupOp({ op: "list" }, { tabs, resolver })).toBe(tree);
  });

  it("open creates an owned tab in the owned window and sets current", async () => {
    const create = vi.fn(async () => ({ id: 200, windowId: 42, url: "https://x" }));
    const tabs = { create, update: vi.fn(), remove: vi.fn() } as unknown as TabsMutApi;
    const resolver = fakeControl();
    const out = await tabsGroupOp({ op: "open", url: "https://x" }, { tabs, resolver });
    // window_id defaulted to the owned window via resolve().
    expect(resolver.resolve).toHaveBeenCalled();
    expect(create).toHaveBeenCalledWith({ url: "https://x", windowId: 42, active: false });
    expect(resolver.adoptCurrent).toHaveBeenCalledWith(
      { windowId: 42, tabId: 200 },
      "owned",
      "https://x",
    );
    expect(out).toEqual({ window_id: 42, tab_id: 200, url: "https://x", created: true });
  });

  it("switch activates the tab in its window and sets current WITHOUT raising the window", async () => {
    const update = vi.fn(async (id: number) => ({ id, windowId: 61, url: "https://hn" }));
    const tabs = { create: vi.fn(), update, remove: vi.fn() } as unknown as TabsMutApi;
    const resolver = fakeControl();
    const out = await tabsGroupOp({ op: "switch", tab_id: 90 }, { tabs, resolver });
    // Activates within its window — the only mutation is {active:true}. There is
    // NO windows.update({focused}) here (this group has no windows API at all).
    expect(update).toHaveBeenCalledWith(90, { active: true });
    expect(out).toEqual({ window_id: 61, tab_id: 90, url: "https://hn", is_current: true });
  });

  it("close REFUSES a user tab without force, and never removes it", async () => {
    const remove = vi.fn(async () => {});
    const tabs = { create: vi.fn(), update: vi.fn(), remove } as unknown as TabsMutApi;
    const resolver = fakeControl({ provenanceOf: vi.fn(async () => "user" as Provenance) });
    await expect(tabsGroupOp({ op: "close", tab_id: 88 }, { tabs, resolver })).rejects.toThrow(
      /user tab.*force/i,
    );
    expect(remove).not.toHaveBeenCalled();
  });

  it("close removes a user tab WITH force, and clears it from the registry", async () => {
    const remove = vi.fn(async () => {});
    const tabs = { create: vi.fn(), update: vi.fn(), remove } as unknown as TabsMutApi;
    const resolver = fakeControl({ provenanceOf: vi.fn(async () => "user" as Provenance) });
    const out = await tabsGroupOp({ op: "close", tab_id: 88, force: true }, { tabs, resolver });
    expect(remove).toHaveBeenCalledWith(88);
    expect(resolver.onTabClosed).toHaveBeenCalledWith(88);
    expect(out).toEqual({ closed: true, tab_id: 88 });
  });

  it("close removes an OWNED tab without force", async () => {
    const remove = vi.fn(async () => {});
    const tabs = { create: vi.fn(), update: vi.fn(), remove } as unknown as TabsMutApi;
    const resolver = fakeControl({ provenanceOf: vi.fn(async () => "owned" as Provenance) });
    const out = await tabsGroupOp({ op: "close", tab_id: 137 }, { tabs, resolver });
    expect(remove).toHaveBeenCalledWith(137);
    expect(out).toEqual({ closed: true, tab_id: 137 });
  });
});

describe("windowsGroupOp", () => {
  it("list delegates to the thin enumeration", async () => {
    const out = { windows: [{ window_id: 42, focused: false, owned: true, tab_count: 1, active_tab_id: 137 }] };
    const resolver = fakeControl({ listWindows: vi.fn(async () => out) });
    expect(await windowsGroupOp({ op: "list" }, { windows: {} as WindowsMutApi, resolver })).toBe(out);
  });

  it("open creates a new owned window (unfocused by default) and sets current", async () => {
    const create = vi.fn(async () => ({ id: 77, tabs: [{ id: 300, url: "about:blank" }] }));
    const windows = { create, update: vi.fn(), remove: vi.fn() } as unknown as WindowsMutApi;
    const resolver = fakeControl();
    const out = await windowsGroupOp({ op: "open" }, { windows, resolver });
    expect(create).toHaveBeenCalledWith(
      expect.objectContaining({ focused: false, state: "normal" }),
    );
    expect(resolver.adoptCurrent).toHaveBeenCalledWith(
      { windowId: 77, tabId: 300 },
      "owned",
      "about:blank",
    );
    expect(out).toEqual({ window_id: 77, tab_id: 300, created: true });
  });

  it("focus is the explicit raise (windows.update focused:true)", async () => {
    const update = vi.fn(async () => ({}));
    const windows = { create: vi.fn(), update, remove: vi.fn() } as unknown as WindowsMutApi;
    const resolver = fakeControl();
    const out = await windowsGroupOp({ op: "focus", window_id: 61 }, { windows, resolver });
    expect(update).toHaveBeenCalledWith(61, { focused: true });
    expect(out).toEqual({ focused: true, window_id: 61 });
  });

  it("close REFUSES a non-owned window without force", async () => {
    const remove = vi.fn(async () => {});
    const windows = { create: vi.fn(), update: vi.fn(), remove } as unknown as WindowsMutApi;
    const resolver = fakeControl({ isOwnedWindow: vi.fn(async () => false) });
    await expect(
      windowsGroupOp({ op: "close", window_id: 61 }, { windows, resolver }),
    ).rejects.toThrow(/non-owned window.*force/i);
    expect(remove).not.toHaveBeenCalled();
  });

  it("close removes an owned window without force", async () => {
    const remove = vi.fn(async () => {});
    const windows = { create: vi.fn(), update: vi.fn(), remove } as unknown as WindowsMutApi;
    const resolver = fakeControl({ isOwnedWindow: vi.fn(async () => true) });
    const out = await windowsGroupOp({ op: "close", window_id: 42 }, { windows, resolver });
    expect(remove).toHaveBeenCalledWith(42);
    expect(resolver.onWindowClosed).toHaveBeenCalledWith(42);
    expect(out).toEqual({ closed: true, window_id: 42 });
  });
});

describe("wrapWithTarget — the per-op target context", () => {
  const ctx = { window_id: 42, tab_id: 137, url: "https://www.youtube.com/" };

  it("wraps an object op result with the resolved target context", async () => {
    const wrapped = wrapWithTarget(async () => ({ typed: 4, ok: true }), async () => ctx);
    expect(await wrapped({})).toEqual({ typed: 4, ok: true, target: ctx });
  });

  it("passes a non-object result (a bare string from read_text) through unchanged", async () => {
    const wrapped = wrapWithTarget(async () => "some text", async () => ctx);
    expect(await wrapped({})).toBe("some text");
  });

  it("does not double-wrap a result that already carries a target", async () => {
    const pre = { closed: true, target: { window_id: 1, tab_id: 2, url: "" } };
    const wrapped = wrapWithTarget(async () => pre, async () => ctx);
    expect(await wrapped({})).toBe(pre);
  });

  it("leaves the result untouched when there is no current target", async () => {
    const wrapped = wrapWithTarget(async () => ({ ok: true }), async () => null);
    expect(await wrapped({})).toEqual({ ok: true });
  });
});

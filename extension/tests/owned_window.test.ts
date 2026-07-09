// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// TDD for OwnedWindowManager — it opens a dedicated automation window in the
// user's real profile (chrome.windows.create), unfocused so it never fights the
// user's foreground tab, and pins its first tab. The chrome.windows glue is
// live-only; the sequencing + shape is pure and tested here against a fake.

import { describe, it, expect } from "vitest";
import { OwnedWindowManager, type WindowsLike } from "../src/target/owned_window";

function fakeWindows(win: any): { windows: WindowsLike; calls: any[] } {
  const calls: any[] = [];
  const windows: WindowsLike = {
    async create(opts) {
      calls.push(opts);
      return win;
    },
  };
  return { windows, calls };
}

describe("OwnedWindowManager", () => {
  it("creates an unfocused window and pins its first tab", async () => {
    const { windows, calls } = fakeWindows({ id: 42, tabs: [{ id: 137 }] });
    const owm = new OwnedWindowManager(windows);
    const target = await owm.create();
    expect(target).toEqual({ windowId: 42, tabId: 137 });
    // focused:false is the whole point — the user keeps working untouched.
    expect(calls[0].focused).toBe(false);
    // ...but NOT minimized: a real, sized viewport so hit-testing works.
    expect(calls[0].state).toBe("normal");
    expect(calls[0].height).toBeGreaterThan(0);
  });

  it("throws if the created window returns no tab", async () => {
    const { windows } = fakeWindows({ id: 42, tabs: [] });
    const owm = new OwnedWindowManager(windows);
    await expect(owm.create()).rejects.toThrow(/tab/i);
  });
});

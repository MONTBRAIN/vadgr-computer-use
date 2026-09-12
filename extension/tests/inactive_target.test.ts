// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.

import { afterEach, describe, expect, it, vi } from "vitest";
import {
  exactTargetReceivesTrustedKeyboard,
  runnableTargetTab,
} from "../src/ops";

function chromeFor(tab: Record<string, unknown>, focused = false) {
  vi.stubGlobal("chrome", {
    tabs: { get: vi.fn().mockResolvedValue(tab) },
    windows: { get: vi.fn().mockResolvedValue({ focused }) },
  });
}

const target = { _target: { window_id: 10, tab_id: 20 } };

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("exact inactive target preflight", () => {
  it("allows trusted keyboard only for an active tab in a focused window", async () => {
    chromeFor({ id: 20, windowId: 10, active: true, url: "https://example.test" }, true);
    await expect(exactTargetReceivesTrustedKeyboard(target)).resolves.toBe(true);
  });

  it("rejects trusted keyboard when either activation flag is false", async () => {
    chromeFor({ id: 20, windowId: 10, active: false, url: "https://example.test" }, false);
    await expect(exactTargetReceivesTrustedKeyboard(target)).resolves.toBe(false);
  });

  it("names discarded and frozen targets before page execution", async () => {
    chromeFor({ id: 20, windowId: 10, discarded: true, url: "https://example.test" });
    await expect(runnableTargetTab(target)).rejects.toMatchObject({ code: "target_discarded" });
    chromeFor({ id: 20, windowId: 10, frozen: true, url: "https://example.test" });
    await expect(runnableTargetTab(target)).rejects.toMatchObject({ code: "target_frozen" });
  });

  it("names browser-internal pages as restricted", async () => {
    chromeFor({ id: 20, windowId: 10, url: "chrome://settings/" });
    await expect(runnableTargetTab(target)).rejects.toMatchObject({ code: "target_restricted" });
  });
});

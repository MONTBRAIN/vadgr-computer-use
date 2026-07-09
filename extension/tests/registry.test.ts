// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// TDD for TargetRegistry — the multi-context model. Provenance tracks who
// created/adopted each context (owned / attached / user); `current` is the one
// the agent acts on; `established` splits cold start from mid-task loss and must
// survive persist + re-hydrate.

import { describe, it, expect } from "vitest";
import { TargetRegistry } from "../src/target/registry";

describe("TargetRegistry — provenance", () => {
  it("tags a created context owned and an unrelated tab user", () => {
    const reg = new TargetRegistry();
    reg.upsert({ windowId: 42, tabId: 137, provenance: "owned" });
    expect(reg.isOwned(137)).toBe(true);
    expect(reg.provenanceOf(137)).toBe("owned");
    // A tab the registry has never seen is the user's.
    expect(reg.provenanceOf(999)).toBe("user");
    expect(reg.isOwned(999)).toBe(false);
  });

  it("marks a user tab adopted via use_target as attached", () => {
    const reg = new TargetRegistry();
    reg.upsert({ windowId: 3, tabId: 9, provenance: "attached" });
    expect(reg.provenanceOf(9)).toBe("attached");
    expect(reg.isOwned(9)).toBe(false);
  });

  it("owned outranks a later attached re-adopt (owned never demoted)", () => {
    const reg = new TargetRegistry();
    reg.upsert({ windowId: 42, tabId: 137, provenance: "owned" });
    // Re-adopting the owned tab (e.g. tabs.switch) must keep it owned.
    reg.upsert({ windowId: 42, tabId: 137, provenance: "attached" });
    expect(reg.provenanceOf(137)).toBe("owned");
  });

  it("a window is owned iff it holds an owned tab", () => {
    const reg = new TargetRegistry();
    reg.upsert({ windowId: 42, tabId: 137, provenance: "owned" });
    reg.upsert({ windowId: 61, tabId: 88, provenance: "attached" });
    expect(reg.isOwnedWindow(42)).toBe(true);
    expect(reg.isOwnedWindow(61)).toBe(false);
    expect(reg.isOwnedWindow(999)).toBe(false);
  });
});

describe("TargetRegistry — current + established", () => {
  it("setCurrent moves the pointer and establishes the session", () => {
    const reg = new TargetRegistry();
    expect(reg.established).toBe(false);
    expect(reg.current).toBeNull();
    reg.upsert({ windowId: 42, tabId: 137, provenance: "owned" });
    reg.setCurrent(137);
    expect(reg.current).toBe(137);
    expect(reg.established).toBe(true);
    expect(reg.currentRecord()).toMatchObject({ tabId: 137, windowId: 42 });
  });

  it("forget of the current tab clears current but KEEPS established (loud loss)", () => {
    const reg = new TargetRegistry();
    reg.upsert({ windowId: 42, tabId: 137, provenance: "owned" });
    reg.setCurrent(137);
    reg.forget(137);
    expect(reg.current).toBeNull();
    expect(reg.established).toBe(true); // so the next resolve() raises, not re-opens
    expect(reg.has(137)).toBe(false);
  });

  it("forget of an unrelated tab leaves current untouched", () => {
    const reg = new TargetRegistry();
    reg.upsert({ windowId: 42, tabId: 137, provenance: "owned" });
    reg.setCurrent(137);
    reg.forget(88);
    expect(reg.current).toBe(137);
  });

  it("forgetWindow drops every tab of a window", () => {
    const reg = new TargetRegistry();
    reg.upsert({ windowId: 42, tabId: 137, provenance: "owned" });
    reg.upsert({ windowId: 42, tabId: 200, provenance: "owned" });
    reg.upsert({ windowId: 61, tabId: 88, provenance: "user" });
    reg.setCurrent(137);
    reg.forgetWindow(42);
    expect(reg.has(137)).toBe(false);
    expect(reg.has(200)).toBe(false);
    expect(reg.has(88)).toBe(true);
    expect(reg.current).toBeNull();
    expect(reg.established).toBe(true);
  });
});

describe("TargetRegistry — persistence", () => {
  it("provenance + current + established survive snapshot -> restore", () => {
    const reg = new TargetRegistry();
    reg.upsert({ windowId: 42, tabId: 137, provenance: "owned", lastSeenUrl: "https://a" });
    reg.upsert({ windowId: 61, tabId: 88, provenance: "attached" });
    reg.setCurrent(137);
    const state = reg.snapshot();

    const woken = new TargetRegistry();
    woken.restore(state);
    expect(woken.current).toBe(137);
    expect(woken.established).toBe(true);
    expect(woken.provenanceOf(137)).toBe("owned");
    expect(woken.provenanceOf(88)).toBe("attached");
    expect(woken.get(137)?.lastSeenUrl).toBe("https://a");
  });

  it("restore(null) yields a fresh empty registry", () => {
    const reg = new TargetRegistry();
    reg.upsert({ windowId: 1, tabId: 2, provenance: "owned" });
    reg.setCurrent(2);
    reg.restore(null);
    expect(reg.current).toBeNull();
    expect(reg.established).toBe(false);
    expect(reg.has(2)).toBe(false);
  });
});

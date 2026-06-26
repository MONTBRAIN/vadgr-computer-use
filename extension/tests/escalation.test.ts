// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// TDD for the escalation policy — the DOM→CDP routing driven by the read-back
// `ok`. Verification is the routing decision, so this is the load-bearing logic.

import { describe, it, expect, vi } from "vitest";
import { okIsFalse, withEscalation } from "../src/executors/escalation";
import type { Executor } from "../src/executors/types";

function fake(name: string, ret: unknown): Executor {
  return { name, execute: vi.fn(async () => ret) };
}
const interactive = () => true;
const notInteractive = () => false;

describe("okIsFalse (the escalation trigger)", () => {
  it("is true only for an explicit ok:false envelope", () => {
    expect(okIsFalse({ ok: false })).toBe(true);
    expect(okIsFalse({ ok: true })).toBe(false);
    expect(okIsFalse({ typed: 3 })).toBe(false); // no ok → not a trigger
    expect(okIsFalse({ navigated: true })).toBe(false);
    expect(okIsFalse("text")).toBe(false);
    expect(okIsFalse(null)).toBe(false);
  });
});

describe("withEscalation", () => {
  it("returns the DOM result and never calls CDP when ok is not false", async () => {
    const dom = fake("dom", { ok: true, value: "x" });
    const cdp = fake("cdp", { ok: true, via: "cdp" });
    const r = await withEscalation("fill", { selector: "#a" }, dom, cdp, interactive);
    expect(r).toEqual({ ok: true, value: "x" });
    expect(cdp.execute).not.toHaveBeenCalled();
  });

  it("escalates an interactive op to CDP on ok:false", async () => {
    const dom = fake("dom", { ok: false });
    const cdp = fake("cdp", { ok: true, via: "cdp" });
    const r = await withEscalation("fill", { selector: "#a", text: "hi" }, dom, cdp, interactive);
    expect(r).toEqual({ ok: true, via: "cdp" });
    expect(cdp.execute).toHaveBeenCalledWith("fill", { selector: "#a", text: "hi" });
  });

  it("does NOT escalate a non-interactive op even on ok:false", async () => {
    const dom = fake("dom", { ok: false });
    const cdp = fake("cdp", { ok: true });
    const r = await withEscalation("query", {}, dom, cdp, notInteractive);
    expect(r).toEqual({ ok: false });
    expect(cdp.execute).not.toHaveBeenCalled();
  });

  it("returns the DOM result unchanged when no CDP path is available", async () => {
    const dom = fake("dom", { ok: false });
    const r = await withEscalation("fill", {}, dom, null, interactive);
    expect(r).toEqual({ ok: false });
  });
});

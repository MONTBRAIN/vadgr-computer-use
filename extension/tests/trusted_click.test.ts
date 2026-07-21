// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// TDD for the trusted click: `HTMLElement.click()` fires ONE synthetic `click`
// with isTrusted:false and no pointer/mouse events at all, so widgets that open
// on `pointerdown` and act on `pointerup` ignore it while the op still reports
// success. This covers the three parts of the fix: the CDP click sequencing, the
// content-script self-verify that triggers escalation, and the routing.

import { describe, it, expect, beforeEach, vi } from "vitest";
import { CdpExecutor, type CdpSend } from "../src/executors/cdp";
import { opClick } from "../src/content/ops";
import { withEscalation } from "../src/executors/escalation";
import type { Executor } from "../src/executors/types";

// A scriptable fake sender; `evalFor` decides what a Runtime.evaluate returns.
function fakeSend(evalFor: (expr: string) => unknown = () => null) {
  const calls: Array<{ method: string; params: any }> = [];
  const send: CdpSend = async (method, params: any = {}) => {
    calls.push({ method, params });
    if (method === "Runtime.evaluate") {
      return { result: { value: evalFor(String(params.expression)) } };
    }
    return {};
  };
  return { send, calls };
}

const exec = (send: CdpSend) => new CdpExecutor(async () => send);

const rect = (x = 10, y = 20) => ({ x, y, covered: false, found: true });

describe("CdpExecutor.click", () => {
  it("dispatches a full trusted mouse stream at the element centre", async () => {
    const { send, calls } = fakeSend((e) =>
      e.includes("getBoundingClientRect") ? rect(42, 84) : null,
    );
    const r: any = await exec(send).execute("click", { selector: ".btn" });

    expect(r.clicked).toBe(true);
    expect(r.via).toBe("cdp");
    expect(r.x).toBe(42);
    expect(r.y).toBe(84);

    const mouse = calls.filter((c) => c.method === "Input.dispatchMouseEvent");
    expect(mouse.map((m) => m.params.type)).toEqual([
      "mouseMoved",
      "mousePressed",
      "mouseReleased",
    ]);
    // Coordinates are viewport CSS px straight from getBoundingClientRect —
    // no DPR or window-chrome correction anywhere.
    for (const m of mouse) {
      expect(m.params.x).toBe(42);
      expect(m.params.y).toBe(84);
    }
    expect(mouse[1].params).toMatchObject({ button: "left", clickCount: 1, buttons: 1 });
    expect(mouse[2].params).toMatchObject({ button: "left", clickCount: 1, buttons: 0 });
  });

  it("throws when the selector matches nothing", async () => {
    const { send } = fakeSend(() => null);
    await expect(exec(send).execute("click", { selector: ".gone" })).rejects.toThrow(
      /no element matches/,
    );
  });

  it("throws when the centre point is covered, unless force", async () => {
    const covered = (e: string) =>
      e.includes("getBoundingClientRect")
        ? { x: 1, y: 2, covered: true, found: true }
        : null;
    const { send } = fakeSend(covered);
    await expect(exec(send).execute("click", { selector: ".btn" })).rejects.toThrow(
      /covered/,
    );

    const { send: send2, calls } = fakeSend(covered);
    const r: any = await exec(send2).execute("click", { selector: ".btn", force: true });
    expect(r.clicked).toBe(true);
    expect(calls.filter((c) => c.method === "Input.dispatchMouseEvent")).toHaveLength(3);
  });

  it("reports ok from the state-signature diff", async () => {
    let state = "closed";
    const { send } = fakeSend((e) => {
      if (e.includes("getBoundingClientRect")) return rect();
      if (e.includes("data-state")) return `data-state=${state}`;
      return null;
    });
    const wrapped: CdpSend = async (m, p: any) => {
      if (m === "Input.dispatchMouseEvent" && p.type === "mouseReleased") state = "open";
      return send(m, p);
    };
    const r: any = await exec(wrapped).execute("click", { selector: ".menu" });
    expect(r.ok).toBe(true);
  });

  it("reports ok:false when a state-bearing widget did not react", async () => {
    const { send } = fakeSend((e) => {
      if (e.includes("getBoundingClientRect")) return rect();
      if (e.includes("data-state")) return "data-state=closed";
      return null;
    });
    const r: any = await exec(send).execute("click", { selector: ".menu" });
    expect(r.ok).toBe(false);
  });

  it("treats a vanished element as having reacted", async () => {
    let gone = false;
    const { send } = fakeSend((e) => {
      if (e.includes("getBoundingClientRect")) return rect();
      if (e.includes("data-state")) return gone ? null : "data-state=open";
      return null;
    });
    const wrapped: CdpSend = async (m, p: any) => {
      if (m === "Input.dispatchMouseEvent" && p.type === "mouseReleased") gone = true;
      return send(m, p);
    };
    const r: any = await exec(wrapped).execute("click", { selector: ".item" });
    expect(r.ok).toBe(true);
  });

  it("omits ok entirely for an element with no state to diff", async () => {
    const { send } = fakeSend((e) =>
      e.includes("getBoundingClientRect") ? rect() : null,
    );
    const r: any = await exec(send).execute("click", { selector: "button" });
    expect(r).not.toHaveProperty("ok");
  });
});

describe("opClick self-verify (the escalation trigger)", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("returns ok:false when a data-state widget ignores the synthetic click", async () => {
    // A pointerdown-driven widget: HTMLElement.click() fires no pointer events,
    // so it never opens.
    document.body.innerHTML = `<button id="m" data-state="closed">Menu</button>`;
    const el = document.getElementById("m")!;
    el.addEventListener("pointerdown", () => el.setAttribute("data-state", "open"));

    const r: any = await opClick({ selector: "#m" });
    expect(r.clicked).toBe(true);
    expect(r.ok).toBe(false);
    expect(el.getAttribute("data-state")).toBe("closed");
  });

  it("returns ok:true when the widget does react to the synthetic click", async () => {
    document.body.innerHTML = `<button id="m" aria-expanded="false">Menu</button>`;
    const el = document.getElementById("m")!;
    el.addEventListener("click", () => el.setAttribute("aria-expanded", "true"));

    const r: any = await opClick({ selector: "#m" });
    expect(r.ok).toBe(true);
  });

  it("reports no ok for a plain button, so it never escalates spuriously", async () => {
    document.body.innerHTML = `<button id="b">Go</button>`;
    const r: any = await opClick({ selector: "#b" });
    expect(r.clicked).toBe(true);
    expect(r).not.toHaveProperty("ok");
  });

  it("keeps the checked read-back for natives and does not ok-gate them", async () => {
    // Escalating a native would re-click and toggle it back.
    document.body.innerHTML = `<input id="c" type="checkbox" />`;
    const r: any = await opClick({ selector: "#c" });
    expect(r.checked).toBe(true);
    expect(r).not.toHaveProperty("ok");
  });

  it("finds an element inside an open shadow root", async () => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = host.attachShadow({ mode: "open" });
    root.innerHTML = `<button id="deep">Deep</button>`;
    const deep = root.getElementById("deep")!;
    let hits = 0;
    deep.addEventListener("click", () => hits++);

    const r: any = await opClick({ selector: "#deep", force: true });
    expect(r.clicked).toBe(true);
    expect(hits).toBe(1);
  });
});

describe("click routing", () => {
  const result = (v: unknown, name = "fake"): Executor =>
    ({ name, execute: vi.fn(async () => v) }) as unknown as Executor;

  it("escalates DOM -> CDP when the DOM read-back says ok:false", async () => {
    const dom = result({ clicked: true, ok: false });
    const cdp = result({ clicked: true, ok: true, via: "cdp" });
    const r: any = await withEscalation("click", { selector: ".m" }, dom, cdp, (o) =>
      o === "click",
    );
    expect(r.via).toBe("cdp");
    expect(cdp.execute).toHaveBeenCalledOnce();
  });

  it("does not escalate when the DOM path reports no ok", async () => {
    const dom = result({ clicked: true });
    const cdp = result({ clicked: true, via: "cdp" });
    const r: any = await withEscalation("click", { selector: "button" }, dom, cdp, (o) =>
      o === "click",
    );
    expect(r.via).toBeUndefined();
    expect(cdp.execute).not.toHaveBeenCalled();
  });
});

// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// TDD for the CDP universal path. The chrome.debugger attach is live-only glue;
// the command sequencing (focus → trusted keys → insertText → read-back) is pure
// and tested here against a fake sender.

import { describe, it, expect } from "vitest";
import { CdpExecutor, type CdpSend } from "../src/executors/cdp";

function fakeSend(readValue: unknown, focusFound = true) {
  const calls: Array<{ method: string; params: any }> = [];
  const send: CdpSend = async (method, params: any = {}) => {
    calls.push({ method, params });
    if (method === "Runtime.evaluate") {
      const e = String(params.expression);
      if (e.includes(".focus()")) return { result: { value: focusFound } };
      return { result: { value: readValue } };
    }
    if (method === "Accessibility.getFullAXTree") {
      return {
        nodes: [
          { role: { value: "textbox" }, name: { value: "Subject" }, value: { value: "hi" }, nodeId: 7 },
        ],
      };
    }
    return {};
  };
  return { send, calls };
}
const exec = (send: CdpSend) => new CdpExecutor(async () => send);

describe("CdpExecutor.type/fill (trusted input)", () => {
  it("focuses, selects-all (Ctrl+A), inserts trusted text, and read-back verifies", async () => {
    const { send, calls } = fakeSend("hello world");
    const r: any = await exec(send).execute("fill", { selector: "#b", text: "hello", clear: true });
    expect(r).toMatchObject({ typed: 5, value: "hello world", ok: true, via: "cdp" });
    // Ctrl+A select-all issued
    expect(calls.some((c) => c.method === "Input.dispatchKeyEvent" && c.params.modifiers === 2)).toBe(true);
    // trusted insertText with the text
    expect(calls.find((c) => c.method === "Input.insertText")!.params).toEqual({ text: "hello" });
  });

  it("skips select-all when clear=false (append)", async () => {
    const { send, calls } = fakeSend("hello");
    await exec(send).execute("type", { selector: "#b", text: "hello", clear: false });
    expect(calls.some((c) => c.method === "Input.dispatchKeyEvent" && c.params.modifiers === 2)).toBe(false);
    expect(calls.some((c) => c.method === "Input.insertText")).toBe(true);
  });

  it("throws when the selector matches nothing", async () => {
    const { send } = fakeSend(null, /*focusFound*/ false);
    await expect(exec(send).execute("fill", { selector: "#missing", text: "x" })).rejects.toThrow(
      /no element/i,
    );
  });
});

describe("CdpExecutor.press", () => {
  it("dispatches a trusted keyDown+keyUp", async () => {
    const { send, calls } = fakeSend(null);
    const r = await exec(send).execute("press", { key: "Enter" });
    expect(r).toEqual({ pressed: "Enter", via: "cdp" });
    const kd = calls.filter((c) => c.method === "Input.dispatchKeyEvent");
    expect(kd.map((c) => c.params.type)).toEqual(["keyDown", "keyUp"]);
    expect(kd[0].params.key).toBe("Enter");
  });
});

describe("CdpExecutor.accessibility_tree", () => {
  it("enables AX and returns simplified role/name/value nodes", async () => {
    const { send } = fakeSend(null);
    const r: any = await exec(send).execute("accessibility_tree", {});
    expect(r.via).toBe("cdp");
    expect(r.nodes).toEqual([{ role: "textbox", name: "Subject", value: "hi", nodeId: 7 }]);
  });
});

describe("CdpExecutor unknown op", () => {
  it("throws for an op it does not handle", async () => {
    const { send } = fakeSend(null);
    await expect(exec(send).execute("frobnicate", {})).rejects.toThrow(/no op/i);
  });
});

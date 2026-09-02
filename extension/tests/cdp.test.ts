// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// TDD for the CDP universal path. The chrome.debugger attach is live-only glue;
// the command sequencing (focus → trusted keys → insertText → read-back) is pure
// and tested here against a fake sender.

import { describe, it, expect } from "vitest";
import { CdpExecutor, type CdpSend } from "../src/executors/cdp";
import { cancelTyping } from "../src/typing-cancellation";

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

  it("human type dispatches ordered key events and returns timing metadata", async () => {
    const { send, calls } = fakeSend("ab");
    const r: any = await exec(send).execute("type", {
      selector: "#b",
      text: "ab",
      clear: true,
      human: true,
      typing_plan: {
        timing_profile: "us_adult_transcription_2026",
        nominal_wpm: 38,
        units: [
          { text: "a", delay_before_ms: 0 },
          { text: "b", delay_before_ms: 0 },
        ],
      },
    });
    expect(r).toMatchObject({
      human: true,
      timing_profile: "us_adult_transcription_2026",
      nominal_wpm: 38,
      units: 2,
      fallback_units: 0,
      ok: true,
    });
    const events = calls
      .filter((call) => call.method === "Input.dispatchKeyEvent")
      .map((call) => call.params.type);
    expect(events.slice(-6)).toEqual([
      "keyDown", "char", "keyUp", "keyDown", "char", "keyUp",
    ]);
    expect(calls.some((call) => call.method === "Input.insertText")).toBe(false);
    const reads = calls.filter((call) => call.method === "Runtime.evaluate");
    expect(reads.some((call) => String(call.params.expression).includes(".trim()"))).toBe(false);
    expect(reads.some((call) => String(call.params.expression).includes("node.shadowRoot"))).toBe(true);
  });

  it("cancels between units and never submits", async () => {
    const { send, calls } = fakeSend("a");
    const pending = exec(send).execute("type", {
      selector: "#b",
      text: "ab",
      clear: true,
      submit: true,
      human: true,
      _request_id: 77,
      typing_plan: {
        timing_profile: "us_adult_transcription_2026",
        nominal_wpm: 38,
        units: [
          { text: "a", delay_before_ms: 0 },
          { text: "b", delay_before_ms: 100 },
        ],
      },
    });
    await new Promise((resolve) => setTimeout(resolve, 10));
    cancelTyping(77);
    await expect(pending).rejects.toMatchObject({ code: "typing_cancelled" });
    const enter = calls.filter(
      (call) => call.method === "Input.dispatchKeyEvent" && call.params.key === "Enter",
    );
    expect(enter).toHaveLength(0);
  });

  it("uses the physical key code and Shift modifier for uppercase text", async () => {
    const { send, calls } = fakeSend("A");
    await exec(send).execute("type", {
      selector: "#b",
      text: "A",
      human: true,
      typing_plan: {
        timing_profile: "us_adult_transcription_2026",
        nominal_wpm: 38,
        units: [{ text: "A", delay_before_ms: 0 }],
      },
    });

    const keyDown = calls.find(
      (call) => call.method === "Input.dispatchKeyEvent" && call.params.type === "keyDown" && call.params.key === "A",
    );
    expect(keyDown?.params).toMatchObject({ code: "KeyA", modifiers: 8, windowsVirtualKeyCode: 65 });
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

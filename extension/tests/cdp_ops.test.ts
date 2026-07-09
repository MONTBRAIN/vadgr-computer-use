// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// TDD for the 0.5.0 CDP interaction ops (hover / upload / focus / blur / clear /
// get_value / snapshot / dialog). The chrome.debugger attach + event wiring is
// live-only; the command sequencing is pure and tested here against a fake sender
// (and, for dialog, a fake debugger-event emitter).

import { describe, it, expect } from "vitest";
import {
  CdpExecutor,
  type CdpSend,
  type DebuggerEvents,
} from "../src/executors/cdp";

// A scriptable fake sender. `evalFor(expr)` lets a test decide what a given
// Runtime.evaluate returns (matched by substring); everything else records + no-ops.
function fakeSend(
  evalFor: (expr: string) => unknown = () => null,
  domNodeId = 5,
) {
  const calls: Array<{ method: string; params: any }> = [];
  const send: CdpSend = async (method, params: any = {}) => {
    calls.push({ method, params });
    if (method === "Runtime.evaluate") {
      return { result: { value: evalFor(String(params.expression)) } };
    }
    if (method === "DOM.getDocument") return { root: { nodeId: 1 } };
    if (method === "DOM.querySelector") return { nodeId: domNodeId };
    if (method === "Accessibility.getFullAXTree") {
      return {
        nodes: [
          {
            role: { value: "textbox" },
            name: { value: "Email" },
            value: { value: "a@b.c" },
            backendDOMNodeId: 21,
            properties: [{ name: "focusable", value: { value: true } }],
          },
          {
            role: { value: "button" },
            name: { value: "Send" },
            backendDOMNodeId: 22,
            properties: [{ name: "disabled", value: { value: false } }],
          },
        ],
      };
    }
    return {};
  };
  return { send, calls };
}

const exec = (send: CdpSend, events?: DebuggerEvents) =>
  new CdpExecutor(async () => send, events);

describe("CdpExecutor.hover", () => {
  it("dispatches mouseMoved at the element centre", async () => {
    // rect centre = (10, 20); reveal target hidden before, visible after.
    let moved = false;
    const evalFor = (e: string) => {
      if (e.includes("getBoundingClientRect"))
        return { x: 10, y: 20, found: true };
      if (e.includes("__vis__")) return moved; // reveal visibility flips post-move
      return null;
    };
    const { send, calls } = fakeSend(evalFor);
    // Flip the reveal visibility the moment the mouse moves.
    const wrapped: CdpSend = async (m, p) => {
      if (m === "Input.dispatchMouseEvent") moved = true;
      return send(m, p);
    };
    const r: any = await exec(wrapped).execute("hover", {
      selector: ".menu",
      reveals: ".submenu",
    });
    expect(r.hovered).toBe(true);
    expect(r.revealed).toBe(true);
    const move = calls.find((c) => c.method === "Input.dispatchMouseEvent");
    expect(move!.params).toMatchObject({ type: "mouseMoved", x: 10, y: 20 });
  });

  it("throws when the hover target matches nothing", async () => {
    const { send } = fakeSend(() => null); // getBoundingClientRect -> null
    await expect(
      exec(send).execute("hover", { selector: "#gone" }),
    ).rejects.toThrow(/no element/i);
  });
});

describe("CdpExecutor.upload", () => {
  it("sets the input files and self-verifies files.length", async () => {
    const files = ["C:\\Users\\me\\cv.pdf"];
    const evalFor = (e: string) => (e.includes(".files") ? 1 : null);
    const { send, calls } = fakeSend(evalFor);
    const r: any = await exec(send).execute("upload", {
      selector: "input[type=file]",
      files,
    });
    expect(r).toMatchObject({ uploaded: 1, ok: true });
    expect(r.files).toEqual(files);
    const set = calls.find((c) => c.method === "DOM.setFileInputFiles");
    expect(set!.params).toMatchObject({ nodeId: 5, files });
  });

  it("reports ok:false when the read-back count does not match", async () => {
    const evalFor = (e: string) => (e.includes(".files") ? 0 : null);
    const { send } = fakeSend(evalFor);
    const r: any = await exec(send).execute("upload", {
      selector: "input[type=file]",
      files: ["C:\\x.pdf"],
    });
    expect(r.ok).toBe(false);
  });
});

describe("CdpExecutor.focus / blur", () => {
  it("focus reports focused:true when activeElement matches", async () => {
    const evalFor = (e: string) => {
      if (e.includes(".focus()")) return true;
      if (e.includes("activeElement")) return true;
      return null;
    };
    const { send } = fakeSend(evalFor);
    const r: any = await exec(send).execute("focus", { selector: "#in" });
    expect(r.focused).toBe(true);
  });

  it("blur reports focused:false", async () => {
    const evalFor = (e: string) => {
      if (e.includes("activeElement")) return false;
      return true;
    };
    const { send } = fakeSend(evalFor);
    const r: any = await exec(send).execute("blur", { selector: "#in" });
    expect(r.focused).toBe(false);
  });
});

describe("CdpExecutor.clear", () => {
  it("select-alls, deletes, and self-verifies value=''", async () => {
    const evalFor = (e: string) => {
      if (e.includes(".focus()")) return true;
      return ""; // read-back value after clear
    };
    const { send, calls } = fakeSend(evalFor);
    const r: any = await exec(send).execute("clear", { selector: "#in" });
    expect(r).toMatchObject({ value: "", ok: true, via: "cdp" });
    // Ctrl+A then Delete.
    expect(
      calls.some(
        (c) => c.method === "Input.dispatchKeyEvent" && c.params.modifiers === 2,
      ),
    ).toBe(true);
    expect(
      calls.some(
        (c) =>
          c.method === "Input.dispatchKeyEvent" && c.params.key === "Delete",
      ),
    ).toBe(true);
  });
});

describe("CdpExecutor.get_value", () => {
  it("reads the element value via the page", async () => {
    const evalFor = (e: string) =>
      e.includes("el.value") || e.includes("innerText") ? "hello" : null;
    const { send } = fakeSend(evalFor);
    const r: any = await exec(send).execute("get_value", { selector: "#in" });
    expect(r.value).toBe("hello");
  });
});

describe("CdpExecutor.snapshot", () => {
  it("returns role/name/state/value/ref nodes, filtered + paginated", async () => {
    const { send } = fakeSend();
    const r: any = await exec(send).execute("snapshot", { limit: 1 });
    expect(r.nodes).toHaveLength(1);
    expect(r.nodes[0]).toMatchObject({
      role: "textbox",
      name: "Email",
      value: "a@b.c",
      ref: 21,
    });
    // more than one node exists → a cursor to resume from.
    expect(r.next_cursor).toBe(1);
  });

  it("filters by role", async () => {
    const { send } = fakeSend();
    const r: any = await exec(send).execute("snapshot", { roles: ["button"] });
    expect(r.nodes).toHaveLength(1);
    expect(r.nodes[0].role).toBe("button");
    expect(r.next_cursor).toBeUndefined();
  });
});

// A minimal debugger-event emitter matching chrome.debugger.onEvent's shape.
function fakeEvents() {
  const listeners: Array<(src: any, method: string, params: any) => void> = [];
  return {
    events: {
      addListener: (cb: any) => listeners.push(cb),
      removeListener: (cb: any) => {
        const i = listeners.indexOf(cb);
        if (i >= 0) listeners.splice(i, 1);
      },
    } as DebuggerEvents,
    emit: (method: string, params: any) =>
      listeners.slice().forEach((l) => l({}, method, params)),
    get count() {
      return listeners.length;
    },
  };
}

describe("CdpExecutor.dialog (one-shot arm)", () => {
  it("arms a one-shot handler that accepts the next dialog with prompt text", async () => {
    const { send, calls } = fakeSend();
    const ev = fakeEvents();
    const r: any = await exec(send, ev.events).execute("dialog", {
      action: "accept",
      text: "hi there",
      arm: true,
    });
    expect(r.armed).toBe(true);
    expect(ev.count).toBe(1); // handler installed

    // A later action pops a prompt; the armed handler resolves it.
    ev.emit("Page.javascriptDialogOpening", {
      type: "prompt",
      message: "Your name?",
    });
    await Promise.resolve();
    const handled = calls.find((c) => c.method === "Page.handleJavaScriptDialog");
    expect(handled!.params).toMatchObject({ accept: true, promptText: "hi there" });
    // one-shot: the listener is removed after firing.
    expect(ev.count).toBe(0);
  });

  it("arms a dismiss handler", async () => {
    const { send, calls } = fakeSend();
    const ev = fakeEvents();
    await exec(send, ev.events).execute("dialog", { action: "dismiss", arm: true });
    ev.emit("Page.javascriptDialogOpening", { type: "confirm", message: "Sure?" });
    await Promise.resolve();
    const handled = calls.find((c) => c.method === "Page.handleJavaScriptDialog");
    expect(handled!.params.accept).toBe(false);
  });
});

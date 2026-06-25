// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// The CDP universal path — chrome.debugger API (the DevTools Protocol, reached
// PROGRAMMATICALLY; no DevTools panel ever opens). It is the widget-agnostic
// substrate: act via *trusted* Input events (any contenteditable / custom ARIA
// widget / React control reacts as it would to a human), perceive via the
// accessibility tree. Reached only when the DOM fast path's read-back fails.
//
// The chrome.debugger attach is thin glue (not unit-testable); the command
// sequencing here is pure and unit-tested against a fake sender.

import type { Executor, Params } from "./types";

// A bound sender: issues a CDP command against the already-attached target.
export type CdpSend = (method: string, params?: object) => Promise<any>;
export type Attach = () => Promise<CdpSend>;

// CDP modifier bitmask.
const CTRL = 2;

interface KeyDef {
  key: string;
  code: string;
  windowsVirtualKeyCode?: number;
  text?: string;
}

// Named keys we synthesize; an unknown single char falls back to a literal.
const KEYS: Record<string, KeyDef> = {
  Enter: { key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, text: "\r" },
  Tab: { key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 },
  Backspace: { key: "Backspace", code: "Backspace", windowsVirtualKeyCode: 8 },
  Delete: { key: "Delete", code: "Delete", windowsVirtualKeyCode: 46 },
  Escape: { key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 },
  ArrowDown: { key: "ArrowDown", code: "ArrowDown", windowsVirtualKeyCode: 40 },
  ArrowUp: { key: "ArrowUp", code: "ArrowUp", windowsVirtualKeyCode: 38 },
  a: { key: "a", code: "KeyA", windowsVirtualKeyCode: 65 },
};

function keyDef(key: string): KeyDef {
  if (KEYS[key]) return KEYS[key];
  // A single literal character.
  return { key, code: `Key${key.toUpperCase()}`, text: key };
}

function simplifyAxNode(n: any) {
  return {
    role: n?.role?.value ?? "",
    name: n?.name?.value ?? "",
    value: n?.value?.value,
    nodeId: n?.nodeId,
  };
}

export class CdpExecutor implements Executor {
  readonly name = "cdp";
  constructor(private readonly attach: Attach) {}

  async execute(op: string, params: Params): Promise<unknown> {
    const send = await this.attach();
    switch (op) {
      case "type":
      case "fill":
        return this.typeText(send, params);
      case "press":
        return this.press(send, params);
      case "accessibility_tree":
        return this.axTree(send);
      default:
        throw new Error(`cdp path has no op '${op}'`);
    }
  }

  // Focus the element by selector (JS focus is fine — it's the *keystrokes* that
  // must be trusted), then insert text via the trusted Input domain. insertText
  // replaces the current selection, so select-all clears first.
  private async typeText(send: CdpSend, p: Params) {
    const text = String(p.text ?? "");
    const selector = String(p.selector);
    await this.focus(send, selector);
    if (p.clear !== false) await this.key(send, "a", CTRL); // select all → replaced
    await send("Input.insertText", { text });
    if (p.submit) await this.key(send, "Enter");
    const value = await this.readValue(send, selector);
    return {
      typed: text.length,
      value,
      ok: typeof value === "string" ? value.includes(text) : true,
      via: "cdp",
    };
  }

  private async press(send: CdpSend, p: Params) {
    const key = String(p.key ?? "");
    if (p.selector) await this.focus(send, String(p.selector));
    await this.key(send, key);
    return { pressed: key, via: "cdp" };
  }

  private async axTree(send: CdpSend) {
    await send("Accessibility.enable");
    const res = await send("Accessibility.getFullAXTree");
    const nodes = (res?.nodes ?? []).map(simplifyAxNode);
    return { nodes, via: "cdp" };
  }

  // --- low-level helpers (pure CDP sequencing) ---

  private async key(send: CdpSend, key: string, modifiers = 0) {
    const d = keyDef(key);
    const base = { ...d, modifiers };
    await send("Input.dispatchKeyEvent", { type: "keyDown", ...base });
    await send("Input.dispatchKeyEvent", { type: "keyUp", ...base });
  }

  private async focus(send: CdpSend, selector: string) {
    const expr =
      `(() => { const el = document.querySelector(${JSON.stringify(selector)});` +
      ` if (!el) return false; el.scrollIntoView({block:'center'}); el.focus(); return true; })()`;
    const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true });
    if (!r?.result?.value) throw new Error(`no element matches ${selector}`);
  }

  private async readValue(send: CdpSend, selector: string): Promise<unknown> {
    const expr =
      `(() => { const el = document.querySelector(${JSON.stringify(selector)});` +
      ` if (!el) return null; return (el.value ?? el.innerText ?? el.textContent ?? '').trim(); })()`;
    const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true });
    return r?.result?.value ?? null;
  }
}

// The real attach (thin chrome.debugger glue — exercised live, not unit-tested).
export function chromeDebuggerAttach(activeTabId: () => Promise<number>): Attach {
  return async () => {
    const tabId = await activeTabId();
    const target = { tabId };
    try {
      await chrome.debugger.attach(target, "1.3");
    } catch (e) {
      if (!/already attached/i.test(String((e as Error)?.message ?? e))) throw e;
    }
    return (method, params) =>
      chrome.debugger.sendCommand(target, method, params) as Promise<any>;
  };
}

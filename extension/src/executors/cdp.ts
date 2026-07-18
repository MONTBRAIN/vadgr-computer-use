// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// The CDP universal path — chrome.debugger API (the DevTools Protocol, reached
// PROGRAMMATICALLY; no DevTools panel ever opens). It is the widget-agnostic
// substrate: act via *trusted* Input events (any contenteditable / custom ARIA
// widget / React control reacts as it would to a human), perceive via the
// accessibility tree, pierce open + closed shadow roots and cross-origin frames,
// set file inputs, and handle JS dialogs. Reached when the DOM fast path can't
// act (or for ops with no DOM equivalent: hover / dialog / upload / snapshot).
//
// The chrome.debugger attach + event wiring is thin glue (not unit-testable); the
// command sequencing here is pure and unit-tested against a fake sender.

import type { Executor, Params } from "./types";

// A bound sender: issues a CDP command against the already-attached target.
export type CdpSend = (method: string, params?: object) => Promise<any>;
export type Attach = () => Promise<CdpSend>;

// The slice of chrome.debugger.onEvent we depend on (for JS-dialog handling).
// Injectable so the dialog arming logic is testable with no browser.
export interface DebuggerEvents {
  addListener(cb: (source: any, method: string, params: any) => void): void;
  removeListener(cb: (source: any, method: string, params: any) => void): void;
}

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

// The 0.4.0 accessibility_tree node shape (role/name/value/nodeId).
function simplifyAxNode(n: any) {
  return {
    role: n?.role?.value ?? "",
    name: n?.name?.value ?? "",
    value: n?.value?.value,
    nodeId: n?.nodeId,
  };
}

// Flatten an AX node's boolean/enum properties to a small state bag.
function axState(n: any): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const p of n?.properties ?? []) out[p?.name] = p?.value?.value;
  return out;
}

// The 0.5.0 snapshot node shape (role/name/state/value/ref). `ref` is the
// backend DOM node id so the agent can correlate an AX node with the DOM.
function snapshotNode(n: any) {
  return {
    role: n?.role?.value ?? "",
    name: n?.name?.value ?? "",
    state: axState(n),
    value: n?.value?.value,
    ref: n?.backendDOMNodeId ?? n?.nodeId,
  };
}

export class CdpExecutor implements Executor {
  readonly name = "cdp";
  private lastDialog: { handled: boolean; type?: string; message?: string } | null =
    null;

  constructor(
    private readonly attach: Attach,
    private readonly events?: DebuggerEvents,
  ) {}

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
      case "snapshot":
        return this.snapshot(send, params);
      case "hover":
        return this.hover(send, params);
      case "upload":
        return this.upload(send, params);
      case "focus":
        return this.focusOp(send, params);
      case "blur":
        return this.blurOp(send, params);
      case "clear":
        return this.clear(send, params);
      case "get_value":
        return this.getValue(send, params);
      case "dialog":
        return this.dialog(send, params);
      case "eval":
        return this.evalOp(send, params);
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

  // The paginated, shadow-/frame-piercing AX successor to accessibility_tree.
  // getFullAXTree pierces frames + shadow roots; we filter by role and page with
  // an offset cursor + limit so a large tree degrades to pages, not a blowout.
  private async snapshot(send: CdpSend, p: Params) {
    await send("Accessibility.enable");
    const res = await send("Accessibility.getFullAXTree");
    let nodes = (res?.nodes ?? []).map(snapshotNode);
    if (Array.isArray(p.roles) && p.roles.length) {
      const want = new Set(p.roles as string[]);
      nodes = nodes.filter((n: any) => want.has(n.role));
    }
    const limit = typeof p.limit === "number" ? p.limit : 50;
    const cursor = typeof p.cursor === "number" ? p.cursor : 0;
    const page = nodes.slice(cursor, cursor + limit);
    const out: Record<string, unknown> = { nodes: page, via: "cdp" };
    if (cursor + limit < nodes.length) out.next_cursor = cursor + limit;
    return out;
  }

  // Move the mouse to the element centre (trusted Input.mouseMoved) so CSS
  // `:hover` fires. `revealed` diffs the visibility of the reveal target (the
  // `reveals` selector, or — absent it — the hover target's own subtree) across
  // the move; a hidden→visible flip is a real reveal. No diffable surface →
  // `revealed` is omitted, never fabricated.
  private async hover(send: CdpSend, p: Params) {
    const selector = String(p.selector);
    const reveals = p.reveals != null ? String(p.reveals) : null;
    const before = await this.visSignature(send, reveals ?? selector, !reveals);
    const c = await this.centre(send, selector);
    await send("Input.dispatchMouseEvent", {
      type: "mouseMoved",
      x: c.x,
      y: c.y,
      buttons: 0,
    });
    const after = await this.visSignature(send, reveals ?? selector, !reveals);
    const out: Record<string, unknown> = { hovered: true, via: "cdp" };
    if (before !== null && after !== null) out.revealed = !before && after;
    return out;
  }

  // Set a file input's files via CDP (paths resolved in Chrome's OS — cua has
  // already rewritten them to Chrome-OS paths). Self-verify by reading back the
  // input's files.length.
  private async upload(send: CdpSend, p: Params) {
    const selector = String(p.selector);
    const files = (Array.isArray(p.files) ? p.files : []) as string[];
    const doc = await send("DOM.getDocument", {});
    const rootId = doc?.root?.nodeId;
    const q = await send("DOM.querySelector", { nodeId: rootId, selector });
    const nodeId = q?.nodeId;
    if (!nodeId) throw new Error(`no element matches ${selector}`);
    await send("DOM.setFileInputFiles", { nodeId, files });
    const count = await this.evalValue(
      send,
      `document.querySelector(${JSON.stringify(selector)})?.files?.length ?? 0`,
    );
    return {
      uploaded: typeof count === "number" ? count : 0,
      files,
      ok: count === files.length,
      via: "cdp",
    };
  }

  private async focusOp(send: CdpSend, p: Params) {
    const selector = String(p.selector);
    await this.focus(send, selector);
    const focused = await this.evalValue(
      send,
      `document.activeElement === document.querySelector(${JSON.stringify(selector)})`,
    );
    return { focused: focused === true, via: "cdp" };
  }

  private async blurOp(send: CdpSend, p: Params) {
    const selector = String(p.selector);
    await send("Runtime.evaluate", {
      expression:
        `(() => { const el = document.querySelector(${JSON.stringify(selector)});` +
        ` if (el && el.blur) el.blur(); return true; })()`,
      returnByValue: true,
    });
    const focused = await this.evalValue(
      send,
      `document.activeElement === document.querySelector(${JSON.stringify(selector)})`,
    );
    return { focused: focused === true, via: "cdp" };
  }

  // Clear a field the trusted way: focus, select-all, Delete. Self-verify the
  // read-back is empty. (The DOM fast path handles plain inputs; this is the CDP
  // escalation for custom / isTrusted-gated fields.)
  private async clear(send: CdpSend, p: Params) {
    const selector = String(p.selector);
    await this.focus(send, selector);
    await this.key(send, "a", CTRL);
    await this.key(send, "Delete");
    const value = await this.readValue(send, selector);
    return { value, ok: value === "", via: "cdp" };
  }

  private async getValue(send: CdpSend, p: Params) {
    const value = await this.readValue(send, String(p.selector));
    return { value, via: "cdp" };
  }

  // Arm a one-shot JS-dialog handler. Arming is mandatory BEFORE the triggering
  // op: a JS dialog pauses the renderer synchronously, so there is no post-hoc
  // catch. The next dialog to open is accepted/dismissed with the configured
  // action/text, then the handler removes itself.
  private async dialog(send: CdpSend, p: Params) {
    const accept = (p.action ?? "accept") !== "dismiss";
    const promptText = p.text != null ? String(p.text) : undefined;
    await send("Page.enable");
    if (!this.events) {
      throw new Error("dialog handling requires the chrome.debugger event channel");
    }
    const events = this.events;
    const listener = (_src: any, method: string, params: any) => {
      if (method !== "Page.javascriptDialogOpening") return;
      events.removeListener(listener); // one-shot
      const args: Record<string, unknown> = { accept };
      if (promptText !== undefined) args.promptText = promptText;
      // The renderer is blocked until this lands; fire it immediately.
      void send("Page.handleJavaScriptDialog", args);
      this.lastDialog = {
        handled: true,
        type: params?.type,
        message: params?.message,
      };
    };
    events.addListener(listener);
    return { armed: true, action: accept ? "accept" : "dismiss" };
  }

  // Page eval via the debugger's Runtime domain. CSP-exempt: a page policy of
  // `script-src 'nonce-…'` (no `'unsafe-eval'`) blocks MAIN-world `eval()`, but
  // the debugger backend is not governed by page CSP — which is exactly why
  // press/snapshot keep working on such pages. Surfaces page exceptions instead
  // of swallowing them; awaitPromise preserves the executeScript promise-await.
  private async evalOp(send: CdpSend, p: Params) {
    const r = await send("Runtime.evaluate", {
      expression: String(p.expression ?? ""),
      returnByValue: true,
      awaitPromise: true,
      userGesture: true,
    });
    if (r?.exceptionDetails) {
      const d: any = r.exceptionDetails;
      throw new Error(d.exception?.description ?? d.text ?? "evaluation threw");
    }
    return { value: r?.result?.value ?? null, via: "cdp" };
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

  // Evaluate an expression in the page and return its value.
  private async evalValue(send: CdpSend, expr: string): Promise<unknown> {
    const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true });
    return r?.result?.value ?? null;
  }

  // The element's centre point (viewport coords). Throws if it matches nothing.
  private async centre(send: CdpSend, selector: string): Promise<{ x: number; y: number }> {
    const expr =
      `(() => { const el = document.querySelector(${JSON.stringify(selector)});` +
      ` if (!el) return null; el.scrollIntoView({block:'center'});` +
      ` const r = el.getBoundingClientRect();` +
      ` return { x: r.left + r.width/2, y: r.top + r.height/2, found: true }; })()`;
    const v: any = await this.evalValue(send, expr);
    if (!v || !v.found) throw new Error(`no element matches ${selector}`);
    return { x: v.x, y: v.y };
  }

  // A visibility signature for the reveal-diff. For a `reveals` selector it is
  // "the element itself is visible"; for the hover target's own subtree it is
  // "any descendant is currently visible". Returns null when the selector matches
  // nothing (no diffable surface).
  private async visSignature(
    send: CdpSend,
    selector: string,
    subtree: boolean,
  ): Promise<boolean | null> {
    const vis =
      `(n) => { if (!n) return false;` +
      ` const s = getComputedStyle(n);` +
      ` if (s.display === 'none' || s.visibility === 'hidden') return false;` +
      ` return n.getClientRects().length > 0; }`;
    const expr = subtree
      ? `(() => { /*__vis__*/ const el = document.querySelector(${JSON.stringify(selector)});` +
        ` if (!el) return null; const vis = ${vis};` +
        ` return Array.from(el.querySelectorAll('*')).some(vis); })()`
      : `(() => { /*__vis__*/ const el = document.querySelector(${JSON.stringify(selector)});` +
        ` if (!el) return null; const vis = ${vis}; return vis(el); })()`;
    const v = await this.evalValue(send, expr);
    return v === null ? null : v === true;
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

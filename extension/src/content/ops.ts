// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// DOM op handlers - run in the content script. Selector-first, re-resolved per
// call (the extension holds no element handles between ops, so ops are robust
// to navigation / DOM churn).

import { fillContentEditable, fillField, setText } from "./fill";
import { OpFailed } from "./errors";
import {
  assertActionable,
  isDisabled,
  isVisible as isActionableVisible,
  receivesEvents,
} from "./actionable";

export { OpFailed };

// Caps for `query` output. A real-site `query` returned ~61k chars and blew the
// token budget; capping the node count (per page) + per-node text degrades a
// large page to pages instead of one budget-blowing blob.
export const MAX_NODES = 50;
export const MAX_NODE_TEXT = 2000;

// Standard XPathResult constants. Referenced by value so the code does not
// depend on a global `XPathResult` binding (absent in some DOM harnesses);
// `document.evaluate` itself is what we actually need.
const FIRST_ORDERED_NODE_TYPE = 9;
const ORDERED_NODE_SNAPSHOT_TYPE = 7;

function resolve(selector: string, by: string = "css"): Element | null {
  if (by === "xpath") {
    const r = document.evaluate(
      selector,
      document,
      null,
      FIRST_ORDERED_NODE_TYPE,
      null,
    );
    return (r.singleNodeValue as Element) ?? null;
  }
  return document.querySelector(selector) ?? deepQuery(selector);
}

// Open-shadow fallback: walk shadow roots breadth-first and retry the selector
// inside each. Only runs when the light DOM missed, so pages without shadow DOM
// behave exactly as before. Closed roots stay unreachable by selector (use
// snapshot/eval for those).
function deepQuery(selector: string): Element | null {
  const roots: (Document | ShadowRoot)[] = [document];
  for (let i = 0; i < roots.length; i++) {
    const hit = roots[i].querySelector(selector);
    if (hit) return hit;
    for (const el of Array.from(roots[i].querySelectorAll("*"))) {
      const sr = (el as HTMLElement).shadowRoot;
      if (sr) roots.push(sr);
    }
  }
  return null;
}

// Same walk, collecting every match across open shadow roots.
function deepQueryAll(selector: string): Element[] {
  const out: Element[] = [];
  const roots: (Document | ShadowRoot)[] = [document];
  for (let i = 0; i < roots.length; i++) {
    out.push(...Array.from(roots[i].querySelectorAll(selector)));
    for (const el of Array.from(roots[i].querySelectorAll("*"))) {
      const sr = (el as HTMLElement).shadowRoot;
      if (sr) roots.push(sr);
    }
  }
  return out;
}

function resolveAll(selector: string, by: string = "css"): Element[] {
  if (by === "xpath") {
    const out: Element[] = [];
    const r = document.evaluate(
      selector,
      document,
      null,
      ORDERED_NODE_SNAPSHOT_TYPE,
      null,
    );
    for (let i = 0; i < r.snapshotLength; i++) {
      out.push(r.snapshotItem(i) as Element);
    }
    return out;
  }
  const light = Array.from(document.querySelectorAll(selector));
  return light.length ? light : deepQueryAll(selector);
}

function require(selector: string, by: string = "css"): Element {
  const el = resolve(selector, by);
  if (!el) throw new OpFailed(`no element matches ${selector}`);
  return el;
}

function summarize(el: Element): {
  tag: string;
  text: string;
  attrs: Record<string, string>;
} {
  const attrs: Record<string, string> = {};
  for (const a of Array.from(el.attributes)) attrs[a.name] = a.value;
  let text = ((el as HTMLElement).innerText ?? el.textContent ?? "").trim();
  // Per-node text cap - a single huge node must not blow the budget on its own.
  if (text.length > MAX_NODE_TEXT) text = text.slice(0, MAX_NODE_TEXT) + "…";
  return { tag: el.tagName.toLowerCase(), text, attrs };
}

function isVisible(el: Element): boolean {
  const he = el as HTMLElement;
  if (he.hidden) return false;
  const style = (el.ownerDocument.defaultView || window).getComputedStyle(he);
  if (style.display === "none" || style.visibility === "hidden") return false;
  if (style.display === "" && he.style.display === "none") return false;
  return true;
}

// The widget-state attributes a component library flips when it reacts to a
// click. Used as the click self-verify signature.
const STATE_ATTRS = [
  "data-state",
  "aria-expanded",
  "aria-checked",
  "aria-pressed",
  "aria-selected",
  "aria-current",
];

// Returns the element's state signature, or null when it carries none of the
// attributes (no diffable surface - we must not fabricate an `ok`).
function stateSignature(el: Element): string | null {
  const parts = STATE_ATTRS.filter((n) => el.hasAttribute(n)).map(
    (n) => `${n}=${el.getAttribute(n)}`,
  );
  return parts.length ? parts.join("|") : null;
}

const nextFrame = () =>
  document.hidden
    // Hidden pages do not receive requestAnimationFrame. A short timer still
    // gives framework state a chance to commit without interpreting the first
    // synchronous read as failure and dispatching a second click.
    ? new Promise<void>((res) => setTimeout(res, 75))
    : new Promise<void>((res) =>
        typeof requestAnimationFrame === "function"
          ? requestAnimationFrame(() => res())
          : setTimeout(res, 0),
      );

export function opAssertActionable(p: {
  selector: string;
  by?: string;
  force?: boolean;
}) {
  const el = require(p.selector, p.by) as HTMLElement;
  assertActionable(el, p.selector, { force: p.force });
  return { actionable: true };
}

function humanKey(text: string): { key: string; code: string; shiftKey: boolean } {
  const key = text === "\n" ? "Enter" : text === "\t" ? "Tab" : text;
  const shifted: Record<string, string> = {
    "~": "`", "!": "1", "@": "2", "#": "3", "$": "4", "%": "5",
    "^": "6", "&": "7", "*": "8", "(": "9", ")": "0", "_": "-",
    "+": "=", "{": "[", "}": "]", "|": "\\", ":": ";", '"': "'",
    "<": ",", ">": ".", "?": "/",
  };
  const punctuation: Record<string, string> = {
    "`": "Backquote", "-": "Minus", "=": "Equal", "[": "BracketLeft",
    "]": "BracketRight", "\\": "Backslash", ";": "Semicolon", "'": "Quote",
    ",": "Comma", ".": "Period", "/": "Slash", " ": "Space",
  };
  const physical = shifted[key] ?? key.toLowerCase();
  const code = /^[a-z]$/.test(physical)
    ? `Key${physical.toUpperCase()}`
    : /^[0-9]$/.test(physical)
      ? `Digit${physical}`
      : key === "Enter"
        ? "Enter"
        : key === "Tab"
          ? "Tab"
          : punctuation[physical] ?? "Unidentified";
  return { key, code, shiftKey: key.toLowerCase() !== key || key in shifted };
}

// One scheduled browser-typing unit. This runs in the content script attached
// to the exact broker target, so Chromium does not redirect or discard it when
// another tab is selected. The service worker owns timing and cancellation;
// this operation owns one indivisible event/value transition and read-back.
export function opHumanTypeUnit(p: {
  selector: string;
  text: string;
  replace?: boolean;
  force?: boolean;
}) {
  const el = require(p.selector) as HTMLElement;
  assertActionable(el, p.selector, { force: p.force });
  const editable =
    el instanceof HTMLInputElement ||
    el instanceof HTMLTextAreaElement;
  if (!editable) {
    throw new OpFailed(`${p.selector} is not a text input or textarea`);
  }

  el.focus({ preventScroll: true });
  if (el.getRootNode() instanceof Document && document.activeElement !== el) {
    throw new OpFailed(`${p.selector} could not receive DOM focus`);
  }

  const { key, code, shiftKey } = humanKey(p.text);
  const keyInit = { key, code, shiftKey, bubbles: true, cancelable: true };
  const inputType = key === "Enter" ? "insertLineBreak" : "insertText";
  const downAccepted = el.dispatchEvent(new KeyboardEvent("keydown", keyInit));
  let inserted = false;
  if (downAccepted) {
    let beforeAccepted = true;
    try {
      beforeAccepted = el.dispatchEvent(
        new InputEvent("beforeinput", {
          inputType,
          data: p.text,
          bubbles: true,
          cancelable: true,
        }),
      );
    } catch {
      // Older engines without constructible InputEvent still receive input.
    }
    if (beforeAccepted) {
      if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
        const proto =
          el instanceof HTMLTextAreaElement
            ? HTMLTextAreaElement.prototype
            : HTMLInputElement.prototype;
        const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
        const next = p.replace ? p.text : el.value + p.text;
        if (setter) setter.call(el, next);
        else el.value = next;
        try {
          el.setSelectionRange(next.length, next.length);
        } catch {
          // Some input types do not expose a text selection.
        }
      }
      try {
        el.dispatchEvent(
          new InputEvent("input", { inputType, data: p.text, bubbles: true }),
        );
      } catch {
        el.dispatchEvent(new Event("input", { bubbles: true }));
      }
      inserted = true;
    }
  }
  el.dispatchEvent(new KeyboardEvent("keyup", keyInit));
  const value = liveValue(el);
  return { inserted, value, ok: inserted && value !== null };
}

export function opHumanSubmit(p: {
  selector: string;
  force?: boolean;
}) {
  const el = require(p.selector) as HTMLElement;
  assertActionable(el, p.selector, { force: p.force });
  const editable =
    el instanceof HTMLInputElement ||
    el instanceof HTMLTextAreaElement;
  if (!editable) {
    throw new OpFailed(`${p.selector} is not a text input or textarea`);
  }

  const form = el.form;
  let observedSubmit = false;
  const observed = () => { observedSubmit = true; };
  form?.addEventListener("submit", observed, { capture: true, once: true });
  const init = {
    key: "Enter",
    code: "Enter",
    keyCode: 13,
    bubbles: true,
    cancelable: true,
  };
  const accepted = el.dispatchEvent(new KeyboardEvent("keydown", init));
  el.dispatchEvent(new KeyboardEvent("keyup", init));
  if (accepted && form && !observedSubmit) form.requestSubmit();
  form?.removeEventListener("submit", observed, { capture: true } as EventListenerOptions);
  return { accepted, submitted: observedSubmit };
}

export async function opClick(p: {
  selector: string;
  by?: string;
  force?: boolean;
}) {
  const el = require(p.selector, p.by) as HTMLElement;
  assertActionable(el, p.selector, { force: p.force });
  const before = stateSignature(el);
  el.scrollIntoView?.({ block: "center" });
  el.click();
  // Self-verify: for a checkable control, read back the post-click state so the
  // result carries the proof the click took effect (not just that it dispatched).
  // For other elements the effect is page-level - the agent verifies via a
  // read-back op (or the SW reports {navigated} when the click navigated away).
  const out: { clicked: boolean; checked?: boolean; ok?: boolean } = {
    clicked: true,
  };
  if (
    el instanceof HTMLInputElement &&
    (el.type === "checkbox" || el.type === "radio")
  ) {
    // Natives always react to the synthetic click. They are deliberately NOT
    // ok-gated: escalating would re-click and toggle them back.
    out.checked = el.checked;
    return out;
  }
  // A state-bearing widget that did not flip means the synthetic click was
  // ignored - the signal that this element needs a trusted event stream. React
  // flushes discrete events synchronously, so one frame is enough headroom for
  // the rest. Elements with no state signature report no `ok` at all, so plain
  // buttons and links never escalate spuriously.
  if (before !== null) {
    let after = stateSignature(el);
    if (after === before) {
      await nextFrame();
      after = el.isConnected ? stateSignature(el) : null;
    }
    // A vanished element (menu item consumed, dialog dismissed) reacted.
    out.ok = after === null ? !el.isConnected : after !== before;
  }
  return out;
}

export function opQuery(p: {
  selector: string;
  by?: string;
  all?: boolean;
  limit?: number;
  cursor?: number;
}) {
  const els = p.all
    ? resolveAll(p.selector, p.by)
    : (() => {
        const one = resolve(p.selector, p.by);
        return one ? [one] : [];
      })();
  const limit = typeof p.limit === "number" && p.limit > 0 ? p.limit : MAX_NODES;
  const cursor = typeof p.cursor === "number" && p.cursor > 0 ? p.cursor : 0;
  // A cursor past the current match set means the page changed under us (the
  // frozen list is gone). Fail loud so the agent re-runs the query from the top,
  // rather than silently skipping or repeating nodes.
  if (cursor > 0 && cursor >= els.length) {
    throw new OpFailed(
      `cursor_stale: cursor ${cursor} is past the ${els.length} current matches - re-run the query`,
    );
  }
  const page = els.slice(cursor, cursor + limit);
  const out: {
    nodes: ReturnType<typeof summarize>[];
    next_cursor?: number;
    truncated?: boolean;
  } = { nodes: page.map(summarize) };
  if (cursor + limit < els.length) {
    out.next_cursor = cursor + limit;
    out.truncated = true;
  }
  return out;
}

export function opReadText(p: { selector?: string | null }) {
  if (!p.selector) {
    return (document.body.innerText ?? document.body.textContent ?? "").trim();
  }
  const el = require(p.selector) as HTMLElement;
  return (el.innerText ?? el.textContent ?? "").trim();
}

const LIVE_PROPS = new Set(["value", "checked", "selected", "disabled"]);

export function opGetAttribute(p: { selector: string; name: string }) {
  const el = require(p.selector);
  if (LIVE_PROPS.has(p.name)) {
    return (el as unknown as Record<string, unknown>)[p.name] ?? null;
  }
  return el.getAttribute(p.name);
}

// A contenteditable host (incl. inherited editability, with an attribute fallback
// for DOM harnesses that don't compute `isContentEditable`).
function isContentEditableEl(el: Element): el is HTMLElement {
  if (!(el instanceof HTMLElement)) return false;
  if (el.isContentEditable) return true;
  const attr = el.getAttribute("contenteditable");
  return attr === "" || attr === "true" || attr === "plaintext-only";
}

export function opType(p: {
  selector: string;
  text: string;
  clear?: boolean;
  submit?: boolean;
  force?: boolean;
}) {
  const el = require(p.selector);
  // Gate first: a hidden text target is almost always a non-authoritative mirror
  // (the Gmail empty-body trap). Refuse it so the read-back can't be hollow.
  assertActionable(el as HTMLElement, p.selector, { force: p.force });

  // Plain text inputs - native value-setter path.
  if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
    const before = el.value;
    const typed = fillField(el, p.text, { clear: p.clear, submit: p.submit });
    // Self-verify: read back the live value and confirm the DOM actually holds
    // what we typed. (On `submit` the field may reset/navigate - verify the page
    // reaction, not the field; `ok` then reflects the field, not the submit.)
    const expected = (p.clear ?? true) ? p.text : before + p.text;
    const value = el.value;
    return { typed, value, ok: value === expected };
  }

  // Rich editors - contenteditable path (execCommand insertText).
  if (isContentEditableEl(el)) {
    const typed = fillContentEditable(el, p.text, { clear: p.clear });
    if (p.submit) {
      el.dispatchEvent(
        new KeyboardEvent("keydown", {
          key: "Enter", code: "Enter", keyCode: 13, bubbles: true, cancelable: true,
        }),
      );
    }
    // Self-verify by read-back: the editor's text must contain what we typed
    // (editors wrap text in nodes, so `includes` not `===`).
    const value = (el.innerText ?? el.textContent ?? "").trim();
    return { typed, value, ok: value.includes(p.text.trim()) };
  }

  throw new OpFailed(`${p.selector} is not a text input or contenteditable`);
}

export function opSelect(p: { selector: string; value: string; force?: boolean }) {
  const el = require(p.selector);
  if (!(el instanceof HTMLSelectElement)) {
    throw new OpFailed(`${p.selector} is not a <select>`);
  }
  assertActionable(el, p.selector, { force: p.force });
  const match = Array.from(el.options).find(
    (o) => o.value === p.value || o.text.trim() === p.value,
  );
  if (!match) throw new OpFailed(`no option matched "${p.value}"`);
  el.value = match.value;
  el.dispatchEvent(new Event("change", { bubbles: true }));
  // Self-verify: read back the live <select> value so the result proves the
  // option stuck (the page's change handler can't have reverted it unseen).
  return { selected: match.value, value: el.value, ok: el.value === match.value };
}

// The explicit actionability read - the same visible / receives-events / enabled
// signals the mutating-op precondition asserts internally, exposed so the agent
// can CHECK before acting and pick the authoritative (visible) element instead of
// discovering a non-actionable target only on a thrown op_failed.
export function opElementState(p: { selector: string; by?: string }) {
  const el = require(p.selector, p.by) as HTMLElement;
  const editable =
    el instanceof HTMLInputElement ||
    el instanceof HTMLTextAreaElement ||
    el instanceof HTMLSelectElement ||
    isContentEditableEl(el);
  const r = el.getBoundingClientRect?.() ?? { x: 0, y: 0, width: 0, height: 0 };
  const out: {
    visible: boolean;
    receives_events: boolean;
    enabled: boolean;
    focused: boolean;
    editable: boolean;
    checked?: boolean;
    value?: unknown;
    bbox: { x: number; y: number; width: number; height: number };
  } = {
    visible: isActionableVisible(el),
    receives_events: receivesEvents(el),
    enabled: !isDisabled(el),
    focused: el.ownerDocument.activeElement === el,
    editable,
    bbox: { x: r.x, y: r.y, width: r.width, height: r.height },
  };
  if (el instanceof HTMLInputElement && (el.type === "checkbox" || el.type === "radio")) {
    out.checked = el.checked;
  }
  const v = liveValue(el);
  if (v !== null) out.value = v;
  return out;
}

// The live value of a standard value-bearing control (input/textarea/select) or
// a contenteditable's text. null for anything else (→ the SW escalates get_value
// to the CDP path for custom widgets).
function liveValue(el: Element): string | null {
  if (
    el instanceof HTMLInputElement ||
    el instanceof HTMLTextAreaElement ||
    el instanceof HTMLSelectElement
  ) {
    return el.value;
  }
  if (isContentEditableEl(el)) {
    return ((el as HTMLElement).innerText ?? el.textContent ?? "").trim();
  }
  return null;
}

export function opGetValue(p: { selector: string; by?: string }) {
  const el = require(p.selector, p.by);
  const value = liveValue(el);
  // ok:false (value===null) is the escalation trigger - a custom/non-DOM widget
  // has no live DOM value, so the SW re-runs get_value on the CDP path.
  return { value, ok: value !== null };
}

export function opClear(p: { selector: string; by?: string; force?: boolean }) {
  const el = require(p.selector, p.by);
  if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
    assertActionable(el, p.selector, { force: p.force });
    setText(el, "");
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.dispatchEvent(new Event("blur", { bubbles: true }));
    return { value: el.value, ok: el.value === "" };
  }
  if (isContentEditableEl(el)) {
    assertActionable(el as HTMLElement, p.selector, { force: p.force });
    (el as HTMLElement).textContent = "";
    el.dispatchEvent(new Event("input", { bubbles: true }));
    const value = ((el as HTMLElement).innerText ?? el.textContent ?? "").trim();
    return { value, ok: value === "" };
  }
  // Not a clearable DOM control - ok:false so the SW escalates to the CDP path
  // (select-all + Delete), rather than masking a no-op as success.
  return { value: null, ok: false };
}

export function opScroll(p: { selector?: string | null; by?: { x?: number; y?: number } }) {
  if (p.selector) {
    const el = require(p.selector) as HTMLElement;
    el.scrollIntoView({ block: "center" });
  } else {
    window.scrollBy(p.by?.x ?? 0, p.by?.y ?? 0);
  }
  return { ok: true };
}

export function opWaitFor(p: {
  selector: string;
  state?: string;
  timeout?: number;
}): Promise<{ matched: boolean }> {
  const state = p.state ?? "visible";
  const timeout = p.timeout ?? 5000;
  const interval = 60;
  const deadline = Date.now() + timeout;

  const holds = (): boolean => {
    const el = resolve(p.selector);
    if (state === "attached") return el !== null;
    if (state === "hidden") return el === null || !isVisible(el);
    // visible
    return el !== null && isVisible(el);
  };

  return new Promise((resolve_) => {
    if (holds()) return resolve_({ matched: true });
    const timer = setInterval(() => {
      if (holds()) {
        clearInterval(timer);
        resolve_({ matched: true });
      } else if (Date.now() >= deadline) {
        clearInterval(timer);
        resolve_({ matched: false });
      }
    }, interval);
  });
}

// NOTE: `eval` is intentionally NOT handled here. The content-script isolated
// world is CSP-blocked from eval under MV3, so it runs in the service worker via
// chrome.scripting main-world injection (see src/ops.ts).

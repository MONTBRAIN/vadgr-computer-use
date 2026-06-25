// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// DOM op handlers — run in the content script. Selector-first, re-resolved per
// call (the extension holds no element handles between ops, so ops are robust
// to navigation / DOM churn).

import { fillContentEditable, fillField, setText } from "./fill";

export class OpFailed extends Error {}

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
  return document.querySelector(selector);
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
  return Array.from(document.querySelectorAll(selector));
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
  const text = ((el as HTMLElement).innerText ?? el.textContent ?? "").trim();
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

export function opClick(p: { selector: string; by?: string }) {
  const el = require(p.selector, p.by) as HTMLElement;
  el.scrollIntoView?.({ block: "center" });
  el.click();
  // Self-verify: for a checkable control, read back the post-click state so the
  // result carries the proof the click took effect (not just that it dispatched).
  // For other elements the effect is page-level — the agent verifies via a
  // read-back op (or the SW reports {navigated} when the click navigated away).
  const out: { clicked: boolean; checked?: boolean } = { clicked: true };
  if (
    el instanceof HTMLInputElement &&
    (el.type === "checkbox" || el.type === "radio")
  ) {
    out.checked = el.checked;
  }
  return out;
}

export function opQuery(p: { selector: string; by?: string; all?: boolean }) {
  const els = p.all ? resolveAll(p.selector, p.by) : (() => {
    const one = resolve(p.selector, p.by);
    return one ? [one] : [];
  })();
  return els.map(summarize);
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
}) {
  const el = require(p.selector);

  // Plain text inputs — native value-setter path.
  if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
    const before = el.value;
    const typed = fillField(el, p.text, { clear: p.clear, submit: p.submit });
    // Self-verify: read back the live value and confirm the DOM actually holds
    // what we typed. (On `submit` the field may reset/navigate — verify the page
    // reaction, not the field; `ok` then reflects the field, not the submit.)
    const expected = (p.clear ?? true) ? p.text : before + p.text;
    const value = el.value;
    return { typed, value, ok: value === expected };
  }

  // Rich editors — contenteditable path (execCommand insertText).
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

export function opSelect(p: { selector: string; value: string }) {
  const el = require(p.selector);
  if (!(el instanceof HTMLSelectElement)) {
    throw new OpFailed(`${p.selector} is not a <select>`);
  }
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

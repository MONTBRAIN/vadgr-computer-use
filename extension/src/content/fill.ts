// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// FILL primitives — ported from task-extractor/core/fill-utils.js. Fills the
// way a person would: a native value-set plus dispatched input/change/blur, so
// React/MUI's value tracker registers the change. No CDP, no debugger.

type Fillable = HTMLInputElement | HTMLTextAreaElement;

/**
 * Set a (possibly React-controlled) text field. Uses the prototype's native
 * value setter so React's value tracker sees the change, then dispatches the
 * events a real keystroke + blur would.
 */
export function setText(el: Fillable, value: string): void {
  const proto =
    el instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
  const next = value == null ? "" : String(value);
  el.focus();
  if (setter) setter.call(el, next);
  else el.value = next;
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  el.dispatchEvent(new Event("blur", { bubbles: true }));
}

export interface FillOptions {
  clear?: boolean;
  submit?: boolean;
}

/**
 * Fill a field end to end: optional clear, set the value, optionally submit
 * with an Enter keydown. Returns the number of characters written.
 */
export function fillField(
  el: Fillable,
  text: string,
  opts: FillOptions = {},
): number {
  const clear = opts.clear ?? true;
  const next = clear ? text : (el.value ?? "") + text;
  setText(el, next);
  if (opts.submit) {
    el.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "Enter",
        code: "Enter",
        keyCode: 13,
        bubbles: true,
        cancelable: true,
      }),
    );
  }
  return text.length;
}

/**
 * Fill a `contenteditable` element (Gmail / Notion / Slack / ProseMirror / Draft).
 *
 * The reliable cross-editor path is `execCommand("insertText")`: it fires a
 * `beforeinput` event with `inputType: "insertText"`, which is what these editors
 * consume to update their *internal state tree*. Setting `innerText` + a generic
 * `input` event does NOT — the editor re-renders from its own state and overwrites
 * the injected text (this is exactly why setting Gmail's body via `eval` came back
 * empty). Falls back to a synthesized `beforeinput`/`input` pair (with the correct
 * inputType) where `execCommand` is unavailable. Returns the chars written.
 */
export function fillContentEditable(
  el: HTMLElement,
  text: string,
  opts: FillOptions = {},
): number {
  const clear = opts.clear ?? true;
  el.focus();

  // Select all (clear → replace) or collapse to the end (append).
  try {
    const view = el.ownerDocument.defaultView ?? window;
    const sel = view.getSelection?.();
    const range = el.ownerDocument.createRange();
    range.selectNodeContents(el);
    if (!clear) range.collapse(false);
    sel?.removeAllRanges();
    sel?.addRange(range);
  } catch {
    /* selection APIs absent in some harnesses — execCommand/fallback still run */
  }

  let ok = false;
  try {
    ok = el.ownerDocument.execCommand("insertText", false, text);
  } catch {
    ok = false;
  }

  if (!ok) {
    // Fallback: synthesize the editing events with the correct inputType, then
    // set the text directly so a non-stateful contenteditable still updates.
    try {
      el.dispatchEvent(
        new InputEvent("beforeinput", {
          inputType: clear ? "insertReplacementText" : "insertText",
          data: text,
          bubbles: true,
          cancelable: true,
        }),
      );
    } catch {
      /* InputEvent unsupported in harness */
    }
    el.textContent = clear ? text : (el.textContent ?? "") + text;
    try {
      el.dispatchEvent(
        new InputEvent("input", { inputType: "insertText", data: text, bubbles: true }),
      );
    } catch {
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }

  el.dispatchEvent(new Event("change", { bubbles: true }));
  return text.length;
}

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

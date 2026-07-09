// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// TDD for the new content-script DOM ops: element_state (the explicit
// actionability read), clear (DOM fast path), get_value (live property for
// standard controls). element_state surfaces the same visible / receives-events /
// enabled signals the actionability precondition asserts, so the agent can check
// before acting and pick the authoritative element.

import { describe, it, expect, beforeEach } from "vitest";
import { opElementState, opClear, opGetValue } from "../src/content/ops";

beforeEach(() => {
  document.body.innerHTML = "";
});

describe("opElementState", () => {
  it("reports visible/enabled/editable/value for a text input", () => {
    document.body.innerHTML = `<input id="n" value="hi" />`;
    const r: any = opElementState({ selector: "#n" });
    expect(r.visible).toBe(true);
    expect(r.enabled).toBe(true);
    expect(r.editable).toBe(true);
    expect(r.value).toBe("hi");
    expect(r).toHaveProperty("receives_events");
    expect(r).toHaveProperty("focused");
    expect(r).toHaveProperty("bbox");
  });

  it("reports checked for a checkbox and disabled state", () => {
    document.body.innerHTML = `<input id="c" type="checkbox" checked disabled />`;
    const r: any = opElementState({ selector: "#c" });
    expect(r.checked).toBe(true);
    expect(r.enabled).toBe(false);
  });

  it("reports not-visible for a display:none element", () => {
    document.body.innerHTML = `<div id="h" style="display:none">x</div>`;
    const r: any = opElementState({ selector: "#h" });
    expect(r.visible).toBe(false);
  });

  it("throws when nothing matches", () => {
    expect(() => opElementState({ selector: "#gone" })).toThrowError(/no element/i);
  });
});

describe("opClear", () => {
  it("empties an input and dispatches events, self-verifying value=''", () => {
    document.body.innerHTML = `<input id="n" value="something" />`;
    const input = document.querySelector("#n") as HTMLInputElement;
    let inputFired = false;
    input.addEventListener("input", () => (inputFired = true));
    const r: any = opClear({ selector: "#n" });
    expect(r).toEqual({ value: "", ok: true });
    expect(input.value).toBe("");
    expect(inputFired).toBe(true);
  });

  it("clears a contenteditable", () => {
    document.body.innerHTML = `<div id="e" contenteditable="true">hello</div>`;
    const r: any = opClear({ selector: "#e" });
    expect(r.value).toBe("");
    expect(r.ok).toBe(true);
  });

  it("returns ok:false for a non-clearable element (escalation trigger)", () => {
    document.body.innerHTML = `<div id="d">x</div>`;
    const r: any = opClear({ selector: "#d" });
    expect(r.ok).toBe(false);
  });
});

describe("opGetValue", () => {
  it("reads an input's live value", () => {
    document.body.innerHTML = `<input id="n" />`;
    (document.querySelector("#n") as HTMLInputElement).value = "typed";
    const r: any = opGetValue({ selector: "#n" });
    expect(r).toEqual({ value: "typed", ok: true });
  });

  it("reads a <select> value", () => {
    document.body.innerHTML = `<select id="s"><option value="a">A</option><option value="b" selected>B</option></select>`;
    const r: any = opGetValue({ selector: "#s" });
    expect(r.value).toBe("b");
  });

  it("reads a contenteditable's text", () => {
    document.body.innerHTML = `<div id="e" contenteditable="true">rich text</div>`;
    const r: any = opGetValue({ selector: "#e" });
    expect(r.value).toContain("rich text");
  });

  it("returns ok:false for a non-value element so the SW escalates to CDP", () => {
    document.body.innerHTML = `<div id="d">x</div>`;
    const r: any = opGetValue({ selector: "#d" });
    expect(r.ok).toBe(false);
    expect(r.value).toBeNull();
  });
});

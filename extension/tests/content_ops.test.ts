// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// TDD for the new content-script DOM ops: element_state (the explicit
// actionability read), clear (DOM fast path), get_value (live property for
// standard controls). element_state surfaces the same visible / receives-events /
// enabled signals the actionability precondition asserts, so the agent can check
// before acting and pick the authoritative element.

import { describe, it, expect, beforeEach } from "vitest";
import {
  opAssertActionable,
  opClear,
  opElementState,
  opGetValue,
  opHumanTypeUnit,
  opHumanSubmit,
} from "../src/content/ops";

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

describe("opAssertActionable", () => {
  it("accepts an actionable target without mutating it", () => {
    document.body.innerHTML = `<input id="n" value="unchanged" />`;
    expect(opAssertActionable({ selector: "#n" })).toEqual({ actionable: true });
    expect((document.querySelector("#n") as HTMLInputElement).value).toBe("unchanged");
  });

  it("rejects a non-actionable target before CDP can mutate it", () => {
    document.body.innerHTML = `<input id="n" style="display:none" />`;
    expect(() => opAssertActionable({ selector: "#n" })).toThrow(/not visible/);
  });
});

describe("opHumanTypeUnit", () => {
  it("DOM-focuses the field and emits ordered units without activating a tab", () => {
    document.body.innerHTML = `<input id="n" value="old" />`;
    const input = document.querySelector("#n") as HTMLInputElement;
    const events: string[] = [];
    for (const name of ["keydown", "beforeinput", "input", "keyup"]) {
      input.addEventListener(name, () => events.push(name));
    }
    expect(opHumanTypeUnit({ selector: "#n", text: "A", replace: true }))
      .toMatchObject({ inserted: true, value: "A", ok: true });
    expect(opHumanTypeUnit({ selector: "#n", text: "b" }))
      .toMatchObject({ inserted: true, value: "Ab", ok: true });
    expect(events).toEqual([
      "keydown", "beforeinput", "input", "keyup",
      "keydown", "beforeinput", "input", "keyup",
    ]);
    expect(document.activeElement).toBe(input);
  });

  it("does not mutate when beforeinput is cancelled", () => {
    document.body.innerHTML = `<input id="n" value="old" />`;
    const input = document.querySelector("#n") as HTMLInputElement;
    input.addEventListener("beforeinput", (event) => event.preventDefault());
    expect(opHumanTypeUnit({ selector: "#n", text: "x", replace: true }))
      .toMatchObject({ inserted: false, value: "old", ok: false });
  });

  it("rejects contenteditable until rich-editor unit insertion is proven", () => {
    document.body.innerHTML = `<div id="e" contenteditable="true">rich</div>`;
    expect(() => opHumanTypeUnit({ selector: "#e", text: "x" }))
      .toThrow(/not a text input or textarea/);
  });
});

describe("opHumanSubmit", () => {
  it("dispatches Enter and requests the owning form submission", () => {
    document.body.innerHTML = `<form><input id="n" /></form>`;
    const form = document.querySelector("form")!;
    const events: string[] = [];
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      events.push("submit");
    });
    const input = document.querySelector("#n")!;
    input.addEventListener("keydown", () => events.push("keydown"));
    input.addEventListener("keyup", () => events.push("keyup"));
    expect(opHumanSubmit({ selector: "#n" })).toEqual({
      accepted: true,
      submitted: true,
    });
    expect(events).toEqual(["keydown", "keyup", "submit"]);
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

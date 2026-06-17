// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.

import { describe, it, expect, beforeEach } from "vitest";
import { setText, fillField } from "../src/content/fill";

describe("setText", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("sets the value via the native setter", () => {
    const input = document.createElement("input");
    document.body.appendChild(input);
    setText(input, "hello");
    expect(input.value).toBe("hello");
  });

  it("dispatches input, change and blur", () => {
    const input = document.createElement("input");
    document.body.appendChild(input);
    const seen: string[] = [];
    for (const t of ["input", "change", "blur"]) {
      input.addEventListener(t, () => seen.push(t));
    }
    setText(input, "x");
    expect(seen).toEqual(["input", "change", "blur"]);
  });

  it("events bubble (so a delegated React handler sees them)", () => {
    const wrap = document.createElement("div");
    const input = document.createElement("input");
    wrap.appendChild(input);
    document.body.appendChild(wrap);
    let bubbled = false;
    wrap.addEventListener("input", () => (bubbled = true));
    setText(input, "y");
    expect(bubbled).toBe(true);
  });

  it("works on a textarea", () => {
    const ta = document.createElement("textarea");
    document.body.appendChild(ta);
    setText(ta, "multi\nline");
    expect(ta.value).toBe("multi\nline");
  });

  it("coerces null to empty string", () => {
    const input = document.createElement("input");
    document.body.appendChild(input);
    setText(input, null as unknown as string);
    expect(input.value).toBe("");
  });
});

describe("fillField", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("clears existing value before typing when clear=true", () => {
    const input = document.createElement("input");
    input.value = "old";
    document.body.appendChild(input);
    const n = fillField(input, "new", { clear: true });
    expect(input.value).toBe("new");
    expect(n).toBe(3);
  });

  it("appends when clear=false", () => {
    const input = document.createElement("input");
    input.value = "ab";
    document.body.appendChild(input);
    fillField(input, "cd", { clear: false });
    expect(input.value).toBe("abcd");
  });

  it("dispatches a keydown Enter when submit=true", () => {
    const input = document.createElement("input");
    document.body.appendChild(input);
    let key = "";
    input.addEventListener("keydown", (e) => (key = (e as KeyboardEvent).key));
    fillField(input, "go", { submit: true });
    expect(key).toBe("Enter");
  });

  it("does not dispatch Enter when submit=false", () => {
    const input = document.createElement("input");
    document.body.appendChild(input);
    let fired = false;
    input.addEventListener("keydown", () => (fired = true));
    fillField(input, "go", { submit: false });
    expect(fired).toBe(false);
  });
});

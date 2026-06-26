// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// TDD for the actionability gate — closes the hollow-verification trap (acting on
// a hidden non-authoritative mirror, e.g. Gmail's compose textarea).

import { describe, it, expect, vi } from "vitest";
import { isVisible, isDisabled, assertActionable } from "../src/content/actionable";

describe("isVisible", () => {
  it("true for a plain attached element", () => {
    document.body.innerHTML = `<div id="d">x</div>`;
    expect(isVisible(document.querySelector("#d") as HTMLElement)).toBe(true);
  });
  it("false for display:none", () => {
    document.body.innerHTML = `<div id="d" style="display:none">x</div>`;
    expect(isVisible(document.querySelector("#d") as HTMLElement)).toBe(false);
  });
  it("false for visibility:hidden", () => {
    document.body.innerHTML = `<div id="d" style="visibility:hidden">x</div>`;
    expect(isVisible(document.querySelector("#d") as HTMLElement)).toBe(false);
  });
  it("false for a zero-box element when layout is live (the size-clipped mirror)", () => {
    document.body.innerHTML = `<textarea id="m"></textarea>`;
    const el = document.querySelector("#m") as HTMLElement;
    vi.spyOn(document.documentElement, "getBoundingClientRect").mockReturnValue(
      { height: 800, width: 1200 } as DOMRect,
    );
    vi.spyOn(el, "getBoundingClientRect").mockReturnValue(
      { width: 0, height: 0, left: 0, top: 0 } as DOMRect,
    );
    vi.spyOn(el, "getClientRects").mockReturnValue({ length: 0 } as unknown as DOMRectList);
    expect(isVisible(el)).toBe(false);
    vi.restoreAllMocks();
  });
});

describe("isDisabled", () => {
  it("true for a disabled input and aria-disabled", () => {
    document.body.innerHTML = `<input id="a" disabled><div id="b" aria-disabled="true"></div>`;
    expect(isDisabled(document.querySelector("#a")!)).toBe(true);
    expect(isDisabled(document.querySelector("#b")!)).toBe(true);
  });
});

describe("assertActionable", () => {
  it("passes a visible, enabled element", () => {
    document.body.innerHTML = `<input id="a">`;
    expect(() => assertActionable(document.querySelector("#a") as HTMLElement, "#a")).not.toThrow();
  });
  it("throws on a hidden target (the mirror trap)", () => {
    document.body.innerHTML = `<textarea id="m" style="display:none"></textarea>`;
    expect(() =>
      assertActionable(document.querySelector("#m") as HTMLElement, "#m"),
    ).toThrowError(/not actionable.*not visible/i);
  });
  it("throws on a disabled target", () => {
    document.body.innerHTML = `<input id="a" disabled>`;
    expect(() =>
      assertActionable(document.querySelector("#a") as HTMLElement, "#a"),
    ).toThrowError(/not actionable.*disabled/i);
  });
  it("force=true bypasses the checks", () => {
    document.body.innerHTML = `<textarea id="m" style="display:none"></textarea>`;
    expect(() =>
      assertActionable(document.querySelector("#m") as HTMLElement, "#m", { force: true }),
    ).not.toThrow();
  });
});

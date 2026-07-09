// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.

import { describe, it, expect, beforeEach } from "vitest";
import {
  opClick,
  opQuery,
  opReadText,
  opGetAttribute,
  opSelect,
  opWaitFor,
  opType,
} from "../src/content/ops";

beforeEach(() => {
  document.body.innerHTML = "";
});

describe("opClick", () => {
  it("clicks a matching element", () => {
    const btn = document.createElement("button");
    btn.id = "go";
    let clicked = false;
    btn.addEventListener("click", () => (clicked = true));
    document.body.appendChild(btn);
    const r = opClick({ selector: "#go" });
    expect(r).toEqual({ clicked: true });
    expect(clicked).toBe(true);
  });

  it("self-verifies a checkbox click by reading back checked", () => {
    document.body.innerHTML = `<input type="checkbox" id="c" />`;
    const r = opClick({ selector: "#c" });
    expect(r).toEqual({ clicked: true, checked: true });
    expect((document.querySelector("#c") as HTMLInputElement).checked).toBe(true);
  });

  it("throws op_failed when nothing matches", () => {
    expect(() => opClick({ selector: "#missing" })).toThrowError(/no element/i);
  });
});

describe("opQuery", () => {
  it("css single returns a light node summary", () => {
    document.body.innerHTML = `<a href="/x" class="lnk">Hello</a>`;
    const r = opQuery({ selector: "a", by: "css", all: false }).nodes;
    expect(r).toHaveLength(1);
    expect(r[0].tag).toBe("a");
    expect(r[0].text).toBe("Hello");
    expect(r[0].attrs.href).toBe("/x");
    expect(r[0].attrs.class).toBe("lnk");
  });

  it("css all returns every match", () => {
    document.body.innerHTML = `<li>1</li><li>2</li><li>3</li>`;
    const r = opQuery({ selector: "li", by: "css", all: true }).nodes;
    expect(r).toHaveLength(3);
    expect(r.map((n) => n.text)).toEqual(["1", "2", "3"]);
  });

  // happy-dom does not implement document.evaluate; the xpath path is the same
  // resolve() branch and runs in real Chrome. Exercise it only when the harness
  // supports it, so the suite stays honest about what it actually verified.
  const xpathIt =
    typeof (document as any).evaluate === "function" ? it : it.skip;
  xpathIt("xpath query works", () => {
    document.body.innerHTML = `<p class="t">findme</p><p>other</p>`;
    const r = opQuery({
      selector: "//p[@class='t']",
      by: "xpath",
      all: false,
    }).nodes;
    expect(r).toHaveLength(1);
    expect(r[0].text).toBe("findme");
  });

  it("returns empty list when nothing matches", () => {
    const r = opQuery({ selector: ".nope", by: "css", all: true });
    expect(r.nodes).toEqual([]);
  });
});

describe("opReadText", () => {
  it("reads an element's text", () => {
    document.body.innerHTML = `<div id="m">  spaced text </div>`;
    expect(opReadText({ selector: "#m" })).toContain("spaced text");
  });

  it("reads the whole body when no selector", () => {
    document.body.innerHTML = `<div>alpha</div><div>beta</div>`;
    const r = opReadText({ selector: null }) as string;
    expect(r).toContain("alpha");
    expect(r).toContain("beta");
  });

  it("throws when selector matches nothing", () => {
    expect(() => opReadText({ selector: "#gone" })).toThrowError(/no element/i);
  });
});

describe("opGetAttribute", () => {
  it("reads a live property for value", () => {
    const input = document.createElement("input");
    input.id = "f";
    input.setAttribute("value", "static");
    input.value = "live";
    document.body.appendChild(input);
    expect(opGetAttribute({ selector: "#f", name: "value" })).toBe("live");
  });

  it("reads checked as a live boolean", () => {
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.id = "c";
    cb.checked = true;
    document.body.appendChild(cb);
    expect(opGetAttribute({ selector: "#c", name: "checked" })).toBe(true);
  });

  it("falls back to getAttribute for static attrs", () => {
    document.body.innerHTML = `<a id="l" href="/p" data-x="9">x</a>`;
    expect(opGetAttribute({ selector: "#l", name: "href" })).toBe("/p");
    expect(opGetAttribute({ selector: "#l", name: "data-x" })).toBe("9");
  });

  it("returns null for a missing attribute", () => {
    document.body.innerHTML = `<a id="l">x</a>`;
    expect(opGetAttribute({ selector: "#l", name: "title" })).toBeNull();
  });
});

describe("opSelect", () => {
  it("selects an option by value and dispatches change", () => {
    document.body.innerHTML = `
      <select id="s">
        <option value="a">A</option>
        <option value="b">B</option>
      </select>`;
    const sel = document.querySelector("#s") as HTMLSelectElement;
    let changed = false;
    sel.addEventListener("change", () => (changed = true));
    const r = opSelect({ selector: "#s", value: "b" });
    expect(r).toEqual({ selected: "b", value: "b", ok: true });
    expect(sel.value).toBe("b");
    expect(changed).toBe(true);
  });

  it("throws if no option matches", () => {
    document.body.innerHTML = `<select id="s"><option value="a">A</option></select>`;
    expect(() => opSelect({ selector: "#s", value: "z" })).toThrowError(
      /no option/i,
    );
  });
});

describe("opType", () => {
  it("fills a field and self-verifies the read-back value", () => {
    document.body.innerHTML = `<input id="n" />`;
    const r = opType({ selector: "#n", text: "abc", clear: true, submit: false });
    expect(r).toEqual({ typed: 3, value: "abc", ok: true });
    expect((document.querySelector("#n") as HTMLInputElement).value).toBe("abc");
  });

  it("appends and self-verifies when clear=false", () => {
    document.body.innerHTML = `<input id="n" value="ab" />`;
    const r = opType({ selector: "#n", text: "cd", clear: false, submit: false });
    expect(r).toEqual({ typed: 2, value: "abcd", ok: true });
  });

  it("fills a contenteditable element and self-verifies the read-back", () => {
    document.body.innerHTML = `<div id="ce" contenteditable="true"></div>`;
    const r = opType({ selector: "#ce", text: "TEST CONTENT", clear: true });
    expect(r.typed).toBe(12);
    expect(r.ok).toBe(true);
    expect(r.value).toContain("TEST CONTENT");
    expect((document.querySelector("#ce") as HTMLElement).textContent).toContain(
      "TEST CONTENT",
    );
  });

  it("rejects an element that is neither a text input nor contenteditable", () => {
    document.body.innerHTML = `<div id="d">x</div>`;
    expect(() => opType({ selector: "#d", text: "y" })).toThrowError(
      /not a text input or contenteditable/i,
    );
  });
});

describe("opWaitFor", () => {
  it("resolves matched=true when already visible", async () => {
    document.body.innerHTML = `<div id="v">x</div>`;
    const r = await opWaitFor({ selector: "#v", state: "visible", timeout: 200 });
    expect(r).toEqual({ matched: true });
  });

  it("resolves matched=true for attached state", async () => {
    document.body.innerHTML = `<div id="a">x</div>`;
    const r = await opWaitFor({ selector: "#a", state: "attached", timeout: 200 });
    expect(r).toEqual({ matched: true });
  });

  it("times out to matched=false when never present", async () => {
    const r = await opWaitFor({ selector: "#never", state: "visible", timeout: 120 });
    expect(r).toEqual({ matched: false });
  });

  it("waits for an element to appear", async () => {
    setTimeout(() => {
      const d = document.createElement("div");
      d.id = "late";
      document.body.appendChild(d);
    }, 40);
    const r = await opWaitFor({ selector: "#late", state: "attached", timeout: 500 });
    expect(r).toEqual({ matched: true });
  });

  it("waits for an element to become hidden", async () => {
    const d = document.createElement("div");
    d.id = "h";
    document.body.appendChild(d);
    setTimeout(() => {
      d.style.display = "none";
    }, 40);
    const r = await opWaitFor({ selector: "#h", state: "hidden", timeout: 500 });
    expect(r).toEqual({ matched: true });
  });
});

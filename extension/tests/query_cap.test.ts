// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// TDD for the 0.4.0 e2e finding: a real-site `query` returned ~61k chars and blew
// the token budget. `query` now caps the node count (limit) + per-node text and
// paginates with an offset cursor → next_cursor, so a large page degrades to
// pages, never a budget blowout. Reproduced first as a failing (over-cap) test.

import { describe, it, expect, beforeEach } from "vitest";
import { opQuery, MAX_NODE_TEXT } from "../src/content/ops";

beforeEach(() => {
  document.body.innerHTML = "";
});

describe("opQuery cap + pagination", () => {
  it("caps a large match set to `limit` and returns a next_cursor", () => {
    document.body.innerHTML = Array.from(
      { length: 120 },
      (_, i) => `<li class="row">item ${i}</li>`,
    ).join("");
    const r: any = opQuery({ selector: ".row", all: true, limit: 50 });
    expect(r.nodes).toHaveLength(50);
    expect(r.next_cursor).toBe(50);
    expect(r.truncated).toBe(true);
  });

  it("resumes from a cursor and stops (no next_cursor) on the last page", () => {
    document.body.innerHTML = Array.from(
      { length: 120 },
      (_, i) => `<li class="row">item ${i}</li>`,
    ).join("");
    const r: any = opQuery({ selector: ".row", all: true, limit: 50, cursor: 100 });
    expect(r.nodes).toHaveLength(20);
    expect(r.next_cursor).toBeUndefined();
    expect(r.nodes[0].text).toBe("item 100");
  });

  it("truncates a huge per-node text to MAX_NODE_TEXT with a marker", () => {
    const big = "x".repeat(MAX_NODE_TEXT + 5000);
    document.body.innerHTML = `<p class="big">${big}</p>`;
    const r: any = opQuery({ selector: ".big", all: true });
    expect(r.nodes[0].text.length).toBeLessThanOrEqual(MAX_NODE_TEXT + 1);
    expect(r.nodes[0].text.endsWith("…")).toBe(true);
  });

  it("small result sets are unpaginated (no next_cursor, not truncated)", () => {
    document.body.innerHTML = `<li class="row">a</li><li class="row">b</li>`;
    const r: any = opQuery({ selector: ".row", all: true });
    expect(r.nodes).toHaveLength(2);
    expect(r.next_cursor).toBeUndefined();
    expect(r.truncated).toBeUndefined();
  });

  it("raises cursor_stale when the cursor is past the current match count", () => {
    document.body.innerHTML = `<li class="row">a</li>`;
    expect(() => opQuery({ selector: ".row", all: true, cursor: 50 })).toThrowError(
      /cursor_stale/i,
    );
  });
});

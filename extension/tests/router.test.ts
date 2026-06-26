// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.

import { describe, it, expect } from "vitest";
import { Router } from "../src/router";
import { okResult, errResult } from "../src/protocol";

describe("Router", () => {
  it("dispatches a registered op and wraps an ok result", async () => {
    const r = new Router();
    r.register("ping", async (p) => ({ pong: p.n }));
    const out = await r.handle({ type: "op", id: 1, op: "ping", params: { n: 5 } });
    expect(out).toEqual(okResult(1, { pong: 5 }));
  });

  it("rejects a duplicate registration", () => {
    const r = new Router();
    r.register("x", async () => 1);
    expect(() => r.register("x", async () => 2)).toThrowError(/duplicate/i);
  });

  it("returns an op_failed error for an unknown op", async () => {
    const r = new Router();
    const out = await r.handle({ type: "op", id: 2, op: "nope", params: {} });
    expect(out).toEqual(errResult(2, "op_failed", expect.stringMatching(/unknown op/i)));
  });

  it("maps a thrown handler error to an error result", async () => {
    const r = new Router();
    r.register("boom", async () => {
      throw new Error("kaboom");
    });
    const out = await r.handle({ type: "op", id: 3, op: "boom", params: {} });
    expect(out).toEqual(errResult(3, "op_failed", "kaboom"));
  });

  it("preserves the message id on the result", async () => {
    const r = new Router();
    r.register("echo", async () => "ok");
    const out = await r.handle({ type: "op", id: 99, op: "echo", params: {} });
    expect((out as any).id).toBe(99);
  });

  it("lists registered op names sorted", () => {
    const r = new Router();
    r.register("b", async () => 1);
    r.register("a", async () => 2);
    expect(r.names).toEqual(["a", "b"]);
  });
});

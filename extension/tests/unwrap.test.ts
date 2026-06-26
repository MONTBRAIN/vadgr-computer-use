// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// Guards the action-verification invariant: a failed DOM op must surface as an
// error, never be masked as a success-looking value. Regression test for the
// bug where the content script replied with a rejected Promise (serialized to
// {} by Chrome), so e.g. clicking a non-existent selector looked like it worked.

import { describe, it, expect } from "vitest";
import { unwrap } from "../src/ops";

describe("unwrap (content result envelope)", () => {
  it("returns the payload on ok:true", () => {
    expect(
      unwrap({ type: "result", id: 1, ok: true, result: { clicked: true } }),
    ).toEqual({ clicked: true });
  });

  it("THROWS on ok:false so a failure cannot masquerade as success", () => {
    expect(() =>
      unwrap({
        type: "result",
        id: 1,
        ok: false,
        error: { code: "op_failed", message: "no element matches #missing" },
      }),
    ).toThrowError(/no element matches #missing/);
  });

  it("passes a non-envelope sentinel through (e.g. {navigated})", () => {
    expect(unwrap({ navigated: true })).toEqual({ navigated: true });
  });
});

// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// TDD for the SW-resolved `profiles` op handler (0.6.1). It touches no page: it
// reports THIS connection's own profile identity + recognition context. The
// authoritative multi-connection enumeration lives cua-side (the connection
// registry); this handler answers for its own profile and advertises the
// capability so cua's op-gate passes.

import { describe, it, expect } from "vitest";
import { profilesOp } from "../src/ops";

const deps = {
  profileId: async () => "9f2c-uuid",
  context: async () => ({
    window_count: 2,
    tab_count: 3,
    sample_tab_titles: ["Work Gmail", "Figma"],
  }),
  browser: "chrome",
};

describe("profilesOp", () => {
  it("list returns this profile with its recognition context", async () => {
    const out = (await profilesOp({ op: "list" }, deps)) as any;
    expect(out.profiles).toHaveLength(1);
    expect(out.profiles[0]).toMatchObject({
      profile_id: "9f2c-uuid",
      browser: "chrome",
      is_current: true,
      window_count: 2,
      tab_count: 3,
      sample_tab_titles: ["Work Gmail", "Figma"],
    });
  });

  it("use reports this profile as current", async () => {
    const out = (await profilesOp({ op: "use" }, deps)) as any;
    expect(out).toEqual({
      profile_id: "9f2c-uuid",
      browser: "chrome",
      is_current: true,
    });
  });

  it("defaults to list and rejects an unknown sub-op", async () => {
    const out = (await profilesOp({}, deps)) as any;
    expect(out.profiles).toHaveLength(1);
    await expect(profilesOp({ op: "bogus" }, deps)).rejects.toThrow(/sub-op/i);
  });
});

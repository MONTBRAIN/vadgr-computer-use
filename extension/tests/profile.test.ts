// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// TDD for the per-profile identity (0.6.1). The extension mints a stable
// per-profile UUID in chrome.storage.local (isolated per profile, no new
// permission), reports it + recognition context in `hello`, and answers the
// SW-resolved `profiles` op for its own connection.

import { describe, it, expect } from "vitest";
import {
  ensureProfileId,
  buildProfileContext,
  type ProfileStorageLike,
} from "../src/target/profile";
import { serverHello } from "../src/protocol";

// A minimal fake of chrome.storage.local: a single in-memory bag, so we can
// prove the UUID is minted once and read back on the next "reload".
function fakeLocal(seed: Record<string, unknown> = {}): ProfileStorageLike & {
  bag: Record<string, unknown>;
  writes: number;
} {
  const bag: Record<string, unknown> = { ...seed };
  let writes = 0;
  return {
    bag,
    get writes() {
      return writes;
    },
    async get(keys: string) {
      return keys in bag ? { [keys]: bag[keys] } : {};
    },
    async set(items: Record<string, unknown>) {
      writes++;
      Object.assign(bag, items);
    },
  };
}

describe("ensureProfileId", () => {
  it("mints a UUID once and persists it in storage.local", async () => {
    const storage = fakeLocal();
    let n = 0;
    const gen = () => `uuid-${++n}`;
    const id = await ensureProfileId(storage, gen);
    expect(id).toBe("uuid-1");
    expect(storage.bag["vadgr_profile_id"]).toBe("uuid-1");
    expect(storage.writes).toBe(1);
  });

  it("is stable across reloads: a second call returns the same id, no re-mint", async () => {
    const storage = fakeLocal();
    let n = 0;
    const gen = () => `uuid-${++n}`;
    const first = await ensureProfileId(storage, gen);
    const second = await ensureProfileId(storage, gen);
    expect(second).toBe(first);
    // A reload rebuilds the module but reads the SAME persisted value.
    const reloaded = await ensureProfileId(fakeLocal({ vadgr_profile_id: first }), gen);
    expect(reloaded).toBe(first);
    // Only the very first mint wrote; later reads never re-mint.
    expect(storage.writes).toBe(1);
  });
});

describe("buildProfileContext", () => {
  it("summarizes windows/tabs + a few sample tab titles from the enumeration", async () => {
    const api = {
      getAll: async () => [
        { id: 1, tabs: [{ id: 10, title: "Gmail - work" }, { id: 11, title: "GitHub" }] },
        { id: 2, tabs: [{ id: 12, title: "Figma" }] },
      ],
    };
    const ctx = await buildProfileContext(api as any, 5);
    expect(ctx.window_count).toBe(2);
    expect(ctx.tab_count).toBe(3);
    expect(ctx.sample_tab_titles).toEqual(["Gmail - work", "GitHub", "Figma"]);
  });

  it("caps the sample titles and skips blank ones", async () => {
    const api = {
      getAll: async () => [
        { id: 1, tabs: [{ id: 1, title: "A" }, { id: 2, title: "" }, { id: 3, title: "B" }, { id: 4, title: "C" }] },
      ],
    };
    const ctx = await buildProfileContext(api as any, 2);
    expect(ctx.tab_count).toBe(4);
    expect(ctx.sample_tab_titles).toEqual(["A", "B"]);
  });
});

describe("serverHello with profile identity", () => {
  it("carries profile_id + context additively; omits them when absent", () => {
    const ctx = { window_count: 3, tab_count: 21, sample_tab_titles: ["Gmail"] };
    const hello = serverHello("0.6.1", "chrome", "9f2c-uuid", ctx);
    expect(hello.proto).toBe(1);
    expect(hello.profile_id).toBe("9f2c-uuid");
    expect(hello.profile).toEqual(ctx);
    expect(hello.supported_ops).toContain("profiles");

    // Back-compat: no profile args -> no profile fields on the wire.
    const bare = serverHello("0.6.1", "chrome");
    expect(bare.profile_id).toBeUndefined();
    expect(bare.profile).toBeUndefined();
  });
});

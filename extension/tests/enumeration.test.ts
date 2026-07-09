// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// TDD for enumeration — chrome.windows.getAll({populate}) mapped to the
// window -> tabs -> {tab_id,url,title,active,owned,is_current} tree, with the
// owned / is_current join against the registry. A window the agent doesn't own
// is tagged owned:false.

import { describe, it, expect } from "vitest";
import {
  enumerateTabs,
  enumerateWindows,
  type WindowsEnumApi,
  type RegistryJoin,
} from "../src/target/enumeration";

const TREE = [
  {
    id: 42,
    focused: false,
    tabs: [
      { id: 137, windowId: 42, url: "https://www.youtube.com/", title: "YouTube", active: true },
    ],
  },
  {
    id: 61,
    focused: true,
    tabs: [
      { id: 88, windowId: 61, url: "https://mail.google.com/", title: "Inbox", active: true },
      { id: 90, windowId: 61, url: "https://news.ycombinator.com/", title: "HN", active: false },
    ],
  },
];

function api(windows = TREE): WindowsEnumApi {
  return { getAll: async () => windows as any };
}

function join(owned: Set<number>, current: number | null): RegistryJoin {
  return { isOwned: (id) => owned.has(id), current };
}

describe("enumerateTabs", () => {
  it("maps getAll({populate}) to the full window -> tabs tree with the join", async () => {
    const tree = await enumerateTabs(api(), join(new Set([137]), 137));
    expect(tree).toEqual({
      windows: [
        {
          window_id: 42,
          focused: false,
          owned: true,
          tabs: [
            {
              tab_id: 137,
              url: "https://www.youtube.com/",
              title: "YouTube",
              active: true,
              owned: true,
              is_current: true,
            },
          ],
        },
        {
          window_id: 61,
          focused: true,
          owned: false,
          tabs: [
            {
              tab_id: 88,
              url: "https://mail.google.com/",
              title: "Inbox",
              active: true,
              owned: false,
              is_current: false,
            },
            {
              tab_id: 90,
              url: "https://news.ycombinator.com/",
              title: "HN",
              active: false,
              owned: false,
              is_current: false,
            },
          ],
        },
      ],
    });
  });

  it("tags a window the agent does not own as owned:false", async () => {
    const tree = await enumerateTabs(api(), join(new Set(), null));
    expect(tree.windows.every((w) => w.owned === false)).toBe(true);
    expect(tree.windows.flatMap((w) => w.tabs).every((t) => !t.owned && !t.is_current)).toBe(true);
  });

  it("passes populate:true to getAll", async () => {
    let seen: any = null;
    const spyApi: WindowsEnumApi = {
      getAll: async (opts) => {
        seen = opts;
        return TREE as any;
      },
    };
    await enumerateTabs(spyApi, join(new Set(), null));
    expect(seen).toEqual({ populate: true });
  });
});

describe("enumerateWindows (thin variant)", () => {
  it("returns per-window summaries with tab_count + active_tab_id", async () => {
    const out = await enumerateWindows(api(), join(new Set([137]), 137));
    expect(out).toEqual({
      windows: [
        { window_id: 42, focused: false, owned: true, tab_count: 1, active_tab_id: 137 },
        { window_id: 61, focused: true, owned: false, tab_count: 2, active_tab_id: 88 },
      ],
    });
  });
});

// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// OwnedWindowManager — opens the agent's dedicated automation window. It lives
// in the user's REAL Chrome profile (real cookies / logins / passkeys), but is a
// SEPARATE window opened `focused:false`, so it never fights the user's
// foreground tab and the user keeps working untouched. The chrome.windows.create
// glue is live-only; the sequencing + shape is pure and unit-tested against a
// fake WindowsLike.

export interface PinnedTarget {
  windowId: number;
  tabId: number;
}

// The slice of chrome.windows we depend on — injectable so the manager is
// testable with no browser.
export interface WindowsLike {
  create(opts: {
    focused?: boolean;
    url?: string;
    state?: "normal" | "minimized" | "maximized" | "fullscreen";
    width?: number;
    height?: number;
  }): Promise<{ id?: number; tabs?: { id?: number }[] }>;
}

export class OwnedWindowManager {
  constructor(private readonly windows: WindowsLike) {}

  // Open a fresh owned window (unfocused) and pin its first tab.
  async create(): Promise<PinnedTarget> {
    // `state: "normal"` at a usable size — NOT minimized — so the page has a real
    // viewport that hit-tests correctly, but `focused: false` so it never steals
    // the user's foreground. A bare `{focused:false}` opens minimized (~0px
    // viewport) on some hosts (e.g. WSL -> Windows Chrome), which then fails the
    // actionability hit-test.
    const win = await this.windows.create({
      focused: false,
      state: "normal",
      width: 1200,
      height: 900,
    });
    const windowId = win.id;
    const tabId = win.tabs?.[0]?.id;
    if (windowId == null || tabId == null) {
      throw new Error("owned window did not return a tab to pin");
    }
    return { windowId, tabId };
  }
}

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
  }): Promise<{ id?: number; tabs?: { id?: number }[] }>;
}

export class OwnedWindowManager {
  constructor(private readonly windows: WindowsLike) {}

  // Open a fresh owned window (unfocused) and pin its first tab.
  async create(): Promise<PinnedTarget> {
    const win = await this.windows.create({ focused: false });
    const windowId = win.id;
    const tabId = win.tabs?.[0]?.id;
    if (windowId == null || tabId == null) {
      throw new Error("owned window did not return a tab to pin");
    }
    return { windowId, tabId };
  }
}

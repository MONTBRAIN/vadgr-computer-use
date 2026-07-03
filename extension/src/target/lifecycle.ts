// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// Target lifecycle — keeps the pinned target correct as tabs/windows spawn and
// close. A tab spawned FROM the pinned tab (openerTabId === pinned: target=_blank,
// an OAuth popup) is the agent's own flow, so we re-pin and follow it; a tab the
// USER opened has no such link and is left alone. When the pinned tab is closed we
// clear it — the next resolve() re-establishes (owned) or raises target_lost
// (attach). We NEVER silently retarget the user's active tab here.

import type { TargetResolver } from "./resolver";

// Only the slice of TargetResolver the listeners touch (event-time state, not
// resolve()).
type ResolverLike = Pick<TargetResolver, "current" | "pin" | "markLost">;

export interface CreatedTab {
  id?: number;
  windowId?: number;
  openerTabId?: number;
}

export class Lifecycle {
  constructor(private readonly resolver: ResolverLike) {}

  async onTabCreated(tab: CreatedTab): Promise<void> {
    const cur = this.resolver.current();
    if (!cur || tab.id == null || tab.windowId == null) return;
    // Caused by our action? (spawned from the pinned tab) → follow the flow.
    if (tab.openerTabId === cur.tabId) {
      await this.resolver.pin({ windowId: tab.windowId, tabId: tab.id });
    }
  }

  async onTabRemoved(tabId: number): Promise<void> {
    const cur = this.resolver.current();
    if (cur && cur.tabId === tabId) await this.resolver.markLost();
  }
}

// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// Target lifecycle — keeps the registry correct as tabs spawn and close. A tab
// spawned FROM an OWNED tab (openerTabId is owned: target=_blank, an OAuth popup)
// is the agent's own flow, so we register it owned and follow it; a tab the USER
// opened has no such link and is left alone (it stays a `user` context). When a
// tab closes we forget it — if it was `current`, the next resolve() raises
// target_lost (established stays true), never a silent blank re-open. We NEVER
// silently retarget the user's active tab here.

import type { TargetResolver } from "./resolver";

// Only the slice of TargetResolver the listeners touch (event-time state, not
// resolve()).
type ResolverLike = Pick<TargetResolver, "isOwnedTab" | "pin" | "onTabClosed">;

export interface CreatedTab {
  id?: number;
  windowId?: number;
  openerTabId?: number;
}

export class Lifecycle {
  constructor(private readonly resolver: ResolverLike) {}

  async onTabCreated(tab: CreatedTab): Promise<void> {
    if (tab.id == null || tab.windowId == null || tab.openerTabId == null) return;
    // Spawned from a tab WE own? (openerTabId chain) -> follow the flow, owned.
    if (await this.resolver.isOwnedTab(tab.openerTabId)) {
      await this.resolver.pin({ windowId: tab.windowId, tabId: tab.id });
    }
  }

  async onTabRemoved(tabId: number): Promise<void> {
    // Drop it from the registry. If it was `current`, the next resolve() raises
    // target_lost — forget() keeps `established`, so loss stays loud.
    await this.resolver.onTabClosed(tabId);
  }
}

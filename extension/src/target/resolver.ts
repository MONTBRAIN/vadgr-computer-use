// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// TargetResolver — the single target authority. 0.4.0 resolved each op's target
// inline via chrome.tabs.query({active:true, currentWindow:true}), so the agent
// acted on whatever window the HUMAN last focused (active-tab hijack; an eval
// landing on a different tab than the DOM ops). 0.5.0 pins an explicit {windowId,
// tabId} session target resolved ONCE and used by every op BY ID. `active` /
// `currentWindow` are banned for op targeting; the only legitimate `active` read
// is the one-time attach snapshot (scoped to lastFocusedWindow, never bare).
//
// Loss is loud: a closed attach target raises target_lost (never a silent grab
// of the user's active tab — that silent retarget IS the bug this exists to kill).

import { OwnedWindowManager, type PinnedTarget } from "./owned_window";
import type { PersistedState, TargetStore } from "./store";

export type TargetMode = "owned" | "attach";

// A terminal, non-retryable error: the pinned tab/window is gone and cannot be
// re-established (attach mode, or an explicit id that no longer exists). The
// router reads `.code` to surface it as `target_lost` on the wire.
export class TargetLost extends Error {
  readonly code = "target_lost";
  constructor(message = "the pinned tab/window was closed") {
    super(message);
    this.name = "TargetLost";
  }
}

// The slice of chrome.tabs we depend on — id validation + the attach snapshot.
export interface TabsLike {
  get(tabId: number): Promise<{ id?: number; windowId?: number } | undefined>;
  query(q: {
    active: boolean;
    lastFocusedWindow: boolean;
  }): Promise<{ id?: number; windowId?: number }[]>;
}

export interface ResolverDeps {
  tabs: TabsLike;
  owned: OwnedWindowManager;
  store: TargetStore;
}

export class TargetResolver {
  private pinned: PinnedTarget | null = null;
  private mode: TargetMode = "owned";
  private hydrated = false;

  constructor(private readonly deps: ResolverDeps) {}

  // The in-memory pinned target, no revalidation. Used by the lifecycle
  // listeners (which react to events, not resolve()).
  current(): PinnedTarget | null {
    return this.pinned;
  }

  // Resolve the target every op acts on, BY ID. Reuses a live pinned target;
  // otherwise re-establishes per mode (owned → open a fresh window; attach →
  // raise target_lost). Never falls back to "active".
  async resolve(): Promise<PinnedTarget> {
    await this.hydrate();
    if (this.pinned && (await this.isAlive(this.pinned))) return this.pinned;
    // No live target.
    this.pinned = null;
    if (this.mode === "attach") throw new TargetLost();
    return this.pinInternal(await this.deps.owned.create());
  }

  // Explicitly pin the session target. `{tabId}` (with optional `windowId`)
  // selects an existing tab by id; `mode:"attach"` snapshots the active tab of
  // the last-focused window ONCE; `mode:"owned"` (default) opens the dedicated
  // window if none is live.
  async useTarget(
    p: { windowId?: number; tabId?: number; mode?: TargetMode } = {},
  ): Promise<PinnedTarget & { created: boolean }> {
    await this.hydrate();
    this.mode = p.mode ?? "owned";

    // Explicit id selection.
    if (p.tabId != null) {
      const windowId =
        p.windowId ?? (await this.deps.tabs.get(p.tabId))?.windowId;
      if (windowId == null) throw new TargetLost(`tab ${p.tabId} not found`);
      const t = await this.pinInternal({ windowId, tabId: p.tabId });
      return { ...t, created: false };
    }

    if (this.mode === "attach") {
      // The single legitimate `active` read — scoped to the last-focused window,
      // NOT bare {active:true} (which returns the active tab of EVERY window).
      const [tab] = await this.deps.tabs.query({
        active: true,
        lastFocusedWindow: true,
      });
      if (!tab?.id || tab.windowId == null) {
        throw new TargetLost("no active tab to attach to");
      }
      const t = await this.pinInternal({ windowId: tab.windowId, tabId: tab.id });
      return { ...t, created: false };
    }

    // Owned, no ids: reuse a live target or open a fresh owned window.
    if (this.pinned && (await this.isAlive(this.pinned))) {
      return { ...this.pinned, created: false };
    }
    const t = await this.pinInternal(await this.deps.owned.create());
    return { ...t, created: true };
  }

  // Re-pin to a spawned target (lifecycle: a tab our own action opened).
  async pin(t: PinnedTarget): Promise<void> {
    await this.pinInternal(t);
  }

  // The pinned target was closed (lifecycle: onRemoved). Clear it so the next
  // resolve() re-establishes (owned) or raises target_lost (attach). The mode is
  // preserved (persisted) so a slept SW never silently falls back to "active".
  async markLost(): Promise<void> {
    this.pinned = null;
    await this.deps.store.save({ target: null, mode: this.mode });
  }

  private async hydrate(): Promise<void> {
    if (this.hydrated) return;
    this.hydrated = true;
    if (this.pinned) return;
    const state = await this.deps.store.load();
    if (state) {
      this.pinned = state.target;
      this.mode = state.mode;
    }
  }

  private async pinInternal(t: PinnedTarget): Promise<PinnedTarget> {
    this.pinned = t;
    await this.deps.store.save({ target: t, mode: this.mode });
    return t;
  }

  private async isAlive(t: PinnedTarget): Promise<boolean> {
    try {
      const tab = await this.deps.tabs.get(t.tabId);
      return !!tab && tab.id === t.tabId;
    } catch {
      return false;
    }
  }
}

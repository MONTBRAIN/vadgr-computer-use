// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// TargetResolver — the single target authority. 0.4.0 resolved each op's target
// inline via chrome.tabs.query({active:true, currentWindow:true}), so the agent
// acted on whatever window the HUMAN last focused. 0.5.0 pinned ONE explicit
// {windowId, tabId} resolved by id. 0.6.0 generalizes that single pin into an
// enumerable, switchable REGISTRY (registry.ts) plus a `current` pointer, while
// resolve() keeps its exact signature — every executor still acts BY ID, the
// focus-proof guarantee is untouched. `active` / `currentWindow` are still banned
// for op targeting; the only legitimate `active` read is the attach snapshot.
//
// The 0.6.0 headline is LOUD LOSS. resolve() splits a COLD start (never
// established -> auto-open the owned window, the zero-use_target default) from a
// MID-TASK loss (established, current gone -> raise target_lost). The 0.5.0
// silent owned re-open of a blank window — which slipped a wrong target under the
// agent — is gone. The split rides on the persisted `established` flag, so it
// survives an SW idle-termination.

import { OwnedWindowManager, type PinnedTarget } from "./owned_window";
import {
  TargetRegistry,
  type Provenance,
  type TargetRecord,
} from "./registry";
import {
  enumerateTabs,
  enumerateWindows,
  type WindowsEnumApi,
  type WindowNode,
  type WindowSummary,
} from "./enumeration";
import type { TargetStore } from "./store";

export type TargetMode = "owned" | "attach";

// A terminal, non-retryable error: the session `current` is gone mid-task (or an
// explicit id / attach target no longer exists) and must NOT be silently
// re-established. The router reads `.code` to surface it as `target_lost`.
export class TargetLost extends Error {
  readonly code = "target_lost";
  constructor(message = "the pinned tab/window was closed") {
    super(message);
    this.name = "TargetLost";
  }
}

const TARGET_LOST_MESSAGE =
  "the pinned tab was closed; run tabs(list) then use_target, or " +
  "use_target(mode=owned) to open a fresh window";

// The slice of chrome.tabs we depend on — id/url validation + the attach snapshot.
export interface TabsLike {
  get(
    tabId: number,
  ): Promise<{ id?: number; windowId?: number; url?: string } | undefined>;
  query(q: {
    active: boolean;
    lastFocusedWindow: boolean;
  }): Promise<{ id?: number; windowId?: number; url?: string }[]>;
}

export interface ResolverDeps {
  tabs: TabsLike;
  owned: OwnedWindowManager;
  windowsApi: WindowsEnumApi;
  store: TargetStore;
}

export interface UseTargetResult extends PinnedTarget {
  created: boolean;
  url: string;
  provenance: Provenance;
}

export class TargetResolver {
  private registry = new TargetRegistry();
  private mode: TargetMode = "owned";
  private hydrated = false;

  constructor(private readonly deps: ResolverDeps) {}

  // The in-memory current target, no revalidation. Used by the target-context
  // wrapping and the lifecycle listeners (which react to events, not resolve()).
  current(): PinnedTarget | null {
    const rec = this.registry.currentRecord();
    return rec ? { windowId: rec.windowId, tabId: rec.tabId } : null;
  }

  // Resolve the target every op acts on, BY ID. A live `current` is returned
  // as-is. A COLD start auto-opens the owned window. A MID-TASK loss (established
  // but current gone) raises target_lost — never a silent blank re-open.
  async resolve(): Promise<PinnedTarget> {
    await this.hydrate();
    if (this.registry.established) {
      const rec = this.registry.currentRecord();
      if (rec && (await this.isAlive(rec))) {
        return { windowId: rec.windowId, tabId: rec.tabId };
      }
      // Mid-task loss: LOUD and terminal, even in owned mode.
      if (this.registry.current != null) {
        this.registry.forget(this.registry.current);
      }
      this.registry.clearCurrent();
      await this.persist();
      throw new TargetLost(TARGET_LOST_MESSAGE);
    }
    // Cold start: the convenient zero-use_target default still auto-opens.
    return this.openOwned();
  }

  // Explicitly pin the session target and report {url, provenance}. `{tabId}`
  // adopts an existing tab as `attached`; `mode:"attach"` snapshots the active
  // tab of the last-focused window ONCE; `mode:"owned"` reuses a live current or
  // opens the dedicated window. Sets `current` in every branch.
  async useTarget(
    p: { windowId?: number; tabId?: number; mode?: TargetMode } = {},
  ): Promise<UseTargetResult> {
    await this.hydrate();
    this.mode = p.mode ?? "owned";

    // Explicit id selection — adopt the tab (owned stays owned via upsert).
    if (p.tabId != null) {
      const tab = await this.deps.tabs.get(p.tabId);
      const windowId = p.windowId ?? tab?.windowId;
      if (windowId == null) throw new TargetLost(`tab ${p.tabId} not found`);
      return this.adopt({ windowId, tabId: p.tabId }, "attached", tab?.url, false);
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
      return this.adopt(
        { windowId: tab.windowId, tabId: tab.id },
        "attached",
        tab.url,
        false,
      );
    }

    // Owned, no ids: reuse a live current or open a fresh owned window.
    const cur = this.registry.currentRecord();
    if (cur && (await this.isAlive(cur))) {
      this.registry.setCurrent(cur.tabId);
      await this.persist();
      return {
        windowId: cur.windowId,
        tabId: cur.tabId,
        created: false,
        url: (await this.urlOf(cur.tabId)) ?? cur.lastSeenUrl ?? "",
        provenance: cur.provenance,
      };
    }
    const t = await this.openOwned();
    return {
      ...t,
      created: true,
      url: (await this.urlOf(t.tabId)) ?? "",
      provenance: "owned",
    };
  }

  // Register a context and make it `current`. Used by tabs.open/switch and
  // windows.open. `owned` outranks a later attached tag (upsert preserves it).
  async adoptCurrent(
    t: PinnedTarget,
    provenance: Provenance,
    url?: string,
  ): Promise<TargetRecord> {
    await this.hydrate();
    const rec = this.registry.upsert({ ...t, provenance, lastSeenUrl: url });
    this.registry.setCurrent(t.tabId);
    await this.persist();
    return rec;
  }

  // Re-pin to a spawned target (lifecycle: a tab an owned tab opened — _blank,
  // OAuth popup). It is the agent's own flow, so it is registered `owned`.
  async pin(t: PinnedTarget): Promise<void> {
    await this.adoptCurrent(t, "owned");
  }

  async isOwnedTab(tabId: number): Promise<boolean> {
    await this.hydrate();
    return this.registry.isOwned(tabId);
  }

  async provenanceOf(tabId: number): Promise<Provenance> {
    await this.hydrate();
    return this.registry.provenanceOf(tabId);
  }

  async isOwnedWindow(windowId: number): Promise<boolean> {
    await this.hydrate();
    return this.registry.isOwnedWindow(windowId);
  }

  // A tab closed (lifecycle onRemoved, or after tabs.close). Drop it; if it was
  // `current`, `established` stays true so the next resolve() raises loud.
  async onTabClosed(tabId: number): Promise<void> {
    await this.hydrate();
    this.registry.forget(tabId);
    await this.persist();
  }

  // A window closed (after windows.close). Drop all its tabs.
  async onWindowClosed(windowId: number): Promise<void> {
    await this.hydrate();
    this.registry.forgetWindow(windowId);
    await this.persist();
  }

  // tabs(op="list") — the full window -> tabs tree, joined with the registry.
  async enumerate(): Promise<{ windows: WindowNode[] }> {
    await this.hydrate();
    return enumerateTabs(this.deps.windowsApi, {
      isOwned: (id) => this.registry.isOwned(id),
      current: this.registry.current,
    });
  }

  // windows(op="list") — the thin variant.
  async listWindows(): Promise<{ windows: WindowSummary[] }> {
    await this.hydrate();
    return enumerateWindows(this.deps.windowsApi, {
      isOwned: (id) => this.registry.isOwned(id),
      current: this.registry.current,
    });
  }

  private async openOwned(): Promise<PinnedTarget> {
    const t = await this.deps.owned.create();
    this.registry.upsert({ ...t, provenance: "owned" });
    this.registry.setCurrent(t.tabId);
    await this.persist();
    return t;
  }

  private async adopt(
    t: PinnedTarget,
    provenance: Provenance,
    url: string | undefined,
    created: boolean,
  ): Promise<UseTargetResult> {
    const rec = await this.adoptCurrent(t, provenance, url);
    return {
      windowId: rec.windowId,
      tabId: rec.tabId,
      created,
      url: url ?? "",
      provenance: rec.provenance,
    };
  }

  private async hydrate(): Promise<void> {
    if (this.hydrated) return;
    this.hydrated = true;
    const state = await this.deps.store.load();
    if (state) {
      this.registry.restore(state.registry);
      this.mode = state.mode;
    }
  }

  private async persist(): Promise<void> {
    await this.deps.store.save({
      registry: this.registry.snapshot(),
      mode: this.mode,
    });
  }

  private async isAlive(t: PinnedTarget): Promise<boolean> {
    try {
      const tab = await this.deps.tabs.get(t.tabId);
      return !!tab && tab.id === t.tabId;
    } catch {
      return false;
    }
  }

  private async urlOf(tabId: number): Promise<string | undefined> {
    try {
      return (await this.deps.tabs.get(tabId))?.url;
    } catch {
      return undefined;
    }
  }
}

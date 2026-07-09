// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// TargetRegistry — the multi-context model 0.6.0 generalizes the 0.5.0 single
// pin into. It holds a Map<tabId, TargetRecord> of KNOWN contexts, a `current`
// pointer every op resolves to, and an `established` flag that survives an SW
// idle-termination (persisted). The flag is what splits a COLD start (never
// established -> auto-open the owned window) from a MID-TASK loss (established,
// current gone -> raise target_lost, never a silent blank re-open).
//
// Provenance is who created/adopted a context: `owned` (the agent's automation
// window / tabs it opened / spawns from an owned tab), `attached` (a user tab
// the agent explicitly adopted via use_target / tabs.switch), or `user` (every
// other context enumeration sees — visible, never acted on). `owned` outranks
// the rest: re-adopting an owned tab never demotes it.

export type Provenance = "owned" | "attached" | "user";

export interface TargetRecord {
  windowId: number;
  tabId: number;
  provenance: Provenance;
  lastSeenUrl?: string;
}

// The persistable shape — records + the current pointer + established, so a
// woken service worker rebuilds the exact registry (and the cold/mid-task split).
export interface RegistryState {
  records: TargetRecord[];
  current: number | null;
  established: boolean;
}

export class TargetRegistry {
  private targets = new Map<number, TargetRecord>();
  private _current: number | null = null;
  private _established = false;

  get current(): number | null {
    return this._current;
  }

  get established(): boolean {
    return this._established;
  }

  get(tabId: number): TargetRecord | undefined {
    return this.targets.get(tabId);
  }

  has(tabId: number): boolean {
    return this.targets.has(tabId);
  }

  // Register or update a known context. `owned` outranks a later attached/user
  // tag: a tab we created stays owned even if it is re-adopted (switched to).
  upsert(rec: TargetRecord): TargetRecord {
    const prev = this.targets.get(rec.tabId);
    const provenance: Provenance =
      prev?.provenance === "owned" ? "owned" : rec.provenance;
    const merged: TargetRecord = { ...prev, ...rec, provenance };
    this.targets.set(rec.tabId, merged);
    return merged;
  }

  // Point `current` at a tab. This is the ONLY place `established` becomes true:
  // once a current has ever been set this session, a later loss is mid-task.
  setCurrent(tabId: number): void {
    this._current = tabId;
    this._established = true;
  }

  currentRecord(): TargetRecord | undefined {
    return this._current == null ? undefined : this.targets.get(this._current);
  }

  // Clear `current` WITHOUT clearing `established` — a mid-task loss must stay
  // distinguishable from a cold start so the next resolve() raises loud.
  clearCurrent(): void {
    this._current = null;
  }

  // A tab closed: drop it, and if it was current, clear the pointer (keeping
  // established, so the next resolve() raises target_lost, never re-opens).
  forget(tabId: number): void {
    this.targets.delete(tabId);
    if (this._current === tabId) this._current = null;
  }

  // Drop every tab of a window (the window closed).
  forgetWindow(windowId: number): void {
    for (const [tabId, rec] of [...this.targets]) {
      if (rec.windowId === windowId) this.forget(tabId);
    }
  }

  isOwned(tabId: number): boolean {
    return this.targets.get(tabId)?.provenance === "owned";
  }

  // A window is owned if it holds any owned tab (the enumeration join + the
  // windows.close safety check).
  isOwnedWindow(windowId: number): boolean {
    for (const rec of this.targets.values()) {
      if (rec.provenance === "owned" && rec.windowId === windowId) return true;
    }
    return false;
  }

  // Provenance as the world sees a raw tabId: an untracked tab is the user's.
  provenanceOf(tabId: number): Provenance {
    return this.targets.get(tabId)?.provenance ?? "user";
  }

  snapshot(): RegistryState {
    return {
      records: [...this.targets.values()].map((r) => ({ ...r })),
      current: this._current,
      established: this._established,
    };
  }

  restore(state: RegistryState | null | undefined): void {
    this.targets.clear();
    this._current = null;
    this._established = false;
    if (!state) return;
    for (const r of state.records) this.targets.set(r.tabId, { ...r });
    this._current = state.current;
    this._established = state.established;
  }
}

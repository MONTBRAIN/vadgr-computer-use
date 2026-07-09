// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// Persistence for the session registry. An MV3 service worker idle-terminates
// (~30s), so the target registry (records + `current` + `established`) plus the
// mode must survive a wake. chrome.storage.session is exactly the right store:
// in-memory, cleared on browser restart, never written to disk — a live target
// id has no business on disk. (This is DISTINCT from the 0.4.0 keep-alive, which
// holds the native PORT in an Offscreen Document; that persists no ids.)
//
// Persisting `established` + `current` is load-bearing for 0.6.0's loud loss: a
// worker that idle-terminates and wakes to a closed `current` still raises
// target_lost, because the flag proves a target HAD been established — the wake
// is not mistaken for a cold start that would silently open a blank window.

import type { RegistryState } from "./registry";
import type { TargetMode } from "./resolver";

export interface PersistedState {
  registry: RegistryState;
  mode: TargetMode;
}

export interface TargetStore {
  load(): Promise<PersistedState | null>;
  save(state: PersistedState | null): Promise<void>;
}

const KEY = "vadgr_session_target";

// The slice of chrome.storage.session we depend on — injectable for tests.
export interface SessionStorageLike {
  get(keys: string): Promise<Record<string, unknown>>;
  set(items: Record<string, unknown>): Promise<void>;
  remove(keys: string): Promise<void>;
}

export class SessionTargetStore implements TargetStore {
  constructor(private readonly storage: SessionStorageLike) {}

  async load(): Promise<PersistedState | null> {
    const got = await this.storage.get(KEY);
    return (got?.[KEY] as PersistedState | undefined) ?? null;
  }

  async save(state: PersistedState | null): Promise<void> {
    if (state) await this.storage.set({ [KEY]: state });
    else await this.storage.remove(KEY);
  }
}

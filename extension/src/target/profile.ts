// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// Per-profile identity (0.6.1). Chrome exposes no supported API for "which
// profile am I?", and native messaging passes only the extension origin (same
// for every profile). So the extension mints its OWN stable id: a UUID written
// once to chrome.storage.local, which is isolated per profile. It needs no new
// permission (storage is already granted) and survives reloads / SW restarts.
//
// Alongside the id, the extension reports recognition context it already has
// from the 0.6.0 tab enumeration — window/tab counts + a few tab titles — so a
// human or agent can tell profiles apart ("the one with work Gmail and Figma")
// with no account permission. Both ride in the `hello` handshake (additive).

import type { WindowsEnumApi } from "./enumeration";

const PROFILE_KEY = "vadgr_profile_id";

// The slice of chrome.storage.local we depend on — injectable so minting is
// testable with no browser.
export interface ProfileStorageLike {
  get(keys: string): Promise<Record<string, unknown>>;
  set(items: Record<string, unknown>): Promise<void>;
}

export interface ProfileContext {
  window_count: number;
  tab_count: number;
  sample_tab_titles: string[];
}

// Read the per-profile UUID, minting + persisting it on first run. Stable across
// reloads and service-worker restarts because storage.local is on-disk and
// per-profile. `gen` is injectable for tests; production uses crypto.randomUUID.
export async function ensureProfileId(
  storage: ProfileStorageLike,
  gen: () => string = () => crypto.randomUUID(),
): Promise<string> {
  const got = await storage.get(PROFILE_KEY);
  const existing = got?.[PROFILE_KEY];
  if (typeof existing === "string" && existing) return existing;
  const id = gen();
  await storage.set({ [PROFILE_KEY]: id });
  return id;
}

// Build the recognition context from the same `chrome.windows.getAll({populate})`
// the 0.6.0 enumeration uses (a pure extension API, no path boundary — identical
// on Linux / Windows / macOS / WSL). `sampleLimit` bounds the titles so the hello
// stays small.
export async function buildProfileContext(
  api: WindowsEnumApi,
  sampleLimit = 5,
): Promise<ProfileContext> {
  const wins = await api.getAll({ populate: true });
  let tabCount = 0;
  const titles: string[] = [];
  for (const w of wins) {
    for (const t of w.tabs ?? []) {
      tabCount++;
      if (titles.length < sampleLimit && t.title) titles.push(t.title);
    }
  }
  return {
    window_count: wins.length,
    tab_count: tabCount,
    sample_tab_titles: titles,
  };
}

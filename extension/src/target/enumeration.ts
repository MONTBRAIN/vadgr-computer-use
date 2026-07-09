// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// Enumeration — the map the agent was missing. `chrome.windows.getAll({populate})`
// returns every window and (populated) every tab; a local join against the
// registry tags each with `owned` / `is_current`. This is both the awareness
// surface ("aware of all — its own and the user's") and the recovery path (after
// any drift: list -> find the real tab -> use_target it). READ_ONLY: it never
// touches or acts on a context.
//
// On WSL `getAll` is a pure extension API inside Windows Chrome — no filesystem
// or path boundary (unlike upload); the tree crosses the wire as plain JSON, so
// Linux / Windows / macOS / WSL behave identically here.

export interface ChromeTabInfo {
  id?: number;
  windowId?: number;
  url?: string;
  title?: string;
  active?: boolean;
}

export interface ChromeWindowInfo {
  id?: number;
  focused?: boolean;
  tabs?: ChromeTabInfo[];
}

// The slice of chrome.windows we depend on — injectable so enumeration is
// testable with no browser.
export interface WindowsEnumApi {
  getAll(opts: { populate?: boolean }): Promise<ChromeWindowInfo[]>;
}

// The registry facts enumeration joins against (kept as a narrow read view so
// enumeration never mutates targeting state).
export interface RegistryJoin {
  isOwned(tabId: number): boolean;
  current: number | null;
}

export interface TabNode {
  tab_id: number | undefined;
  url: string;
  title: string;
  active: boolean;
  owned: boolean;
  is_current: boolean;
}

export interface WindowNode {
  window_id: number | undefined;
  focused: boolean;
  owned: boolean;
  tabs: TabNode[];
}

export interface WindowSummary {
  window_id: number | undefined;
  focused: boolean;
  owned: boolean;
  tab_count: number;
  active_tab_id: number | null;
}

// tabs(op="list") — the full window -> tabs tree, every window, every tab.
export async function enumerateTabs(
  api: WindowsEnumApi,
  join: RegistryJoin,
): Promise<{ windows: WindowNode[] }> {
  const wins = await api.getAll({ populate: true });
  return {
    windows: wins.map((w) => {
      const tabs: TabNode[] = (w.tabs ?? []).map((t) => ({
        tab_id: t.id,
        url: t.url ?? "",
        title: t.title ?? "",
        active: !!t.active,
        owned: t.id != null && join.isOwned(t.id),
        is_current: t.id != null && join.current === t.id,
      }));
      return {
        window_id: w.id,
        focused: !!w.focused,
        // A window is owned if it holds any owned tab (local registry join).
        owned: tabs.some((t) => t.owned),
        tabs,
      };
    }),
  };
}

// windows(op="list") — the thin variant (windows without the per-tab breakdown).
export async function enumerateWindows(
  api: WindowsEnumApi,
  join: RegistryJoin,
): Promise<{ windows: WindowSummary[] }> {
  const wins = await api.getAll({ populate: true });
  return {
    windows: wins.map((w) => {
      const tabs = w.tabs ?? [];
      const active = tabs.find((t) => t.active);
      return {
        window_id: w.id,
        focused: !!w.focused,
        owned: tabs.some((t) => t.id != null && join.isOwned(t.id)),
        tab_count: tabs.length,
        active_tab_id: active?.id ?? null,
      };
    }),
  };
}

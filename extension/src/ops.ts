// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// Service-worker-side op handlers + registration. Non-DOM ops run here against
// the extension APIs (chrome.tabs, chrome.cookies); DOM ops are forwarded to
// the content script in the active tab. Registration is the OCP seam — adding
// an op is a new handler + a register() line.

import { Router } from "./router";
import type { Executor, Params } from "./executors/types";
import { withEscalation } from "./executors/escalation";
import { CdpExecutor, chromeDebuggerAttach } from "./executors/cdp";
import { TargetResolver, type TargetMode } from "./target/resolver";
import { OwnedWindowManager } from "./target/owned_window";
import { SessionTargetStore } from "./target/store";

// --- the session target (the headline of 0.5.0) ---
//
// Every executor resolves its target through ONE TargetResolver, BY ID. The
// 0.4.0 focus-coupled `query({active, currentWindow})` is GONE from op targeting
// — the only legitimate `active` read is the one-time attach snapshot inside the
// resolver. The resolver is a lazy singleton so importing this module never
// touches chrome.* (safe under the unit-test DOM harness); it is shared with the
// lifecycle listeners in background.ts so re-pins reach the same instance.

let _resolver: TargetResolver | null = null;

function defaultResolver(): TargetResolver {
  const tabs = {
    get: (tabId: number) => chrome.tabs.get(tabId),
    query: (q: { active: boolean; lastFocusedWindow: boolean }) =>
      chrome.tabs.query(q),
  };
  const owned = new OwnedWindowManager({
    create: (opts) => chrome.windows.create(opts) as Promise<any>,
  });
  const store = new SessionTargetStore({
    // @ts-ignore - chrome.storage.session is present at runtime (session perm).
    get: (keys: string) => chrome.storage.session.get(keys),
    // @ts-ignore
    set: (items: Record<string, unknown>) => chrome.storage.session.set(items),
    // @ts-ignore
    remove: (keys: string) => chrome.storage.session.remove(keys),
  });
  return new TargetResolver({ tabs, owned, store });
}

export function sharedResolver(): TargetResolver {
  if (!_resolver) _resolver = defaultResolver();
  return _resolver;
}

function detectBrowserName(): string {
  try {
    return navigator.userAgent.includes("Edg/") ? "edge" : "chrome";
  } catch {
    return "chrome";
  }
}

// The `use_target` control op — explicitly pin the session target and report it.
async function useTargetOp(p: Params) {
  const out = await sharedResolver().useTarget({
    windowId: p.window_id as number | undefined,
    tabId: p.tab_id as number | undefined,
    mode: (p.mode as TargetMode | undefined) ?? "owned",
  });
  return {
    browser: detectBrowserName(),
    window_id: out.windowId,
    tab_id: out.tabId,
    created: out.created,
  };
}

// --- helpers ---

// The pinned target tab, resolved BY ID (never "active"/"currentWindow"). In
// owned mode a first call opens the dedicated window; a lost attach target
// raises target_lost (surfaced by the router as a terminal error).
async function targetTab(): Promise<chrome.tabs.Tab> {
  const { tabId } = await sharedResolver().resolve();
  const tab = await chrome.tabs.get(tabId);
  if (!tab?.id) throw new Error("the pinned tab is gone");
  return tab;
}

// How long to wait for a navigation to settle before returning whatever state
// the tab reached. A heavy SPA — or a tab that never reports "complete" — must
// NOT block the op, and thus the whole single-lock native pipe, forever.
const NAV_SETTLE_TIMEOUT_MS = 15000;

// Resolve when the navigation settles, always bounded by a timeout. `wait`
// mirrors cua's navigate wait: "none" returns immediately; anything else waits
// for tab status "complete". (Chrome's tabs API doesn't surface
// DOMContentLoaded, so "domcontentloaded" shares the "complete" path but is
// still time-bounded.) On timeout we resolve — the caller reads the tab's
// actual url/title — rather than hanging.
function tabComplete(tabId: number, wait?: string): Promise<void> {
  if (wait === "none") return Promise.resolve();
  return new Promise((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      chrome.tabs.onUpdated.removeListener(listener);
      clearTimeout(timer);
      resolve();
    };
    const listener = (id: number, info: chrome.tabs.TabChangeInfo) => {
      if (id === tabId && info.status === "complete") finish();
    };
    chrome.tabs.onUpdated.addListener(listener);
    const timer = setTimeout(finish, NAV_SETTLE_TIMEOUT_MS);
  });
}

async function summary(tab: chrome.tabs.Tab) {
  return { url: tab.url ?? "", title: tab.title ?? "" };
}

// Ops that are safe to re-deliver: pure reads + idempotent scroll. A mutating
// op (click/type/fill/select) must NEVER be auto-retried — a retry could double-
// click or act on the wrong page after a navigation.
const RETRYABLE_OPS = new Set([
  "wait_for",
  "query",
  "read_text",
  "get_attribute",
  "scroll",
  "element_state",
  "get_value",
]);

// The content script is reachable only once its onMessage listener has
// registered. On a fresh page (just navigated) there is a window where it has
// not — sendMessage then throws "Receiving end does not exist" / "Could not
// establish connection". The content script is declared for <all_urls> but
// races document_idle; force it in and retry.
function isUnreachable(msg: string): boolean {
  return /receiving end does not exist|could not establish connection/i.test(msg);
}
// The op's own navigation tore down the page mid-message (channel/bfcache
// closed). The action still happened — report it as a navigation, not an error.
function isNavClose(msg: string): boolean {
  return /message channel is closed|back\/forward cache/i.test(msg);
}

// Unwrap a content-script result envelope. On ok:false we THROW so the SW
// router turns it into a proper {ok:false, error} reply — otherwise an op
// failure (e.g. a selector that matches nothing) would reach cua as a
// success-looking value and defeat verification. Exported for unit testing.
export function unwrap(res: unknown): unknown {
  if (res && typeof res === "object" && (res as any).type === "result") {
    const r = res as { ok: boolean; result?: unknown; error?: { message?: string } };
    if (r.ok) return r.result;
    throw new Error(r.error?.message ?? "op failed");
  }
  return res; // navigation sentinel or legacy shape — pass through
}

// Forward a DOM op into the active tab's content script and await its reply.
// Handles the two post-navigation failure modes distinctly: an unreachable
// content script (re-inject + retry, for safe read ops) vs the op having itself
// navigated away (report {navigated}). A mutating op that loses its channel is
// reported as a navigation, never blindly retried. A genuine op failure
// (ok:false) is re-raised by unwrap, never masked.
async function forwardToContent(op: string, params: Record<string, unknown>) {
  const tab = await targetTab();
  try {
    return unwrap(await chrome.tabs.sendMessage(tab.id!, { type: "op", op, params }));
  } catch (e) {
    const msg = String((e as Error)?.message ?? e);
    if (isUnreachable(msg) && RETRYABLE_OPS.has(op)) {
      // Content script not present yet (fresh navigation) — inject + retry once.
      await chrome.scripting.executeScript({
        target: { tabId: tab.id! },
        files: ["content.js"],
      });
      return unwrap(
        await chrome.tabs.sendMessage(tab.id!, { type: "op", op, params }),
      );
    }
    if (isNavClose(msg)) {
      // The op's own navigation tore down the page mid-message. The action
      // dispatched; report the navigation rather than a transport error.
      return { navigated: true };
    }
    throw e;
  }
}

// `eval` runs JS in the page's MAIN world via chrome.scripting — the content
// script's isolated world is CSP-blocked from eval under MV3. Returns {value}.
// (HIGH-risk escape hatch; page CSP may still forbid eval, which now surfaces
// as a real error instead of an empty result.)
async function evalInPage(expression: string) {
  const tab = await targetTab();
  const [inj] = await chrome.scripting.executeScript({
    target: { tabId: tab.id! },
    world: "MAIN",
    func: (expr: string) => (0, eval)(expr),
    args: [expression],
  });
  return { value: inj?.result };
}

// Wait for a navigation to leave `beforeUrl` and finish loading, or give up
// after `timeout`. A history move with no entry in that direction is a benign
// no-op: it never leaves `beforeUrl`, times out, and the caller returns the
// unchanged page — far friendlier than the old hard "no page in history" error.
function settleNav(
  tabId: number,
  beforeUrl: string | undefined,
  timeout = 4000,
): Promise<void> {
  return new Promise((resolve) => {
    const deadline = Date.now() + timeout;
    const tick = async () => {
      const t = await chrome.tabs.get(tabId).catch(() => null);
      if (t && t.url !== beforeUrl && t.status === "complete") return resolve();
      if (Date.now() >= deadline) return resolve();
      setTimeout(tick, 80);
    };
    tick();
  });
}

// back/forward via the page History API (run in the MAIN world like eval).
// chrome.tabs.goBack/goForward are gated by the user-gesture rule, so
// extension-initiated chrome.tabs.update navigations are unreachable through
// them — they fail "no page in history" even when history.length is large.
// history.go() uses the page session history and is not gated.
async function historyGo(delta: number) {
  const tab = await targetTab();
  const before = (await chrome.tabs.get(tab.id!)).url;
  await chrome.scripting.executeScript({
    target: { tabId: tab.id! },
    world: "MAIN",
    func: (d: number) => history.go(d),
    args: [delta],
  });
  await settleNav(tab.id!, before);
  return summary(await chrome.tabs.get(tab.id!));
}

// --- executors (the backends behind the Executor seam) ---

async function cookiesOp(p: Params) {
  const action = (p.action as string) ?? "get";
  if (action === "get") return chrome.cookies.getAll({ url: p.url as string | undefined });
  if (action === "set")
    return chrome.cookies.set({ url: String(p.url), name: String(p.name), value: String(p.value) });
  if (action === "clear") {
    await chrome.cookies.remove({ url: String(p.url), name: String(p.name) });
    return { ok: true };
  }
  throw new Error(`unknown cookies action ${action}`);
}

// chrome.tabs / chrome.cookies / scripting — navigation, cookies, page eval.
// Not interactive page actions, so these never escalate.
const tabsExecutor: Executor = {
  name: "tabs",
  async execute(op: string, p: Params) {
    switch (op) {
      case "navigate": {
        const tab = await targetTab();
        await chrome.tabs.update(tab.id!, { url: String(p.url) });
        await tabComplete(tab.id!, p.wait as string | undefined);
        return summary(await chrome.tabs.get(tab.id!));
      }
      case "back":
        return historyGo(-1);
      case "forward":
        return historyGo(1);
      case "reload": {
        const tab = await targetTab();
        await chrome.tabs.reload(tab.id!);
        await tabComplete(tab.id!, p.wait as string | undefined);
        return summary(await chrome.tabs.get(tab.id!));
      }
      case "cookies":
        return cookiesOp(p);
      case "eval":
        return evalInPage(String(p.expression));
      default:
        throw new Error(`tabs path has no op '${op}'`);
    }
  },
};

// The content-script DOM fast path.
const domExecutor: Executor = {
  name: "dom",
  execute(op: string, p: Params) {
    return forwardToContent(op, p);
  },
};

// The CDP universal path (chrome.debugger). Null when the API is absent (no
// `debugger` permission / non-extension test context) → escalation is skipped.
// The onEvent channel is passed so the CDP path can handle JS dialogs.
function defaultCdp(): Executor | null {
  if (typeof chrome === "undefined" || !chrome.debugger) return null;
  return new CdpExecutor(
    chromeDebuggerAttach(async () => (await targetTab()).id!),
    chrome.debugger.onEvent,
  );
}

const TABS_OPS = ["navigate", "back", "forward", "reload", "cookies", "eval"];
const DOM_OPS = [
  "wait_for", "query", "read_text", "get_attribute",
  "click", "type", "fill", "select", "scroll",
  // 0.5.0 DOM fast-path ops.
  "element_state", "clear", "get_value",
];
// Interactive ops that self-verify (have a read-back `ok`) AND that the CDP path
// can perform — these escalate DOM→CDP on `ok:false`. (click/select gain
// escalation when the CDP path grows those ops; until then they stay DOM-only.)
const ESCALATING = new Set(["type", "fill", "clear", "get_value"]);
// CDP-only ops (no DOM equivalent).
const CDP_ONLY = [
  "press", "accessibility_tree",
  // 0.5.0 CDP-only ops.
  "hover", "dialog", "upload", "focus", "blur", "snapshot",
];
const isInteractive = (op: string) => ESCALATING.has(op);

// --- registration ---

export function buildRouter(cdp: Executor | null = defaultCdp()): Router {
  const r = new Router();

  for (const op of TABS_OPS) r.register(op, (p) => tabsExecutor.execute(op, p));

  for (const op of DOM_OPS) {
    if (ESCALATING.has(op)) {
      r.register(op, (p) => withEscalation(op, p, domExecutor, cdp, isInteractive));
    } else {
      r.register(op, (p) => domExecutor.execute(op, p));
    }
  }

  if (cdp) for (const op of CDP_ONLY) r.register(op, (p) => cdp.execute(op, p));

  // The session-target control op (SW-resolved; touches no page).
  r.register("use_target", (p) => useTargetOp(p));

  return r;
}

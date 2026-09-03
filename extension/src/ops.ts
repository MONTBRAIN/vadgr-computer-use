// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// Service-worker-side op handlers + registration. Non-DOM ops run here against
// the extension APIs (chrome.tabs, chrome.cookies); DOM ops are forwarded to
// the content script in the active tab. Registration is the OCP seam - adding
// an op is a new handler + a register() line.

import { Router } from "./router";
import type { Executor, Params } from "./executors/types";
import { withEscalation } from "./executors/escalation";
import { CdpExecutor, chromeDebuggerAttach } from "./executors/cdp";
import { TargetResolver, type TargetMode } from "./target/resolver";
import { OwnedWindowManager } from "./target/owned_window";
import { SessionTargetStore } from "./target/store";
import {
  ensureProfileId,
  buildProfileContext,
  type ProfileContext,
  type ProfileStorageLike,
} from "./target/profile";
import type { Provenance } from "./target/registry";
import type { PinnedTarget } from "./target/owned_window";
import type {
  WindowNode,
  WindowSummary,
  WindowsEnumApi,
} from "./target/enumeration";
import {
  clearTypingCancellation,
  typingCancelled,
  waitTypingDelay,
} from "./typing-cancellation";

// --- the session target (the headline of 0.5.0) ---
//
// Every executor resolves its target through ONE TargetResolver, BY ID. The
// 0.4.0 focus-coupled `query({active, currentWindow})` is GONE from op targeting
// - the only legitimate `active` read is the one-time attach snapshot inside the
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
  const windowsApi: WindowsEnumApi = {
    getAll: (opts) => chrome.windows.getAll(opts) as Promise<any>,
  };
  const store = new SessionTargetStore({
    // @ts-ignore - chrome.storage.session is present at runtime (session perm).
    get: (keys: string) => chrome.storage.session.get(keys),
    // @ts-ignore
    set: (items: Record<string, unknown>) => chrome.storage.session.set(items),
    // @ts-ignore
    remove: (keys: string) => chrome.storage.session.remove(keys),
  });
  return new TargetResolver({ tabs, owned, windowsApi, store });
}

export function sharedResolver(): TargetResolver {
  if (!_resolver) _resolver = defaultResolver();
  return _resolver;
}

// chrome.storage.local wrapper for the per-profile UUID (0.6.1). Distinct from
// the session store (chrome.storage.session) the resolver uses: the profile id
// must PERSIST across browser restarts, so it lives on disk in storage.local.
function localProfileStorage(): ProfileStorageLike {
  return {
    // @ts-ignore - chrome.storage.local is present at runtime (storage perm).
    get: (keys: string) => chrome.storage.local.get(keys),
    // @ts-ignore
    set: (items: Record<string, unknown>) => chrome.storage.local.set(items),
  };
}

// The chrome.windows enumeration slice the profile context is built from.
function windowsEnumApi(): WindowsEnumApi {
  return { getAll: (opts) => chrome.windows.getAll(opts) as Promise<any> };
}

function detectBrowserName(): string {
  try {
    return navigator.userAgent.includes("Edg/") ? "edge" : "chrome";
  } catch {
    return "chrome";
  }
}

// This build's version, straight from the manifest. Guarded so the router can
// be built in unit tests with no chrome.* at all.
function extensionVersion(): string {
  try {
    return chrome.runtime?.getManifest?.().version ?? "unknown";
  } catch {
    return "unknown";
  }
}

// The `use_target` control op - explicitly pin the session target and report it.
// 0.6.0 also switches `current` in the registry and reports `url` + `provenance`.
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
    url: out.url,
    provenance: out.provenance,
  };
}

// --- helpers ---

// The pinned target tab, resolved BY ID (never "active"/"currentWindow"). In
// owned mode a first call opens the dedicated window; a lost attach target
// raises target_lost (surfaced by the router as a terminal error).
async function targetTab(params: Params = {}): Promise<chrome.tabs.Tab> {
  const exact = params._target as { window_id?: number; tab_id?: number } | undefined;
  if (exact?.tab_id != null) {
    const tab = await chrome.tabs.get(exact.tab_id);
    if (!tab?.id || (exact.window_id != null && tab.windowId !== exact.window_id)) {
      throw new Error("the exact broker target is gone");
    }
    return tab;
  }
  const { tabId } = await sharedResolver().resolve();
  const tab = await chrome.tabs.get(tabId);
  if (!tab?.id) throw new Error("the pinned tab is gone");
  return tab;
}

function wireError(code: string, message: string): Error {
  return Object.assign(new Error(message), { code });
}

function restrictedPage(url: string): boolean {
  return /^(chrome|edge|devtools|chrome-extension|file):/i.test(url) ||
    /^https:\/\/chromewebstore\.google\.com\//i.test(url);
}

export async function runnableTargetTab(
  params: Params = {},
): Promise<chrome.tabs.Tab> {
  const tab = await targetTab(params);
  if (tab.discarded) {
    throw wireError("target_discarded", "the exact browser target is discarded");
  }
  if ((tab as chrome.tabs.Tab & { frozen?: boolean }).frozen) {
    throw wireError("target_frozen", "the exact browser target is frozen");
  }
  if (restrictedPage(tab.url ?? "")) {
    throw wireError(
      "target_restricted",
      `the extension cannot access the exact browser target URL`,
    );
  }
  return tab;
}

export async function exactTargetReceivesTrustedKeyboard(
  params: Params,
): Promise<boolean> {
  const tab = await runnableTargetTab(params);
  const win = await chrome.windows.get(tab.windowId);
  return tab.active === true && win.focused === true;
}

async function inactiveSafeKeyboardMutation(
  op: string,
  p: Params,
  cdp: Executor | null,
) {
  if (await exactTargetReceivesTrustedKeyboard(p)) {
    return withEscalation(op, p, domExecutor, cdp, isInteractive);
  }
  const result = await domExecutor.execute(op, p) as any;
  if (result?.ok === false) {
    throw wireError(
      "inactive_tab_trusted_keyboard_unsupported",
      `the exact inactive target rejected the ${op} content operation; trusted keyboard fallback was not dispatched`,
    );
  }
  return result;
}

// How long to wait for a navigation to settle before returning whatever state
// the tab reached. A heavy SPA - or a tab that never reports "complete" - must
// NOT block the op, and thus the whole single-lock native pipe, forever.
const NAV_SETTLE_TIMEOUT_MS = 15000;

// Resolve when the navigation settles, always bounded by a timeout. `wait`
// mirrors cua's navigate wait: "none" returns immediately; anything else waits
// for tab status "complete". (Chrome's tabs API doesn't surface
// DOMContentLoaded, so "domcontentloaded" shares the "complete" path but is
// still time-bounded.) On timeout we resolve - the caller reads the tab's
// actual url/title - rather than hanging.
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

// The content script is reachable only once its onMessage listener has
// registered. On a fresh page (just navigated) there is a window where it has
// not - sendMessage then throws "Receiving end does not exist" / "Could not
// establish connection". The content script is declared for <all_urls> but
// races document_idle; force it in and retry.
function isUnreachable(msg: string): boolean {
  return /receiving end does not exist|could not establish connection/i.test(msg);
}
// The op's own navigation tore down the page mid-message (channel/bfcache
// closed). The action still happened - report it as a navigation, not an error.
function isNavClose(msg: string): boolean {
  return /message channel is closed|back\/forward cache/i.test(msg);
}

// Unwrap a content-script result envelope. On ok:false we THROW so the SW
// router turns it into a proper {ok:false, error} reply - otherwise an op
// failure (e.g. a selector that matches nothing) would reach cua as a
// success-looking value and defeat verification. Exported for unit testing.
export function unwrap(res: unknown): unknown {
  if (res && typeof res === "object" && (res as any).type === "result") {
    const r = res as { ok: boolean; result?: unknown; error?: { message?: string } };
    if (r.ok) return r.result;
    throw new Error(r.error?.message ?? "op failed");
  }
  return res; // navigation sentinel or legacy shape - pass through
}

// The two channel primitives self-heal needs, injectable so the retry logic is
// unit-testable with no chrome.* (self_heal.test.ts drives a fake channel).
export interface ContentChannel {
  send(op: string, params: Record<string, unknown>): Promise<unknown>;
  reinject(): Promise<void>;
}

// Deliver a DOM op to the content script, healing the two post-navigation
// failure modes distinctly:
//   - UNREACHABLE ("Receiving end does not exist"): sendMessage found NO
//     listener, so the message never arrived and the op NEVER RAN. Re-injecting
//     content.js and delivering ONCE is therefore a first delivery, not a retry
//     of an executed action - safe for EVERY op, click/fill/type included (0.6.0
//     closes the 0.5.0 "reads self-heal, writes fail on a fresh page" split).
//   - NAV-CLOSE (channel torn down mid-message): the op MAY have run, so it is
//     reported as {navigated} and NEVER redelivered.
// A genuine op failure (ok:false) is re-raised by unwrap, never masked.
export async function deliverWithSelfHeal(
  op: string,
  params: Record<string, unknown>,
  ch: ContentChannel,
): Promise<unknown> {
  try {
    return unwrap(await ch.send(op, params));
  } catch (e) {
    const msg = String((e as Error)?.message ?? e);
    if (isUnreachable(msg)) {
      // Content script not present yet (fresh navigation) - inject + deliver
      // ONCE. Unreachable means not-yet-executed, so this is safe for all ops.
      await ch.reinject();
      return unwrap(await ch.send(op, params));
    }
    if (isNavClose(msg)) {
      // The op's own navigation tore down the page mid-message. The action
      // dispatched; report the navigation rather than a transport error.
      return { navigated: true };
    }
    throw e;
  }
}

// Forward a DOM op into the pinned tab's content script and await its reply.
async function forwardToContent(op: string, params: Record<string, unknown>) {
  const tab = await runnableTargetTab(params);
  const ch: ContentChannel = {
    send: (o, p) => chrome.tabs.sendMessage(tab.id!, { type: "op", op: o, params: p }),
    reinject: async () => {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id! },
        files: ["content.js"],
      });
    },
  };
  try {
    const delivery = deliverWithSelfHeal(op, params, ch);
    if (op !== "wait_for") return await delivery;
    const requested = Number(params.timeout ?? 5000);
    const bound = Math.max(
      2000,
      (Number.isFinite(requested) ? requested : 5000) + 1500,
    );
    return await Promise.race([
      delivery,
      new Promise((resolve) => setTimeout(() => resolve({ matched: false }), bound)),
    ]);
  } catch (e) {
    const message = String((e as Error)?.message ?? e);
    if (/cannot access|extensions gallery|missing host permission/i.test(message)) {
      throw wireError(
        "target_restricted",
        "the extension cannot access the exact browser target",
      );
    }
    throw e;
  }
}

// `eval` runs JS in the page's MAIN world via chrome.scripting - the content
// script's isolated world is CSP-blocked from eval under MV3. Returns {value}.
// (HIGH-risk escape hatch; page CSP may still forbid eval, which now surfaces
// as a real error instead of an empty result.)
async function evalInPage(expression: string, params: Params = {}) {
  const tab = await runnableTargetTab(params);
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
// unchanged page - far friendlier than the old hard "no page in history" error.
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
// them - they fail "no page in history" even when history.length is large.
// history.go() uses the page session history and is not gated.
async function historyGo(delta: number, params: Params = {}) {
  const tab = await targetTab(params);
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

// chrome.tabs / chrome.cookies / scripting - navigation, cookies, page eval.
// Not interactive page actions, so these never escalate.
const tabsExecutor: Executor = {
  name: "tabs",
  async execute(op: string, p: Params) {
    switch (op) {
      case "navigate": {
        const tab = await targetTab(p);
        await chrome.tabs.update(tab.id!, { url: String(p.url) });
        await tabComplete(tab.id!, p.wait as string | undefined);
        return summary(await chrome.tabs.get(tab.id!));
      }
      case "back":
        return historyGo(-1, p);
      case "forward":
        return historyGo(1, p);
      case "reload": {
        const tab = await targetTab(p);
        await chrome.tabs.reload(tab.id!);
        await tabComplete(tab.id!, p.wait as string | undefined);
        return summary(await chrome.tabs.get(tab.id!));
      }
      case "cookies":
        return cookiesOp(p);
      case "eval":
        return evalInPage(String(p.expression), p);
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

interface HumanTypingStream {
  identity: string;
  selector: string;
  clear: boolean;
  submit: boolean;
  expectedValue: string;
  totalUnits: number;
  completedUnits: number;
  fallbackUnits: number;
  timingProfile: string | null;
  nominalWpm: number | null;
  started: number;
  aborted: boolean;
  idleTimer: ReturnType<typeof setTimeout> | null;
}

const humanTypingStreams = new Map<string, HumanTypingStream>();
const HUMAN_TYPING_STREAM_IDLE_MS = 60_000;

function removeHumanTypingStream(
  streamId: string,
  state: HumanTypingStream,
): void {
  state.aborted = true;
  if (state.idleTimer !== null) clearTimeout(state.idleTimer);
  state.idleTimer = null;
  if (humanTypingStreams.get(streamId) === state) {
    humanTypingStreams.delete(streamId);
  }
}

function refreshHumanTypingStreamIdle(
  streamId: string,
  state: HumanTypingStream,
): void {
  if (state.idleTimer !== null) clearTimeout(state.idleTimer);
  state.idleTimer = setTimeout(() => {
    if (humanTypingStreams.get(streamId) === state) {
      removeHumanTypingStream(streamId, state);
    }
  }, HUMAN_TYPING_STREAM_IDLE_MS);
}

export function abortAllHumanTypingStreams(): void {
  for (const [streamId, state] of humanTypingStreams) {
    removeHumanTypingStream(streamId, state);
  }
}

function typingTargetIdentity(p: Params): string {
  return JSON.stringify({
    target: p._target ?? null,
    ownership_revision: p._ownership_revision ?? null,
  });
}

function typingProgressError(code: string, completedUnits: number): Error {
  return Object.assign(
    new Error(`${code}: ${completedUnits} complete units`),
    { code },
  );
}

async function legacyHumanTypeViaExactContentTarget(p: Params, dom: Executor) {
  const plan = p.typing_plan as any;
  if (!plan || !Array.isArray(plan.units)) {
    throw new Error("human typing requires a validated typing plan");
  }
  await dom.execute("assert_actionable", p);
  const beforeResult = await dom.execute("get_value", p) as any;
  if (!beforeResult || beforeResult.ok !== true || typeof beforeResult.value !== "string") {
    throw new Error(`${String(p.selector)} is not a text input or textarea`);
  }
  const requestId = Number(p._request_id);
  let completedUnits = 0;
  let fallbackUnits = 0;
  let expectedValue = p.clear !== false ? "" : beforeResult.value;
  const started = Date.now();
  try {
    if (plan.units.length === 0 && p.clear !== false) {
      const cleared = await dom.execute("clear", p) as any;
      if (!cleared || cleared.ok !== true || cleared.value !== "") {
        throw Object.assign(new Error("typing_mismatch: empty clear did not complete"), {
          code: "typing_mismatch",
        });
      }
    }
    for (const unit of plan.units) {
      const delay = Number(unit?.delay_before_ms ?? 0);
      if (!Number.isFinite(delay) || delay < 0) {
        throw new Error("typing plan contains an invalid delay");
      }
      if (delay > 0) await waitTypingDelay(delay, requestId);
      if (typingCancelled(requestId)) {
        throw typingProgressError("typing_cancelled", completedUnits);
      }
      const unitText = String(unit?.text ?? "");
      const unitResult = await dom.execute("human_type_unit", {
        ...p,
        text: unitText,
        replace: p.clear !== false && completedUnits === 0,
      }) as any;
      expectedValue = p.clear !== false && completedUnits === 0
        ? unitText
        : expectedValue + unitText;
      if (!unitResult || unitResult.ok !== true || unitResult.value !== expectedValue) {
        throw Object.assign(new Error("typing_mismatch: the page rejected a planned input unit"), {
          code: "typing_mismatch",
        });
      }
      if (unit?.fallback === true) fallbackUnits += 1;
      completedUnits += 1;
    }
    if (typingCancelled(requestId)) {
      throw typingProgressError("typing_cancelled", completedUnits);
    }
    const finalResult = await dom.execute("get_value", p) as any;
    const expected = p.clear !== false
      ? String(p.text ?? "")
      : beforeResult.value + String(p.text ?? "");
    if (!finalResult || finalResult.value !== expected) {
      throw Object.assign(
        new Error("typing_mismatch: final value does not match expected text"),
        { code: "typing_mismatch" },
      );
    }
    if (p.submit) await dom.execute("human_submit", p);
    return {
      human: true,
      timing_profile: plan.timing_profile ?? null,
      nominal_wpm: plan.nominal_wpm ?? null,
      units: plan.units.length,
      fallback_units: fallbackUnits,
      elapsed_ms: Date.now() - started,
      ok: true,
      via: "content",
    };
  } finally {
    clearTypingCancellation(requestId);
  }
}

export async function humanTypeViaExactContentTarget(
  p: Params,
  dom: Executor = domExecutor,
) {
  if (p.typing_stream === undefined && p.typing_plan !== undefined) {
    return legacyHumanTypeViaExactContentTarget(p, dom);
  }
  const stream = p.typing_stream as any;
  const action = String(stream?.action ?? "");
  const streamId = String(stream?.stream_id ?? "");
  if (!streamId || !["begin", "chunk", "finish", "abort"].includes(action)) {
    throw new Error("human typing requires a validated typing stream");
  }
  if (action === "abort") {
    const state = humanTypingStreams.get(streamId);
    if (state) removeHumanTypingStream(streamId, state);
    return { aborted: true };
  }

  const identity = typingTargetIdentity(p);
  if (action === "begin") {
    if (humanTypingStreams.has(streamId)) {
      throw new Error("human typing stream already exists");
    }
    await dom.execute("assert_actionable", p);
    const beforeResult = await dom.execute("get_value", p) as any;
    if (!beforeResult || beforeResult.ok !== true || typeof beforeResult.value !== "string") {
      throw new Error(`${String(p.selector)} is not a text input or textarea`);
    }
    const totalUnits = Number(stream.total_units);
    const predictedMs = Number(stream.predicted_ms);
    if (!Number.isInteger(totalUnits) || totalUnits < 0 || !Number.isFinite(predictedMs)) {
      throw new Error("human typing stream metadata is invalid");
    }
    const state: HumanTypingStream = {
      identity,
      selector: String(p.selector),
      clear: p.clear !== false,
      submit: p.submit === true,
      expectedValue: p.clear !== false ? "" : beforeResult.value,
      totalUnits,
      completedUnits: 0,
      fallbackUnits: 0,
      timingProfile: stream.timing_profile ?? null,
      nominalWpm: stream.nominal_wpm ?? null,
      started: Date.now(),
      aborted: false,
      idleTimer: null,
    };
    humanTypingStreams.set(streamId, state);
    refreshHumanTypingStreamIdle(streamId, state);
    return { started: true, completed_units: 0, value_length: beforeResult.value.length };
  }

  const state = humanTypingStreams.get(streamId);
  if (!state || state.aborted) {
    throw new Error("human typing stream is not active");
  }
  if (state.identity !== identity || state.selector !== String(p.selector)) {
    removeHumanTypingStream(streamId, state);
    throw Object.assign(new Error("typing_state_uncertain: typing target changed"), {
      code: "typing_state_uncertain",
    });
  }

  let remainingMs = stream.remaining_ms === undefined
    ? undefined
    : Number(stream.remaining_ms);
  if (stream.deadline_epoch_ms !== undefined) {
    const epochRemaining = Number(stream.deadline_epoch_ms) - Date.now();
    remainingMs = remainingMs === undefined
      ? epochRemaining
      : Math.min(remainingMs, epochRemaining);
  }
  if (remainingMs !== undefined && (!Number.isFinite(remainingMs) || remainingMs <= 0)) {
    removeHumanTypingStream(streamId, state);
    throw typingProgressError("typing_deadline_exceeded", state.completedUnits);
  }
  const deadlineMs = remainingMs === undefined ? undefined : performance.now() + remainingMs;

  if (action === "chunk") {
    const requestId = Number(p._request_id);
    try {
      const units = stream.units as any[];
      if (!Array.isArray(units) || units.length === 0 || units.length > 256) {
        throw new Error("human typing chunk unit count is invalid");
      }
      if (Number(stream.confirmed_units) !== state.completedUnits) {
        throw Object.assign(new Error("typing_state_uncertain: progress count changed"), {
          code: "typing_state_uncertain",
        });
      }
      const plannedMs = units.reduce(
        (sum, unit) => sum + Number(unit?.delay_before_ms ?? Number.NaN),
        0,
      );
      const wireBytes = new TextEncoder().encode(JSON.stringify(units)).byteLength;
      if (!Number.isFinite(plannedMs) || plannedMs < 0 || plannedMs > 5_000) {
        throw new Error("human typing chunk duration is invalid");
      }
      if (wireBytes > 256 * 1024) {
        throw new Error("human typing chunk is too large");
      }
      refreshHumanTypingStreamIdle(streamId, state);

      for (const unit of units) {
        if (state.aborted || typingCancelled(requestId)) {
          throw typingProgressError("typing_cancelled", state.completedUnits);
        }
        if (deadlineMs !== undefined && performance.now() >= deadlineMs) {
          throw typingProgressError("typing_deadline_exceeded", state.completedUnits);
        }
        const delay = Number(unit?.delay_before_ms ?? Number.NaN);
        if (!Number.isFinite(delay) || delay < 0) {
          throw new Error("typing plan contains an invalid delay");
        }
        if (delay > 0) {
          const waited = await waitTypingDelay(
            delay,
            requestId,
            deadlineMs,
            () => state.aborted,
          );
          if (waited === "deadline") {
            throw typingProgressError("typing_deadline_exceeded", state.completedUnits);
          }
          if (waited === "cancelled") {
            throw typingProgressError("typing_cancelled", state.completedUnits);
          }
        }
        const unitText = String(unit?.text ?? "");
        const unitResult = await dom.execute("human_type_unit", {
          ...p,
          text: unitText,
          replace: state.clear && state.completedUnits === 0,
        }) as any;
        const expected = state.clear && state.completedUnits === 0
          ? unitText
          : state.expectedValue + unitText;
        if (!unitResult || unitResult.ok !== true || unitResult.value !== expected) {
          throw Object.assign(
            new Error("typing_mismatch: the page rejected a planned input unit"),
            { code: "typing_mismatch" },
          );
        }
        state.expectedValue = expected;
        if (unit?.fallback === true) state.fallbackUnits += 1;
        state.completedUnits += 1;
        if (state.aborted || typingCancelled(requestId)) {
          throw typingProgressError("typing_cancelled", state.completedUnits);
        }
        if (deadlineMs !== undefined && performance.now() >= deadlineMs) {
          throw typingProgressError("typing_deadline_exceeded", state.completedUnits);
        }
      }
      refreshHumanTypingStreamIdle(streamId, state);
      return {
        completed_units: state.completedUnits,
        value_length: state.expectedValue.length,
      };
    } catch (error) {
      removeHumanTypingStream(streamId, state);
      throw error;
    } finally {
      clearTypingCancellation(requestId);
    }
  }

  const finishRequestId = Number(p._request_id);
  try {
    if (Number(stream.confirmed_units) !== state.completedUnits) {
      throw Object.assign(new Error("typing_state_uncertain: progress count changed"), {
        code: "typing_state_uncertain",
      });
    }
    if (state.completedUnits !== state.totalUnits) {
      throw Object.assign(new Error("typing_state_uncertain: typing stream is incomplete"), {
        code: "typing_state_uncertain",
      });
    }
    refreshHumanTypingStreamIdle(streamId, state);
    const requireRemainingDeadline = () => {
      if (state.aborted || typingCancelled(finishRequestId)) {
        throw typingProgressError("typing_cancelled", state.completedUnits);
      }
      if (deadlineMs !== undefined && performance.now() >= deadlineMs) {
        throw typingProgressError("typing_deadline_exceeded", state.completedUnits);
      }
    };
    requireRemainingDeadline();
    if (state.totalUnits === 0 && state.clear) {
      const cleared = await dom.execute("clear", p) as any;
      if (!cleared || cleared.ok !== true || cleared.value !== "") {
        throw Object.assign(new Error("typing_mismatch: empty clear did not complete"), {
          code: "typing_mismatch",
        });
      }
    }
    const finalResult = await dom.execute("get_value", p) as any;
    if (!finalResult || finalResult.value !== state.expectedValue) {
      throw Object.assign(
        new Error("typing_mismatch: final value does not match expected text"),
        { code: "typing_mismatch" },
      );
    }
    requireRemainingDeadline();
    if (state.submit) await dom.execute("human_submit", p);
    return {
      human: true,
      timing_profile: state.timingProfile,
      nominal_wpm: state.nominalWpm,
      units: state.completedUnits,
      fallback_units: state.fallbackUnits,
      elapsed_ms: Date.now() - state.started,
      ok: true,
      via: "content",
    };
  } finally {
    clearTypingCancellation(finishRequestId);
    removeHumanTypingStream(streamId, state);
  }
}

// The CDP universal path (chrome.debugger). Null when the API is absent (no
// `debugger` permission / non-extension test context) → escalation is skipped.
// The onEvent channel is passed so the CDP path can handle JS dialogs.
function defaultCdp(): Executor | null {
  if (typeof chrome === "undefined" || !chrome.debugger) return null;
  return new CdpExecutor(
    chromeDebuggerAttach(async (p) => (await runnableTargetTab(p)).id!),
    chrome.debugger.onEvent,
  );
}

const TABS_OPS = ["navigate", "back", "forward", "reload", "cookies"];
const DOM_OPS = [
  "wait_for", "query", "read_text", "get_attribute",
  "click", "type", "fill", "select", "scroll",
  // 0.5.0 DOM fast-path ops.
  "element_state", "clear", "get_value",
];
// Interactive ops that self-verify (have a read-back `ok`) AND that the CDP path
// can perform - these escalate DOM→CDP on `ok:false`. (`select` gains escalation
// when the CDP path grows that op; until then it stays DOM-only.)
const ESCALATING = new Set(["click", "type", "fill", "clear", "get_value"]);
// CDP-only ops (no DOM equivalent).
const CDP_ONLY = [
  "press", "accessibility_tree",
  // 0.5.0 CDP-only ops.
  "hover", "dialog", "upload", "focus", "blur", "snapshot",
];
const isInteractive = (op: string) => ESCALATING.has(op);

// --- tabs / windows op-groups (0.6.0) ---
//
// `tabs` and `windows` are OPERATION GROUPS (sub-op routed via params.op, like
// cua's Tier-0 fs/shell tools) - so the wire op is "tabs"/"windows" and the
// sub-op rides in params.op. Provenance-aware and user-context-safe: the agent
// SEES every context (list), but ACTS only on `current`; a `user` tab/window is
// closed only with force=True. The chrome.* glue is injected so the routing is
// unit-testable with no browser.

// The slice of chrome.tabs the mutating group ops depend on.
export interface TabsMutApi {
  create(opts: {
    url?: string;
    windowId?: number;
    active?: boolean;
  }): Promise<{ id?: number; windowId?: number; url?: string }>;
  update(
    tabId: number,
    opts: { active?: boolean },
  ): Promise<{ id?: number; windowId?: number; url?: string }>;
  remove(tabId: number): Promise<void>;
}

// The slice of chrome.windows the mutating group ops depend on.
export interface WindowsMutApi {
  create(opts: {
    url?: string;
    focused?: boolean;
    state?: "normal" | "minimized" | "maximized" | "fullscreen";
    width?: number;
    height?: number;
  }): Promise<{ id?: number; tabs?: { id?: number; url?: string }[] }>;
  update(windowId: number, opts: { focused?: boolean }): Promise<unknown>;
  remove(windowId: number): Promise<void>;
}

// The registry surface the group ops drive - the TargetResolver satisfies it.
export interface TargetControl {
  resolve(): Promise<PinnedTarget>;
  adoptCurrent(
    t: PinnedTarget,
    provenance: Provenance,
    url?: string,
  ): Promise<{ windowId: number; tabId: number; provenance: Provenance }>;
  provenanceOf(tabId: number): Promise<Provenance>;
  isOwnedWindow(windowId: number): Promise<boolean>;
  onTabClosed(tabId: number): Promise<void>;
  onWindowClosed(windowId: number): Promise<void>;
  enumerate(): Promise<{ windows: WindowNode[] }>;
  listWindows(): Promise<{ windows: WindowSummary[] }>;
}

export async function tabsGroupOp(
  p: Params,
  deps: { tabs: TabsMutApi; resolver: TargetControl },
): Promise<unknown> {
  const sub = String(p.op ?? "");
  switch (sub) {
    case "list":
      return deps.resolver.enumerate();
    case "open": {
      // Default window: the owned window (resolve() opens it cold if needed).
      let windowId = p.window_id as number | undefined;
      if (windowId == null) windowId = (await deps.resolver.resolve()).windowId;
      // background=true (the owned-window discipline) opens unfocused.
      const background = p.background !== false;
      const tab = await deps.tabs.create({
        url: p.url as string | undefined,
        windowId,
        active: !background,
      });
      const rec = await deps.resolver.adoptCurrent(
        { windowId: tab.windowId!, tabId: tab.id! },
        "owned",
        tab.url,
      );
      return {
        window_id: rec.windowId,
        tab_id: rec.tabId,
        url: tab.url ?? "",
        created: true,
      };
    }
    case "switch": {
      const tabId = p.tab_id as number;
      // Activate the tab WITHIN its window - deliberately NO
      // windows.update({focused}); routing attention never steals the user's
      // screen (bringing a window forward is windows.focus only).
      const updated = await deps.tabs.update(tabId, { active: true });
      const windowId = (p.window_id as number | undefined) ?? updated.windowId!;
      // Making a context `current` adopts it (owned stays owned via upsert).
      const rec = await deps.resolver.adoptCurrent(
        { windowId, tabId },
        "attached",
        updated.url,
      );
      return {
        window_id: rec.windowId,
        tab_id: rec.tabId,
        url: updated.url ?? "",
        is_current: true,
      };
    }
    case "close": {
      const tabId = p.tab_id as number;
      const force = p.force === true;
      if ((await deps.resolver.provenanceOf(tabId)) === "user" && !force) {
        throw new Error(
          `refusing to close user tab ${tabId} without force=true`,
        );
      }
      await deps.tabs.remove(tabId);
      await deps.resolver.onTabClosed(tabId);
      return { closed: true, tab_id: tabId };
    }
    default:
      throw new Error(`tabs has no sub-op '${sub}'`);
  }
}

export async function windowsGroupOp(
  p: Params,
  deps: { windows: WindowsMutApi; resolver: TargetControl },
): Promise<unknown> {
  const sub = String(p.op ?? "");
  switch (sub) {
    case "list":
      return deps.resolver.listWindows();
    case "open": {
      // A new OWNED window - unfocused by default (the owned-window discipline).
      const win = await deps.windows.create({
        url: p.url as string | undefined,
        focused: p.focused === true,
        state: "normal",
        width: 1200,
        height: 900,
      });
      const tabId = win.tabs?.[0]?.id;
      if (win.id == null || tabId == null) {
        throw new Error("windows.open did not return a tab to pin");
      }
      const rec = await deps.resolver.adoptCurrent(
        { windowId: win.id, tabId },
        "owned",
        win.tabs?.[0]?.url,
      );
      return { window_id: rec.windowId, tab_id: rec.tabId, created: true };
    }
    case "focus": {
      // The explicit, agent-intended raise (never automatic).
      const windowId = p.window_id as number;
      await deps.windows.update(windowId, { focused: true });
      return { focused: true, window_id: windowId };
    }
    case "close": {
      const windowId = p.window_id as number;
      const force = p.force === true;
      if (!(await deps.resolver.isOwnedWindow(windowId)) && !force) {
        throw new Error(
          `refusing to close non-owned window ${windowId} without force=true`,
        );
      }
      await deps.windows.remove(windowId);
      await deps.resolver.onWindowClosed(windowId);
      return { closed: true, window_id: windowId };
    }
    default:
      throw new Error(`windows has no sub-op '${sub}'`);
  }
}

// --- profiles op-group (0.6.1) ---
//
// `profiles` is SW-resolved (touches no page): it reports THIS connection's own
// profile identity + recognition context. cua answers the authoritative
// multi-connection enumeration from its own connection registry (the only place
// that knows every connection); this handler serves its own profile and, by
// advertising `profiles` in supported_ops, tells cua it is a profile-aware
// build. The deps are injected so the routing is unit-testable with no browser.

export interface ProfilesDeps {
  profileId: () => Promise<string>;
  context: () => Promise<ProfileContext>;
  browser: string;
}

export async function profilesOp(
  p: Params,
  deps: ProfilesDeps,
): Promise<unknown> {
  const sub = String(p.op ?? "list");
  const profileId = await deps.profileId();
  if (sub === "list") {
    const ctx = await deps.context();
    return {
      profiles: [
        {
          profile_id: profileId,
          browser: deps.browser,
          is_current: true,
          window_count: ctx.window_count,
          tab_count: ctx.tab_count,
          sample_tab_titles: ctx.sample_tab_titles,
        },
      ],
    };
  }
  if (sub === "use") {
    // A single extension only has itself to select; the real cross-profile
    // selection is cua-side (the `current` pointer over the connection registry).
    return { profile_id: profileId, browser: deps.browser, is_current: true };
  }
  throw new Error(`profiles has no sub-op '${sub}'`);
}

// --- per-op target context (0.6.0) ---
//
// Every op result is wrapped with {window_id, tab_id, url} (additive; no proto
// bump), so the agent always sees WHICH tab it just acted on - a surprise
// chrome://newtab is visible immediately, not inferred two ops later. Only
// object results carry it (a bare string from read_text is passed through); a
// result that already has `target` is left untouched.
export type TargetProvider = (p: Params) =>
  | Promise<{ window_id: number; tab_id: number; url: string } | null>
  | { window_id: number; tab_id: number; url: string }
  | null;

export function wrapWithTarget(
  handler: (p: Params) => unknown | Promise<unknown>,
  provider: TargetProvider,
): (p: Params) => Promise<unknown> {
  return async (p: Params) => {
    const result = await handler(p);
    if (
      result == null ||
      typeof result !== "object" ||
      Array.isArray(result) ||
      "target" in (result as Record<string, unknown>)
    ) {
      return result;
    }
    const ctx = await provider(p);
    if (!ctx) return result;
    return { ...(result as Record<string, unknown>), target: ctx };
  };
}

// The live target-context provider: the in-memory `current` (never resolve() - 
// wrapping must not itself open a window) plus the tab's real url.
async function currentTargetContext(p: Params = {}): Promise<
  { window_id: number; tab_id: number; url: string } | null
> {
  const exact = p._target as { window_id?: number; tab_id?: number } | undefined;
  if (exact?.window_id != null && exact.tab_id != null) {
    let url = "";
    try {
      url = (await chrome.tabs.get(exact.tab_id)).url ?? "";
    } catch {
      // A target that vanished mid-op still reports the exact broker ids.
    }
    return { window_id: exact.window_id, tab_id: exact.tab_id, url };
  }
  const cur = sharedResolver().current();
  if (!cur) return null;
  let url = "";
  try {
    url = (await chrome.tabs.get(cur.tabId)).url ?? "";
  } catch {
    // best-effort - a target that vanished mid-op still reports its ids.
  }
  return { window_id: cur.windowId, tab_id: cur.tabId, url };
}

// --- registration ---

export function buildRouter(cdp: Executor | null = defaultCdp()): Router {
  const r = new Router();

  // Every op result is wrapped with the resolved target context (additive).
  const reg = (op: string, handler: (p: Params) => unknown | Promise<unknown>) =>
    r.register(op, wrapWithTarget(handler, currentTargetContext));

  for (const op of TABS_OPS) reg(op, (p) => tabsExecutor.execute(op, p));

  for (const op of DOM_OPS) {
    if (op === "click") {
      // `trusted:true` skips the DOM fast path entirely and goes straight to the
      // trusted CDP event stream. It is the escape hatch for widgets that expose
      // NO readable state (so the `ok:false` escalation trigger can never fire)
      // yet still ignore an untrusted click - e.g. a pointerdown-driven overlay
      // button. Without the flag, click behaves as before and only escalates
      // when its read-back says the state did not change.
      reg(op, (p) =>
        p.trusted === true && cdp
          ? cdp.execute(op, p)
          : withEscalation(op, p, domExecutor, cdp, isInteractive),
      );
    } else if (op === "type") {
      reg(op, async (p) => {
        if (p.human === true) {
          return humanTypeViaExactContentTarget(p);
        }
        return inactiveSafeKeyboardMutation(op, p, cdp);
      });
    } else if (op === "fill" || op === "clear") {
      reg(op, (p) => inactiveSafeKeyboardMutation(op, p, cdp));
    } else if (ESCALATING.has(op)) {
      reg(op, (p) => withEscalation(op, p, domExecutor, cdp, isInteractive));
    } else {
      reg(op, (p) => domExecutor.execute(op, p));
    }
  }

  // Private streamed form of human `type`. Advertising this separately makes
  // a matching extension a precondition, instead of sending stream data to an
  // older extension that only understands the released whole-operation shape.
  reg("human_type_stream", (p) => humanTypeViaExactContentTarget(p));

  if (cdp) {
    for (const op of CDP_ONLY) {
      if (op === "press") {
        reg(op, async (p) => {
          if (!(await exactTargetReceivesTrustedKeyboard(p))) {
            throw wireError(
              "inactive_tab_trusted_keyboard_unsupported",
              "trusted keyboard input is unavailable while the exact target tab or window is inactive",
            );
          }
          return cdp.execute(op, p);
        });
      } else {
        reg(op, (p) => cdp.execute(op, p));
      }
    }
  }

  // `eval` prefers the CDP path: page-world eval() is governed by the page's
  // CSP (a `script-src` without 'unsafe-eval' blocks it, and executeScript
  // swallows the throw → a silent {value:null}), while Runtime.evaluate is
  // CSP-exempt and surfaces page exceptions. The MAIN-world injection stays as
  // the fallback when chrome.debugger is unavailable.
  reg("eval", (p) => (cdp ? cdp.execute("eval", p) : tabsExecutor.execute("eval", p)));

  // `status` is normally answered cua-side by bridge.status() without touching
  // the wire, but it IS advertised in SUPPORTED_OPS (the hello capability
  // list), so the router must honor it - an advertised op must never come back
  // `unknown op` (issue #36, minor). SW-resolved; touches no page.
  reg("status", () => ({
    connected: true,
    ext_version: extensionVersion(),
    browser: detectBrowserName(),
  }));

  // The session-target control op (SW-resolved; touches no page).
  reg("use_target", (p) => useTargetOp(p));

  // The 0.6.0 window/tab op-groups (sub-op routed via params.op).
  const tabsMut: TabsMutApi = {
    create: (o) => chrome.tabs.create(o) as Promise<any>,
    update: (id, o) => chrome.tabs.update(id, o) as Promise<any>,
    remove: (id) => chrome.tabs.remove(id),
  };
  const windowsMut: WindowsMutApi = {
    create: (o) => chrome.windows.create(o) as Promise<any>,
    update: (id, o) => chrome.windows.update(id, o) as Promise<any>,
    remove: (id) => chrome.windows.remove(id),
  };
  reg("tabs", (p) => tabsGroupOp(p, { tabs: tabsMut, resolver: sharedResolver() }));
  reg("windows", (p) =>
    windowsGroupOp(p, { windows: windowsMut, resolver: sharedResolver() }),
  );

  // The 0.6.1 profiles op-group (SW-resolved; touches no page). Reports this
  // connection's own profile identity from storage.local + the tab enumeration.
  reg("profiles", (p) =>
    profilesOp(p, {
      profileId: () => ensureProfileId(localProfileStorage()),
      context: () => buildProfileContext(windowsEnumApi()),
      browser: detectBrowserName(),
    }),
  );

  return r;
}

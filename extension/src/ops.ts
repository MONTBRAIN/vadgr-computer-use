// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// Service-worker-side op handlers + registration. Non-DOM ops run here against
// the extension APIs (chrome.tabs, chrome.cookies); DOM ops are forwarded to
// the content script in the active tab. Registration is the OCP seam — adding
// an op is a new handler + a register() line.

import { Router } from "./router";

// --- helpers ---

async function activeTab(): Promise<chrome.tabs.Tab> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) throw new Error("no active tab");
  return tab;
}

function tabComplete(tabId: number): Promise<void> {
  return new Promise((resolve) => {
    const listener = (id: number, info: chrome.tabs.TabChangeInfo) => {
      if (id === tabId && info.status === "complete") {
        chrome.tabs.onUpdated.removeListener(listener);
        resolve();
      }
    };
    chrome.tabs.onUpdated.addListener(listener);
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
  "eval",
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

// Forward a DOM op into the active tab's content script and await its reply.
// Handles the two post-navigation failure modes distinctly: an unreachable
// content script (re-inject + retry, for safe read ops) vs the op having itself
// navigated away (report {navigated}). A mutating op that loses its channel is
// reported as a navigation, never blindly retried.
async function forwardToContent(op: string, params: Record<string, unknown>) {
  const tab = await activeTab();
  try {
    return await chrome.tabs.sendMessage(tab.id!, { type: "op", op, params });
  } catch (e) {
    const msg = String((e as Error)?.message ?? e);
    if (isUnreachable(msg) && RETRYABLE_OPS.has(op)) {
      // Inject the content script into the current page, then retry once.
      await chrome.scripting.executeScript({
        target: { tabId: tab.id! },
        files: ["content.js"],
      });
      return await chrome.tabs.sendMessage(tab.id!, { type: "op", op, params });
    }
    if (isNavClose(msg) || isUnreachable(msg)) {
      // A mutating op (or a read whose page is still tearing down) lost its
      // channel to a navigation. The action dispatched; report the navigation.
      return { navigated: true };
    }
    throw e;
  }
}

// --- registration ---

export function buildRouter(): Router {
  const r = new Router();

  // navigation (chrome.tabs)
  r.register("navigate", async (p) => {
    const tab = await activeTab();
    await chrome.tabs.update(tab.id!, { url: String(p.url) });
    await tabComplete(tab.id!);
    const updated = await chrome.tabs.get(tab.id!);
    return summary(updated);
  });
  r.register("back", async () => {
    const tab = await activeTab();
    await chrome.tabs.goBack(tab.id!);
    return summary(await chrome.tabs.get(tab.id!));
  });
  r.register("forward", async () => {
    const tab = await activeTab();
    await chrome.tabs.goForward(tab.id!);
    return summary(await chrome.tabs.get(tab.id!));
  });
  r.register("reload", async () => {
    const tab = await activeTab();
    await chrome.tabs.reload(tab.id!);
    await tabComplete(tab.id!);
    return summary(await chrome.tabs.get(tab.id!));
  });

  // cookies (chrome.cookies)
  r.register("cookies", async (p) => {
    const action = (p.action as string) ?? "get";
    if (action === "get") {
      return chrome.cookies.getAll({ url: p.url as string | undefined });
    }
    if (action === "set") {
      return chrome.cookies.set({
        url: String(p.url),
        name: String(p.name),
        value: String(p.value),
      });
    }
    if (action === "clear") {
      await chrome.cookies.remove({ url: String(p.url), name: String(p.name) });
      return { ok: true };
    }
    throw new Error(`unknown cookies action ${action}`);
  });

  // DOM ops — forwarded to the content script.
  for (const op of [
    "wait_for",
    "query",
    "read_text",
    "get_attribute",
    "click",
    "type",
    "fill",
    "select",
    "scroll",
    "eval",
  ]) {
    r.register(op, (p) => forwardToContent(op, p));
  }

  return r;
}

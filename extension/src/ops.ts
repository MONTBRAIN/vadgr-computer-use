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

// Forward a DOM op into the active tab's content script and await its reply.
// A DOM op (e.g. clicking a submit/link) can trigger a full-page navigation,
// which unloads the content script before it replies — the message channel /
// bfcache closes. The action still happened, so report it as a navigation
// rather than surfacing a transport error. (A genuinely missing content script
// raises "Receiving end does not exist", which we deliberately do NOT swallow.)
async function forwardToContent(op: string, params: Record<string, unknown>) {
  const tab = await activeTab();
  try {
    return await chrome.tabs.sendMessage(tab.id!, { type: "op", op, params });
  } catch (e) {
    const msg = String((e as Error)?.message ?? e);
    if (/message channel is closed|back\/forward cache/i.test(msg)) {
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

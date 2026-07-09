// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// Content-script entry. Builds a DOM-op router and answers op messages the
// service worker forwards from the native port. Selector-first, stateless
// between ops (no element handles held across calls).

import { Router } from "../router";
import {
  opClear,
  opClick,
  opElementState,
  opGetAttribute,
  opGetValue,
  opQuery,
  opReadText,
  opScroll,
  opSelect,
  opType,
  opWaitFor,
} from "./ops";

export function buildContentRouter(): Router {
  const r = new Router();
  r.register("click", (p) => opClick(p as any));
  r.register("query", (p) => opQuery(p as any));
  r.register("read_text", (p) => opReadText(p as any));
  r.register("get_attribute", (p) => opGetAttribute(p as any));
  r.register("type", (p) => opType(p as any));
  r.register("fill", (p) => opType(p as any));
  r.register("select", (p) => opSelect(p as any));
  r.register("scroll", (p) => opScroll(p as any));
  r.register("wait_for", (p) => opWaitFor(p as any));
  r.register("element_state", (p) => opElementState(p as any));
  r.register("clear", (p) => opClear(p as any));
  r.register("get_value", (p) => opGetValue(p as any));
  // `eval` is handled in the service worker (main-world injection): the
  // content-script isolated world is CSP-blocked from eval under MV3.
  return r;
}

// This script is both a declared content script (auto-injected at document_idle)
// and re-injected on demand by the service worker after a navigation. Guard so a
// second injection into the same page does not register a duplicate listener
// (which would double-respond and close the message channel).
const w = window as unknown as { __vadgrCuaContent?: boolean };
if (!w.__vadgrCuaContent) {
  w.__vadgrCuaContent = true;
  const router = buildContentRouter();

  chrome.runtime?.onMessage?.addListener((msg, _sender, sendResponse) => {
    if (msg?.type !== "op") return false;
    router
      .handle({ type: "op", id: 0, op: msg.op, params: msg.params ?? {} })
      // Send the full result envelope ({ok, result|error}) — it is serializable
      // and the service worker unwraps it, re-raising on ok:false. (A rejected
      // Promise here is NOT serializable: Chrome turns it into {}, which the SW
      // would read as a successful empty result and silently mask the failure.)
      .then((res) => sendResponse(res));
    return true; // async response
  });
}

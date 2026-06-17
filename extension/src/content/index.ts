// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// Content-script entry. Builds a DOM-op router and answers op messages the
// service worker forwards from the native port. Selector-first, stateless
// between ops (no element handles held across calls).

import { Router } from "../router";
import {
  opClick,
  opEval,
  opGetAttribute,
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
  r.register("eval", (p) => opEval(p as any));
  return r;
}

const router = buildContentRouter();

chrome.runtime?.onMessage?.addListener((msg, _sender, sendResponse) => {
  if (msg?.type !== "op") return false;
  router
    .handle({ type: "op", id: 0, op: msg.op, params: msg.params ?? {} })
    .then((res) => {
      if (res.ok) sendResponse(res.result);
      else sendResponse(Promise.reject(new Error(res.error.message)));
    });
  return true; // async response
});

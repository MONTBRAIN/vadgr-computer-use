// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// Actionability precondition for mutating ops - Playwright's model (visible /
// receives-events / enabled). It makes read-back verification trustworthy: a
// mutating op refuses a NON-AUTHORITATIVE target (e.g. a hidden form-mirror that
// shares an aria-label with the real editor, as Gmail's compose body does), so
// `ok:true` can't be hollow. See the design doc § Verification model (pillar 4).

import { OpFailed } from "./errors";

// Layout is only measurable in a real browser; jsdom/happy-dom report every box
// as 0×0. Probe the document's own root box: if it has height, layout is live and
// the box / hit-test checks apply; otherwise they're skipped so the op logic stays
// unit-testable on a no-layout DOM.
function layoutIsLive(doc: Document): boolean {
  try {
    return doc.documentElement.getBoundingClientRect().height > 0;
  } catch {
    return false;
  }
}

// Visible = not display:none / visibility:hidden / [hidden], AND (in a real
// browser) a non-empty layout box. `opacity:0` counts as visible (Playwright).
export function isVisible(el: HTMLElement): boolean {
  const view = el.ownerDocument.defaultView || window;
  const style = view.getComputedStyle(el);
  if (el.hidden) return false;
  if (style.display === "none" || style.visibility === "hidden") return false;
  if (layoutIsLive(el.ownerDocument)) {
    const r = el.getBoundingClientRect();
    if (r.width <= 0 && r.height <= 0 && el.getClientRects().length === 0) return false;
  }
  return true;
}

export function isDisabled(el: Element): boolean {
  if ((el as HTMLInputElement).disabled === true) return true;
  return el.getAttribute("aria-disabled") === "true";
}

const MAX_COMPOSED_DEPTH = 64;

/** Hit-test through nested open shadow roots at one viewport point. */
export function deepElementFromPoint(
  doc: Document,
  x: number,
  y: number,
): Element | null {
  let hit = doc.elementFromPoint(x, y);
  for (let depth = 0; hit && depth < MAX_COMPOSED_DEPTH; depth += 1) {
    const root = hit.shadowRoot;
    if (!root || root.mode !== "open" || !root.elementFromPoint) return hit;
    const nested = root.elementFromPoint(x, y);
    if (!nested || nested === hit) return hit;
    hit = nested;
  }
  return hit;
}

/** Test containment across regular parents and open-shadow hosts. */
export function composedContains(ancestor: Element, node: Element): boolean {
  let current: Node | null = node;
  for (let depth = 0; current && depth < MAX_COMPOSED_DEPTH; depth += 1) {
    if (current === ancestor) return true;
    if (current.parentNode) {
      current = current.parentNode;
      continue;
    }
    const root = current.getRootNode?.();
    current = root instanceof ShadowRoot ? root.host : null;
  }
  return false;
}

// Receives events = the element is the hit target at its own centre, not behind an
// overlay. Skipped without live layout (can't hit-test a no-layout DOM).
export function receivesEvents(el: HTMLElement): boolean {
  if (!layoutIsLive(el.ownerDocument)) return true;
  const r = el.getBoundingClientRect();
  const hit = deepElementFromPoint(
    el.ownerDocument,
    r.left + r.width / 2,
    r.top + r.height / 2,
  );
  // A null hit means the hit-test couldn't resolve, NOT that a DOM element covers
  // the target. A fully-occluded / throttled window (e.g. the agent-owned window,
  // opened unfocused, while the user works elsewhere) is not composited, so
  // elementFromPoint returns null - but the CDP action still lands there, and no
  // DOM overlay is blocking it. Only a DIFFERENT, unrelated element at the centre
  // (the hollow-mirror trap) is a real block; that always returns that element,
  // never null. So don't gate on a null hit.
  if (hit === null) return true;
  return composedContains(el, hit) || composedContains(hit, el);
}

// Gate a mutating op. Throws OpFailed (so the agent RETARGETS - it must not
// escalate to CDP, which would hit the same non-authoritative element). `force`
// bypasses the non-essential checks (the standard escape hatch for the rare case
// where the real control is intentionally a visually-hidden node).
export function assertActionable(
  el: HTMLElement,
  selector: string,
  opts: { force?: boolean } = {},
): void {
  if (opts.force) return;
  if (!isVisible(el)) {
    throw new OpFailed(
      `target not actionable (not visible): ${selector} - act on the visible element, not a hidden mirror`,
    );
  }
  if (isDisabled(el)) {
    throw new OpFailed(`target not actionable (disabled): ${selector}`);
  }
  if (!receivesEvents(el)) {
    throw new OpFailed(`target not actionable (covered by another element): ${selector}`);
  }
}

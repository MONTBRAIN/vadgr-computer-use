// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// The escalation policy (SRP — one place). An interactive op runs on the DOM
// fast path; if its self-verify read-back says the action did not take
// (`ok:false`), it escalates to the CDP universal path. Verification IS the
// routing decision. Pure logic — unit-tested with fake executors.

import type { Executor, Params } from "./types";

// The escalation trigger: a result whose self-verify read-back failed. Only an
// `ok === false` envelope qualifies — a missing `ok` (reads, navigations) does
// not, so non-self-verifying ops never escalate spuriously.
export function okIsFalse(result: unknown): boolean {
  return (
    !!result &&
    typeof result === "object" &&
    (result as { ok?: unknown }).ok === false
  );
}

// Run `op` on the DOM fast path; for interactive ops, escalate to CDP when the
// read-back failed. Non-interactive ops, or a missing CDP path, return the DOM
// result unchanged.
export async function withEscalation(
  op: string,
  params: Params,
  dom: Executor,
  cdp: Executor | null,
  isInteractive: (op: string) => boolean,
): Promise<unknown> {
  const result = await dom.execute(op, params);
  if (!cdp || !isInteractive(op) || !okIsFalse(result)) return result;
  return cdp.execute(op, params);
}

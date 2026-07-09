// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// TDD for content-script self-heal (0.6.0 strand d.3). An UNREACHABLE reply
// ("Receiving end does not exist") means the message never arrived and the op
// NEVER RAN — so re-injecting content.js and delivering ONCE is safe for EVERY
// op, click/fill/type included (0.5.0 excluded mutating ops; 0.6.0 does not,
// because unreachable => not-executed). A NAV-CLOSE reply (maybe-executed) is
// reported {navigated} and NEVER redelivered; a genuine ok:false is re-raised.

import { describe, it, expect, vi } from "vitest";
import { deliverWithSelfHeal, type ContentChannel } from "../src/ops";

const okEnvelope = (result: unknown) => ({ type: "result", id: 1, ok: true, result });

function channel(sendImpl: (op: string, p: any) => Promise<unknown>) {
  const reinject = vi.fn(async () => {});
  const send = vi.fn(sendImpl);
  const ch: ContentChannel = { send, reinject };
  return { ch, send, reinject };
}

describe("deliverWithSelfHeal — mutating ops (click / fill)", () => {
  it("re-injects ONCE and redelivers a fill after an unreachable reply, then succeeds", async () => {
    let calls = 0;
    const { ch, send, reinject } = channel(async () => {
      calls += 1;
      if (calls === 1) throw new Error("Could not establish connection. Receiving end does not exist.");
      return okEnvelope({ typed: 4, value: "lofi", ok: true });
    });
    const out = await deliverWithSelfHeal("fill", { selector: "#q", text: "lofi" }, ch);
    expect(out).toEqual({ typed: 4, value: "lofi", ok: true });
    expect(reinject).toHaveBeenCalledTimes(1);
    expect(send).toHaveBeenCalledTimes(2); // first (unreachable) + one redelivery
  });

  it("re-injects for a click too — mutating ops are no longer excluded", async () => {
    let calls = 0;
    const { ch, reinject, send } = channel(async () => {
      calls += 1;
      if (calls === 1) throw new Error("Receiving end does not exist");
      return okEnvelope({ clicked: true });
    });
    const out = await deliverWithSelfHeal("click", { selector: "#go" }, ch);
    expect(out).toEqual({ clicked: true });
    expect(reinject).toHaveBeenCalledTimes(1);
    expect(send).toHaveBeenCalledTimes(2);
  });

  it("delivers only ONCE more — a second unreachable after re-inject propagates", async () => {
    const { ch, send, reinject } = channel(async () => {
      throw new Error("Receiving end does not exist");
    });
    await expect(deliverWithSelfHeal("fill", { selector: "#q", text: "x" }, ch)).rejects.toThrow(
      /receiving end/i,
    );
    expect(reinject).toHaveBeenCalledTimes(1);
    expect(send).toHaveBeenCalledTimes(2); // never a third delivery
  });
});

describe("deliverWithSelfHeal — nav-close + genuine failures", () => {
  it("reports a nav-close as {navigated} and NEVER redelivers", async () => {
    const { ch, send, reinject } = channel(async () => {
      throw new Error("The message channel is closed before a response was received");
    });
    const out = await deliverWithSelfHeal("click", { selector: "a" }, ch);
    expect(out).toEqual({ navigated: true });
    expect(reinject).not.toHaveBeenCalled();
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("re-raises a genuine ok:false — a failure never masquerades as success", async () => {
    const { ch, reinject } = channel(async () =>
      ({ type: "result", id: 1, ok: false, error: { code: "op_failed", message: "no element matches #x" } }),
    );
    await expect(deliverWithSelfHeal("click", { selector: "#x" }, ch)).rejects.toThrow(
      /no element matches #x/,
    );
    expect(reinject).not.toHaveBeenCalled();
  });
});

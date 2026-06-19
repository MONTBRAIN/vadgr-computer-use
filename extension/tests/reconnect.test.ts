// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.

import { describe, it, expect, vi } from "vitest";
import { ReconnectController } from "../src/reconnect";

function harness(opts = {}) {
  const connect = vi.fn();
  const scheduled: Array<{ fn: () => void; delay: number }> = [];
  const schedule = (fn: () => void, delay: number) => {
    scheduled.push({ fn, delay });
    return scheduled.length;
  };
  const c = new ReconnectController(connect, schedule, {
    baseDelayMs: 500,
    maxDelayMs: 8000,
    factor: 2,
    ...opts,
  });
  const flush = () => {
    const next = scheduled.shift();
    if (next) next.fn();
  };
  return { c, connect, scheduled, flush };
}

describe("ReconnectController", () => {
  it("schedules a reconnect on disconnect using the base delay first", () => {
    const { c, scheduled } = harness();
    c.onDisconnect();
    expect(scheduled).toHaveLength(1);
    expect(scheduled[0].delay).toBe(500);
  });

  it("backs off exponentially across repeated failures", () => {
    const { c, scheduled, flush } = harness();
    const delays: number[] = [];
    c.onDisconnect(); // 500
    delays.push(scheduled[scheduled.length - 1].delay);
    flush();
    c.onDisconnect(); // 1000
    delays.push(scheduled[scheduled.length - 1].delay);
    flush();
    c.onDisconnect(); // 2000
    delays.push(scheduled[scheduled.length - 1].delay);
    expect(delays).toEqual([500, 1000, 2000]);
  });

  it("caps the backoff at maxDelayMs", () => {
    const { c } = harness({ baseDelayMs: 1000, maxDelayMs: 4000, factor: 2 });
    // attempts: 0->1000, 1->2000, 2->4000, 3->cap 4000, 4->cap 4000
    const delays: number[] = [];
    for (let i = 0; i < 5; i++) {
      delays.push(c.nextDelay());
      c.onDisconnect();
      // simulate the scheduled callback firing so pending clears
      (c as any).pending = false;
    }
    expect(delays).toEqual([1000, 2000, 4000, 4000, 4000]);
  });

  it("actually calls connect when the scheduled timer fires", () => {
    const { c, connect, flush } = harness();
    c.onDisconnect();
    expect(connect).not.toHaveBeenCalled();
    flush();
    expect(connect).toHaveBeenCalledTimes(1);
  });

  it("resets the backoff to base after a successful connect", () => {
    const { c, scheduled, flush } = harness();
    c.onDisconnect(); // 500
    flush();
    c.onDisconnect(); // 1000
    flush();
    c.onConnected(); // reset
    c.onDisconnect(); // back to 500
    expect(scheduled[scheduled.length - 1].delay).toBe(500);
  });

  it("coalesces overlapping disconnects into one pending reconnect", () => {
    const { c, scheduled } = harness();
    c.onDisconnect();
    c.onDisconnect();
    c.onDisconnect();
    expect(scheduled).toHaveLength(1);
    expect(c.isPending).toBe(true);
  });

  it("allows a new reconnect after the pending one fires", () => {
    const { c, scheduled, flush } = harness();
    c.onDisconnect();
    flush();
    expect(c.isPending).toBe(false);
    c.onDisconnect();
    expect(scheduled).toHaveLength(1);
  });
});

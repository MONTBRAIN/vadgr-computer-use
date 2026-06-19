// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// Auto-reconnect for the native-messaging port. MV3 service workers
// idle-terminate (~30s) and the native host can drop, so load order must never
// matter: on every disconnect we schedule a reconnect with capped exponential
// backoff, and reset the backoff once a connection succeeds. The controller is
// pure (injected connect + timer) so the backoff/reconnect logic is unit-tested
// without chrome.* — background.ts wires it to the real APIs.

export interface ReconnectOptions {
  baseDelayMs?: number;
  maxDelayMs?: number;
  factor?: number;
}

export type ConnectFn = () => void;
export type ScheduleFn = (fn: () => void, delayMs: number) => unknown;

export class ReconnectController {
  private readonly base: number;
  private readonly max: number;
  private readonly factor: number;
  private attempt = 0;
  private pending = false;

  constructor(
    private readonly connect: ConnectFn,
    private readonly schedule: ScheduleFn,
    opts: ReconnectOptions = {},
  ) {
    this.base = opts.baseDelayMs ?? 500;
    this.max = opts.maxDelayMs ?? 30_000;
    this.factor = opts.factor ?? 2;
  }

  /** The delay (ms) for the current attempt count, capped at maxDelayMs. */
  nextDelay(): number {
    const raw = this.base * Math.pow(this.factor, this.attempt);
    return Math.min(raw, this.max);
  }

  /** Called on a port disconnect: schedule exactly one reconnect, backing off.
   *  Coalesces — a second disconnect while one is already pending is a no-op. */
  onDisconnect(): void {
    if (this.pending) return;
    this.pending = true;
    const delay = this.nextDelay();
    this.attempt += 1;
    this.schedule(() => {
      this.pending = false;
      this.connect();
    }, delay);
  }

  /** Called once a connection succeeds: reset the backoff to the base delay. */
  onConnected(): void {
    this.attempt = 0;
    this.pending = false;
  }

  get attempts(): number {
    return this.attempt;
  }

  get isPending(): boolean {
    return this.pending;
  }
}

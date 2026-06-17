// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// The op router — mirrors cua's core/ops.py OperationGroup. Op name -> handler,
// registered at load. Adding an op is a new handler + registration, never a
// dispatcher edit. It owns the result/error envelope shaping.

import { OpMessage, ResultMessage, errResult, okResult } from "./protocol";

export type OpHandler = (params: Record<string, any>) => unknown | Promise<unknown>;

export class Router {
  private handlers = new Map<string, OpHandler>();

  register(name: string, handler: OpHandler): void {
    if (this.handlers.has(name)) {
      throw new Error(`duplicate op ${name}`);
    }
    this.handlers.set(name, handler);
  }

  get names(): string[] {
    return [...this.handlers.keys()].sort();
  }

  async handle(msg: OpMessage): Promise<ResultMessage> {
    const handler = this.handlers.get(msg.op);
    if (!handler) {
      return errResult(
        msg.id,
        "op_failed",
        `unknown op ${msg.op}; expected one of ${this.names.join(", ")}`,
      );
    }
    try {
      const result = await handler(msg.params ?? {});
      return okResult(msg.id, result);
    } catch (e) {
      return errResult(msg.id, "op_failed", e instanceof Error ? e.message : String(e));
    }
  }
}

// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// The Executor seam (DIP/LSP). An op is fulfilled by whichever execution path
// (backend) can satisfy it; the router/policy depend on this interface, not on
// chrome.tabs / chrome.debugger / sendMessage concretes. Adding a backend is a
// new Executor, never a router edit (OCP). See the design doc § Interaction
// architecture.

export type Params = Record<string, unknown>;

export interface Executor {
  readonly name: string;
  execute(op: string, params: Params): Promise<unknown>;
}

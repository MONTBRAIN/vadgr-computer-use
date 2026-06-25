// Copyright 2026 Victor Santiago Montaño Diaz
//
// Licensed under the Apache License, Version 2.0 (the "License").
// http://www.apache.org/licenses/LICENSE-2.0
//
// The wire contract — the only coupling between the extension and cua. This is
// a mirror of computer_use/browser/protocol.py: keep PROTOCOL_VERSION and
// SUPPORTED_OPS in sync. The two builds share no imports, only this envelope.

export const PROTOCOL_VERSION = 1;

// The op-level capability list reported in `hello`. Adding an op in a later
// MINOR appends here; it does NOT bump PROTOCOL_VERSION.
export const SUPPORTED_OPS = [
  "navigate",
  "back",
  "forward",
  "reload",
  "wait_for",
  "query",
  "read_text",
  "get_attribute",
  "click",
  "type",
  "fill",
  "select",
  "scroll",
  "cookies",
  "status",
  "eval",
  // CDP universal path (chrome.debugger) — additive (no PROTOCOL_VERSION bump).
  "press",
  "accessibility_tree",
] as const;

export type OpName = (typeof SUPPORTED_OPS)[number];

export interface ClientHello {
  type: "hello";
  proto: number;
  cua_version: string;
}

export interface ServerHello {
  type: "hello";
  proto: number;
  ext_version: string;
  browser: string;
  supported_ops: string[];
}

export interface OpMessage {
  type: "op";
  id: number;
  op: string;
  params: Record<string, unknown>;
}

export interface OkResult {
  type: "result";
  id: number;
  ok: true;
  result: unknown;
}

export interface ErrResult {
  type: "result";
  id: number;
  ok: false;
  error: { code: string; message: string };
}

export type ResultMessage = OkResult | ErrResult;

export function serverHello(extVersion: string, browser: string): ServerHello {
  return {
    type: "hello",
    proto: PROTOCOL_VERSION,
    ext_version: extVersion,
    browser,
    supported_ops: [...SUPPORTED_OPS],
  };
}

export function okResult(id: number, result: unknown): OkResult {
  return { type: "result", id, ok: true, result };
}

export function errResult(id: number, code: string, message: string): ErrResult {
  return { type: "result", id, ok: false, error: { code, message } };
}

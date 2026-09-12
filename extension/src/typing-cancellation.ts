// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.

const cancelled = new Set<number>();

export function cancelTyping(requestId: number): void {
  if (Number.isInteger(requestId)) cancelled.add(requestId);
}

export function clearTypingCancellation(requestId: number): void {
  cancelled.delete(requestId);
}

export function typingCancelled(requestId: number): boolean {
  return cancelled.has(requestId);
}

export async function waitTypingDelay(
  delayMs: number,
  requestId: number,
  deadlineMs?: number,
  stopped?: () => boolean,
): Promise<"complete" | "cancelled" | "deadline"> {
  const deadline = performance.now() + delayMs;
  while (performance.now() < deadline) {
    if (typingCancelled(requestId) || stopped?.()) return "cancelled";
    if (deadlineMs !== undefined && performance.now() >= deadlineMs) return "deadline";
    const deadlineRemaining = deadlineMs === undefined
      ? Number.POSITIVE_INFINITY
      : Math.max(0, deadlineMs - performance.now());
    await new Promise((resolve) =>
      setTimeout(
        resolve,
        Math.min(20, Math.max(0, deadline - performance.now()), deadlineRemaining),
      ),
    );
  }
  if (typingCancelled(requestId) || stopped?.()) return "cancelled";
  if (deadlineMs !== undefined && performance.now() >= deadlineMs) return "deadline";
  return "complete";
}

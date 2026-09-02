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

export async function waitTypingDelay(delayMs: number, requestId: number): Promise<void> {
  const deadline = performance.now() + delayMs;
  while (performance.now() < deadline) {
    if (typingCancelled(requestId)) return;
    await new Promise((resolve) =>
      setTimeout(resolve, Math.min(20, Math.max(0, deadline - performance.now()))),
    );
  }
}

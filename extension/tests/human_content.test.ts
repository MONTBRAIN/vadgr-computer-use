// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.

import { describe, expect, it, vi } from "vitest";
import {
  abortAllHumanTypingStreams,
  humanTypeViaExactContentTarget,
} from "../src/ops";
import type { Executor, Params } from "../src/executors/types";
import { cancelTyping } from "../src/typing-cancellation";

function fakeContent(initial = "") {
  let value = initial;
  const calls: Array<{ op: string; params: Params }> = [];
  const executor: Executor = {
    name: "fake-content",
    async execute(op, params) {
      calls.push({ op, params });
      if (op === "assert_actionable") return { actionable: true };
      if (op === "get_value") return { value, ok: true };
      if (op === "human_type_unit") {
        const text = String(params.text ?? "");
        value = params.replace === true ? text : value + text;
        return { inserted: true, value, ok: true };
      }
      if (op === "human_submit") return { accepted: true, submitted: true };
      throw new Error(`unexpected ${op}`);
    },
  };
  return { executor, calls, value: () => value };
}

const stream = (action: string, extra: Record<string, unknown> = {}) => ({
  selector: "#n",
  clear: true,
  human: true,
  _request_id: 400,
  _target: { window_id: 1, tab_id: 2 },
  _ownership_revision: 3,
  typing_stream: {
    action,
    stream_id: "stream-1",
    timing_profile: "test",
    nominal_wpm: 65,
    total_units: 2,
    predicted_ms: 200,
    ...extra,
  },
});

describe("humanTypeViaExactContentTarget", () => {
  it("retains the protocol-v1 whole-plan request", async () => {
    const fake = fakeContent();
    const result: any = await humanTypeViaExactContentTarget({
      selector: "#n",
      text: "ab",
      clear: true,
      human: true,
      _request_id: 399,
      typing_plan: {
        timing_profile: "legacy",
        nominal_wpm: 38,
        units: [
          { text: "a", delay_before_ms: 0 },
          { text: "b", delay_before_ms: 0 },
        ],
      },
    }, fake.executor);
    expect(result).toMatchObject({ units: 2, ok: true, via: "content" });
    expect(fake.value()).toBe("ab");
  });

  it("aborts retained streams when the native port disconnects", async () => {
    const fake = fakeContent();
    await humanTypeViaExactContentTarget(stream("begin"), fake.executor);
    abortAllHumanTypingStreams();
    await expect(humanTypeViaExactContentTarget(stream("chunk", {
      confirmed_units: 0,
      units: [{ text: "a", delay_before_ms: 0 }],
    }), fake.executor)).rejects.toThrow("human typing stream is not active");
  });

  it("consumes planned units through the exact content executor", async () => {
    const fake = fakeContent("old");
    await humanTypeViaExactContentTarget(stream("begin"), fake.executor);
    const progress: any = await humanTypeViaExactContentTarget(stream("chunk", {
      confirmed_units: 0,
      units: [
        { text: "a", delay_before_ms: 0 },
        { text: "b", delay_before_ms: 0, fallback: true },
      ],
    }), fake.executor);
    expect(progress).toMatchObject({ completed_units: 2, value_length: 2 });
    const result: any = await humanTypeViaExactContentTarget(
      stream("finish", { confirmed_units: 2 }), fake.executor,
    );
    expect(result).toMatchObject({
      human: true,
      units: 2,
      fallback_units: 1,
      ok: true,
      via: "content",
    });
    expect(fake.value()).toBe("ab");
    expect(fake.calls.filter((call) => call.op === "human_type_unit")).toHaveLength(2);
  });

  it("cancels before the next unit and clears cancellation state", async () => {
    const fake = fakeContent();
    await humanTypeViaExactContentTarget(stream("begin"), fake.executor);
    const params = {
      ...stream("chunk", {
        confirmed_units: 0,
        units: [{ text: "a", delay_before_ms: 0 }],
      }),
      _request_id: 401,
    };
    cancelTyping(401);
    await expect(humanTypeViaExactContentTarget(params, fake.executor))
      .rejects.toMatchObject({ code: "typing_cancelled" });
    expect(fake.calls.some((call) => call.op === "human_type_unit")).toBe(false);
    await expect(humanTypeViaExactContentTarget(stream("abort"), fake.executor)).resolves
      .toMatchObject({ aborted: true });
  });

  it("expires an unfinished stream after bounded inactivity", async () => {
    vi.useFakeTimers();
    try {
      const fake = fakeContent();
      await humanTypeViaExactContentTarget(stream("begin"), fake.executor);

      await vi.advanceTimersByTimeAsync(60_001);

      await expect(humanTypeViaExactContentTarget(stream("chunk", {
        confirmed_units: 0,
        units: [{ text: "a", delay_before_ms: 0 }],
      }), fake.executor)).rejects.toThrow("human typing stream is not active");
    } finally {
      abortAllHumanTypingStreams();
      vi.useRealTimers();
    }
  });

  it("keeps a long stream alive while valid chunks arrive before idle expiry", async () => {
    vi.useFakeTimers();
    try {
      const fake = fakeContent();
      await humanTypeViaExactContentTarget(
        stream("begin", { total_units: 3 }), fake.executor,
      );

      for (const [index, text] of ["a", "b", "c"].entries()) {
        await vi.advanceTimersByTimeAsync(59_000);
        await expect(humanTypeViaExactContentTarget(stream("chunk", {
          confirmed_units: index,
          units: [{ text, delay_before_ms: 0 }],
        }), fake.executor)).resolves.toMatchObject({ completed_units: index + 1 });
      }

      await expect(humanTypeViaExactContentTarget(stream("finish", {
        confirmed_units: 3,
      }), fake.executor)).resolves.toMatchObject({ units: 3, ok: true });
      expect(fake.value()).toBe("abc");
    } finally {
      abortAllHumanTypingStreams();
      vi.useRealTimers();
    }
  });

  it("reports cancellation that arrives during the final unit", async () => {
    const fake = fakeContent();
    const executor: Executor = {
      name: "cancel-final-unit",
      async execute(op, params) {
        const result = await fake.executor.execute(op, params);
        if (op === "human_type_unit") cancelTyping(403);
        return result;
      },
    };
    await humanTypeViaExactContentTarget(
      stream("begin", { total_units: 1 }), executor,
    );
    await expect(humanTypeViaExactContentTarget({
      ...stream("chunk", {
        total_units: 1,
        confirmed_units: 0,
        units: [{ text: "a", delay_before_ms: 0 }],
      }),
      _request_id: 403,
    }, executor)).rejects.toMatchObject({
      code: "typing_cancelled",
      message: "typing_cancelled: 1 complete units",
    });
    expect(fake.value()).toBe("a");
  });

  it("verifies text before dispatching submit", async () => {
    const fake = fakeContent();
    await humanTypeViaExactContentTarget(
      { ...stream("begin", { total_units: 1 }), submit: true }, fake.executor,
    );
    await humanTypeViaExactContentTarget(
      {
        ...stream("chunk", {
          confirmed_units: 0,
          units: [{ text: "a", delay_before_ms: 0 }],
        }),
        submit: true,
      }, fake.executor,
    );
    await humanTypeViaExactContentTarget(
      {
        ...stream("finish", { total_units: 1, confirmed_units: 1 }),
        submit: true,
      }, fake.executor,
    );
    expect(fake.calls.map((call) => call.op).slice(-2))
      .toEqual(["get_value", "human_submit"]);
  });

  it("cancels after the final unit without submitting", async () => {
    const fake = fakeContent();
    await humanTypeViaExactContentTarget(
      { ...stream("begin", { total_units: 1 }), submit: true }, fake.executor,
    );
    await humanTypeViaExactContentTarget(
      {
        ...stream("chunk", {
          confirmed_units: 0,
          total_units: 1,
          units: [{ text: "a", delay_before_ms: 0 }],
        }),
        submit: true,
      }, fake.executor,
    );
    cancelTyping(402);
    await expect(humanTypeViaExactContentTarget(
      {
        ...stream("finish", {
          total_units: 1,
          confirmed_units: 1,
        }),
        _request_id: 402,
        submit: true,
      }, fake.executor,
    )).rejects.toMatchObject({
      code: "typing_cancelled",
      message: "typing_cancelled: 1 complete units",
    });
    expect(fake.calls.some((call) => call.op === "human_submit")).toBe(false);
  });

  it("clears an existing value when the requested text is empty", async () => {
    let value = "old";
    const executor: Executor = {
      name: "empty-clear",
      async execute(op) {
        if (op === "assert_actionable") return { actionable: true };
        if (op === "get_value") return { value, ok: true };
        if (op === "clear") {
          value = "";
          return { value, ok: true };
        }
        throw new Error(`unexpected ${op}`);
      },
    };
    await humanTypeViaExactContentTarget(
      stream("begin", { total_units: 0, predicted_ms: 0 }), executor,
    );
    await expect(humanTypeViaExactContentTarget(
      stream("finish", {
        total_units: 0,
        predicted_ms: 0,
        confirmed_units: 0,
      }), executor,
    )).resolves.toMatchObject({ units: 0, ok: true, via: "content" });
    expect(value).toBe("");
  });

  it("expires an explicit deadline with the exact confirmed prefix", async () => {
    const fake = fakeContent();
    await humanTypeViaExactContentTarget(stream("begin"), fake.executor);
    await humanTypeViaExactContentTarget(stream("chunk", {
      confirmed_units: 0,
      units: [{ text: "a", delay_before_ms: 0 }],
    }), fake.executor);
    await expect(humanTypeViaExactContentTarget(stream("chunk", {
      remaining_ms: 10_000,
      deadline_epoch_ms: Date.now() - 1,
      confirmed_units: 1,
      units: [{ text: "b", delay_before_ms: 0 }],
    }), fake.executor)).rejects.toMatchObject({
      code: "typing_deadline_exceeded",
      message: "typing_deadline_exceeded: 1 complete units",
    });
    expect(fake.value()).toBe("a");
  });
});

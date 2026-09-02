// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.

import { describe, expect, it } from "vitest";
import { humanTypeViaExactContentTarget } from "../src/ops";
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

const plan = (units: Array<{ text: string; delay_before_ms?: number; fallback?: boolean }>) => ({
  selector: "#n",
  text: units.map((unit) => unit.text).join(""),
  clear: true,
  human: true,
  _request_id: 400,
  typing_plan: {
    timing_profile: "test",
    nominal_wpm: 38,
    units,
  },
});

describe("humanTypeViaExactContentTarget", () => {
  it("consumes planned units through the exact content executor", async () => {
    const fake = fakeContent("old");
    const result: any = await humanTypeViaExactContentTarget(
      plan([{ text: "a" }, { text: "b", fallback: true }]),
      fake.executor,
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
    const params = { ...plan([{ text: "a" }]), _request_id: 401 };
    cancelTyping(401);
    await expect(humanTypeViaExactContentTarget(params, fake.executor))
      .rejects.toMatchObject({ code: "typing_cancelled" });
    expect(fake.calls.some((call) => call.op === "human_type_unit")).toBe(false);
    await expect(humanTypeViaExactContentTarget(params, fake.executor)).resolves
      .toMatchObject({ ok: true });
  });

  it("verifies text before dispatching submit", async () => {
    const fake = fakeContent();
    await humanTypeViaExactContentTarget(
      { ...plan([{ text: "a" }]), submit: true },
      fake.executor,
    );
    expect(fake.calls.map((call) => call.op).slice(-2))
      .toEqual(["get_value", "human_submit"]);
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
    await expect(humanTypeViaExactContentTarget(plan([]), executor))
      .resolves.toMatchObject({ units: 0, ok: true, via: "content" });
    expect(value).toBe("");
  });
});

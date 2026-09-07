// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.

import { describe, expect, it } from "vitest";

import config from "../vitest.config";

describe("extension gate worker bounds", () => {
  it("keeps one CPU available on small native hosts", () => {
    expect(config.test?.minWorkers).toBe(1);
    expect(config.test?.maxWorkers).toBe(2);
  });
});

import { describe, expectTypeOf, it } from "vitest";

import type { EvaluationBatch } from "../../src/api/evaluations";

describe("public evaluation API contract", () => {
  it("does not expose the provider request identifier", () => {
    expectTypeOf<EvaluationBatch>().not.toHaveProperty("provider_request_id");
  });
});

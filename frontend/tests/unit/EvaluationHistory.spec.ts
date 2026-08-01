import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import type { EvaluationBatch } from "../../src/api/evaluations";
import EvaluationHistory from "../../src/components/evaluations/EvaluationHistory.vue";

const cancelledEvaluation: EvaluationBatch = {
  id: 24,
  policy_version_id: 12,
  status: "cancelled" as EvaluationBatch["status"],
  prompt_version: "stage2-v1",
  adapter_key: "mock",
  model_name: null,
  profile_snapshot: [],
  summary: null,
  key_conditions: null,
  conclusion: null,
  error_message: null,
  started_at: null,
  finished_at: "2026-07-31T10:00:00Z",
  created_at: "2026-07-31T09:00:00Z",
  entities: [],
};

describe("EvaluationHistory", () => {
  it("identifies a cancelled batch by attempt number and keeps the batch ID secondary", async () => {
    const wrapper = mount(EvaluationHistory, {
      props: {
        evaluations: [cancelledEvaluation],
        attemptNumberById: { 24: 5 },
      },
    });

    await wrapper.get("button").trigger("click");

    expect(wrapper.text()).toContain("第 5 次评估");
    expect(wrapper.text()).toContain("批次 #24");
    expect(wrapper.text()).toContain("已取消");
    expect(wrapper.text()).not.toContain("评估失败");
  });
});

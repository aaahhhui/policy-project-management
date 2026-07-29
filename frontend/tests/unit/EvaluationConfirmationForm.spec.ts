import { mount } from "@vue/test-utils";
import { expect, it, vi } from "vitest";

import { confirmEvaluation } from "../../src/api/evaluations";
import EvaluationConfirmationForm from "../../src/components/evaluations/EvaluationConfirmationForm.vue";

vi.mock("../../src/api/evaluations", () => ({ confirmEvaluation: vi.fn() }));

const evaluation = {
  id: 17,
  conclusion: "recommend_apply" as const,
  summary: "建议申报",
  key_conditions: ["注册地区"],
  entities: ["ENTITY-BEIJING", "ENTITY-SUZHOU", "ENTITY-SHENZHEN"].map((code) => ({
    entity_seed_code: code,
    match_level: "high" as const,
    score: 88,
    hard_rule_results: [],
    weighted_rule_results: [],
    evidence: ["匹配"],
    unmet_conditions: [],
    risks: [],
    recommended_action: "准备材料",
  })),
};

it("requires a reason after changing an AI score", async () => {
  const wrapper = mount(EvaluationConfirmationForm, { props: { evaluation } });
  await wrapper.get('[data-score="ENTITY-BEIJING"]').setValue("91");
  await wrapper.get("form").trigger("submit");

  expect(wrapper.text()).toContain("修改 AI 建议后必须填写原因");
  expect(confirmEvaluation).not.toHaveBeenCalled();
});

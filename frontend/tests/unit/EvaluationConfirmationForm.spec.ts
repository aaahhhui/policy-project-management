import { mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";

import { confirmEvaluation } from "../../src/api/evaluations";
import EvaluationConfirmationForm from "../../src/components/evaluations/EvaluationConfirmationForm.vue";

vi.mock("../../src/api/evaluations", () => ({ confirmEvaluation: vi.fn() }));

beforeEach(() => {
  vi.clearAllMocks();
});

const evaluation = {
  id: 17,
  conclusion: "recommend_apply" as const,
  summary: "建议申报",
  key_conditions: ["注册地区"],
  profile_snapshot: [
    { seed_code: "ENTITY-BEIJING", legal_name: "北京适创科技有限公司" },
    { seed_code: "ENTITY-SUZHOU", legal_name: "苏州数算软云科技有限公司" },
    { seed_code: "ENTITY-SHENZHEN", legal_name: "深圳适创腾扬科技有限公司" },
  ],
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

it("shows Chinese enterprise names instead of internal entity codes", () => {
  const wrapper = mount(EvaluationConfirmationForm, { props: { evaluation } });

  expect(wrapper.text()).toContain("北京适创科技有限公司");
  expect(wrapper.text()).toContain("苏州数算软云科技有限公司");
  expect(wrapper.text()).toContain("深圳适创腾扬科技有限公司");
  expect(wrapper.text()).not.toContain("ENTITY-");
  expect(wrapper.text()).not.toContain("AI");
});

it("requires a reason after changing a model score", async () => {
  const wrapper = mount(EvaluationConfirmationForm, { props: { evaluation } });
  await wrapper.get('[data-score="ENTITY-BEIJING"]').setValue("91");
  await wrapper.get("form").trigger("submit");

  expect(wrapper.text()).toContain("修改模型建议后必须填写原因");
  expect(confirmEvaluation).not.toHaveBeenCalled();
});

it("offers the four policy conclusions in Chinese", () => {
  const wrapper = mount(EvaluationConfirmationForm, { props: { evaluation } });

  expect(wrapper.text()).toContain("建议申报");
  expect(wrapper.text()).toContain("持续关注");
  expect(wrapper.text()).toContain("暂不建议申报");
  expect(wrapper.text()).toContain("无法判断");
});

it("requires one of the three candidate enterprises for a recommendation", async () => {
  const wrapper = mount(EvaluationConfirmationForm, { props: { evaluation } });

  await wrapper.get("form").trigger("submit");

  expect(wrapper.text()).toContain("请选择主申报企业");
  expect(confirmEvaluation).not.toHaveBeenCalled();
});

it("submits the selected candidate with the confirmed conclusion", async () => {
  vi.mocked(confirmEvaluation).mockResolvedValue({});
  const wrapper = mount(EvaluationConfirmationForm, { props: { evaluation } });
  await wrapper.get<HTMLInputElement>('[name="primary-entity"][value="ENTITY-SHENZHEN"]').setValue();

  await wrapper.get("form").trigger("submit");

  expect(confirmEvaluation).toHaveBeenCalledWith(17, expect.objectContaining({
    conclusion: "recommend_apply",
    primary_entity_seed_code: "ENTITY-SHENZHEN",
  }));
});

it("requires a reason after changing the model conclusion", async () => {
  const wrapper = mount(EvaluationConfirmationForm, { props: { evaluation } });
  await wrapper.get<HTMLInputElement>('[name="policy-conclusion"][value="watch"]').setValue();

  await wrapper.get("form").trigger("submit");

  expect(wrapper.text()).toContain("修改模型建议后必须填写原因");
  expect(confirmEvaluation).not.toHaveBeenCalled();
});

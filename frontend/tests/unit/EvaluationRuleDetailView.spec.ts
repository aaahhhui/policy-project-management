import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getEvaluationRule, publishRuleVersion } from "../../src/api/evaluationRules";
import { clearCurrentUser, currentUser } from "../../src/auth/state";
import EvaluationRuleDetailView from "../../src/views/EvaluationRuleDetailView.vue";

vi.mock("vue-router", () => ({ useRoute: () => ({ params: { id: "7" } }) }));
vi.mock("../../src/api/evaluationRules", () => ({
  getEvaluationRule: vi.fn(),
  createRuleDraft: vi.fn(),
  updateRuleDraft: vi.fn(),
  publishRuleVersion: vi.fn(),
  retireRuleVersion: vi.fn(),
}));

const draftRule = {
  id: 7,
  name: "政策适配规则",
  description: "三经营主体统一评估规则",
  created_by: 1,
  created_at: "2026-07-29T08:00:00Z",
  updated_at: "2026-07-29T09:00:00Z",
  versions: [
    {
      id: 13,
      rule_set_id: 7,
      version_number: 3,
      status: "draft" as const,
      hard_rules: [
        { code: "REGION", name: "注册地区", instruction: "判断注册地区", enabled: true },
      ],
      weighted_rules: [
        { code: "TECH", name: "技术匹配", instruction: "判断技术匹配", weight: 60, enabled: true },
        { code: "VALUE", name: "申报价值", instruction: "判断申报价值", weight: 30, enabled: true },
      ],
      prompt_version: "stage2-decision-v1",
      created_by: 1,
      published_by: null,
      published_at: null,
      created_at: "2026-07-29T09:00:00Z",
      updated_at: "2026-07-29T09:00:00Z",
    },
  ],
};

describe("EvaluationRuleDetailView", () => {
  beforeEach(() => {
    clearCurrentUser();
    currentUser.value = {
      id: 1,
      login_name: "owner",
      display_name: "Owner",
      roles: ["applicant_owner"],
    };
    vi.mocked(getEvaluationRule).mockResolvedValue(draftRule);
  });

  it("shows the enabled weight total and blocks publishing until it is 100", async () => {
    const wrapper = mount(EvaluationRuleDetailView, {
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } },
    });
    await vi.dynamicImportSettled();

    expect(wrapper.text()).toContain("启用权重合计 90%");
    const publish = wrapper.get("button[data-action='publish']");
    expect(publish.attributes("disabled")).toBeDefined();
    await publish.trigger("click");
    expect(publishRuleVersion).not.toHaveBeenCalled();
  });

  it("shows the public weight-total validation message when publishing is rejected", async () => {
    vi.mocked(getEvaluationRule).mockResolvedValue({
      ...draftRule,
      versions: [{
        ...draftRule.versions[0],
        weighted_rules: [
          { code: "TECH", name: "技术匹配", instruction: "判断技术匹配", weight: 60, enabled: true },
          { code: "VALUE", name: "申报价值", instruction: "判断申报价值", weight: 40, enabled: true },
        ],
      }],
    });
    vi.stubGlobal("confirm", vi.fn(() => true));
    vi.mocked(publishRuleVersion).mockRejectedValue({
      response: { data: { detail: { code: "rule_weight_total_invalid" } } },
    });

    const wrapper = mount(EvaluationRuleDetailView, {
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } },
    });
    await vi.dynamicImportSettled();
    await wrapper.get("button[data-action='publish']").trigger("click");
    await vi.dynamicImportSettled();

    expect(wrapper.text()).toContain("启用的评分条件权重合计必须为 100");
  });
});

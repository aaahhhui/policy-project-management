import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { listEvaluationRules } from "../../src/api/evaluationRules";
import { clearCurrentUser, currentUser } from "../../src/auth/state";
import EvaluationRulesView from "../../src/views/EvaluationRulesView.vue";

vi.mock("../../src/api/evaluationRules", () => ({
  listEvaluationRules: vi.fn(),
}));
vi.mock("vue-router", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const rules = [
  {
    id: 7,
    name: "政策适配规则",
    description: "三经营主体统一评估规则",
    created_by: 1,
    created_at: "2026-07-29T08:00:00Z",
    updated_at: "2026-07-29T09:00:00Z",
    versions: [
      {
        id: 12,
        rule_set_id: 7,
        version_number: 2,
        status: "published" as const,
        hard_rules: [],
        weighted_rules: [],
        prompt_version: "stage2-decision-v1",
        created_by: 1,
        published_by: 1,
        published_at: "2026-07-29T09:00:00Z",
        created_at: "2026-07-29T08:00:00Z",
        updated_at: "2026-07-29T09:00:00Z",
      },
    ],
  },
];

describe("EvaluationRulesView", () => {
  beforeEach(() => {
    clearCurrentUser();
    currentUser.value = {
      id: 2,
      login_name: "reader",
      display_name: "Reader",
      roles: ["reader"],
    };
    vi.mocked(listEvaluationRules).mockResolvedValue(rules);
  });

  it("shows the published version and hides owner actions from readers", async () => {
    const wrapper = mount(EvaluationRulesView, {
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } },
    });
    await vi.dynamicImportSettled();

    expect(wrapper.get("h1").text()).toBe("评估规则");
    expect(wrapper.text()).toContain("当前发布版 V2");
    expect(wrapper.findAll("button").some((button) => button.text() === "新建规则")).toBe(false);
  });
});

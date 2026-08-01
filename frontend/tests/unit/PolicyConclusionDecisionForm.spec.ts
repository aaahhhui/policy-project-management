import { mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";

import { adjustPolicyConclusion } from "../../src/api/policies";
import PolicyConclusionDecisionForm from "../../src/components/evaluations/PolicyConclusionDecisionForm.vue";

vi.mock("../../src/api/policies", () => ({ adjustPolicyConclusion: vi.fn() }));

beforeEach(() => {
  vi.clearAllMocks();
});

it("blocks an adjustment whose reason is blank", async () => {
  const wrapper = mount(PolicyConclusionDecisionForm, {
    props: { policyId: 8, currentConclusion: "watch", hasPrimaryEntity: true },
  });

  await wrapper.get("form").trigger("submit");

  expect(wrapper.text()).toContain("请填写调整原因");
  expect(adjustPolicyConclusion).not.toHaveBeenCalled();
});

it("explains the primary enterprise prerequisite before recommending application", async () => {
  const wrapper = mount(PolicyConclusionDecisionForm, {
    props: { policyId: 8, currentConclusion: "watch", hasPrimaryEntity: false },
  });
  await wrapper.get<HTMLSelectElement>("select").setValue("recommend_apply");

  expect(wrapper.text()).toContain("请先确认主申报企业，再调整为建议申报");
  expect(wrapper.get<HTMLButtonElement>('button[type="submit"]').element.disabled).toBe(true);
});

it("submits a trimmed reason and emits the saved decision", async () => {
  const decision = {
    id: 3, policy_id: 8, evaluation_batch_id: 31,
    previous_conclusion: "watch" as const, conclusion: "not_recommended" as const,
    source: "manual_override" as const, reason: "暂缓投入", decided_by: 1,
    decided_at: "2026-07-31T06:20:00Z",
  };
  vi.mocked(adjustPolicyConclusion).mockResolvedValue(decision);
  const wrapper = mount(PolicyConclusionDecisionForm, {
    props: { policyId: 8, currentConclusion: "watch", hasPrimaryEntity: true },
  });
  await wrapper.get<HTMLSelectElement>("select").setValue("not_recommended");
  await wrapper.get<HTMLTextAreaElement>("textarea").setValue("  暂缓投入  ");

  await wrapper.get("form").trigger("submit");

  expect(adjustPolicyConclusion).toHaveBeenCalledWith(8, {
    conclusion: "not_recommended",
    reason: "暂缓投入",
  });
  expect(wrapper.emitted("decided")).toEqual([[decision]]);
});

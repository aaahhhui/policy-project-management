import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  createEvaluation,
  cancelEvaluation,
  getEvaluations,
  getPrimaryEntityHistory,
  selectPrimaryEntity,
  type EntityEvaluation,
  type EvaluationBatch,
  type PrimaryEntityDecision,
} from "../../src/api/evaluations";
import {
  getPolicy,
  getPolicyConclusionHistory,
  getPolicyVersions,
  type PolicyDetail,
} from "../../src/api/policies";
import { currentUser } from "../../src/auth/state";
import PolicyDetailView from "../../src/views/PolicyDetailView.vue";

vi.mock("vue-router", () => ({
  useRoute: () => ({ params: { id: "8" } }),
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: { props: ["to"], template: "<a :href=\"to\"><slot /></a>" },
}));
vi.mock("../../src/api/policies", () => ({
  getPolicy: vi.fn(),
  getPolicyVersions: vi.fn(),
  getPolicyConclusionHistory: vi.fn(),
  adjustPolicyConclusion: vi.fn(),
}));
vi.mock("../../src/api/evaluations", () => ({
  getEvaluations: vi.fn(),
  createEvaluation: vi.fn(),
  cancelEvaluation: vi.fn(),
  getPrimaryEntityHistory: vi.fn(),
  selectPrimaryEntity: vi.fn(),
}));

const policy: PolicyDetail = {
  id: 8,
  title: "制造业数字化转型项目申报通知",
  document_number: "粤工信〔2026〕8号",
  published_on: "2026-07-20",
  deadline_on: "2026-08-20",
  current_conclusion: "recommend_apply",
  conclusion_confirmed: false,
  current_conclusion_source: "system_suggestion",
  conclusion_confirmed_at: null,
  converted_to_project: false,
  project_id: null,
  project_name: null,
  current_evaluation_batch_id: 31,
  current_version: {
    id: 12,
    version_number: 2,
    title: "制造业数字化转型项目申报通知",
    body_text: "支持制造业企业开展数字化改造。",
    body_html: "<p>支持制造业企业开展数字化改造。</p>",
    collected_at: "2026-07-27T02:00:00Z",
    snapshot_url: "/api/files/snapshots/12",
  },
  discoveries: [],
  attachments: [],
};

const succeeded: EvaluationBatch = {
  id: 31,
  policy_version_id: 12,
  status: "succeeded",
  prompt_version: "stage1-v1",
  adapter_key: "mock",
  model_name: null,
  profile_snapshot: [],
  summary: "政策方向与公司数字化仿真能力匹配。",
  key_conditions: ["申报主体须在广东省内开展项目"],
  conclusion: "recommend_apply",
  error_message: null,
  started_at: "2026-07-28T01:00:00Z",
  finished_at: "2026-07-28T01:00:05Z",
  created_at: "2026-07-28T01:00:00Z",
  entities: [
    ["ENTITY-BEIJING", "high"],
    ["ENTITY-SUZHOU", "medium"],
    ["ENTITY-SHENZHEN", "uncertain"],
  ].map(([entity_seed_code, match_level]) => ({
    entity_seed_code,
    match_level: match_level as EntityEvaluation["match_level"],
    evidence: ["企业能力与政策方向匹配"],
    unmet_conditions: [],
    risks: [],
    recommended_action: "复核申报条件",
  })),
};

const pending: EvaluationBatch = {
  ...succeeded,
  id: 32,
  status: "pending",
  summary: null,
  key_conditions: null,
  conclusion: null,
  started_at: null,
  finished_at: null,
  entities: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getPolicy).mockResolvedValue(policy);
  vi.mocked(getPolicyVersions).mockResolvedValue([policy.current_version]);
  vi.mocked(getPrimaryEntityHistory).mockResolvedValue([]);
  vi.mocked(getPolicyConclusionHistory).mockResolvedValue([]);
});

describe("PolicyDetailView evaluation", () => {
  it("loads and displays the saved primary entity for a confirmed evaluation", async () => {
    currentUser.value = {
      id: 1, login_name: "owner", display_name: "负责人", roles: ["applicant_owner"],
    };
    vi.mocked(getEvaluations).mockResolvedValue([{
      ...succeeded,
      status: "confirmed",
      profile_snapshot: [
        { seed_code: "ENTITY-BEIJING", legal_name: "北京适创科技有限公司" },
        { seed_code: "ENTITY-SUZHOU", legal_name: "苏州数算软云科技有限公司" },
        { seed_code: "ENTITY-SHENZHEN", legal_name: "深圳适创腾扬科技有限公司" },
      ],
    }]);
    vi.mocked(getPrimaryEntityHistory).mockResolvedValue([{
      id: 1,
      entity_seed_code: "ENTITY-SHENZHEN",
      entity_legal_name: "深圳适创腾扬科技有限公司",
      is_current: true,
    }]);

    const wrapper = mount(PolicyDetailView);
    await flushPromises();

    expect(getPrimaryEntityHistory).toHaveBeenCalledWith(8);
    expect(wrapper.get<HTMLInputElement>('input[value="ENTITY-SHENZHEN"]').element.checked).toBe(true);
    expect(wrapper.get(".primary-selector button").text()).toBe("当前企业已确认");
    expect(selectPrimaryEntity).not.toHaveBeenCalled();
  });

  it("refreshes the saved primary entity after the owner confirms it", async () => {
    currentUser.value = {
      id: 1, login_name: "owner", display_name: "负责人", roles: ["applicant_owner"],
    };
    vi.mocked(getEvaluations).mockResolvedValue([{
      ...succeeded,
      status: "confirmed",
      profile_snapshot: [
        { seed_code: "ENTITY-BEIJING", legal_name: "北京适创科技有限公司" },
        { seed_code: "ENTITY-SUZHOU", legal_name: "苏州数算软云科技有限公司" },
        { seed_code: "ENTITY-SHENZHEN", legal_name: "深圳适创腾扬科技有限公司" },
      ],
    }]);
    vi.mocked(getPrimaryEntityHistory)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([{
        id: 2,
        entity_seed_code: "ENTITY-BEIJING",
        entity_legal_name: "北京适创科技有限公司",
        is_current: true,
      }]);
    vi.mocked(selectPrimaryEntity).mockResolvedValue({
      id: 2,
      entity_seed_code: "ENTITY-BEIJING",
      entity_legal_name: "北京适创科技有限公司",
      is_current: true,
    });

    const wrapper = mount(PolicyDetailView);
    await flushPromises();
    await wrapper.get("form.primary-selector").trigger("submit");
    await flushPromises();

    expect(selectPrimaryEntity).toHaveBeenCalledWith(8, {
      entity_seed_code: "ENTITY-BEIJING",
      reason: null,
    });
    expect(getPrimaryEntityHistory).toHaveBeenCalledTimes(2);
    expect(wrapper.get(".primary-selector button").text()).toBe("当前企业已确认");
  });

  it("shows one policy conclusion, the current evaluation, and collapsed history", async () => {
    currentUser.value = {
      id: 1, login_name: "owner", display_name: "负责人", roles: ["applicant_owner"],
    };
    vi.mocked(getEvaluations).mockResolvedValue([
      succeeded,
      { ...succeeded, id: 29, created_at: "2026-07-27T01:00:00Z" },
    ]);

    const wrapper = mount(PolicyDetailView);
    await flushPromises();

    expect(wrapper.findAll("[data-conclusion]")).toHaveLength(1);
    expect(wrapper.get("[data-conclusion]").text()).toBe("建议申报");
    expect(wrapper.text()).toContain("政策方向与公司数字化仿真能力匹配");
    expect(wrapper.text()).toContain("北京适创科技有限公司");
    expect(wrapper.get("#evaluation-history-list").isVisible()).toBe(false);
    expect(wrapper.get("button[aria-expanded='false']").text()).toContain("历史评估");
    await wrapper.get("button[aria-expanded='false']").trigger("click");
    expect(wrapper.text()).toContain("第 1 次评估");
    expect(wrapper.text()).toContain("批次 #29");
  });

  it("does not render retry for a reader when evaluation failed", async () => {
    currentUser.value = {
      id: 2, login_name: "reader", display_name: "只读用户", roles: ["reader"],
    };
    vi.mocked(getEvaluations).mockResolvedValue([{
      ...pending, status: "failed", error_message: "模型输出不完整", finished_at: "2026-07-28T01:00:05Z",
    }]);

    const wrapper = mount(PolicyDetailView);
    await flushPromises();

    expect(wrapper.text()).toContain("评估失败");
    expect(wrapper.text()).not.toContain("模型输出不完整");
    expect(wrapper.text()).toContain("本次评估未生成有效结果");
    expect(wrapper.findAll("button").some((button) => button.text() === "重新评估")).toBe(false);
    expect(wrapper.findAll("[data-conclusion]")).toHaveLength(1);
  });

  it("does not show a false failure below an evaluation awaiting confirmation", async () => {
    currentUser.value = {
      id: 1, login_name: "owner", display_name: "负责人", roles: ["applicant_owner"],
    };
    vi.mocked(getEvaluations).mockResolvedValue([{
      ...succeeded,
      status: "awaiting_confirmation",
      profile_snapshot: [
        { seed_code: "ENTITY-BEIJING", legal_name: "北京适创科技有限公司" },
        { seed_code: "ENTITY-SUZHOU", legal_name: "苏州数算软云科技有限公司" },
        { seed_code: "ENTITY-SHENZHEN", legal_name: "深圳适创腾扬科技有限公司" },
      ],
    }]);

    const wrapper = mount(PolicyDetailView);
    await flushPromises();

    expect(wrapper.text()).toContain("北京适创科技有限公司");
    expect(wrapper.text()).not.toContain("评估失败");
    expect(wrapper.text()).not.toContain("ENTITY-");
    expect(wrapper.text()).not.toContain("AI");
  });

  it("passes the saved primary enterprise into a reevaluation confirmation", async () => {
    currentUser.value = {
      id: 1, login_name: "owner", display_name: "负责人", roles: ["applicant_owner"],
    };
    vi.mocked(getEvaluations).mockResolvedValue([{
      ...succeeded,
      status: "awaiting_confirmation",
      profile_snapshot: [
        { seed_code: "ENTITY-BEIJING", legal_name: "北京适创科技有限公司" },
        { seed_code: "ENTITY-SUZHOU", legal_name: "苏州数算软云科技有限公司" },
        { seed_code: "ENTITY-SHENZHEN", legal_name: "深圳适创腾扬科技有限公司" },
      ],
    }]);
    vi.mocked(getPrimaryEntityHistory).mockResolvedValue([{
      id: 3,
      entity_seed_code: "ENTITY-SUZHOU",
      entity_legal_name: "苏州数算软云科技有限公司",
      is_current: true,
    }]);

    const wrapper = mount(PolicyDetailView);
    await flushPromises();

    expect(wrapper.get<HTMLInputElement>('[name="primary-entity"][value="ENTITY-SUZHOU"]').element.checked).toBe(true);
    expect(wrapper.text()).toContain("苏州数算软云科技有限公司（当前主企业）");
  });

  it("waits for primary enterprise history before enabling reevaluation confirmation", async () => {
    currentUser.value = {
      id: 1, login_name: "owner", display_name: "负责人", roles: ["applicant_owner"],
    };
    vi.mocked(getEvaluations).mockResolvedValue([{
      ...succeeded,
      status: "awaiting_confirmation",
      profile_snapshot: [
        { seed_code: "ENTITY-BEIJING", legal_name: "北京适创科技有限公司" },
        { seed_code: "ENTITY-SUZHOU", legal_name: "苏州数算软云科技有限公司" },
        { seed_code: "ENTITY-SHENZHEN", legal_name: "深圳适创腾扬科技有限公司" },
      ],
    }]);
    let resolvePrimaryHistory!: (history: PrimaryEntityDecision[]) => void;
    vi.mocked(getPrimaryEntityHistory).mockReturnValue(new Promise((resolve) => {
      resolvePrimaryHistory = resolve;
    }));

    const wrapper = mount(PolicyDetailView);
    await flushPromises();

    expect(wrapper.text()).toContain("正在加载主申报企业信息");
    expect(wrapper.find("form.confirmation-form").exists()).toBe(false);

    resolvePrimaryHistory([{
      id: 2,
      entity_seed_code: "ENTITY-BEIJING",
      entity_legal_name: "北京适创科技有限公司",
      is_current: true,
    }]);
    await flushPromises();

    expect(wrapper.get<HTMLInputElement>('[name="primary-entity"][value="ENTITY-BEIJING"]').element.checked).toBe(true);
    await wrapper.get<HTMLInputElement>('[name="primary-entity"][value="ENTITY-SUZHOU"]').setValue();
    await wrapper.get("form.confirmation-form").trigger("submit");
    expect(wrapper.text()).toContain("切换主申报企业后必须填写原因");
  });

  it("asks an owner to confirm retry and refreshes to pending state", async () => {
    currentUser.value = {
      id: 1, login_name: "owner", display_name: "负责人", roles: ["applicant_owner"],
    };
    vi.mocked(getEvaluations)
      .mockResolvedValueOnce([succeeded])
      .mockResolvedValueOnce([pending, succeeded]);
    vi.mocked(createEvaluation).mockResolvedValue(pending);
    const wrapper = mount(PolicyDetailView);
    await flushPromises();

    await wrapper.get("[data-retry-evaluation]").trigger("click");
    expect(wrapper.get("[role='dialog']").text()).toContain("创建新的历史批次");
    await wrapper.get("[data-confirm-retry]").trigger("click");
    await flushPromises();

    expect(createEvaluation).toHaveBeenCalledWith(8);
    expect(getEvaluations).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain("评估中");
  });

  it("lets an owner cancel without a reason and shows the current batch as cancelled", async () => {
    currentUser.value = {
      id: 1, login_name: "owner", display_name: "Owner", roles: ["applicant_owner"],
    };
    vi.mocked(getEvaluations)
      .mockResolvedValueOnce([pending])
      .mockResolvedValueOnce([{ ...pending, status: "cancelled", finished_at: "2026-07-31T10:00:00Z" }]);
    vi.mocked(cancelEvaluation).mockResolvedValue({ ...pending, status: "cancelled", finished_at: "2026-07-31T10:00:00Z" });
    const wrapper = mount(PolicyDetailView);
    await flushPromises();

    await wrapper.get("[data-cancel-evaluation]").trigger("click");
    expect(wrapper.find("[role='dialog']").exists()).toBe(true);
    await wrapper.get("[data-confirm-cancel]").trigger("click");
    await flushPromises();

    expect(cancelEvaluation).toHaveBeenCalledWith(32, null);
    expect(getEvaluations).toHaveBeenCalledTimes(2);
    expect(wrapper.find("[role='dialog']").exists()).toBe(false);
    expect(wrapper.text()).toContain("已取消");
    expect(wrapper.text()).not.toContain("评估失败");
    expect(wrapper.get("[data-retry-evaluation]").text()).toBe("重新评估");
  });

  it("shows a cancelled batch to a reader without a retry action", async () => {
    currentUser.value = {
      id: 2, login_name: "reader", display_name: "Reader", roles: ["reader"],
    };
    vi.mocked(getEvaluations).mockResolvedValue([{
      ...pending, status: "cancelled", finished_at: "2026-07-31T10:00:00Z",
    }]);
    const wrapper = mount(PolicyDetailView);
    await flushPromises();

    expect(wrapper.text()).toContain("已取消");
    expect(wrapper.find("[data-retry-evaluation]").exists()).toBe(false);
  });

  it("does not show the cancellation action to a reader", async () => {
    currentUser.value = {
      id: 2, login_name: "reader", display_name: "Reader", roles: ["reader"],
    };
    vi.mocked(getEvaluations).mockResolvedValue([pending]);
    const wrapper = mount(PolicyDetailView);
    await flushPromises();

    expect(wrapper.find("[data-cancel-evaluation]").exists()).toBe(false);
  });

  it("focuses, traps, and restores focus for the owner cancellation dialog", async () => {
    currentUser.value = {
      id: 1, login_name: "owner", display_name: "Owner", roles: ["applicant_owner"],
    };
    vi.mocked(getEvaluations).mockResolvedValue([pending]);
    const wrapper = mount(PolicyDetailView, { attachTo: document.body });
    await flushPromises();
    const trigger = wrapper.get<HTMLButtonElement>("[data-cancel-evaluation]");
    trigger.element.focus();

    await trigger.trigger("click");
    await flushPromises();
    const dialog = wrapper.get<HTMLElement>("[role='dialog']");
    const confirm = wrapper.get<HTMLButtonElement>("[data-confirm-cancel]");
    const dismiss = wrapper.get<HTMLButtonElement>("[data-dismiss-cancel]");
    const reason = wrapper.get<HTMLTextAreaElement>("#cancel-reason");
    expect(trigger.text()).toBe("取消评估");
    expect(document.activeElement).toBe(confirm.element);

    reason.element.focus();
    await dialog.trigger("keydown", { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(confirm.element);
    confirm.element.focus();
    await dialog.trigger("keydown", { key: "Tab" });
    expect(document.activeElement).toBe(reason.element);
    await dialog.trigger("keydown", { key: "Escape" });
    await flushPromises();
    expect(wrapper.find("[role='dialog']").exists()).toBe(false);
    expect(document.activeElement).toBe(trigger.element);
    wrapper.unmount();
  });

  it("uses a Chinese fallback when cancellation fails", async () => {
    currentUser.value = {
      id: 1, login_name: "owner", display_name: "Owner", roles: ["applicant_owner"],
    };
    vi.mocked(getEvaluations).mockResolvedValue([pending]);
    vi.mocked(cancelEvaluation).mockRejectedValue(new Error("offline"));
    const wrapper = mount(PolicyDetailView);
    await flushPromises();

    await wrapper.get("[data-cancel-evaluation]").trigger("click");
    await wrapper.get("[data-confirm-cancel]").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("无法取消本次评估，请稍后重试");
    expect(wrapper.text()).not.toContain("Unable to cancel");
  });

  it("shows confirmed conclusion metadata, reverse history, and owner adjustment controls", async () => {
    currentUser.value = {
      id: 1, login_name: "owner", display_name: "负责人", roles: ["applicant_owner"],
    };
    vi.mocked(getPolicy).mockResolvedValue({
      ...policy,
      current_conclusion: "watch",
      conclusion_confirmed: true,
      current_conclusion_source: "manual_override",
      conclusion_confirmed_at: "2026-07-31T06:20:00Z",
    });
    vi.mocked(getEvaluations).mockResolvedValue([{ ...succeeded, status: "confirmed" }]);
    vi.mocked(getPolicyConclusionHistory).mockResolvedValue([
      {
        id: 1, policy_id: 8, evaluation_batch_id: 31,
        previous_conclusion: "recommend_apply", conclusion: "watch",
        source: "evaluation_confirmation", reason: "首次确认", decided_by: 1,
        decided_at: "2026-07-30T06:20:00Z",
      },
      {
        id: 2, policy_id: 8, evaluation_batch_id: 31,
        previous_conclusion: "watch", conclusion: "not_recommended",
        source: "manual_override", reason: "预算暂缓", decided_by: 1,
        decided_at: "2026-07-31T06:20:00Z",
      },
    ]);

    const wrapper = mount(PolicyDetailView);
    await flushPromises();

    expect(wrapper.get("[data-conclusion-metadata]").text()).toContain("当前结论：持续关注");
    expect(wrapper.get("[data-conclusion-metadata]").text()).toContain("来源：负责人调整");
    expect(wrapper.get("[data-conclusion-metadata]").text()).toContain("确认时间：2026年7月31日 14:20");
    await wrapper.get("[data-open-conclusion-decision]").trigger("click");
    expect(wrapper.find("[data-conclusion-decision-form]").exists()).toBe(true);
    const history = wrapper.findAll("[data-conclusion-history-item]");
    expect(history).toHaveLength(2);
    expect(history[0].text()).toContain("持续关注 → 暂不建议申报");
    expect(history[0].text()).toContain("预算暂缓");
    expect(history[1].text()).toContain("建议申报 → 持续关注");
  });

  it("shows conclusion history but no adjustment form to a reader", async () => {
    currentUser.value = {
      id: 2, login_name: "reader", display_name: "只读用户", roles: ["reader"],
    };
    vi.mocked(getPolicy).mockResolvedValue({
      ...policy,
      current_conclusion: "watch",
      conclusion_confirmed: true,
      current_conclusion_source: "evaluation_confirmation",
      conclusion_confirmed_at: "2026-07-31T06:20:00Z",
    });
    vi.mocked(getEvaluations).mockResolvedValue([{ ...succeeded, status: "confirmed" }]);
    vi.mocked(getPolicyConclusionHistory).mockResolvedValue([{
      id: 1, policy_id: 8, evaluation_batch_id: 31,
      previous_conclusion: "recommend_apply", conclusion: "watch",
      source: "evaluation_confirmation", reason: null, decided_by: 1,
      decided_at: "2026-07-31T06:20:00Z",
    }]);

    const wrapper = mount(PolicyDetailView);
    await flushPromises();

    expect(wrapper.find("[data-conclusion-decision-form]").exists()).toBe(false);
    expect(wrapper.findAll("[data-conclusion-history-item]")).toHaveLength(1);
  });

  it("shows evaluation loading instead of a false empty state", async () => {
    currentUser.value = {
      id: 2, login_name: "reader", display_name: "只读用户", roles: ["reader"],
    };
    let resolveEvaluations!: (value: EvaluationBatch[]) => void;
    vi.mocked(getEvaluations).mockReturnValue(
      new Promise((resolve) => { resolveEvaluations = resolve; }),
    );

    const wrapper = mount(PolicyDetailView);
    await flushPromises();

    expect(wrapper.text()).toContain("正在加载评估记录");
    expect(wrapper.text()).not.toContain("当前政策尚无评估批次");
    resolveEvaluations([succeeded]);
    await flushPromises();
  });

  it("keeps the new pending batch visible when history refresh fails", async () => {
    currentUser.value = {
      id: 1, login_name: "owner", display_name: "负责人", roles: ["applicant_owner"],
    };
    vi.mocked(getEvaluations)
      .mockResolvedValueOnce([succeeded])
      .mockRejectedValueOnce(new Error("offline"));
    vi.mocked(createEvaluation).mockResolvedValue(pending);
    const wrapper = mount(PolicyDetailView);
    await flushPromises();

    await wrapper.get("[data-retry-evaluation]").trigger("click");
    await wrapper.get("[data-confirm-retry]").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("评估中");
    expect(wrapper.text()).toContain("新的评估批次已创建，但历史记录暂时无法刷新");
  });

  it("moves focus into the retry dialog, traps it, closes on Escape, and restores focus", async () => {
    currentUser.value = {
      id: 1, login_name: "owner", display_name: "负责人", roles: ["applicant_owner"],
    };
    vi.mocked(getEvaluations).mockResolvedValue([succeeded]);
    const wrapper = mount(PolicyDetailView, { attachTo: document.body });
    await flushPromises();
    const trigger = wrapper.get<HTMLButtonElement>("[data-retry-evaluation]");
    trigger.element.focus();

    await trigger.trigger("click");
    await flushPromises();
    const confirm = wrapper.get<HTMLButtonElement>("[data-confirm-retry]");
    const cancel = wrapper.get<HTMLButtonElement>("[data-cancel-retry]");
    expect(document.activeElement).toBe(confirm.element);

    cancel.element.focus();
    await wrapper.get("[role='dialog']").trigger("keydown", { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(confirm.element);
    await wrapper.get("[role='dialog']").trigger("keydown", { key: "Escape" });
    await flushPromises();
    expect(wrapper.find("[role='dialog']").exists()).toBe(false);
    expect(document.activeElement).toBe(trigger.element);
    wrapper.unmount();
  });

  it("keeps keyboard focus in the dialog while retry is submitting", async () => {
    currentUser.value = {
      id: 1, login_name: "owner", display_name: "负责人", roles: ["applicant_owner"],
    };
    vi.mocked(getEvaluations).mockResolvedValue([succeeded]);
    vi.mocked(createEvaluation).mockReturnValue(new Promise(() => {}));
    const wrapper = mount(PolicyDetailView, { attachTo: document.body });
    await flushPromises();

    await wrapper.get("[data-retry-evaluation]").trigger("click");
    await flushPromises();
    await wrapper.get("[data-confirm-retry]").trigger("click");
    await flushPromises();
    const dialog = wrapper.get<HTMLElement>("[role='dialog']");
    expect(dialog.attributes("aria-busy")).toBe("true");
    await dialog.trigger("keydown", { key: "Tab" });

    expect(document.activeElement).toBe(dialog.element);
    wrapper.unmount();
  });
});

import { flushPromises, mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getPrimaryEntityHistory } from "../../src/api/evaluations";
import { getPolicy, getPolicyVersions, type PolicyDetail } from "../../src/api/policies";
import { getConvertiblePolicies, getProjectUserOptions } from "../../src/api/projects";
import { currentUser } from "../../src/auth/state";
import ProjectCreateDrawer from "../../src/components/projects/ProjectCreateDrawer.vue";
import PolicyDetailView from "../../src/views/PolicyDetailView.vue";

const push = vi.fn();

vi.mock("vue-router", () => ({
  useRoute: () => ({ params: { id: "8" } }),
  useRouter: () => ({ push }),
  RouterLink: { props: ["to"], template: "<a :href=\"to\"><slot /></a>" },
}));
vi.mock("../../src/api/evaluations", () => ({
  getEvaluations: vi.fn().mockResolvedValue([]),
  createEvaluation: vi.fn(),
  cancelEvaluation: vi.fn(),
  getPrimaryEntityHistory: vi.fn(),
}));
vi.mock("../../src/api/policies", () => ({
  getPolicy: vi.fn(),
  getPolicyVersions: vi.fn(),
  getPolicyConclusionHistory: vi.fn().mockResolvedValue([]),
  adjustPolicyConclusion: vi.fn(),
}));
vi.mock("../../src/api/projects", () => ({
  createProjectFromPolicy: vi.fn(),
  getConvertiblePolicies: vi.fn(),
  getProjectUserOptions: vi.fn(),
}));

const policy: PolicyDetail = {
  id: 8,
  title: "制造业数字化转型项目申报通知",
  document_number: "粤工信〔2026〕8号",
  published_on: "2026-07-20",
  deadline_on: "2026-08-20",
  current_conclusion: "recommend_apply",
  conclusion_confirmed: true,
  current_conclusion_source: "evaluation_confirmation",
  conclusion_confirmed_at: "2026-08-01T08:00:00Z",
  converted_to_project: false,
  project_id: null,
  project_name: null,
  current_evaluation_batch_id: null,
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

const desktopMedia = {
  matches: false,
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
};

beforeEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn().mockReturnValue(desktopMedia),
  });
  currentUser.value = {
    id: 1,
    login_name: "owner",
    display_name: "负责人",
    roles: ["applicant_owner"],
  };
  vi.mocked(getPolicy).mockResolvedValue({ ...policy });
  vi.mocked(getPolicyVersions).mockResolvedValue([policy.current_version]);
  vi.mocked(getPrimaryEntityHistory).mockResolvedValue([{
    id: 31,
    entity_seed_code: "ENTITY-SHENZHEN",
    entity_legal_name: "深圳适创腾扬科技有限公司",
    is_current: true,
  }]);
  vi.mocked(getConvertiblePolicies).mockResolvedValue({
    items: [{
      id: 8,
      title: policy.title,
      primary_entity_decision_id: 31,
      primary_entity_seed_code: "ENTITY-SHENZHEN",
      primary_entity_legal_name: "深圳适创腾扬科技有限公司",
      deadline_on: policy.deadline_on,
      conversion_warnings: [],
    }],
    page: 1,
    page_size: 20,
    total: 1,
  });
  vi.mocked(getProjectUserOptions).mockResolvedValue([]);
});

describe("PolicyDetailView project lifecycle", () => {
  it("lets an eligible owner open the desktop conversion drawer and navigates after creation", async () => {
    const wrapper = mount(PolicyDetailView, {
      global: { stubs: { ElDrawer: { template: "<aside><slot name='header' /><slot /></aside>" } } },
    });
    await flushPromises();

    const action = wrapper.get("[data-open-project-conversion]");
    expect(action.text()).toBe("转为项目");
    expect(wrapper.get("[aria-label='项目状态']").text()).not.toContain("已转项目");

    await action.trigger("click");
    await flushPromises();
    expect(wrapper.findComponent(ProjectCreateDrawer).props("open")).toBe(true);
    expect(wrapper.findComponent(ProjectCreateDrawer).props("policyId")).toBe(8);

    wrapper.findComponent(ProjectCreateDrawer).vm.$emit("created", 19);
    await nextTick();
    expect(push).toHaveBeenCalledWith("/projects/19");
  });

  it("keeps the confirmed human conclusion and renders one project link after conversion", async () => {
    vi.mocked(getPolicy).mockResolvedValue({
      ...policy,
      converted_to_project: true,
      project_id: 19,
      project_name: "数字化改造申报项目",
    });

    const wrapper = mount(PolicyDetailView);
    await flushPromises();

    expect(wrapper.get("[data-conclusion]").text()).toBe("建议申报");
    expect(wrapper.get("[aria-label='项目状态'] a").text()).toBe("已转项目：数字化改造申报项目");
    expect(wrapper.get("[aria-label='项目状态'] a").attributes("href")).toBe("/projects/19");
    expect(wrapper.find("[data-open-project-conversion]").exists()).toBe(false);
    expect(wrapper.findComponent(ProjectCreateDrawer).exists()).toBe(false);
  });

  it.each([
    ["reader", { roles: ["reader"] }, {}, false],
    ["unconfirmed policy", {}, { conclusion_confirmed: false }, false],
    ["non-recommend policy", {}, { current_conclusion: "watch" }, false],
    ["missing current primary entity", {}, {}, true],
  ])("does not offer conversion to a %s", async (_label, userPatch, policyPatch, noPrimary) => {
    currentUser.value = { ...currentUser.value!, ...userPatch };
    vi.mocked(getPolicy).mockResolvedValue({ ...policy, ...policyPatch } as PolicyDetail);
    if (noPrimary) vi.mocked(getPrimaryEntityHistory).mockResolvedValue([]);

    const wrapper = mount(PolicyDetailView);
    await flushPromises();

    expect(wrapper.find("[data-open-project-conversion]").exists()).toBe(false);
    expect(wrapper.findComponent(ProjectCreateDrawer).exists()).toBe(false);
  });

  it("hides conversion controls at mobile width while preserving policy content", async () => {
    vi.mocked(window.matchMedia).mockReturnValue({
      ...desktopMedia,
      matches: true,
    } as unknown as MediaQueryList);

    const wrapper = mount(PolicyDetailView);
    await flushPromises();

    expect(wrapper.text()).toContain(policy.title);
    expect(wrapper.get("[data-conclusion]").text()).toBe("建议申报");
    expect(wrapper.find("[data-open-project-conversion]").exists()).toBe(false);
    expect(wrapper.findComponent(ProjectCreateDrawer).exists()).toBe(false);
  });
});

import { mount } from "@vue/test-utils";
import { nextTick, reactive } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getProject, type ProjectDetail } from "../../src/api/projects";
import ProjectDetailView from "../../src/views/ProjectDetailView.vue";

const route = reactive({ params: { id: "19" } });
vi.mock("vue-router", () => ({ useRoute: () => route, RouterLink: { template: "<a><slot /></a>" } }));
vi.mock("../../src/api/projects", () => ({ getProject: vi.fn() }));

const project: ProjectDetail = {
  id: 19, policy_id: 7, name: "制造业数字化改造项目", primary_entity_decision_id: 11,
  primary_entity_seed_code: "E-1", primary_entity_legal_name: "示例企业", applicant_owner_id: 1,
  applicant_owner_display_name: "王负责人", liaison_user_id: 4, liaison_display_name: "李联络", status: "submitted",
  deadline_on: null, submitted_on: "2026-08-01", result_on: null, progress_note: null, result_note: null,
  termination_note: null, version: 3, members: [{ id: 1, user_id: 5, display_name: "项目成员", added_at: "2026-08-01T00:00:00Z" }], conversion_warnings: [],
  policy: { id: 7, title: "制造业数字化改造通知", conclusion: "recommend_apply", conclusion_source: "evaluation_confirmation", conclusion_confirmed_at: "2026-07-31T00:00:00Z" },
  entity: { decision_id: 11, seed_code: "E-1", legal_name: "示例企业" }, applicant_owner: { id: 1, display_name: "王负责人" }, liaison: { id: 4, display_name: "李联络" },
  dates: { deadline_on: null, submitted_on: "2026-08-01", result_on: null }, notes: { progress_note: null, result_note: null, termination_note: null }, status_history: [],
  capabilities: { can_edit_project: false, can_update_progress: false, can_transition: false, can_correct_status: false, can_correct_primary_entity: false },
};

describe("ProjectDetailView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    route.params.id = "19";
    vi.mocked(getProject).mockResolvedValue(project);
    Object.defineProperty(window, "matchMedia", { configurable: true, value: vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }) });
  });

  it("renders project facts in order with policy link, human conclusion and placeholders but no reader controls", async () => {
    const wrapper = mount(ProjectDetailView, { global: { stubs: { RouterLink: { props: ["to"], template: "<a :href=\"to\"><slot /></a>" } } } });
    await vi.dynamicImportSettled();
    const text = wrapper.text();

    expect(text.indexOf("制造业数字化改造项目")).toBeLessThan(text.indexOf("制造业数字化改造通知"));
    expect(text.indexOf("制造业数字化改造通知")).toBeLessThan(text.indexOf("示例企业"));
    expect(wrapper.find("a[href='/policies/7']").exists()).toBe(true);
    expect(text).toContain("建议申报");
    expect(text).toContain("——");
    expect(wrapper.find("[data-project-mutations]").exists()).toBe(false);
  });

  it("uses backend conclusion codes and reloads when the route project ID changes", async () => {
    const nextProject = { ...project, id: 20, policy: { ...project.policy, conclusion: "not_recommended" }, capabilities: { ...project.capabilities } };
    vi.mocked(getProject).mockImplementation(async (id) => id === 20 ? nextProject : { ...project, policy: { ...project.policy, conclusion: "uncertain" } });
    const wrapper = mount(ProjectDetailView, { global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } } });
    await vi.dynamicImportSettled();
    expect(wrapper.text()).toContain("无法判断");
    route.params.id = "20";
    await nextTick();
    await vi.dynamicImportSettled();
    expect(getProject).toHaveBeenLastCalledWith(20);
    expect(wrapper.text()).toContain("暂不建议申报");
  });

  it("hides mutation controls on mobile without hiding project content", async () => {
    project.capabilities = { ...project.capabilities, can_transition: true };
    const media = { matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() };
    vi.mocked(window.matchMedia).mockReturnValue(media as unknown as MediaQueryList);
    const wrapper = mount(ProjectDetailView, { global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } } });
    await vi.dynamicImportSettled();
    expect(wrapper.find("[data-project-mutations]").exists()).toBe(true);
    media.matches = true;
    const listener = media.addEventListener.mock.calls[0][1] as () => void;
    listener();
    await nextTick();
    expect(wrapper.find("[data-project-mutations]").exists()).toBe(false);
    expect(wrapper.text()).toContain("制造业数字化改造项目");
  });
});

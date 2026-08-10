import { mount } from "@vue/test-utils";
import ElementPlus from "element-plus";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createProjectFromPolicy, getConvertiblePolicies, getProjectUserOptions, type ProjectDetail } from "../../src/api/projects";
import { clearCurrentUser, currentUser } from "../../src/auth/state";
import ProjectCreateDrawer from "../../src/components/projects/ProjectCreateDrawer.vue";

vi.mock("../../src/api/projects", () => ({
  createProjectFromPolicy: vi.fn(), getConvertiblePolicies: vi.fn(), getProjectUserOptions: vi.fn(),
}));

describe("ProjectCreateDrawer", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearCurrentUser();
    currentUser.value = { id: 1, login_name: "owner", display_name: "Owner", roles: ["applicant_owner"] };
    vi.mocked(getConvertiblePolicies).mockResolvedValue({
      items: [{ id: 7, title: "制造业数字化改造通知", primary_entity_decision_id: 11, primary_entity_seed_code: "E-1", primary_entity_legal_name: "示例企业", deadline_on: "2026-01-01", conversion_warnings: ["deadline_expired"] }],
      page: 1, page_size: 20, total: 1,
    });
    vi.mocked(getProjectUserOptions).mockResolvedValue([
      { id: 4, display_name: "对接人", role: "liaison" }, { id: 5, display_name: "成员", role: "member" },
    ]);
  });

  const createdProject: ProjectDetail = {
    id: 19, policy_id: 7, name: "制造业数字化改造通知", primary_entity_decision_id: 11,
    primary_entity_seed_code: "E-1", primary_entity_legal_name: "示例企业", applicant_owner_id: 1,
    applicant_owner_display_name: "Owner", liaison_user_id: 4, liaison_display_name: "对接人", status: "pending_application",
    deadline_on: "2026-01-01", submitted_on: null, result_on: null, progress_note: null, result_note: null,
    termination_note: null, version: 1, members: [], conversion_warnings: ["deadline_expired"],
    policy: { id: 7, title: "制造业数字化改造通知", conclusion: "recommend_apply", conclusion_source: "evaluation_confirmation", conclusion_confirmed_at: "2026-08-01T00:00:00Z" },
    entity: { decision_id: 11, seed_code: "E-1", legal_name: "示例企业" }, applicant_owner: { id: 1, display_name: "Owner" },
    liaison: { id: 4, display_name: "对接人" }, dates: { deadline_on: "2026-01-01", submitted_on: null, result_on: null },
    notes: { progress_note: null, result_note: null, termination_note: null }, status_history: [],
    capabilities: { can_edit_project: true, can_update_progress: true, can_transition: true, can_correct_status: true, can_correct_primary_entity: true },
  };

  it("loads convertible policies for an owner and inherits policy values with a non-blocking deadline warning", async () => {
    const wrapper = mount(ProjectCreateDrawer, { props: { open: true }, global: { plugins: [ElementPlus], stubs: { ElDrawer: { template: "<div><slot name='header' /><slot /></div>" } } } });
    await vi.dynamicImportSettled();

    expect(getConvertiblePolicies).toHaveBeenCalledWith(1, 20);
    expect(getProjectUserOptions).toHaveBeenCalledOnce();
    expect(wrapper.text()).toContain("制造业数字化改造通知");
    expect(wrapper.text()).toContain("示例企业");
    expect(wrapper.text()).toContain("申请截止日期已过");
    expect(wrapper.get("button[type='submit']").attributes("disabled")).toBeDefined();
  });

  it("keeps one idempotency key after a failed creation and navigates after retry", async () => {
    vi.mocked(createProjectFromPolicy)
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce(createdProject);
    const wrapper = mount(ProjectCreateDrawer, {
      props: { open: true, keyGenerator: () => "fixed-project-key" }, global: { plugins: [ElementPlus], stubs: { ElDrawer: { template: "<div><slot name='header' /><slot /></div>" } } },
    });
    await vi.dynamicImportSettled();
    await wrapper.get("select[aria-label='项目对接人']").setValue("4");
    await wrapper.get("form").trigger("submit");
    await vi.dynamicImportSettled();
    expect(wrapper.get("[role='alert']").text()).toContain("创建项目未完成");
    await wrapper.get("form").trigger("submit");
    await vi.dynamicImportSettled();

    expect(createProjectFromPolicy).toHaveBeenNthCalledWith(1, 7, expect.objectContaining({ liaison_user_id: 4 }), "fixed-project-key");
    expect(createProjectFromPolicy).toHaveBeenNthCalledWith(2, 7, expect.objectContaining({ liaison_user_id: 4 }), "fixed-project-key");
    expect(wrapper.emitted("created")?.[0]).toEqual([19]);
  });

  it("sends members only once and never repeats the selected liaison", async () => {
    vi.mocked(createProjectFromPolicy).mockResolvedValueOnce(createdProject);
    const wrapper = mount(ProjectCreateDrawer, {
      props: { open: true, keyGenerator: () => "member-key" }, global: { plugins: [ElementPlus], stubs: { ElDrawer: { template: "<div><slot name='header' /><slot /></div>" } } },
    });
    await vi.dynamicImportSettled();
    await wrapper.get("select[aria-label='项目对接人']").setValue("4");
    await wrapper.get("select[aria-label='项目成员']").setValue(["4", "5"]);
    await wrapper.get("form").trigger("submit");
    await vi.dynamicImportSettled();

    expect(createProjectFromPolicy).toHaveBeenCalledWith(7, expect.objectContaining({ liaison_user_id: 4, member_user_ids: [5] }), "member-key");
  });

  it("loads the next convertible-policy page", async () => {
    vi.mocked(getConvertiblePolicies)
      .mockResolvedValueOnce({ items: [{ id: 7, title: "第一页政策", primary_entity_decision_id: 11, primary_entity_seed_code: "E-1", primary_entity_legal_name: "示例企业", deadline_on: null, conversion_warnings: [] }], page: 1, page_size: 20, total: 21 })
      .mockResolvedValueOnce({ items: [{ id: 8, title: "第二页政策", primary_entity_decision_id: 12, primary_entity_seed_code: "E-2", primary_entity_legal_name: "第二企业", deadline_on: null, conversion_warnings: [] }], page: 2, page_size: 20, total: 21 });
    const wrapper = mount(ProjectCreateDrawer, { props: { open: true }, global: { plugins: [ElementPlus], stubs: { ElDrawer: { template: "<div><slot name='header' /><slot /></div>" } } } });
    await vi.dynamicImportSettled();
    await wrapper.get(".policy-pages button:last-child").trigger("click");
    await vi.dynamicImportSettled();

    expect(getConvertiblePolicies).toHaveBeenLastCalledWith(2, 20);
    expect(wrapper.text()).toContain("第二页政策");
  });

  it("submits the policy fixed by a detail view even when it is not on the first page", async () => {
    vi.mocked(getConvertiblePolicies).mockImplementation(async (page) => page === 1
      ? {
          items: [{ id: 7, title: "Policy B", primary_entity_decision_id: 11, primary_entity_seed_code: "E-1", primary_entity_legal_name: "Entity B", deadline_on: null, conversion_warnings: [] }],
          page: 1,
          page_size: 20,
          total: 21,
        }
      : {
          items: [{ id: 8, title: "Policy A", primary_entity_decision_id: 12, primary_entity_seed_code: "E-2", primary_entity_legal_name: "Entity A", deadline_on: "2026-12-31", conversion_warnings: [] }],
          page: 2,
          page_size: 20,
          total: 21,
        });
    const wrapper = mount(ProjectCreateDrawer, {
      props: { open: true, policyId: 8, keyGenerator: () => "fixed-policy-key" },
      global: { plugins: [ElementPlus], stubs: { ElDrawer: { template: "<div><slot name='header' /><slot /></div>" } } },
    });
    await vi.dynamicImportSettled();

    expect(getConvertiblePolicies).toHaveBeenNthCalledWith(1, 1, 20);
    expect(getConvertiblePolicies).toHaveBeenNthCalledWith(2, 2, 20);
    expect((wrapper.get("select[aria-label='可转换政策']").element as HTMLSelectElement).value).toBe("8");
    expect(wrapper.get("select[aria-label='可转换政策']").attributes("disabled")).toBeDefined();

    await wrapper.get("select[aria-label='项目对接人']").setValue("4");
    await wrapper.get("form").trigger("submit");
    await vi.dynamicImportSettled();

    expect(createProjectFromPolicy).toHaveBeenCalledWith(
      8,
      expect.objectContaining({ name: "Policy A", liaison_user_id: 4 }),
      "fixed-policy-key",
    );
  });

  it("shows the non-blocking unknown-deadline warning", async () => {
    vi.mocked(getConvertiblePolicies).mockResolvedValueOnce({
      items: [{ id: 7, title: "未知截止政策", primary_entity_decision_id: 11, primary_entity_seed_code: "E-1", primary_entity_legal_name: "示例企业", deadline_on: null, conversion_warnings: ["deadline_unknown"] }], page: 1, page_size: 20, total: 1,
    });
    const wrapper = mount(ProjectCreateDrawer, { props: { open: true }, global: { plugins: [ElementPlus], stubs: { ElDrawer: { template: "<div><slot name='header' /><slot /></div>" } } } });
    await vi.dynamicImportSettled();

    expect(wrapper.text()).toContain("申请截止日期未知");
  });

  it("prevents a duplicate submit while creation is pending", async () => {
    let resolveCreation: (project: ProjectDetail) => void;
    vi.mocked(createProjectFromPolicy).mockImplementationOnce(() => new Promise((resolve) => { resolveCreation = resolve; }));
    const wrapper = mount(ProjectCreateDrawer, { props: { open: true, keyGenerator: () => "pending-key" }, global: { plugins: [ElementPlus], stubs: { ElDrawer: { template: "<div><slot name='header' /><slot /></div>" } } } });
    await vi.dynamicImportSettled();
    await wrapper.get("select[aria-label='项目对接人']").setValue("4");
    await wrapper.get("form").trigger("submit");
    await wrapper.get("form").trigger("submit");
    expect(createProjectFromPolicy).toHaveBeenCalledTimes(1);
    resolveCreation!(createdProject);
    await vi.dynamicImportSettled();
  });

  it("does not load or render conversion controls for readers", async () => {
    currentUser.value = { id: 2, login_name: "reader", display_name: "Reader", roles: ["reader"] };
    const wrapper = mount(ProjectCreateDrawer, { props: { open: true }, global: { plugins: [ElementPlus], stubs: { ElDrawer: { template: "<div><slot name='header' /><slot /></div>" } } } });
    await vi.dynamicImportSettled();
    expect(getConvertiblePolicies).not.toHaveBeenCalled();
    expect(wrapper.text()).not.toContain("转为项目");
  });
});

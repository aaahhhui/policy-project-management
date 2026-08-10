import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getProjectUserOptions, updateProject, type ProjectDetail } from "../../src/api/projects";
import ProjectEditForm from "../../src/components/projects/ProjectEditForm.vue";

vi.mock("../../src/api/projects", () => ({ updateProject: vi.fn(), getProjectUserOptions: vi.fn() }));

const project: ProjectDetail = {
  id: 19, policy_id: 7, name: "项目", primary_entity_decision_id: 11, primary_entity_seed_code: "E-1", primary_entity_legal_name: "企业", applicant_owner_id: 1, applicant_owner_display_name: "负责人", liaison_user_id: 4, liaison_display_name: "联络", status: "submitted", deadline_on: "2026-09-01", submitted_on: "2026-08-01", result_on: null, progress_note: "进展", result_note: null, termination_note: null, version: 3, members: [{ id: 1, user_id: 5, display_name: "成员", added_at: "2026-08-01T00:00:00Z" }], conversion_warnings: [], policy: { id: 7, title: "政策", conclusion: "recommend_apply", conclusion_source: "manual", conclusion_confirmed_at: null }, entity: { decision_id: 11, seed_code: "E-1", legal_name: "企业" }, applicant_owner: { id: 1, display_name: "负责人" }, liaison: { id: 4, display_name: "联络" }, dates: { deadline_on: "2026-09-01", submitted_on: "2026-08-01", result_on: null }, notes: { progress_note: "进展", result_note: null, termination_note: null }, status_history: [], recent_audits: [], capabilities: { can_edit_project: true, can_update_progress: true, can_transition: true, can_correct_status: true, can_correct_primary_entity: true },
};

describe("ProjectEditForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getProjectUserOptions).mockResolvedValue([
      { id: 4, display_name: "李联络", role: "liaison" }, { id: 5, display_name: "项目成员", role: "member" },
    ]);
  });

  it("submits only owner allowlisted fields using the current version and replaces detail", async () => {
    vi.mocked(updateProject).mockResolvedValue({ ...project, name: "新项目", version: 4 });
    const wrapper = mount(ProjectEditForm, { props: { project } });
    await wrapper.get<HTMLInputElement>("[aria-label='项目名称']").setValue("新项目");
    await wrapper.get<HTMLTextAreaElement>("[aria-label='进展备注']").setValue("   ");
    await wrapper.get("form").trigger("submit");

    expect(updateProject).toHaveBeenCalledWith(19, expect.objectContaining({ expected_version: 3, name: "新项目", member_user_ids: [5], progress_note: null }));
    expect(wrapper.emitted("updated")?.[0]?.[0]).toMatchObject({ version: 4, name: "新项目" });
  });

  it.each([
    ["pending_application", ["expected_version", "name", "deadline_on", "liaison_user_id", "member_user_ids", "submitted_on", "progress_note"]],
    ["submitted", ["expected_version", "name", "deadline_on", "liaison_user_id", "member_user_ids", "submitted_on", "progress_note"]],
    ["succeeded", ["expected_version", "name", "deadline_on", "liaison_user_id", "member_user_ids", "submitted_on", "progress_note", "result_on", "result_note"]],
    ["rejected", ["expected_version", "name", "deadline_on", "liaison_user_id", "member_user_ids", "submitted_on", "progress_note", "result_on", "result_note"]],
    ["terminated", ["expected_version", "name", "deadline_on", "liaison_user_id", "member_user_ids", "submitted_on", "progress_note", "termination_note"]],
  ] as const)("sends only %s-compatible owner maintenance fields", async (status, expectedKeys) => {
    const stateProject = {
      ...project, status,
      result_on: status === "succeeded" || status === "rejected" ? "2026-08-04" : null,
      result_note: status === "succeeded" || status === "rejected" ? "结果" : null,
      termination_note: status === "terminated" ? "终止" : null,
    };
    vi.mocked(updateProject).mockResolvedValue(stateProject);
    const wrapper = mount(ProjectEditForm, { props: { project: stateProject } });
    await wrapper.get("form").trigger("submit");

    expect(Object.keys(vi.mocked(updateProject).mock.calls[0][1]).sort()).toEqual([...expectedKeys].sort());
  });

  it("gives a liaison only dates and notes, never owner fields", async () => {
    vi.mocked(updateProject).mockResolvedValue(project);
    const liaisonProject = { ...project, capabilities: { ...project.capabilities, can_edit_project: false, can_update_progress: true } };
    const wrapper = mount(ProjectEditForm, { props: { project: liaisonProject } });

    expect(wrapper.find("[aria-label='项目名称']").exists()).toBe(false);
    expect(wrapper.find("[aria-label='项目对接人']").exists()).toBe(false);
    await wrapper.get("form").trigger("submit");
    expect(updateProject).toHaveBeenCalledWith(19, expect.not.objectContaining({ name: expect.anything(), deadline_on: expect.anything(), liaison_user_id: expect.anything(), member_user_ids: expect.anything() }));
    expect(Object.keys(vi.mocked(updateProject).mock.calls[0][1]).sort()).toEqual(["expected_version", "submitted_on", "progress_note"].sort());
  });

  it("uses active-user name and role selectors, validates required owner values, and sends selected members", async () => {
    vi.mocked(updateProject).mockResolvedValue(project);
    const wrapper = mount(ProjectEditForm, { props: { project } });
    await vi.dynamicImportSettled();

    expect(getProjectUserOptions).toHaveBeenCalledOnce();
    expect(wrapper.get("[aria-label='项目对接人']").text()).toContain("李联络（liaison）");
    expect(wrapper.get("[aria-label='项目成员']").text()).toContain("项目成员（member）");
    expect(wrapper.get<HTMLInputElement>("[aria-label='项目名称']").attributes("maxlength")).toBe("300");
    await wrapper.get<HTMLInputElement>("[aria-label='项目名称']").setValue("  ");
    await wrapper.get<HTMLSelectElement>("[aria-label='项目对接人']").setValue("");
    await wrapper.get("form").trigger("submit");
    expect(updateProject).not.toHaveBeenCalled();
    expect(wrapper.get("[role='alert']").text()).toContain("项目名称");

    await wrapper.get<HTMLInputElement>("[aria-label='项目名称']").setValue("已验证名称");
    await wrapper.get<HTMLSelectElement>("[aria-label='项目对接人']").setValue("4");
    await wrapper.get<HTMLSelectElement>("[aria-label='项目成员']").setValue(["5"]);
    await wrapper.get("form").trigger("submit");
    expect(updateProject).toHaveBeenCalledWith(19, expect.objectContaining({ name: "已验证名称", liaison_user_id: 4, member_user_ids: [5] }));
  });

  it("offers a reload action instead of resubmitting stale values after a version conflict", async () => {
    vi.mocked(updateProject).mockRejectedValue({ response: { data: { detail: { code: "project_version_conflict" } } } });
    const wrapper = mount(ProjectEditForm, { props: { project } });
    await wrapper.get("form").trigger("submit");
    expect(wrapper.text()).toContain("重新加载");
    await wrapper.get("[data-reload-project]").trigger("click");
    expect(wrapper.emitted("reload")).toBeTruthy();
  });
});

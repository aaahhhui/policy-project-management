import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { transitionProject, type ProjectDetail } from "../../src/api/projects";
import ProjectStatusForm from "../../src/components/projects/ProjectStatusForm.vue";

vi.mock("../../src/api/projects", () => ({ transitionProject: vi.fn() }));

const project = { id: 19, status: "submitted", submitted_on: "2026-08-01", result_on: null, result_note: null, termination_note: null, version: 3, capabilities: { can_transition: true } } as ProjectDetail;

describe("ProjectStatusForm", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows only permitted submitted-state targets and sends an optional result note with the version", async () => {
    vi.mocked(transitionProject).mockResolvedValue(project);
    const wrapper = mount(ProjectStatusForm, { props: { project } });
    expect(wrapper.text()).toContain("已成功");
    expect(wrapper.text()).toContain("未获批");
    expect(wrapper.text()).toContain("已终止");
    expect(wrapper.text()).not.toContain("待申报");
    await wrapper.get<HTMLSelectElement>("[aria-label='目标状态']").setValue("succeeded");
    await wrapper.get<HTMLInputElement>("[aria-label='结果日期']").setValue("2026-08-04");
    await wrapper.get<HTMLTextAreaElement>("[aria-label='结果备注']").setValue("可选备注");
    await wrapper.get("form").trigger("submit");
    expect(transitionProject).toHaveBeenCalledWith(19, { expected_version: 3, target_status: "succeeded", result_on: "2026-08-04", result_note: "可选备注" });
  });

  it("requires a bounded termination note and does not expose result fields for termination", async () => {
    const wrapper = mount(ProjectStatusForm, { props: { project } });
    await wrapper.get<HTMLSelectElement>("[aria-label='目标状态']").setValue("terminated");
    expect(wrapper.find("[aria-label='结果日期']").exists()).toBe(false);
    expect(wrapper.get<HTMLTextAreaElement>("[aria-label='终止备注']").attributes("maxlength")).toBe("2000");
    await wrapper.get("form").trigger("submit");
    expect(transitionProject).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("终止备注");
  });

  it("sends only status-compatible fields for submitted and terminated transitions", async () => {
    vi.mocked(transitionProject).mockResolvedValue(project);
    const submittedProject = { ...project, status: "pending_application" as const, submitted_on: null };
    const submitted = mount(ProjectStatusForm, { props: { project: submittedProject } });
    await submitted.get<HTMLInputElement>("[aria-label='提交日期']").setValue("2026-08-01");
    await submitted.get("form").trigger("submit");
    expect(transitionProject).toHaveBeenLastCalledWith(19, { expected_version: 3, target_status: "submitted", submitted_on: "2026-08-01" });

    const terminated = mount(ProjectStatusForm, { props: { project } });
    await terminated.get<HTMLSelectElement>("[aria-label='目标状态']").setValue("terminated");
    await terminated.get<HTMLTextAreaElement>("[aria-label='终止备注']").setValue("主动终止");
    await terminated.get("form").trigger("submit");
    expect(transitionProject).toHaveBeenLastCalledWith(19, { expected_version: 3, target_status: "terminated", termination_note: "主动终止" });
  });

  it("offers a reload action on a transition version conflict", async () => {
    vi.mocked(transitionProject).mockRejectedValue({ response: { data: { detail: { code: "project_version_conflict" } } } });
    const wrapper = mount(ProjectStatusForm, { props: { project } });
    await wrapper.get<HTMLSelectElement>("[aria-label='目标状态']").setValue("terminated");
    await wrapper.get<HTMLTextAreaElement>("[aria-label='终止备注']").setValue("主动终止");
    await wrapper.get("form").trigger("submit");
    expect(wrapper.find("[data-reload-project]").exists()).toBe(true);
    await wrapper.get("[data-reload-project]").trigger("click");
    expect(wrapper.emitted("reload")).toBeTruthy();
  });
});

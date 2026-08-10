import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

import { correctProjectPrimaryEntity, correctProjectStatus, type ProjectDetail } from "../../src/api/projects";
import ProjectCorrectionDialog from "../../src/components/projects/ProjectCorrectionDialog.vue";

vi.mock("../../src/api/projects", () => ({ correctProjectStatus: vi.fn(), correctProjectPrimaryEntity: vi.fn() }));

const project = { id: 19, status: "terminated", primary_entity_decision_id: 11, submitted_on: "2026-08-01", result_on: null, result_note: null, termination_note: "材料撤回", version: 3, status_history: [{ id: 3, action: "transition", previous_status: "submitted", new_status: "terminated", actor: { id: 4, display_name: "联络" }, reason: null, related_date: null, before_values: {}, after_values: {}, from_version: 2, to_version: 3, occurred_at: "2026-08-04T00:00:00Z" }], capabilities: { can_correct_status: true, can_correct_primary_entity: true } } as ProjectDetail;

describe("ProjectCorrectionDialog", () => {
  it("uses the actual pre-termination status and confirms before clearing termination fields", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(correctProjectStatus).mockResolvedValue(project);
    const wrapper = mount(ProjectCorrectionDialog, { props: { project, mode: "status" } });
    expect(wrapper.get<HTMLSelectElement>("[aria-label='更正目标状态']").element.value).toBe("submitted");
    expect(wrapper.text()).not.toContain("待申报");
    await wrapper.get("form").trigger("submit");
    expect(correctProjectStatus).toHaveBeenCalledWith(19, expect.objectContaining({ expected_version: 3, target_status: "submitted", reason: null }));
    expect(window.confirm).toHaveBeenCalled();
  });

  it("does not permit terminal-to-pending correction and restricts primary corrections to backend owners", async () => {
    const forbidden = { ...project, status: "succeeded" as const, capabilities: { ...project.capabilities, can_correct_primary_entity: false } };
    const statusWrapper = mount(ProjectCorrectionDialog, { props: { project: forbidden, mode: "status" } });
    expect(statusWrapper.text()).not.toContain("待申报");
    const primaryWrapper = mount(ProjectCorrectionDialog, { props: { project: forbidden, mode: "primary-entity" } });
    expect(primaryWrapper.find("form").exists()).toBe(false);
  });

  it("sends an exact bounded primary-entity correction payload", async () => {
    vi.mocked(correctProjectPrimaryEntity).mockResolvedValue(project);
    const wrapper = mount(ProjectCorrectionDialog, { props: { project, mode: "primary-entity" } });
    await wrapper.get<HTMLInputElement>("[aria-label='主申报企业决定 ID']").setValue("12");
    await wrapper.get<HTMLTextAreaElement>("[aria-label='更正原因']").setValue("更换企业");
    await wrapper.get("form").trigger("submit");
    expect(correctProjectPrimaryEntity).toHaveBeenCalledWith(19, { expected_version: 3, primary_entity_decision_id: 12, reason: "更换企业" });
  });
});

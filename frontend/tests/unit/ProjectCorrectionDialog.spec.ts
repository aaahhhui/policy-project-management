import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { correctProjectPrimaryEntity, correctProjectStatus, type ProjectDetail } from "../../src/api/projects";
import { getPrimaryEntityHistory } from "../../src/api/evaluations";
import ProjectCorrectionDialog from "../../src/components/projects/ProjectCorrectionDialog.vue";

vi.mock("../../src/api/projects", () => ({ correctProjectStatus: vi.fn(), correctProjectPrimaryEntity: vi.fn() }));
vi.mock("../../src/api/evaluations", () => ({ getPrimaryEntityHistory: vi.fn() }));

const project = { id: 19, policy_id: 7, status: "terminated", primary_entity_decision_id: 11, submitted_on: "2026-08-01", result_on: null, result_note: null, termination_note: "材料撤回", version: 3, status_history: [{ id: 3, action: "transitioned", previous_status: "submitted", new_status: "terminated", actor: { id: 4, display_name: "联络" }, reason: null, related_date: null, before_values: {}, after_values: {}, from_version: 2, to_version: 3, occurred_at: "2026-08-04T00:00:00Z" }], capabilities: { can_correct_status: true, can_correct_primary_entity: true } } as ProjectDetail;

describe("ProjectCorrectionDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getPrimaryEntityHistory).mockResolvedValue([{ id: 12, entity_seed_code: "E-2", entity_legal_name: "当前政策企业", is_current: true }]);
  });
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

  it("sends only status-compatible correction fields", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(correctProjectStatus).mockResolvedValue(project);
    const wrapper = mount(ProjectCorrectionDialog, { props: { project, mode: "status" } });
    await wrapper.get("form").trigger("submit");
    expect(correctProjectStatus).toHaveBeenCalledWith(19, { expected_version: 3, target_status: "submitted", reason: null });
  });

  it("shows the policy's current primary candidate by name instead of requesting an opaque ID", async () => {
    vi.mocked(correctProjectPrimaryEntity).mockResolvedValue(project);
    const wrapper = mount(ProjectCorrectionDialog, { props: { project, mode: "primary-entity" } });
    await vi.dynamicImportSettled();
    expect(getPrimaryEntityHistory).toHaveBeenCalledWith(7);
    expect(wrapper.get("[data-primary-candidate]").text()).toContain("当前政策企业");
    expect(wrapper.find("[aria-label='主申报企业决定 ID']").exists()).toBe(false);
    await wrapper.get<HTMLTextAreaElement>("[aria-label='更正原因']").setValue("更换企业");
    await wrapper.get("form").trigger("submit");
    expect(correctProjectPrimaryEntity).toHaveBeenCalledWith(19, { expected_version: 3, primary_entity_decision_id: 12, reason: "更换企业" });
  });

  it("offers a reload action on a correction version conflict", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(correctProjectStatus).mockRejectedValue({ response: { data: { detail: { code: "project_version_conflict" } } } });
    const wrapper = mount(ProjectCorrectionDialog, { props: { project, mode: "status" } });
    await wrapper.get("form").trigger("submit");
    expect(wrapper.find("[data-reload-project]").exists()).toBe(true);
    await wrapper.get("[data-reload-project]").trigger("click");
    expect(wrapper.emitted("reload")).toBeTruthy();
  });
});

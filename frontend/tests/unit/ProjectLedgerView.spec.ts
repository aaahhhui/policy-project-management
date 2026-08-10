import { mount } from "@vue/test-utils";
import ElementPlus from "element-plus";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getProjectSummary, getProjects } from "../../src/api/projects";
import { clearCurrentUser, currentUser } from "../../src/auth/state";
import ProjectLedgerView from "../../src/views/ProjectLedgerView.vue";

const replace = vi.fn();
const route = { query: { status: "submitted", liaison_id: "4", page: "2" } };

vi.mock("vue-router", () => ({
  useRoute: () => route,
  useRouter: () => ({ replace }),
  RouterLink: { template: "<a><slot /></a>" },
}));
vi.mock("../../src/api/projects", () => ({
  getProjectSummary: vi.fn(),
  getProjects: vi.fn(),
}));

const page = {
  items: [{
    id: 8, policy_id: 7, name: "数字化改造项目", policy_title: "制造业数字化改造通知",
    primary_entity_seed_code: "E-1", primary_entity_legal_name: "示例企业", applicant_owner: { id: 1, display_name: "负责人" },
    liaison: { id: 4, display_name: "对接人" }, status: "submitted" as const, deadline_on: "2026-09-30",
    updated_at: "2026-08-01T10:00:00Z", version: 1,
    capabilities: { can_edit_project: false, can_update_progress: false, can_transition: false, can_correct_status: false, can_correct_primary_entity: false },
  }], page: 2, page_size: 20 as const, total: 41,
};

describe("ProjectLedgerView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearCurrentUser();
    currentUser.value = { id: 3, login_name: "reader", display_name: "Reader", roles: ["reader"] };
    route.query = { status: "submitted", liaison_id: "4", page: "2" };
    vi.mocked(getProjectSummary).mockResolvedValue({ total: 8, by_status: { submitted: 3 }, convertible_policy_count: 3 });
    vi.mocked(getProjects).mockResolvedValue(page);
  });

  it("hydrates filters from the URL, keeps projects visible to readers, and writes stable pagination", async () => {
    const wrapper = mount(ProjectLedgerView, { global: { plugins: [ElementPlus], stubs: { RouterLink: { template: "<a><slot /></a>" } } } });
    await vi.dynamicImportSettled();

    expect(getProjects).toHaveBeenCalledWith(expect.objectContaining({ status: "submitted", liaison_user_id: 4, page: 2, page_size: 20 }));
    expect(wrapper.text()).toContain("3 条政策可转项目");
    expect(wrapper.text()).toContain("数字化改造项目");
    expect(wrapper.find("[data-status-legend]").exists()).toBe(false);
    expect(wrapper.find("[data-open-project-conversion]").exists()).toBe(false);

    await wrapper.get("[aria-label='下一页']").trigger("click");
    expect(replace).toHaveBeenCalledWith({ query: { status: "submitted", liaison_id: "4", page: "3" } });
  });

  it("renders loading, error and empty states without losing the summary", async () => {
    vi.mocked(getProjects).mockRejectedValueOnce(new Error("offline"));
    const wrapper = mount(ProjectLedgerView, { global: { plugins: [ElementPlus], stubs: { RouterLink: { template: "<a><slot /></a>" } } } });
    await vi.dynamicImportSettled();
    expect(wrapper.get("[role='alert']").text()).toContain("无法加载项目台账");

    vi.mocked(getProjects).mockResolvedValueOnce({ ...page, items: [], total: 0 });
    await wrapper.get("button[data-retry-projects]").trigger("click");
    await vi.dynamicImportSettled();
    expect(wrapper.text()).toContain("没有符合条件的项目");
    expect(wrapper.text()).toContain("3 条政策可转项目");
  });
});

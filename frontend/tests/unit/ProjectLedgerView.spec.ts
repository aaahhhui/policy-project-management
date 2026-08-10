import { mount } from "@vue/test-utils";
import { nextTick, reactive } from "vue";
import ElementPlus from "element-plus";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getProjectSummary, getProjects, type ProjectPage } from "../../src/api/projects";
import { clearCurrentUser, currentUser } from "../../src/auth/state";
import ProjectCreateDrawer from "../../src/components/projects/ProjectCreateDrawer.vue";
import ProjectLedgerView from "../../src/views/ProjectLedgerView.vue";

const replace = vi.fn();
const push = vi.fn();
const route = reactive<{ query: Record<string, string> }>({ query: { status: "submitted", liaison_id: "4", page: "2" } });

vi.mock("vue-router", () => ({
  useRoute: () => route,
  useRouter: () => ({ replace, push }),
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
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 1024, writable: true });
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
    expect(wrapper.text()).toContain("共 8 个项目");
    expect(wrapper.text()).toContain("数字化改造项目");
    expect(wrapper.find("[data-status-legend]").exists()).toBe(false);
    expect(wrapper.find("[data-open-project-conversion]").exists()).toBe(false);

    await wrapper.get("[aria-label='下一页']").trigger("click");
    expect(replace).toHaveBeenCalledWith({ query: { status: "submitted", liaison_id: "4", page: "3" } });
  });

  it("canonicalizes invalid query values and reloads when browser history changes the route", async () => {
    route.query = { liaison_id: "-3", status: "unknown", page: "0", page_size: "30", extra: "drop" };
    const wrapper = mount(ProjectLedgerView, { global: { plugins: [ElementPlus], stubs: { RouterLink: { template: "<a><slot /></a>" } } } });
    await vi.dynamicImportSettled();

    expect(replace).toHaveBeenCalledWith({ query: {} });
    expect(getProjects).toHaveBeenLastCalledWith(expect.objectContaining({ liaison_user_id: undefined, status: undefined, page: 1, page_size: 20 }));

    route.query = { status: "submitted", liaison_id: "4", page: "3", page_size: "50" };
    await nextTick();
    await vi.dynamicImportSettled();
    expect(getProjects).toHaveBeenLastCalledWith(expect.objectContaining({ status: "submitted", liaison_user_id: 4, page: 3, page_size: 50 }));
    wrapper.unmount();
  });

  it("writes server-normalized page and page size back to the URL", async () => {
    route.query = { status: "submitted", liaison_id: "4", page: "8", page_size: "50" };
    vi.mocked(getProjects).mockResolvedValue({ ...page, page: 2, page_size: 10 });
    const wrapper = mount(ProjectLedgerView, { global: { plugins: [ElementPlus], stubs: { RouterLink: { template: "<a><slot /></a>" } } } });
    await vi.dynamicImportSettled();

    expect(replace).toHaveBeenCalledWith({ query: { status: "submitted", liaison_id: "4", page: "2", page_size: "10" } });
    wrapper.unmount();
  });

  it("renders total and per-status summaries, reserving conversion text for owners", async () => {
    currentUser.value = { id: 1, login_name: "owner", display_name: "Owner", roles: ["applicant_owner"] };
    const wrapper = mount(ProjectLedgerView, { global: { plugins: [ElementPlus], stubs: { RouterLink: { template: "<a><slot /></a>" }, ElDrawer: { template: "<div><slot /></div>" } } } });
    await vi.dynamicImportSettled();

    expect(wrapper.text()).toContain("共 8 个项目");
    expect(wrapper.text()).toContain("已提交 3");
    expect(wrapper.get("[data-open-project-conversion]").text()).toBe("3 条政策可转项目");
    currentUser.value = { id: 3, login_name: "reader", display_name: "Reader", roles: ["reader"] };
    await nextTick();
    expect(wrapper.text()).not.toContain("3 条政策可转项目");
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
    expect(wrapper.text()).toContain("共 8 个项目");
  });

  it("distinguishes an unfiltered empty ledger and allows summary-load retry", async () => {
    route.query = {};
    vi.mocked(getProjectSummary).mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({ total: 0, by_status: {}, convertible_policy_count: 0 });
    vi.mocked(getProjects).mockResolvedValue({ ...page, items: [], total: 0, page: 1 });
    const wrapper = mount(ProjectLedgerView, { global: { plugins: [ElementPlus], stubs: { RouterLink: { template: "<a><slot /></a>" } } } });
    await vi.dynamicImportSettled();

    expect(wrapper.text()).toContain("暂无项目");
    expect(wrapper.get("[data-retry-project-summary]").attributes("aria-label")).toBe("重试加载项目汇总");
    await wrapper.get("[data-retry-project-summary]").trigger("click");
    await vi.dynamicImportSettled();
    expect(wrapper.text()).toContain("共 0 个项目");
  });

  it("keeps an owner conversion action available when the summary fails", async () => {
    currentUser.value = { id: 1, login_name: "owner", display_name: "Owner", roles: ["applicant_owner"] };
    vi.mocked(getProjectSummary).mockRejectedValueOnce(new Error("offline"));
    const wrapper = mount(ProjectLedgerView, { global: { plugins: [ElementPlus], stubs: { RouterLink: { template: "<a><slot /></a>" }, ElDrawer: { template: "<div><slot /></div>" } } } });
    await vi.dynamicImportSettled();

    expect(wrapper.find("[data-retry-project-summary]").exists()).toBe(true);
    expect(wrapper.get("[data-open-project-conversion]").text()).toBe("将政策转为项目");
  });

  it("closes an open drawer and suppresses conversion controls at the 720px breakpoint", async () => {
    currentUser.value = { id: 1, login_name: "owner", display_name: "Owner", roles: ["applicant_owner"] };
    const wrapper = mount(ProjectLedgerView, { global: { plugins: [ElementPlus], stubs: { RouterLink: { template: "<a><slot /></a>" }, ElDrawer: { template: "<div><slot /></div>" } } } });
    await vi.dynamicImportSettled();
    await wrapper.get("[data-open-project-conversion]").trigger("click");
    expect(wrapper.findComponent(ProjectCreateDrawer).props("open")).toBe(true);

    window.innerWidth = 720;
    window.dispatchEvent(new Event("resize"));
    await nextTick();
    expect(wrapper.find("[data-open-project-conversion]").exists()).toBe(false);
    expect(wrapper.findComponent(ProjectCreateDrawer).exists()).toBe(false);
  });

  it("navigates after project creation", async () => {
    currentUser.value = { id: 1, login_name: "owner", display_name: "Owner", roles: ["applicant_owner"] };
    const wrapper = mount(ProjectLedgerView, { global: { plugins: [ElementPlus], stubs: { RouterLink: { template: "<a><slot /></a>" }, ElDrawer: { template: "<div><slot /></div>" } } } });
    await vi.dynamicImportSettled();
    wrapper.findComponent(ProjectCreateDrawer).vm.$emit("created", 19);
    await nextTick();
    expect(push).toHaveBeenCalledWith("/projects/19");
  });

  it("does not let a response resolve into a destroyed ledger", async () => {
    route.query = { status: "submitted", liaison_id: "4", page: "8", page_size: "50" };
    await nextTick();
    vi.clearAllMocks();
    let resolvePage: (value: ProjectPage) => void;
    vi.mocked(getProjects).mockImplementationOnce(() => new Promise<ProjectPage>((resolve) => { resolvePage = resolve; }));
    const wrapper = mount(ProjectLedgerView, { global: { plugins: [ElementPlus], stubs: { RouterLink: { template: "<a><slot /></a>" } } } });
    await nextTick();
    wrapper.unmount();
    vi.clearAllMocks();
    resolvePage!({ ...page, page: 2, page_size: 10 });
    await vi.dynamicImportSettled();

    expect(replace).not.toHaveBeenCalled();
  });
});

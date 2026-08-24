import { mount } from "@vue/test-utils";
import ElementPlus from "element-plus";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createSource, disableSource, enableSource, getSources, retrySourceRecognition, type PolicySource } from "../../src/api/sources";
import { clearCurrentUser, currentUser } from "../../src/auth/state";
import PolicySourcesView from "../../src/views/PolicySourcesView.vue";

vi.mock("../../src/api/sources", () => ({
  getSources: vi.fn(), createSource: vi.fn(), retrySourceRecognition: vi.fn(), enableSource: vi.fn(), disableSource: vi.fn(),
}));

function setViewportWidth(width: number): void {
  const query = "(max-width: 720px)";
  Object.defineProperty(window, "matchMedia", { configurable: true, value: vi.fn().mockImplementation((value: string) => ({
    matches: value === query && width <= 720, media: value, addEventListener: vi.fn(), removeEventListener: vi.fn(),
  })) });
}

const baseSource: PolicySource = {
  id: 1, name: "广东省科技业务管理阳光政务平台", entry_url: "https://public.example/guangdong", region_labels: ["广东"], topic_labels: ["科技"],
  recognition_status: "recognizing", recognition_kind: null, recognition_summary: "正在核验公开入口。", previewed_at: null, owner_confirmed_at: null,
  enabled_at: null, disabled_at: null, version: 3, latest_collection_at: null, latest_result: null,
};

function page(items: PolicySource[], pageNumber = 1, total = items.length) { return { items, page: pageNumber, page_size: 20, total }; }
function mountView() { return mount(PolicySourcesView, { global: { plugins: [ElementPlus] } }); }

describe("PolicySourcesView", () => {
  beforeEach(() => {
    vi.clearAllMocks(); clearCurrentUser();
    currentUser.value = { id: 1, login_name: "owner", display_name: "负责人", roles: ["applicant_owner"] };
    setViewportWidth(1024);
  });

  it("renders business lifecycle labels and keeps recognition summaries as text", async () => {
    vi.mocked(getSources).mockResolvedValue(page([
      baseSource, { ...baseSource, id: 2, recognition_status: "ready_to_enable", recognition_summary: "广东省科技业务管理阳光政务平台" },
      { ...baseSource, id: 3, recognition_status: "enabled" }, { ...baseSource, id: 4, recognition_status: "pending_verification" },
      { ...baseSource, id: 5, recognition_status: "rejected", recognition_summary: "<strong>入口无法使用</strong>" }, { ...baseSource, id: 6, recognition_status: "disabled" },
    ]));
    const wrapper = mountView(); await vi.dynamicImportSettled();
    for (const label of ["识别中", "可启用", "已启用", "待人工确认", "无法使用", "已停用"]) expect(wrapper.text()).toContain(label);
    expect(wrapper.text()).toContain("<strong>入口无法使用</strong>");
    expect(wrapper.find("strong").exists()).toBe(false);
  });

  it("shows safe preview and enable only for a ready source", async () => {
    const ready = { ...baseSource, name: "Feed", recognition_status: "ready_to_enable" as const, recognition_summary: "广东省科技业务管理阳光政务平台" };
    vi.mocked(getSources).mockResolvedValue(page([ready])); vi.mocked(enableSource).mockResolvedValue({ ...ready, recognition_status: "enabled", version: 4 });
    const wrapper = mountView(); await vi.dynamicImportSettled();
    expect(wrapper.text()).toContain("预览：广东省科技业务管理阳光政务平台");
    await wrapper.get("button[aria-label='启用 Feed']").trigger("click");
    expect(enableSource).toHaveBeenCalledWith(1, 3); expect(wrapper.text()).toContain("已启用");
  });

  it("offers retry only for pending or rejected sources and disable only for enabled sources", async () => {
    vi.mocked(getSources).mockResolvedValue(page([
      { ...baseSource, id: 2, name: "待确认", recognition_status: "pending_verification" }, { ...baseSource, id: 3, name: "无法识别", recognition_status: "rejected" },
      { ...baseSource, id: 4, name: "已启用来源", recognition_status: "enabled" }, { ...baseSource, id: 5, name: "识别中来源", recognition_status: "recognizing" },
    ]));
    const wrapper = mountView(); await vi.dynamicImportSettled();
    expect(wrapper.find("button[aria-label='重新识别 待确认']").exists()).toBe(true);
    expect(wrapper.find("button[aria-label='重新识别 无法识别']").exists()).toBe(true);
    expect(wrapper.find("button[aria-label='停用 已启用来源']").exists()).toBe(true);
    expect(wrapper.find("button[aria-label='启用 识别中来源']").exists()).toBe(false);
    expect(wrapper.find("button[aria-label='停用 识别中来源']").exists()).toBe(false);
    expect(wrapper.find("button[aria-label='立即采集 已启用来源']").exists()).toBe(false);
  });

  it("reloads page two through getSources", async () => {
    vi.mocked(getSources).mockResolvedValueOnce(page([{ ...baseSource, name: "第一页来源" }], 1, 21)).mockResolvedValueOnce(page([{ ...baseSource, id: 2, name: "第二页来源" }], 2, 21));
    const wrapper = mountView(); await vi.dynamicImportSettled(); await wrapper.get("button[aria-label='下一页来源']").trigger("click"); await vi.dynamicImportSettled();
    expect(getSources).toHaveBeenNthCalledWith(1, 1, 20); expect(getSources).toHaveBeenNthCalledWith(2, 2, 20); expect(wrapper.text()).toContain("第二页来源");
  });

  it("gives reload guidance for a version conflict without reapplying a stale enable", async () => {
    const ready = { ...baseSource, name: "Feed", recognition_status: "ready_to_enable" as const };
    vi.mocked(getSources).mockResolvedValue(page([ready]));
    vi.mocked(enableSource).mockRejectedValue({ response: { status: 409, data: { detail: { code: "source_version_conflict", current_version: 4 } } } });
    const wrapper = mountView(); await vi.dynamicImportSettled(); await wrapper.get("button[aria-label='启用 Feed']").trigger("click"); await vi.dynamicImportSettled();
    expect(enableSource).toHaveBeenCalledTimes(1); expect(getSources).toHaveBeenCalledTimes(1);
    expect(wrapper.get("[role='alert']").text()).toContain("来源已被更新，请重新加载后再操作");
  });

  it("keeps mobile source status, preview, and history but hides every mutation control", async () => {
    setViewportWidth(640);
    const ready = { ...baseSource, recognition_status: "ready_to_enable" as const, recognition_summary: "广东省科技业务管理阳光政务平台", latest_collection_at: "2026-08-20T08:00:00Z", latest_result: "succeeded" };
    vi.mocked(getSources).mockResolvedValue(page([ready]));
    const wrapper = mountView(); await vi.dynamicImportSettled();
    expect(wrapper.text()).toContain("可启用"); expect(wrapper.text()).toContain("预览：广东省科技业务管理阳光政务平台"); expect(wrapper.text()).toContain("最近采集");
    for (const label of ["添加政策来源", "重新识别", "启用 Feed", "停用"]) expect(wrapper.find(`button[aria-label*='${label}']`).exists()).toBe(false);
  });

  it("keeps a reader read-only on desktop", async () => {
    currentUser.value = { id: 2, login_name: "reader", display_name: "阅读者", roles: ["reader"] };
    vi.mocked(getSources).mockResolvedValue(page([{ ...baseSource, recognition_status: "enabled" }]));
    const wrapper = mountView(); await vi.dynamicImportSettled();
    expect(wrapper.text()).toContain("已启用"); expect(wrapper.find("button").exists()).toBe(false);
  });

  it("reloads after recognition retry without a hidden automatic stale action", async () => {
    vi.mocked(getSources).mockResolvedValue(page([{ ...baseSource, recognition_status: "pending_verification" }]));
    vi.mocked(retrySourceRecognition).mockResolvedValue({ ...baseSource, recognition_status: "recognizing", version: 4 });
    const wrapper = mountView(); await vi.dynamicImportSettled();
    await wrapper.get("button[aria-label='重新识别 广东省科技业务管理阳光政务平台']").trigger("click"); await vi.dynamicImportSettled();
    expect(retrySourceRecognition).toHaveBeenCalledWith(1); expect(getSources).toHaveBeenCalledTimes(2); expect(createSource).not.toHaveBeenCalled();
  });
});

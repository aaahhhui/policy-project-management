import { mount } from "@vue/test-utils";
import ElementPlus from "element-plus";
import { describe, expect, it, vi } from "vitest";

import { createSource, getSources, toggleSource } from "../../src/api/sources";
import PolicySourcesView from "../../src/views/PolicySourcesView.vue";

vi.mock("../../src/api/sources", () => ({
  getSources: vi.fn(),
  createSource: vi.fn(),
  updateSource: vi.fn(),
  toggleSource: vi.fn(),
}));

const pendingSource = {
  id: 1,
  name: "Custom source",
  home_url: "https://example.com",
  adapter_status: "pending" as const,
  is_enabled: true,
  created_by: 1,
  updated_by: 1,
  channels: [],
  latest_collection_at: null,
  latest_result: null,
};

describe("PolicySourcesView", () => {
  it("makes a pending adaptation unmistakable without rendering a collection control", async () => {
    vi.mocked(getSources).mockResolvedValue([pendingSource]);
    const wrapper = mount(PolicySourcesView, { global: { plugins: [ElementPlus] } });

    await vi.dynamicImportSettled();

    expect(wrapper.get("h1").text()).toBe("政策来源");
    expect(wrapper.text()).toContain("待适配");
    expect(wrapper.text()).not.toContain("立即采集");
    expect(wrapper.find("button[aria-label*='立即采集']").exists()).toBe(false);
  });

  it("shows loading, an actionable loading error, and an empty-state invitation", async () => {
    let resolveSources: (value: typeof pendingSource[]) => void;
    vi.mocked(getSources).mockReturnValue(
      new Promise((resolve) => {
        resolveSources = resolve;
      }),
    );
    const wrapper = mount(PolicySourcesView, { global: { plugins: [ElementPlus] } });
    expect(wrapper.get("[role=status]").text()).toContain("正在加载");

    resolveSources!([]);
    await vi.dynamicImportSettled();
    expect(wrapper.get("[data-testid='empty-sources']").text()).toContain("添加来源");
    wrapper.unmount();

    vi.mocked(getSources).mockReset();
    vi.mocked(getSources).mockRejectedValue(new Error("network"));
    const errorWrapper = mount(PolicySourcesView, { global: { plugins: [ElementPlus] } });
    await vi.dynamicImportSettled();
    expect(errorWrapper.get("[role=alert]").text()).toContain("无法加载政策来源");
  });

  it("creates an enabled source without offering or serializing an ignored enabled choice", async () => {
    vi.mocked(getSources).mockResolvedValue([]);
    vi.mocked(createSource).mockResolvedValue(pendingSource);
    const wrapper = mount(PolicySourcesView, { attachTo: document.body, global: { plugins: [ElementPlus] } });
    await vi.dynamicImportSettled();

    await wrapper.get("button[aria-label='添加政策来源']").trigger("click");
    expect(document.body.querySelector("[role=dialog] h2")?.textContent).toContain("添加政策来源");
    expect(document.body.querySelector("label[for='source-name']")?.textContent).toContain("来源名称");
    expect(document.body.querySelector("button[aria-label='添加栏目']")).not.toBeNull();
    expect(document.body.querySelector("label[for='source-enabled']")).toBeNull();

    const name = document.body.querySelector("#source-name") as HTMLInputElement;
    const homeUrl = document.body.querySelector("#source-home-url") as HTMLInputElement;
    name.value = "Created source";
    homeUrl.value = "https://created.example";
    name.dispatchEvent(new Event("input"));
    homeUrl.dispatchEvent(new Event("input"));
    document.body.querySelector(".source-form")?.dispatchEvent(new Event("submit", { cancelable: true }));
    await vi.dynamicImportSettled();

    expect(createSource).toHaveBeenCalledWith({
      name: "Created source",
      home_url: "https://created.example",
      channels: [],
    });
    wrapper.unmount();
  });

  it.each([
    [409, "该来源名称已存在"],
    [422, "名称、官网地址或栏目内容不符合要求"],
  ])("maps a source save response with status %s to a useful form error", async (status, message) => {
    vi.mocked(getSources).mockResolvedValue([]);
    vi.mocked(createSource).mockRejectedValue({ response: { status } });
    const wrapper = mount(PolicySourcesView, { attachTo: document.body, global: { plugins: [ElementPlus] } });
    await vi.dynamicImportSettled();

    await wrapper.get("button[aria-label='添加政策来源']").trigger("click");
    const name = document.body.querySelector("#source-name") as HTMLInputElement;
    const homeUrl = document.body.querySelector("#source-home-url") as HTMLInputElement;
    name.value = "Created source";
    homeUrl.value = "https://created.example";
    name.dispatchEvent(new Event("input"));
    homeUrl.dispatchEvent(new Event("input"));
    document.body.querySelector(".source-form")?.dispatchEvent(new Event("submit", { cancelable: true }));
    await vi.dynamicImportSettled();

    expect(document.body.querySelector("[role=dialog] [role=alert]")?.textContent).toContain(message);
    wrapper.unmount();
  });

  it("issues one toggle request while a row is pending and restores its controls on success", async () => {
    vi.mocked(getSources).mockResolvedValue([pendingSource]);
    let resolveToggle: (value: typeof pendingSource) => void;
    vi.mocked(toggleSource).mockReturnValue(
      new Promise((resolve) => {
        resolveToggle = resolve;
      }),
    );
    const wrapper = mount(PolicySourcesView, { global: { plugins: [ElementPlus] } });
    await vi.dynamicImportSettled();

    const [edit, toggle] = wrapper.findAll(".actions button");
    await toggle.trigger("click");
    await toggle.trigger("click");
    expect(toggleSource).toHaveBeenCalledTimes(1);
    expect(edit.attributes("disabled")).toBeDefined();
    expect(toggle.attributes("disabled")).toBeDefined();

    resolveToggle!(pendingSource);
    await vi.waitFor(() => {
      const [restoredEdit, restoredToggle] = wrapper.findAll(".actions button");
      expect(restoredEdit.attributes("disabled")).toBeUndefined();
      expect(restoredToggle.attributes("disabled")).toBeUndefined();
    });
  });

  it("restores row controls and shows an error after a toggle failure", async () => {
    vi.mocked(getSources).mockResolvedValue([pendingSource]);
    vi.mocked(toggleSource).mockRejectedValue(new Error("network"));
    const wrapper = mount(PolicySourcesView, { global: { plugins: [ElementPlus] } });
    await vi.dynamicImportSettled();

    const [edit, toggle] = wrapper.findAll(".actions button");
    await toggle.trigger("click");
    await vi.dynamicImportSettled();

    expect(edit.attributes("disabled")).toBeUndefined();
    expect(toggle.attributes("disabled")).toBeUndefined();
    expect(wrapper.get("[role=alert]").text()).toContain("无法更新来源状态");
  });
});

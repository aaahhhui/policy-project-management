import { mount } from "@vue/test-utils";
import ElementPlus from "element-plus";
import { describe, expect, it, vi } from "vitest";

import { getPolicies, getPolicySourceOptions } from "../../src/api/policies";
import PolicyCenterView from "../../src/views/PolicyCenterView.vue";

const replace = vi.fn();
vi.mock("vue-router", () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ replace }),
  RouterLink: { template: "<a><slot /></a>" },
}));
vi.mock("../../src/api/policies", () => ({
  getPolicies: vi.fn(),
  getPolicySourceOptions: vi.fn(),
}));

describe("PolicyCenterView", () => {
  it("renders the compact policy columns and writes filters to the URL", async () => {
    vi.mocked(getPolicySourceOptions).mockResolvedValue([{ id: 3, name: "广东省工业和信息化厅" }]);
    vi.mocked(getPolicies).mockResolvedValue({
      items: [{
        id: 8,
        title: "制造业数字化转型项目申报通知",
        document_number: "粤工信〔2026〕8号",
        published_on: "2026-07-20",
        deadline_on: "2026-08-20",
        current_conclusion: "pending_confirmation",
        conclusion_confirmed: false,
        converted_to_project: false,
        project_id: null,
        project_name: null,
        sources: ["广东省工业和信息化厅"],
      }],
      page: 1,
      page_size: 20,
      total: 1,
    });
    const wrapper = mount(PolicyCenterView, {
      global: {
        plugins: [ElementPlus],
        stubs: { RouterLink: { template: "<a><slot /></a>" } },
      },
    });
    await vi.dynamicImportSettled();

    expect(wrapper.text()).toContain("政策名称");
    expect(wrapper.text()).toContain("发布日期");
    expect(wrapper.text()).toContain("申报截止日期");
    expect(wrapper.text()).toContain("来源");
    expect(wrapper.text()).toContain("当前结论");
    expect(wrapper.text()).toContain("制造业数字化转型项目申报通知");

    await wrapper.get("input[aria-label='搜索政策']").setValue("数字化");
    await wrapper.get("form").trigger("submit");
    expect(replace).toHaveBeenCalledWith({ query: { q: "数字化" } });
  });
});

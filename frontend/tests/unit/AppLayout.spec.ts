import { mount } from "@vue/test-utils";
import ElementPlus from "element-plus";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";

import { logout } from "../../src/api/auth";
import { clearCurrentUser, currentUser } from "../../src/auth/state";
import AppLayout from "../../src/layouts/AppLayout.vue";

vi.mock("../../src/api/auth", () => ({ logout: vi.fn() }));

describe("AppLayout", () => {
  beforeEach(() => {
    clearCurrentUser();
    currentUser.value = {
      id: 1,
      login_name: "owner",
      display_name: "Owner",
      roles: ["applicant_owner"],
    };
    vi.clearAllMocks();
  });

  it("keeps the session visible and offers retry feedback when logout fails", async () => {
    vi.mocked(logout).mockRejectedValue(new Error("unavailable"));
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/", component: AppLayout },
        { path: "/profile", component: { template: "<div />" } },
        { path: "/policies", component: { template: "<div />" } },
        { path: "/evaluation-rules", component: { template: "<div />" } },
        { path: "/sources", component: { template: "<div />" } },
        { path: "/projects", component: { template: "<div />" } },
      ],
    });
    const wrapper = mount(AppLayout, { global: { plugins: [router, ElementPlus] } });

    await wrapper.get("button").trigger("click");

    expect(wrapper.text()).toContain("退出失败，请重试");
    expect(wrapper.text()).toContain("退出登录");
  });

  it("shows the project ledger link to both owners and readers", () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/", component: AppLayout },
        { path: "/policies", component: { template: "<div />" } },
        { path: "/projects", component: { template: "<div />" } },
        { path: "/evaluation-rules", component: { template: "<div />" } },
        { path: "/sources", component: { template: "<div />" } },
        { path: "/profile", component: { template: "<div />" } },
      ],
    });

    for (const roles of [["applicant_owner"], ["reader"]]) {
      currentUser.value = { id: 1, login_name: "user", display_name: "User", roles };
      const wrapper = mount(AppLayout, { global: { plugins: [router, ElementPlus] } });

      expect(wrapper.get("nav").text()).toContain("项目台账");
      expect(wrapper.find('a[href="/projects"]').exists()).toBe(true);
      wrapper.unmount();
    }
  });
});

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
        { path: "/sources", component: { template: "<div />" } },
      ],
    });
    const wrapper = mount(AppLayout, { global: { plugins: [router, ElementPlus] } });

    await wrapper.get("button").trigger("click");

    expect(wrapper.text()).toContain("退出失败，请重试");
    expect(wrapper.text()).toContain("退出登录");
  });
});

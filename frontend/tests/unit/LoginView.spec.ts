import { mount } from "@vue/test-utils";
import ElementPlus from "element-plus";
import { describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";

import { login } from "../../src/api/auth";
import LoginView from "../../src/views/LoginView.vue";

vi.mock("../../src/api/auth", () => ({
  login: vi.fn(),
  isUnauthorizedError: (error: unknown) =>
    typeof error === "object" && error !== null && "response" in error
      ? (error.response as { status?: number }).status === 401
      : false,
}));

function testRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/", component: { template: "<div />" } }],
  });
}

describe("LoginView", () => {
  it("submits credentials and directs an authenticated user to the application", async () => {
    vi.mocked(login).mockResolvedValue();
    const router = testRouter();
    const wrapper = mount(LoginView, { global: { plugins: [router, ElementPlus] } });

    await wrapper.get('input[autocomplete="username"]').setValue("owner");
    await wrapper.get('input[autocomplete="current-password"]').setValue("password");
    await wrapper.get("form").trigger("submit");

    expect(login).toHaveBeenCalledWith({ login_name: "owner", password: "password" });
    expect(router.currentRoute.value.fullPath).toBe("/");
  });

  it("shows a credential error only for a 401 response", async () => {
    vi.mocked(login).mockRejectedValue(
      Object.assign(new Error("rejected"), { response: { status: 401 } }),
    );
    const wrapper = mount(LoginView, {
      global: { plugins: [testRouter(), ElementPlus] },
    });

    await wrapper.get("form").trigger("submit");

    expect(wrapper.text()).toContain("账号或密码错误");
  });

  it("shows a service-unavailable message for network or server failures", async () => {
    vi.mocked(login).mockRejectedValue(
      Object.assign(new Error("unavailable"), { response: { status: 503 } }),
    );
    const wrapper = mount(LoginView, {
      global: { plugins: [testRouter(), ElementPlus] },
    });

    await wrapper.get("form").trigger("submit");

    expect(wrapper.text()).toContain("服务暂时不可用，请稍后重试");
  });
});

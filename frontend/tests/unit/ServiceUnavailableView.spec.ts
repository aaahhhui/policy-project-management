import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { createMemoryHistory } from "vue-router";

import type { CurrentUser } from "../../src/api/auth";
import { createPolicyRouter } from "../../src/router";
import ServiceUnavailableView from "../../src/views/ServiceUnavailableView.vue";

const owner: CurrentUser = {
  id: 1,
  login_name: "owner",
  display_name: "Owner",
  roles: ["applicant_owner"],
};

describe("ServiceUnavailableView", () => {
  it("retries the protected route that failed session confirmation", async () => {
    const router = createPolicyRouter({
      history: createMemoryHistory(),
      loadCurrentUser: async () => owner,
    });
    await router.push("/service-unavailable?retry=%2Fsources");
    const wrapper = mount(ServiceUnavailableView, { global: { plugins: [router] } });

    await wrapper.get("button").trigger("click");
    await flushPromises();

    expect(router.currentRoute.value.fullPath).toBe("/sources");
  });

  it("falls back to the workbench instead of accepting an external retry target", async () => {
    const router = createPolicyRouter({
      history: createMemoryHistory(),
      loadCurrentUser: async () => owner,
    });
    await router.push("/service-unavailable?retry=https%3A%2F%2Fevil.example");
    const wrapper = mount(ServiceUnavailableView, { global: { plugins: [router] } });

    await wrapper.get("button").trigger("click");
    await flushPromises();

    expect(router.currentRoute.value.fullPath).toBe("/");
  });
});

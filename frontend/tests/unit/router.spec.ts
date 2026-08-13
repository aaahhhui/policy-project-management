import { describe, expect, it } from "vitest";
import { createMemoryHistory } from "vue-router";

import type { CurrentUser } from "../../src/api/auth";
import { createPolicyRouter } from "../../src/router";

const owner: CurrentUser = {
  id: 1,
  login_name: "owner",
  display_name: "Owner",
  roles: ["applicant_owner"],
};
const reader: CurrentUser = { ...owner, id: 2, login_name: "reader", roles: ["reader"] };

describe("policy router", () => {
  it("allows an owner to navigate directly to policy sources", async () => {
    const router = createPolicyRouter({
      history: createMemoryHistory(),
      loadCurrentUser: async () => owner,
    });

    await router.push("/sources");

    expect(router.currentRoute.value.name).toBe("sources");
  });

  it("redirects a reader away from direct policy-source navigation", async () => {
    const router = createPolicyRouter({
      history: createMemoryHistory(),
      loadCurrentUser: async () => reader,
    });

    await router.push("/sources");

    expect(router.currentRoute.value.name).toBe("home");
  });

  it("allows both owners and readers to view evaluation rules", async () => {
    for (const user of [owner, reader]) {
      const router = createPolicyRouter({
        history: createMemoryHistory(),
        loadCurrentUser: async () => user,
      });

      await router.push("/evaluation-rules");

      expect(router.currentRoute.value.name).toBe("evaluation-rules");
    }
  });

  it("allows only an owner to open notification records", async () => {
    for (const [user, expected] of [[owner, "notifications"], [reader, "home"]] as const) {
      const router = createPolicyRouter({
        history: createMemoryHistory(),
        loadCurrentUser: async () => user,
      });

      await router.push("/notifications");

      expect(router.currentRoute.value.name).toBe(expected);
    }
  });

  it("allows every authenticated role to view the project ledger and detail", async () => {
    for (const user of [owner, reader]) {
      const router = createPolicyRouter({ history: createMemoryHistory(), loadCurrentUser: async () => user });

      await router.push("/projects");
      expect(router.currentRoute.value.name).toBe("projects");
      await router.push("/projects/8");
      expect(router.currentRoute.value.name).toBe("project-detail");
    }
  });

  it("redirects unauthenticated project access to login", async () => {
    const unauthorized = Object.assign(new Error("unauthorized"), { response: { status: 401 } });
    const router = createPolicyRouter({
      history: createMemoryHistory(),
      loadCurrentUser: async () => Promise.reject(unauthorized),
    });

    await router.push("/projects/8");

    expect(router.currentRoute.value.name).toBe("login");
    expect(router.currentRoute.value.query.redirect).toBe("/projects/8");
  });

  it("redirects only 401 session failures to login", async () => {
    const unauthorized = Object.assign(new Error("unauthorized"), { response: { status: 401 } });
    const router = createPolicyRouter({
      history: createMemoryHistory(),
      loadCurrentUser: async () => Promise.reject(unauthorized),
    });

    await router.push("/");

    expect(router.currentRoute.value.name).toBe("login");
  });

  it("routes service failures to a readable public fallback instead of login", async () => {
    const unavailable = Object.assign(new Error("unavailable"), { response: { status: 503 } });
    const router = createPolicyRouter({
      history: createMemoryHistory(),
      loadCurrentUser: async () => Promise.reject(unavailable),
    });

    await router.push("/sources");

    expect(router.currentRoute.value.name).toBe("service-unavailable");
    expect(router.currentRoute.value.matched).toHaveLength(1);
    expect(router.currentRoute.value.query.retry).toBe("/sources");
  });

  it("routes project service failures to the existing unavailable page", async () => {
    const unavailable = Object.assign(new Error("unavailable"), { response: { status: 503 } });
    const router = createPolicyRouter({
      history: createMemoryHistory(),
      loadCurrentUser: async () => Promise.reject(unavailable),
    });

    await router.push("/projects");

    expect(router.currentRoute.value.name).toBe("service-unavailable");
    expect(router.currentRoute.value.query.retry).toBe("/projects");
  });
});

import { createRouter, createWebHistory, type RouterHistory } from "vue-router";

import type { CurrentUser } from "../api/auth";
import { loadCurrentUser } from "../auth/state";
import { isUnauthorizedError } from "../api/auth";
import AppLayout from "../layouts/AppLayout.vue";
import LoginView from "../views/LoginView.vue";
import ServiceUnavailableView from "../views/ServiceUnavailableView.vue";
import EnterpriseProfileView from "../views/EnterpriseProfileView.vue";
import PolicySourcesView from "../views/PolicySourcesView.vue";
import PolicyCenterView from "../views/PolicyCenterView.vue";
import PolicyDetailView from "../views/PolicyDetailView.vue";
import EvaluationRulesView from "../views/EvaluationRulesView.vue";
import EvaluationRuleDetailView from "../views/EvaluationRuleDetailView.vue";
import ProjectLedgerView from "../views/ProjectLedgerView.vue";
import ProjectDetailView from "../views/ProjectDetailView.vue";
import NotificationRecordsView from "../views/NotificationRecordsView.vue";
import { isSafeReturnPath } from "./safeReturn";

type RouterOptions = {
  history?: RouterHistory;
  loadCurrentUser?: () => Promise<CurrentUser>;
};

export function createPolicyRouter(options: RouterOptions = {}) {
  const router = createRouter({
    history: options.history ?? createWebHistory(),
    routes: [
      { path: "/login", name: "login", component: LoginView, meta: { public: true } },
      {
        path: "/service-unavailable",
        name: "service-unavailable",
        component: ServiceUnavailableView,
        meta: { public: true },
      },
      {
        path: "/",
        component: AppLayout,
        children: [
          { path: "", name: "home", component: { template: "<section>工作台</section>" } },
          { path: "profile", name: "enterprise-profile", component: EnterpriseProfileView },
          { path: "policies", name: "policies", component: PolicyCenterView },
          { path: "policies/:id", name: "policy-detail", component: PolicyDetailView },
          { path: "projects", name: "projects", component: ProjectLedgerView },
          { path: "projects/:id", name: "project-detail", component: ProjectDetailView },
          {
            path: "notifications",
            name: "notifications",
            component: NotificationRecordsView,
            meta: { requiredRole: "applicant_owner" },
          },
          { path: "evaluation-rules", name: "evaluation-rules", component: EvaluationRulesView },
          { path: "evaluation-rules/:id", name: "evaluation-rule-detail", component: EvaluationRuleDetailView },
          {
            path: "sources",
            name: "sources",
            component: PolicySourcesView,
            meta: { requiredRole: "applicant_owner" },
          },
        ],
      },
    ],
  });
  const getUser = options.loadCurrentUser ?? loadCurrentUser;

  router.beforeEach(async (to) => {
    if (to.meta.public) return true;
    try {
      const user = await getUser();
      const requiredRole = to.meta.requiredRole;
      if (typeof requiredRole === "string" && !user.roles.includes(requiredRole)) {
        return { name: "home" };
      }
      return true;
    } catch (error) {
      if (isUnauthorizedError(error)) {
        return {
          name: "login",
          query: { redirect: isSafeReturnPath(to.fullPath) ? to.fullPath : "/" },
        };
      }
      return {
        name: "service-unavailable",
        query: { retry: isSafeReturnPath(to.fullPath) ? to.fullPath : "/" },
      };
    }
  });
  return router;
}

export default createPolicyRouter();

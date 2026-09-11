import { beforeEach, describe, expect, it, vi } from "vitest";

const { http } = vi.hoisted(() => ({
  http: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}));

vi.mock("../../src/api/http", () => ({ default: http }));

import {
  correctProjectPrimaryEntity,
  correctProjectStatus,
  createProjectFromPolicy,
  getConvertiblePolicies,
  getProject,
  getProjectSummary,
  getProjectUserOptions,
  getProjects,
  transitionProject,
  updateProject,
} from "../../src/api/projects";
import { businessErrorMessage, getBusinessErrorCode } from "../../src/api/errors";

describe("project API contract", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    http.get.mockResolvedValue({ data: { ok: true } });
    http.post.mockResolvedValue({ data: { ok: true } });
    http.patch.mockResolvedValue({ data: { ok: true } });
  });

  it("uses the project read endpoints with their exact query parameters", async () => {
    await getProjectSummary();
    await getProjects({ q: "digital", status: "submitted", page: 2, page_size: 50, mine: true });
    await getProject(9);
    await getConvertiblePolicies(3, 10);
    await getProjectUserOptions();

    expect(http.get).toHaveBeenNthCalledWith(1, "/projects/summary");
    expect(http.get).toHaveBeenNthCalledWith(2, "/projects", {
      params: { q: "digital", status: "submitted", page: 2, page_size: 50, mine: true },
    });
    expect(http.get).toHaveBeenNthCalledWith(3, "/projects/9");
    expect(http.get).toHaveBeenNthCalledWith(4, "/policies/convertible", { params: { page: 3, page_size: 10 } });
    expect(http.get).toHaveBeenNthCalledWith(5, "/users/project-options");
  });

  it("uses the conversion endpoint with its idempotency key", async () => {
    const payload = { liaison_user_id: 4, member_user_ids: [5], deadline_on: "2026-09-30" };

    await createProjectFromPolicy(7, payload, "project-key-2026");

    expect(http.post).toHaveBeenCalledWith("/policies/7/project", payload, {
      headers: { "Idempotency-Key": "project-key-2026" },
    });
  });

  it("uses the project write endpoints with unmodified payloads", async () => {
    const update = { expected_version: 2, name: "New name", progress_note: "Working" };
    const transition = { expected_version: 3, target_status: "submitted" as const, submitted_on: "2026-08-01" };
    const correction = { ...transition, reason: "Corrected entry" };
    const entityCorrection = { expected_version: 4, primary_entity_decision_id: 12, reason: "Entity correction" };

    await updateProject(8, update);
    await transitionProject(8, transition);
    await correctProjectStatus(8, correction);
    await correctProjectPrimaryEntity(8, entityCorrection);

    expect(http.patch).toHaveBeenCalledWith("/projects/8", update);
    expect(http.post).toHaveBeenNthCalledWith(1, "/projects/8/transitions", transition);
    expect(http.post).toHaveBeenNthCalledWith(2, "/projects/8/corrections", correction);
    expect(http.post).toHaveBeenNthCalledWith(3, "/projects/8/primary-entity-corrections", entityCorrection);
  });

  it("maps every Stage 3 business code to actionable Chinese copy", () => {
    const cases: Array<[string, number, string]> = [
      ["policy_not_convertible", 422, "当前政策不满足转项目条件，请刷新政策详情。"],
      ["policy_already_converted", 409, "该政策已转为项目，请打开现有项目。"],
      ["primary_entity_missing", 422, "当前政策缺少主申报企业，暂不能转为项目。"],
      ["project_liaison_required", 422, "请选择项目对接人。"],
      ["project_user_inactive", 422, "所选项目用户已停用，请重新选择。"],
      ["project_write_forbidden", 403, "你没有权限修改这个项目。"],
      ["project_transition_invalid", 422, "当前状态不能执行这次变更。"],
      ["project_correction_invalid", 422, "当前状态不能执行这次更正。"],
      ["project_field_validation_failed", 422, "项目字段填写不符合要求，请检查后重试。"],
      ["project_version_conflict", 409, "项目已被他人更新，请重新加载后再操作。"],
      ["idempotency_key_reused", 409, "该创建请求已被使用，请刷新后重试。"],
    ];

    for (const [code, status, message] of cases) {
      const detail = code === "project_version_conflict"
        ? { code, current_version: 4 }
        : { code };
      expect(businessErrorMessage({ response: { status, data: { detail } } })).toBe(message);
    }
  });

  it("rejects inherited prototype business codes without throwing", () => {
    for (const code of ["toString", "constructor", "__proto__"]) {
      const error = { response: { status: 422, data: { detail: { code } } } };

      expect(() => getBusinessErrorCode(error)).not.toThrow();
      expect(getBusinessErrorCode(error)).toBeNull();
      expect(() => businessErrorMessage(error)).not.toThrow();
      expect(businessErrorMessage(error)).toBe("操作未完成，请稍后重试。");
    }
  });
});

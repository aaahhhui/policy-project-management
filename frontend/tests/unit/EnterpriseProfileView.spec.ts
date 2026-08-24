import { mount } from "@vue/test-utils";
import ElementPlus from "element-plus";
import { nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getBusinessEntities, getSharedProfile, updateSharedProfile } from "../../src/api/profiles";
import { clearCurrentUser, currentUser } from "../../src/auth/state";
import EnterpriseProfileView from "../../src/views/EnterpriseProfileView.vue";

vi.mock("../../src/api/profiles", () => ({
  getBusinessEntities: vi.fn().mockResolvedValue([
    {
      seed_code: "ENTITY-BEIJING",
      legal_name: "北京适创科技有限公司",
      data: { registered_region: { city: "北京市" }, unified_social_credit_code: "BJ-1" },
      verification_status: "pending_business_license_review",
      version: 1, recent_audits: [],
    },
    {
      seed_code: "ENTITY-SUZHOU",
      legal_name: "苏州数算软云科技有限公司",
      data: { registered_region: { city: "苏州市" }, unified_social_credit_code: null },
      verification_status: "pending_business_license_review",
      version: 1, recent_audits: [],
    },
    {
      seed_code: "ENTITY-SHENZHEN",
      legal_name: "深圳适创腾扬科技有限公司",
      data: {
        registered_region: { city: "深圳市" },
        unified_social_credit_code: null,
        registered_capital_candidate: { amount: 1000 },
      },
      verification_status: "candidate_pending_business_license_review",
      version: 1, recent_audits: [],
    },
  ]),
  getSharedProfile: vi.fn().mockResolvedValue({
    code: "COMPANY-SHARED",
    display_name: "适创科技",
    data: {
      industries: ["工业软件", "CAE 仿真"],
      contact_phone: "400-870-8600",
      contact_email: "contacts@supreium.com",
    },
    verification_status: "public_verified",
    version: 1,
    recent_audits: [{ id: 9, action: "enterprise_profile_updated", actor_id: 1, actor_display_name: "王负责人", object_type: "enterprise_profile", object_id: 1, changed_fields: ["display_name", "data"], before_values: { display_name: "旧名称", data: "[redacted]" }, after_values: { display_name: "适创科技", data: "[redacted]" }, occurred_at: "2026-08-20 10:00" }],
  }),
  updateSharedProfile: vi.fn(), updateBusinessEntity: vi.fn(),
}));

function setViewportWidth(width: number) {
  const query = "(max-width: 720px)"; let mobile = width <= 720;
  const listeners = new Set<(event: MediaQueryListEvent) => void>();
  Object.defineProperty(window, "matchMedia", { configurable: true, value: vi.fn().mockImplementation((value: string) => ({
    matches: value === query && mobile, media: value,
    addEventListener: (_type: string, listener: (event: MediaQueryListEvent) => void) => listeners.add(listener),
    removeEventListener: (_type: string, listener: (event: MediaQueryListEvent) => void) => listeners.delete(listener),
  })) });
  return { setWidth: (next: number) => { mobile = next <= 720; listeners.forEach((listener) => listener({ matches: mobile } as MediaQueryListEvent)); } };
}

describe("EnterpriseProfileView", () => {
  beforeEach(() => { vi.clearAllMocks(); clearCurrentUser(); currentUser.value = { id: 1, login_name: "owner", display_name: "负责人", roles: ["applicant_owner"] }; setViewportWidth(1024); });
  it("renders the shared profile and every entity with the source verification status", async () => {
    const wrapper = mount(EnterpriseProfileView, { global: { plugins: [ElementPlus] } });

    await vi.dynamicImportSettled();

    expect(wrapper.get("h1").text()).toBe("企业档案");
    expect(wrapper.text()).toContain("适创科技");
    expect(wrapper.text()).toContain("北京适创科技有限公司");
    expect(wrapper.text()).toContain("苏州数算软云科技有限公司");
    expect(wrapper.text()).toContain("深圳适创腾扬科技有限公司");
    expect(wrapper.text()).toContain("候选信息，待核验");
    expect(wrapper.text()).toContain("候选注册资本");
  });

  it("labels unknown verification states as pending and exposes the raw code", async () => {
    const { default: VerificationBadge } = await import("../../src/components/VerificationBadge.vue");
    const wrapper = mount(VerificationBadge, { props: { status: "unlisted_status" } });

    expect(wrapper.text()).toContain("待核验");
    expect(wrapper.get("[title]").attributes("title")).toBe("unlisted_status");
    expect(wrapper.get("[title]").attributes("tabindex")).toBe("0");
    expect(wrapper.get("[title]").attributes("aria-label")).toBe("待核验：unlisted_status");
  });

  it("explains that entity seed data has not been imported when the entity response is empty", async () => {
    vi.mocked(getBusinessEntities).mockResolvedValue([]);
    const wrapper = mount(EnterpriseProfileView, { global: { plugins: [ElementPlus] } });

    await vi.dynamicImportSettled();

    expect(wrapper.get("[role=alert]").text()).toContain("企业主体种子数据尚未导入");
    expect(wrapper.findAll(".entity-card")).toHaveLength(0);
  });

  it("names missing cities and keeps partial entities in the expected city order", async () => {
    vi.mocked(getBusinessEntities).mockResolvedValue([
      {
        seed_code: "ENTITY-SHENZHEN",
        legal_name: "深圳适创腾扬科技有限公司",
        data: { registered_region: { city: "深圳市" } },
      verification_status: "candidate_pending_business_license_review",
      version: 1, recent_audits: [],
      },
      {
        seed_code: "ENTITY-BEIJING",
        legal_name: "北京适创科技有限公司",
        data: { registered_region: { city: "北京市" } },
      verification_status: "pending_business_license_review",
      version: 1, recent_audits: [],
      },
    ]);
    const wrapper = mount(EnterpriseProfileView, { global: { plugins: [ElementPlus] } });

    await vi.dynamicImportSettled();

    expect(wrapper.get("[role=alert]").text()).toContain("苏州");
    expect(wrapper.get("[role=alert]").text()).toContain("请联系管理员完成种子导入后刷新重试");
    expect(wrapper.findAll(".entity-code").map((card) => card.text())).toEqual([
      "ENTITY-BEIJING",
      "ENTITY-SHENZHEN",
    ]);
  });

  it("keeps versioned audit evidence readable and reloads a conflict without replaying the stale draft", async () => {
    vi.mocked(getSharedProfile).mockResolvedValueOnce({ code: "COMPANY-SHARED", display_name: "适创科技", data: { industries: ["工业软件"] }, verification_status: "public_verified", version: 1, recent_audits: [{ id: 9, action: "enterprise_profile_updated", actor_id: 1, actor_display_name: "王负责人", object_type: "enterprise_profile", object_id: 1, changed_fields: ["display_name", "data"], before_values: { display_name: "旧名称", data: "[redacted]" }, after_values: { display_name: "适创科技", data: "[redacted]" }, occurred_at: "2026-08-20 10:00" }] })
      .mockResolvedValueOnce({ code: "COMPANY-SHARED", display_name: "别人更新的名称", data: { industries: ["工业软件"] }, verification_status: "public_verified", version: 4, recent_audits: [] });
    vi.mocked(updateSharedProfile).mockRejectedValue({ response: { status: 409, data: { detail: { code: "profile_version_conflict", current_version: 4 } } } });
    const wrapper = mount(EnterpriseProfileView, { global: { plugins: [ElementPlus] } }); await vi.dynamicImportSettled();

    expect(wrapper.text()).toContain("变更字段：display_name");
    expect(wrapper.text()).toContain("王负责人");
    expect(wrapper.text()).toContain("已隐藏");
    await wrapper.get("button[aria-label='编辑公司共享档案']").trigger("click");
    await wrapper.get("input[aria-label='公司名称']").setValue("过期草稿");
    await wrapper.get("form").trigger("submit");
    expect(wrapper.text()).toContain("资料已被他人更新（当前版本 4）。重新加载后再编辑。");
    await wrapper.get("button[data-reload-profile]").trigger("click"); await vi.dynamicImportSettled();
    expect(updateSharedProfile).toHaveBeenCalledTimes(1);
    expect(wrapper.text()).toContain("别人更新的名称");
    expect(wrapper.find("input[aria-label='公司名称']").exists()).toBe(false);
  });

  it("keeps readers and a 640px viewport fully readable without profile mutation controls", async () => {
    currentUser.value = { id: 2, login_name: "reader", display_name: "阅读者", roles: ["reader"] };
    const reader = mount(EnterpriseProfileView, { global: { plugins: [ElementPlus] } }); await vi.dynamicImportSettled();
    expect(reader.text()).toContain("适创科技"); expect(reader.text()).toContain("最近审计");
    expect(reader.find("button[aria-label='编辑公司共享档案']").exists()).toBe(false);

    currentUser.value = { id: 1, login_name: "owner", display_name: "负责人", roles: ["applicant_owner"] };
    const viewport = setViewportWidth(1024); const owner = mount(EnterpriseProfileView, { global: { plugins: [ElementPlus] } }); await vi.dynamicImportSettled();
    expect(owner.find("button[aria-label='编辑公司共享档案']").exists()).toBe(true);
    viewport.setWidth(640); await nextTick();
    expect(owner.text()).toContain("适创科技"); expect(owner.text()).toContain("最近审计");
    expect(owner.find("button[aria-label='编辑公司共享档案']").exists()).toBe(false);
    expect(owner.find("button[aria-label='编辑企业主体 ENTITY-BEIJING']").exists()).toBe(false);
  });
});

import { mount } from "@vue/test-utils";
import ElementPlus from "element-plus";
import { describe, expect, it, vi } from "vitest";

import { getBusinessEntities } from "../../src/api/profiles";
import EnterpriseProfileView from "../../src/views/EnterpriseProfileView.vue";

vi.mock("../../src/api/profiles", () => ({
  getBusinessEntities: vi.fn().mockResolvedValue([
    {
      seed_code: "ENTITY-BEIJING",
      legal_name: "北京适创科技有限公司",
      data: { registered_region: { city: "北京市" }, unified_social_credit_code: "BJ-1" },
      verification_status: "pending_business_license_review",
    },
    {
      seed_code: "ENTITY-SUZHOU",
      legal_name: "苏州数算软云科技有限公司",
      data: { registered_region: { city: "苏州市" }, unified_social_credit_code: null },
      verification_status: "pending_business_license_review",
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
  }),
}));

describe("EnterpriseProfileView", () => {
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
      },
      {
        seed_code: "ENTITY-BEIJING",
        legal_name: "北京适创科技有限公司",
        data: { registered_region: { city: "北京市" } },
        verification_status: "pending_business_license_review",
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
});

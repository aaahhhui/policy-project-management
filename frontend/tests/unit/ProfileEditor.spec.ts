import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { updateBusinessEntity, updateSharedProfile, type BusinessEntityResponse, type ProfileResponse } from "../../src/api/profiles";
import ProfileEditor from "../../src/components/profiles/ProfileEditor.vue";

vi.mock("../../src/api/profiles", async (importOriginal) => {
  const original = await importOriginal<typeof import("../../src/api/profiles")>();
  return { ...original, updateSharedProfile: vi.fn(), updateBusinessEntity: vi.fn() };
});

const audit = {
  id: 18, action: "enterprise_profile_updated" as const, actor_id: 1, actor_display_name: "王负责人",
  object_type: "enterprise_profile" as const, object_id: 1, changed_fields: ["display_name"],
  before_values: { display_name: "适创科技" }, after_values: { display_name: "适创科技（更新）" }, occurred_at: "2026-08-20 10:00",
};
const shared: ProfileResponse = {
  code: "COMPANY-SHARED", display_name: "适创科技", data: { industry: "工业软件" }, verification_status: "public_verified", version: 1, recent_audits: [audit],
};
const entity: BusinessEntityResponse = {
  seed_code: "ENTITY-SHENZHEN", legal_name: "深圳适创腾扬科技有限公司", data: { city: "深圳" }, verification_status: "pending_business_license_review", version: 3,
  recent_audits: [{ ...audit, id: 19, action: "business_entity_updated", object_type: "business_entity", object_id: 3, changed_fields: ["legal_name"] }],
};

describe("ProfileEditor", () => {
  beforeEach(() => vi.clearAllMocks());

  it("submits only changed shared fields with the current expected version and replaces the response", async () => {
    vi.mocked(updateSharedProfile).mockResolvedValue({ ...shared, display_name: "适创科技（更新）", version: 2 });
    const wrapper = mount(ProfileEditor, { props: { target: "shared", profile: shared } });

    await wrapper.get("input[aria-label='公司名称']").setValue("适创科技（更新）");
    await wrapper.get("form").trigger("submit");

    expect(updateSharedProfile).toHaveBeenCalledWith({ expected_version: 1, display_name: "适创科技（更新）" });
    expect(wrapper.emitted("updated")?.[0]).toEqual([{ ...shared, display_name: "适创科技（更新）", version: 2 }]);
  });

  it("submits only changed entity fields with the current expected version", async () => {
    vi.mocked(updateBusinessEntity).mockResolvedValue({ ...entity, legal_name: "深圳适创科技有限公司", data: { city: "深圳", sectors: ["工业软件"] }, verification_status: "pending_review", version: 4 });
    const wrapper = mount(ProfileEditor, { props: { target: "entity", profile: entity } });

    await wrapper.get("input[aria-label='企业主体名称']").setValue("深圳适创科技有限公司");
    await wrapper.get("textarea[aria-label='档案结构化数据']").setValue('{"city":"深圳","sectors":["工业软件"]}');
    await wrapper.get("input[aria-label='核验状态']").setValue("pending_review");
    await wrapper.get("form").trigger("submit");

    expect(updateBusinessEntity).toHaveBeenCalledWith("ENTITY-SHENZHEN", { expected_version: 3, legal_name: "深圳适创科技有限公司", data: { city: "深圳", sectors: ["工业软件"] }, verification_status: "pending_review" });
    expect(wrapper.emitted("updated")?.[0]).toEqual([{ ...entity, legal_name: "深圳适创科技有限公司", data: { city: "深圳", sectors: ["工业软件"] }, verification_status: "pending_review", version: 4 }]);
  });

  it("normalizes the 255-character name and 64-character status before comparing and sending", async () => {
    const name = "企".repeat(255); const status = "a".repeat(64);
    vi.mocked(updateSharedProfile).mockResolvedValue({ ...shared, display_name: name, verification_status: status, version: 2 });
    const wrapper = mount(ProfileEditor, { props: { target: "shared", profile: shared } });

    await wrapper.get("input[aria-label='公司名称']").setValue(` ${name} `);
    await wrapper.get("input[aria-label='核验状态']").setValue(` ${status} `);
    await wrapper.get("form").trigger("submit");

    expect(updateSharedProfile).toHaveBeenCalledWith({ expected_version: 1, display_name: name, verification_status: status });
  });

  it("does not send a no-op patch when whitespace normalizes to the current profile", async () => {
    const wrapper = mount(ProfileEditor, { props: { target: "shared", profile: shared } });
    await wrapper.get("input[aria-label='公司名称']").setValue("  适创科技  ");
    await wrapper.get("input[aria-label='核验状态']").setValue("  public_verified  ");
    await wrapper.get("form").trigger("submit");
    expect(updateSharedProfile).not.toHaveBeenCalled();
    expect(wrapper.get("[role=alert]").text()).toContain("没有可保存的变更");
  });

  it("keeps invalid name/status boundaries and patterns local", async () => {
    const wrapper = mount(ProfileEditor, { props: { target: "shared", profile: shared } });
    await wrapper.get("input[aria-label='公司名称']").setValue("x".repeat(256));
    await wrapper.get("form").trigger("submit");
    expect(wrapper.get("[role=alert]").text()).toContain("255");

    await wrapper.get("input[aria-label='公司名称']").setValue("适创科技");
    await wrapper.get("input[aria-label='核验状态']").setValue("A-not-valid");
    await wrapper.get("form").trigger("submit");
    expect(wrapper.get("[role=alert]").text()).toContain("[a-z0-9_]+");

    await wrapper.get("input[aria-label='核验状态']").setValue("a".repeat(65));
    await wrapper.get("form").trigger("submit");
    expect(wrapper.get("[role=alert]").text()).toContain("64");
    expect(updateSharedProfile).not.toHaveBeenCalled();
  });

  it("accepts the backend-supported data shape and rejects deeper or malformed data locally", async () => {
    vi.mocked(updateSharedProfile).mockResolvedValue({ ...shared, data: { label: "text", amount: 1, enabled: true, nullable: null, tags: ["a", 2, false, null], address: { city: "深圳", postal: 518000 } }, version: 2 });
    const wrapper = mount(ProfileEditor, { props: { target: "shared", profile: shared } });
    await wrapper.get("textarea[aria-label='档案结构化数据']").setValue('{"label":"text","amount":1,"enabled":true,"nullable":null,"tags":["a",2,false,null],"address":{"city":"深圳","postal":518000}}');
    await wrapper.get("form").trigger("submit");
    expect(updateSharedProfile).toHaveBeenCalledTimes(1);

    for (const invalid of ['{"nested":{"too_deep":{"value":1}}}', '{"nested":[[1]]}', '{"":1}', `{"${"k".repeat(65)}":1}`]) {
      const invalidWrapper = mount(ProfileEditor, { props: { target: "shared", profile: shared } });
      await invalidWrapper.get("textarea[aria-label='档案结构化数据']").setValue(invalid);
      await invalidWrapper.get("form").trigger("submit");
      expect(invalidWrapper.get("[role=alert]").text()).toContain("档案结构化数据");
    }
    expect(updateSharedProfile).toHaveBeenCalledTimes(1);
  });

  it("measures 32 KiB from compact canonical UTF-8 JSON instead of pretty input whitespace", async () => {
    vi.mocked(updateSharedProfile).mockResolvedValue({ ...shared, data: { note: "中".repeat(10919) }, version: 2 });
    const wrapper = mount(ProfileEditor, { props: { target: "shared", profile: shared } });
    const nearLimit = { note: "中".repeat(10919) };
    await wrapper.get("textarea[aria-label='档案结构化数据']").setValue(`${" ".repeat(40_000)}\n${JSON.stringify(nearLimit, null, 2)}`);
    await wrapper.get("form").trigger("submit");
    expect(updateSharedProfile).toHaveBeenCalledWith({ expected_version: 1, data: nearLimit });

    const overLimit = { note: "中".repeat(10920) };
    const overLimitWrapper = mount(ProfileEditor, { props: { target: "shared", profile: shared } });
    await overLimitWrapper.get("textarea[aria-label='档案结构化数据']").setValue(JSON.stringify(overLimit, null, 2));
    await overLimitWrapper.get("form").trigger("submit");
    expect(overLimitWrapper.get("[role=alert]").text()).toContain("32 KiB");
    expect(updateSharedProfile).toHaveBeenCalledTimes(1);
  });

  it("keeps malformed, oversized, and missing form values local and disables submit during a request", async () => {
    let resolveRequest: (value: ProfileResponse) => void = () => undefined;
    vi.mocked(updateSharedProfile).mockImplementation(() => new Promise((resolve) => { resolveRequest = resolve; }));
    const wrapper = mount(ProfileEditor, { props: { target: "shared", profile: shared } });

    await wrapper.get("input[aria-label='公司名称']").setValue("");
    await wrapper.get("form").trigger("submit");
    expect(wrapper.get("[role=alert]").text()).toContain("公司名称不能为空");
    expect(updateSharedProfile).not.toHaveBeenCalled();

    await wrapper.get("input[aria-label='公司名称']").setValue("适创科技");
    await wrapper.get("textarea[aria-label='档案结构化数据']").setValue("{");
    await wrapper.get("form").trigger("submit");
    expect(wrapper.get("[role=alert]").text()).toContain("JSON 格式");
    expect(updateSharedProfile).not.toHaveBeenCalled();

    await wrapper.get("textarea[aria-label='档案结构化数据']").setValue(`{"notes":"${"x".repeat(32 * 1024)}"}`);
    await wrapper.get("form").trigger("submit");
    expect(wrapper.get("[role=alert]").text()).toContain("32 KiB");
    expect(updateSharedProfile).not.toHaveBeenCalled();

    await wrapper.get("textarea[aria-label='档案结构化数据']").setValue('{"industry":"工业软件","products":["CAE"]}');
    await wrapper.get("input[aria-label='核验状态']").setValue("pending_review");
    await wrapper.get("form").trigger("submit");
    await nextTick();
    expect(wrapper.get("button[type=submit]").attributes("disabled")).toBeDefined();
    expect(updateSharedProfile).toHaveBeenCalledWith({ expected_version: 1, data: { industry: "工业软件", products: ["CAE"] }, verification_status: "pending_review" });
    resolveRequest({ ...shared, data: { industry: "工业软件", products: ["CAE"] }, verification_status: "pending_review", version: 2 });
    await nextTick();
  });

  it("shows only reload guidance for a profile version conflict", async () => {
    vi.mocked(updateSharedProfile).mockRejectedValue({ response: { status: 409, data: { detail: { code: "profile_version_conflict", current_version: 4 } } } });
    const wrapper = mount(ProfileEditor, { props: { target: "shared", profile: shared } });

    await wrapper.get("input[aria-label='公司名称']").setValue("新名称");
    await wrapper.get("form").trigger("submit");

    expect(wrapper.get("[role=alert]").text()).toBe("资料已被他人更新（当前版本 4）。重新加载后再编辑。重新加载");
    await wrapper.get("button[data-reload-profile]").trigger("click");
    expect(wrapper.emitted("reload")).toHaveLength(1);
    expect(updateSharedProfile).toHaveBeenCalledTimes(1);
  });
});

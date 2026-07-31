import { mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";

import { selectPrimaryEntity } from "../../src/api/evaluations";
import PrimaryEntitySelector from "../../src/components/evaluations/PrimaryEntitySelector.vue";

vi.mock("../../src/api/evaluations", () => ({ selectPrimaryEntity: vi.fn() }));

beforeEach(() => {
  vi.clearAllMocks();
});

it("makes the unchanged current entity explicit and only enables a real switch", async () => {
  const wrapper = mount(PrimaryEntitySelector, {
    props: {
      policyId: 8,
      candidates: [
        { entity_seed_code: "ENTITY-BEIJING", label: "北京企业" },
        { entity_seed_code: "ENTITY-SHENZHEN", label: "深圳企业" },
      ],
      current: { entity_seed_code: "ENTITY-SHENZHEN", entity_legal_name: "深圳企业" },
    },
  });

  expect(wrapper.text()).toContain("当前主申报企业：深圳企业");
  expect(wrapper.get<HTMLButtonElement>("button").element.disabled).toBe(true);

  await wrapper.get('[value="ENTITY-BEIJING"]').setValue();

  expect(wrapper.get<HTMLButtonElement>("button").element.disabled).toBe(false);
});

it("syncs the selected radio when the saved current entity loads later", async () => {
  const wrapper = mount(PrimaryEntitySelector, {
    props: {
      policyId: 8,
      candidates: [
        { entity_seed_code: "ENTITY-BEIJING", label: "北京企业" },
        { entity_seed_code: "ENTITY-SHENZHEN", label: "深圳企业" },
      ],
      current: null,
    },
  });

  await wrapper.setProps({
    current: { entity_seed_code: "ENTITY-SHENZHEN", entity_legal_name: "深圳企业" },
  });

  expect(wrapper.get<HTMLInputElement>('[value="ENTITY-SHENZHEN"]').element.checked).toBe(true);
  expect(wrapper.get<HTMLButtonElement>("button").element.disabled).toBe(true);
});

it("requires a reason when changing the selected entity", async () => {
  const wrapper = mount(PrimaryEntitySelector, {
    props: {
      policyId: 8,
      candidates: [
        { entity_seed_code: "ENTITY-BEIJING", label: "北京企业" },
        { entity_seed_code: "ENTITY-SUZHOU", label: "苏州企业" },
      ],
      current: { entity_seed_code: "ENTITY-BEIJING", entity_legal_name: "北京企业" },
    },
  });
  await wrapper.get('[value="ENTITY-SUZHOU"]').setValue();
  await wrapper.get("form").trigger("submit");

  expect(wrapper.text()).toContain("切换主申报企业必须填写原因");
  expect(selectPrimaryEntity).not.toHaveBeenCalled();
});

import { mount } from "@vue/test-utils";
import { expect, it, vi } from "vitest";

import { selectPrimaryEntity } from "../../src/api/evaluations";
import PrimaryEntitySelector from "../../src/components/evaluations/PrimaryEntitySelector.vue";

vi.mock("../../src/api/evaluations", () => ({ selectPrimaryEntity: vi.fn() }));

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

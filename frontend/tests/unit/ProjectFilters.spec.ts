import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import ProjectFilters, {
  filtersFromQuery,
  filtersToQuery,
} from "../../src/components/projects/ProjectFilters.vue";

describe("ProjectFilters", () => {
  it("hydrates supported URL values and removes empty/default values when applying", async () => {
    const filters = filtersFromQuery({
      q: "digital",
      status: "submitted",
      liaison_id: "4",
      page: "2",
      page_size: "50",
      ignored: "value",
    });
    const wrapper = mount(ProjectFilters, { props: { filters } });

    expect((wrapper.get("input[aria-label='搜索项目']").element as HTMLInputElement).value).toBe("digital");
    expect(filtersToQuery({ ...filters, q: "", page: 1, page_size: 20 })).toEqual({
      status: "submitted",
      liaison_id: "4",
    });

    await wrapper.get("form").trigger("submit");
    expect(wrapper.emitted("apply")?.[0]).toEqual([{
      ...filters,
      page: 1,
    }]);
  });

  it("restricts page sizes and resets to the first page when a filter changes", async () => {
    const wrapper = mount(ProjectFilters, {
      props: { filters: { ...filtersFromQuery({ page: "4", page_size: "10" }) } },
    });

    expect((wrapper.get("select[aria-label='每页项目数']").element as HTMLSelectElement).value).toBe("20");
    await wrapper.get("select[aria-label='项目状态']").setValue("submitted");
    await wrapper.get("form").trigger("submit");

    expect(wrapper.emitted("apply")?.[0]).toEqual([{
      q: "", primary_entity_seed_code: "", liaison_id: "", status: "submitted",
      deadline_from: "", deadline_to: "", mine: false, page: 1, page_size: 20,
    }]);
  });
});

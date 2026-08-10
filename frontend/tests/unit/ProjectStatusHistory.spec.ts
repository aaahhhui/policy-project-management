import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import type { ProjectStatusHistoryDetail } from "../../src/api/projects";
import ProjectStatusHistory from "../../src/components/projects/ProjectStatusHistory.vue";

const entries: ProjectStatusHistoryDetail[] = [
  {
    id: 1, action: "transition", previous_status: "pending_application", new_status: "submitted",
    actor: { id: 4, display_name: "李联络" }, reason: null, related_date: "2026-08-01",
    before_values: { status: "pending_application" }, after_values: { status: "submitted", submitted_on: "2026-08-01" },
    from_version: 1, to_version: 2, occurred_at: "2026-08-01T09:00:00Z",
  },
  {
    id: 2, action: "correction", previous_status: "submitted", new_status: "rejected",
    actor: { id: 1, display_name: "王负责人" }, reason: "录入结果", related_date: "2026-08-04",
    before_values: { status: "submitted" }, after_values: { status: "rejected", result_on: "2026-08-04" },
    from_version: 2, to_version: 3, occurred_at: "2026-08-04T10:00:00Z",
  },
];

describe("ProjectStatusHistory", () => {
  it("shows newest history first with the actor, action, snapshots, and related date", () => {
    const wrapper = mount(ProjectStatusHistory, { props: { entries } });
    const text = wrapper.text();

    expect(text.indexOf("王负责人")).toBeLessThan(text.indexOf("李联络"));
    expect(text).toContain("更正");
    expect(text).toContain("submitted");
    expect(text).toContain("rejected");
    expect(text).toContain("2026-08-04");
  });
});

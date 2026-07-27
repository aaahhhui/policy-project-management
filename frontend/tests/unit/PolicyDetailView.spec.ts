import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

import { getPolicy, getPolicyVersions } from "../../src/api/policies";
import PolicyDetailView from "../../src/views/PolicyDetailView.vue";

vi.mock("vue-router", () => ({ useRoute: () => ({ params: { id: "8" } }) }));
vi.mock("../../src/api/policies", () => ({
  getPolicy: vi.fn(),
  getPolicyVersions: vi.fn(),
}));

describe("PolicyDetailView", () => {
  it("renders one weak conclusion followed by evidence, body, files, and history", async () => {
    vi.mocked(getPolicy).mockResolvedValue({
      id: 8,
      title: "制造业数字化转型项目申报通知",
      document_number: "粤工信〔2026〕8号",
      published_on: "2026-07-20",
      deadline_on: "2026-08-20",
      current_conclusion: "pending_confirmation",
      conclusion_confirmed: false,
      current_evaluation_batch_id: null,
      current_version: {
        id: 12,
        version_number: 2,
        title: "制造业数字化转型项目申报通知",
        body_text: "支持制造业企业开展数字化改造。",
        body_html: "<p>支持制造业企业开展数字化改造。</p>",
        collected_at: "2026-07-27T02:00:00Z",
        snapshot_url: "/api/files/snapshots/12",
      },
      discoveries: [{
        id: 2,
        source_id: 3,
        source_name: "广东省工业和信息化厅",
        channel_id: 4,
        channel_name: "通知公告",
        original_url: "https://gdii.gd.gov.cn/policy/8",
        first_seen_at: "2026-07-27T02:00:00Z",
        last_seen_at: "2026-07-27T02:00:00Z",
      }],
      attachments: [{
        id: 9,
        display_name: "申报指南.pdf",
        source_url: "https://gdii.gd.gov.cn/guide.pdf",
        status: "downloaded",
        content_type: "application/pdf",
        error_message: null,
        download_url: "/api/files/attachments/9",
      }],
    });
    vi.mocked(getPolicyVersions).mockResolvedValue([
      {
        id: 12,
        version_number: 2,
        title: "制造业数字化转型项目申报通知",
        body_text: "支持制造业企业开展数字化改造。",
        body_html: "<p>支持制造业企业开展数字化改造。</p>",
        collected_at: "2026-07-27T02:00:00Z",
        snapshot_url: "/api/files/snapshots/12",
      },
    ]);
    const wrapper = mount(PolicyDetailView);
    await vi.dynamicImportSettled();

    expect(wrapper.findAll("[data-conclusion]")).toHaveLength(1);
    expect(wrapper.get("[data-conclusion]").text()).toBe("待确认");
    expect(wrapper.get("[data-conclusion]").classes()).toContain("weak");
    const text = wrapper.text();
    expect(text).toContain("广东省工业和信息化厅");
    expect(text).toContain("支持制造业企业开展数字化改造");
    expect(text).toContain("原始网页快照");
    expect(text).toContain("申报指南.pdf");
    expect(text).toContain("版本 2");
  });
});

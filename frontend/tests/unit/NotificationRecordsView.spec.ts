import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  getNotification,
  listNotifications,
  retryNotification,
  type NotificationDetail,
  type NotificationListItem,
} from "../../src/api/notifications";
import NotificationRecordsView from "../../src/views/NotificationRecordsView.vue";

vi.mock("../../src/api/notifications", () => ({
  listNotifications: vi.fn(),
  getNotification: vi.fn(),
  retryNotification: vi.fn(),
}));

const failed: NotificationListItem = {
  id: 9, event_type: "project_created", display_type: "政策转项目", object_type: "project",
  object_id: 17, object_name: "星河项目", detail_path: "/projects/17",
  triggered_at: "2026-08-11T08:00:00Z", status: "failed", attempt_count: 4,
  send_round: 1, round_attempt_count: 4, next_attempt_at: null, sent_at: null,
  last_error_code: "wecom_connection_timeout",
  last_failure_summary: "连接企业微信超时，已停止自动重试。", version: 7,
};
const succeeded: NotificationListItem = {
  ...failed, id: 10, event_type: "project_first_succeeded", display_type: "项目成功",
  status: "succeeded", sent_at: "2026-08-11T08:00:02Z", last_error_code: null,
  last_failure_summary: null, version: 4,
};
const detail: NotificationDetail = {
  ...failed,
  message_snapshot: { deadline_on: "2026-08-31" },
  attempts: [{
    id: 1, attempt_number: 1, trigger_type: "initial", started_at: "2026-08-11T08:00:00Z",
    finished_at: "2026-08-11T08:00:01Z", result: "retryable_failure", http_status: null,
    provider_error_code: null, failure_summary: "连接企业微信超时，将按计划重试。",
  }],
};

function page(items = [failed, succeeded]) {
  return { items, page: 1, page_size: 20, total: items.length };
}

function mountView() {
  return mount(NotificationRecordsView, { global: { stubs: { RouterLink: true } } });
}

describe("NotificationRecordsView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.innerWidth = 1200;
    vi.mocked(listNotifications).mockResolvedValue(page());
    vi.mocked(getNotification).mockResolvedValue(detail);
    vi.mocked(retryNotification).mockResolvedValue({
      ...detail, status: "pending", send_round: 2, round_attempt_count: 0, version: 8,
    });
  });

  afterEach(() => { window.innerWidth = 1024; });

  it("applies type, status, time, and page filters on the server", async () => {
    vi.mocked(listNotifications).mockResolvedValue({ ...page(), total: 41 });
    const wrapper = mountView();
    await flushPromises();
    await wrapper.get("[data-filter-type]").setValue("project_created");
    await wrapper.get("[data-filter-status]").setValue("failed");
    await wrapper.get("[data-filter-from]").setValue("2026-08-01T08:00");
    await wrapper.get("[data-filter-to]").setValue("2026-08-31T18:00");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(listNotifications).toHaveBeenLastCalledWith({
      event_type: "project_created", status: "failed",
      triggered_from: new Date("2026-08-01T08:00").toISOString(),
      triggered_to: new Date("2026-08-31T18:00").toISOString(), page: 1, page_size: 20,
    });

    vi.mocked(listNotifications).mockResolvedValue({ ...page(), page: 2, total: 41 });
    await wrapper.get("[data-next-notification-page]").trigger("click");
    await flushPromises();
    expect(listNotifications).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }));
  });

  it("shows safe detail, attempt history, failure guidance, and retries only a failed record", async () => {
    const wrapper = mountView();
    await flushPromises();
    expect(wrapper.find('[data-retry-notification="10"]').exists()).toBe(false);
    await wrapper.get('[data-open-notification="9"]').trigger("click");
    await flushPromises();

    expect(getNotification).toHaveBeenCalledWith(9);
    expect(wrapper.text()).toContain("连接企业微信超时，将按计划重试。");
    expect(wrapper.text()).toContain("截止日期");
    expect(wrapper.find('[data-retry-notification="9"]').exists()).toBe(true);
    await wrapper.get('[data-retry-notification="9"]').trigger("click");
    await flushPromises();
    expect(retryNotification).toHaveBeenCalledWith(9, 7);
    expect(listNotifications).toHaveBeenCalledTimes(2);
  });

  it("reloads detail after a version conflict and hides retry controls on mobile", async () => {
    vi.mocked(retryNotification).mockRejectedValue(Object.assign(new Error("conflict"), {
      response: { status: 409, data: { detail: { code: "notification_version_conflict" } } },
    }));
    window.innerWidth = 700;
    const wrapper = mountView();
    await flushPromises();
    await wrapper.get('[data-open-notification="9"]').trigger("click");
    await flushPromises();
    expect(wrapper.find('[data-retry-notification="9"]').exists()).toBe(false);

    window.innerWidth = 1200;
    window.dispatchEvent(new Event("resize"));
    await wrapper.vm.$nextTick();
    await wrapper.get('[data-retry-notification="9"]').trigger("click");
    await flushPromises();
    expect(getNotification).toHaveBeenCalledTimes(2);
    expect(wrapper.find("[data-notification-conflict]").exists()).toBe(true);
  });
});

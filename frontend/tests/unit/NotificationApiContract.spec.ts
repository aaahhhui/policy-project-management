import { beforeEach, describe, expect, it, vi } from "vitest";
const { http } = vi.hoisted(() => ({ http: { get: vi.fn(), post: vi.fn() } }));

vi.mock("../../src/api/http", () => ({ default: http }));

import { getNotification, listNotifications, retryNotification } from "../../src/api/notifications";

describe("notification API contract", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    http.get.mockResolvedValue({ data: { ok: true } });
    http.post.mockResolvedValue({ data: { ok: true } });
  });

  it("uses exact list, detail, and retry endpoints without accepting message or webhook input", async () => {
    const filters = {
      event_type: "project_created",
      status: "failed" as const,
      triggered_from: "2026-08-01T00:00:00Z",
      triggered_to: "2026-08-31T23:59:59Z",
      page: 2,
      page_size: 10 as const,
    };

    await listNotifications(filters);
    await getNotification(19);
    await retryNotification(19, 7);

    expect(http.get).toHaveBeenNthCalledWith(1, "/notifications", { params: filters });
    expect(http.get).toHaveBeenNthCalledWith(2, "/notifications/19");
    expect(http.post).toHaveBeenCalledWith("/notifications/19/retry", { expected_version: 7 });
  });
});

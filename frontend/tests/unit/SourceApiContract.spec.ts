import { beforeEach, describe, expect, it, vi } from "vitest";

const { http } = vi.hoisted(() => ({
  http: { get: vi.fn(), post: vi.fn() },
}));

vi.mock("../../src/api/http", () => ({ default: http }));

import {
  createSource,
  disableSource,
  enableSource,
  getSources,
  retrySourceRecognition,
  type PolicySource,
  type SourceCreateInput,
} from "../../src/api/sources";
import { getBusinessErrorCode } from "../../src/api/errors";

type ForbiddenSourceKey = "adapter_key" | "selector" | "channels" | "raw_body" | "raw_html" | "headers" | "credential" | "credentials" | "password" | "token";
type AssertNever<Value extends never> = Value;
type SourceInputHasNoForbiddenKeys = AssertNever<Extract<keyof SourceCreateInput, ForbiddenSourceKey>>;
type SourceResponseHasNoForbiddenKeys = AssertNever<Extract<keyof PolicySource, ForbiddenSourceKey>>;

describe("source API contract", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    http.get.mockResolvedValue({ data: { items: [] } });
    http.post.mockResolvedValue({ data: { id: 7 } });
  });

  it("sends only safe source lifecycle requests and narrows documented source conflicts", async () => {
    const input: SourceCreateInput = {
      name: "Public policy feed",
      entry_url: "https://public.example/feed.xml",
      region_labels: ["Guangdong"],
      topic_labels: ["Manufacturing"],
    };
    // @ts-expect-error Source inputs must never select server implementations.
    const unsafeSource: SourceCreateInput = { ...input, adapter_key: "rss_atom" };
    void unsafeSource;

    await getSources(2, 20);
    await createSource(input);
    await retrySourceRecognition(7);
    await retrySourceRecognition(7, "https://public.example/policy/42");
    await enableSource(7, 3);
    await disableSource(7, 4);

    expect(http.get).toHaveBeenCalledWith("/sources", { params: { page: 2, page_size: 20 } });
    expect(http.post).toHaveBeenNthCalledWith(1, "/sources", input);
    expect(http.post).toHaveBeenNthCalledWith(2, "/sources/7/recognition-retries", {});
    expect(http.post).toHaveBeenNthCalledWith(3, "/sources/7/recognition-retries", {
      representative_url: "https://public.example/policy/42",
    });
    expect(http.post).toHaveBeenNthCalledWith(4, "/sources/7/enable", { expected_version: 3 });
    expect(http.post).toHaveBeenNthCalledWith(5, "/sources/7/disable", { expected_version: 4 });
    expect(getBusinessErrorCode({ response: { data: { detail: {
      code: "source_version_conflict", current_version: 5,
    } } } })).toEqual({ code: "source_version_conflict", currentVersion: 5 });
    expect(getBusinessErrorCode({ response: { data: { detail: {
      code: "source_version_conflict", current_version: "5",
    } } } })).toBeNull();
  });
});

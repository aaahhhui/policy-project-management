import { beforeEach, describe, expect, it, vi } from "vitest";

const { http } = vi.hoisted(() => ({
  http: { get: vi.fn(), patch: vi.fn() },
}));

vi.mock("../../src/api/http", () => ({ default: http }));

import {
  updateBusinessEntity,
  updateSharedProfile,
  type ProfileResponse,
  type ProfilePatchInput,
} from "../../src/api/profiles";
import { getBusinessErrorCode } from "../../src/api/errors";

type ForbiddenProfileKey = "adapter_key" | "selector" | "channels" | "raw_body" | "raw_html" | "headers" | "credential" | "credentials" | "password" | "token";
type AssertNever<Value extends never> = Value;
type ProfileInputHasNoForbiddenKeys = AssertNever<Extract<keyof ProfilePatchInput, ForbiddenProfileKey>>;
type ProfileResponseHasNoForbiddenKeys = AssertNever<Extract<keyof ProfileResponse, ForbiddenProfileKey>>;

describe("profile API contract", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    http.patch.mockResolvedValue({ data: { version: 2, recent_audits: [] } });
  });

  it("uses exact versioned profile PATCH requests without accepting transport or credential fields", async () => {
    const shared: ProfilePatchInput = {
      expected_version: 1,
      display_name: "Updated company",
      data: { industry: "Software" },
      verification_status: "public_verified",
    };
    const entity = {
      expected_version: 3,
      legal_name: "Updated entity",
      data: { city: "Shenzhen" },
      verification_status: "pending_business_license_review",
    };
    // @ts-expect-error Profile writes must not expose HTTP transport details.
    const unsafeProfile: ProfilePatchInput = { ...shared, headers: { Authorization: "secret" } };
    void unsafeProfile;

    await updateSharedProfile(shared);
    await updateBusinessEntity("ENTITY-SHENZHEN", entity);

    expect(http.patch).toHaveBeenNthCalledWith(1, "/profiles/shared", shared);
    expect(http.patch).toHaveBeenNthCalledWith(2, "/profiles/entities/ENTITY-SHENZHEN", entity);
    expect(getBusinessErrorCode({ response: { data: { detail: {
      code: "profile_version_conflict", current_version: 4,
    } } } })).toEqual({ code: "profile_version_conflict", currentVersion: 4 });
    expect(getBusinessErrorCode({ response: { data: { detail: "raw server error" } } })).toBeNull();
  });
});

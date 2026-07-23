import { beforeEach, describe, expect, it, vi } from "vitest";

import { getCurrentUser, logout } from "../../src/api/auth";
import {
  clearCurrentUser,
  currentUser,
  loadCurrentUser,
  signOut,
} from "../../src/auth/state";

vi.mock("../../src/api/auth", () => ({
  getCurrentUser: vi.fn(),
  logout: vi.fn(),
}));

describe("auth state", () => {
  beforeEach(() => {
    clearCurrentUser();
    vi.clearAllMocks();
  });

  it("shares one current-user request across consumers", async () => {
    vi.mocked(getCurrentUser).mockResolvedValue({
      id: 1,
      login_name: "owner",
      display_name: "Owner",
      roles: ["applicant_owner"],
    });

    await loadCurrentUser();
    await loadCurrentUser();

    expect(getCurrentUser).toHaveBeenCalledTimes(1);
  });

  it("clears the cached user after logout", async () => {
    vi.mocked(getCurrentUser).mockResolvedValue({
      id: 1,
      login_name: "owner",
      display_name: "Owner",
      roles: ["applicant_owner"],
    });
    vi.mocked(logout).mockResolvedValue();
    await loadCurrentUser();

    await signOut();

    expect(currentUser.value).toBeNull();
  });

  it("keeps the cached user when server logout fails", async () => {
    vi.mocked(getCurrentUser).mockResolvedValue({
      id: 1,
      login_name: "owner",
      display_name: "Owner",
      roles: ["applicant_owner"],
    });
    vi.mocked(logout).mockRejectedValue(new Error("unavailable"));
    await loadCurrentUser();

    await expect(signOut()).rejects.toThrow("unavailable");

    expect(currentUser.value?.login_name).toBe("owner");
  });
});

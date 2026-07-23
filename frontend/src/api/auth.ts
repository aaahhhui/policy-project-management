import http from "./http";

export interface CurrentUser {
  id: number;
  login_name: string;
  display_name: string;
  roles: string[];
}

export interface LoginCredentials {
  login_name: string;
  password: string;
}

export async function login(credentials: LoginCredentials): Promise<void> {
  await http.post("/auth/login", credentials);
}

export async function logout(): Promise<void> {
  await http.post("/auth/logout");
}

export async function getCurrentUser(): Promise<CurrentUser> {
  const response = await http.get<CurrentUser>("/auth/me");
  return response.data;
}

export function isUnauthorizedError(error: unknown): boolean {
  if (typeof error !== "object" || error === null || !("response" in error)) return false;
  const response = error.response;
  return typeof response === "object" && response !== null && "status" in response
    ? response.status === 401
    : false;
}

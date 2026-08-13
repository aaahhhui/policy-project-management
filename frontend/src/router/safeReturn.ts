const allowedPathPatterns = [
  /^\/$/,
  /^\/policies(?:\/\d+)?$/,
  /^\/projects(?:\/\d+)?$/,
  /^\/sources$/,
  /^\/notifications$/,
];

export function isSafeReturnPath(value: unknown): value is string {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//")) return false;
  if (value.includes("\\") || /[\u0000-\u001f]/.test(value)) return false;
  try {
    const parsed = new URL(value, "https://local.invalid");
    return parsed.origin === "https://local.invalid"
      && allowedPathPatterns.some((pattern) => pattern.test(parsed.pathname));
  } catch {
    return false;
  }
}

export function safeReturnPath(value: unknown): string {
  return isSafeReturnPath(value) ? value : "/";
}

/** Safe same-origin relative path for post-login redirect (`next` query). */
export function safeNextPath(raw: string | null | undefined, fallback = "/free-numbers"): string {
  if (!raw) return fallback;
  const value = raw.trim();
  if (!value.startsWith("/") || value.startsWith("//")) return fallback;
  if (value.includes("://")) return fallback;
  return value;
}

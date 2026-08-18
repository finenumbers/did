import { clearSession, getAccessToken } from "@/lib/auth";

/** Browser calls Next proxy by default. */
export const API_URL = process.env.NEXT_PUBLIC_API_URL || "/api/backend";

export class ApiError extends Error {
  code: string;
  details?: Record<string, unknown>;

  constructor(message: string, code: string, details?: Record<string, unknown>) {
    super(message);
    this.code = code;
    this.details = details;
  }
}

function errorMessageFromBody(
  data: unknown,
  fallback: string,
): {
  message: string;
  code: string;
  details?: Record<string, unknown>;
} {
  const body = (data && typeof data === "object" ? data : {}) as Record<string, unknown>;
  const err = body.error as Record<string, unknown> | undefined;
  if (err && typeof err.message === "string") {
    return {
      message: err.message,
      code: typeof err.code === "string" ? err.code : "HTTP_ERROR",
      details: (err.details as Record<string, unknown>) || undefined,
    };
  }
  const detail = body.detail;
  if (typeof detail === "string") {
    return { message: detail, code: "HTTP_ERROR" };
  }
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0] as { msg?: string };
    return { message: first?.msg || fallback, code: "HTTP_ERROR" };
  }
  if (detail && typeof detail === "object" && "msg" in (detail as object)) {
    return { message: String((detail as { msg: string }).msg), code: "HTTP_ERROR" };
  }
  return { message: fallback, code: "HTTP_ERROR" };
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };
  const token = getAccessToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const parsed = errorMessageFromBody(data, res.statusText || "Request failed");
    if (res.status === 401 && typeof window !== "undefined" && !path.includes("/auth/login")) {
      clearSession();
      if (!window.location.pathname.startsWith("/login")) {
        window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
      }
    }
    throw new ApiError(parsed.message, parsed.code, parsed.details);
  }
  return data as T;
}

/** Authenticated multipart upload. Do not set Content-Type — browser sets the boundary. */
export async function apiUpload<T>(path: string, body: FormData): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getAccessToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers,
    body,
    cache: "no-store",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const parsed = errorMessageFromBody(data, res.statusText || "Upload failed");
    if (res.status === 401 && typeof window !== "undefined") {
      clearSession();
      if (!window.location.pathname.startsWith("/login")) {
        window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
      }
    }
    throw new ApiError(parsed.message, parsed.code, parsed.details);
  }
  return data as T;
}

/** Authenticated binary download (Authorization header — no token in URL). */
export async function apiDownload(path: string): Promise<Blob> {
  const headers: Record<string, string> = {};
  const token = getAccessToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const res = await fetch(`${API_URL}${path}`, {
    headers,
    cache: "no-store",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const parsed = errorMessageFromBody(data, res.statusText || "Download failed");
    if (res.status === 401 && typeof window !== "undefined") {
      clearSession();
      if (!window.location.pathname.startsWith("/login")) {
        window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
      }
    }
    throw new ApiError(parsed.message, parsed.code, parsed.details);
  }
  return res.blob();
}

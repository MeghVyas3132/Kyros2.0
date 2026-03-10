import { ApiErrorEnvelope, ApiResponse } from "@/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  code: string;
  details?: unknown;

  constructor(code: string, message: string, details?: unknown) {
    super(message);
    this.code = code;
    this.details = details;
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("kyros_access_token");
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("kyros_refresh_token");
}

export function setAuthTokens(accessToken: string, refreshToken: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem("kyros_access_token", accessToken);
  localStorage.setItem("kyros_refresh_token", refreshToken);
}

export function clearAuthTokens(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem("kyros_access_token");
  localStorage.removeItem("kyros_refresh_token");
  localStorage.removeItem("kyros_user");
}

async function tryRefreshToken(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;

  const response = await fetch(`${API_URL}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!response.ok) {
    clearAuthTokens();
    return false;
  }

  const payload = (await response.json()) as ApiResponse<{ access_token: string }>;
  localStorage.setItem("kyros_access_token", payload.data.access_token);
  return true;
}

export async function apiRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getToken();
  const isFormData = options?.body instanceof FormData;

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  });

  if (response.status === 401) {
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      return apiRequest<T>(path, options);
    }
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
    throw new ApiError("AUTH_EXPIRED", "Session expired");
  }

  if (!response.ok) {
    const error = (await response.json()) as ApiErrorEnvelope;
    throw new ApiError(error.error.code, error.error.message, error.error.details);
  }

  const payload = (await response.json()) as ApiResponse<T>;
  return payload.data;
}

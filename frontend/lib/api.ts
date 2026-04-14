import { ApiErrorEnvelope, ApiResponse } from "@/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const DEFAULT_REQUEST_TIMEOUT_MS = 12000;

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

function mergeAbortSignals(signals: Array<AbortSignal | undefined>): AbortSignal | undefined {
  const activeSignals = signals.filter((signal): signal is AbortSignal => Boolean(signal));
  if (activeSignals.length === 0) return undefined;
  if (activeSignals.length === 1) return activeSignals[0];

  const controller = new AbortController();
  const onAbort = () => controller.abort();
  activeSignals.forEach((signal) => {
    if (signal.aborted) {
      controller.abort();
      return;
    }
    signal.addEventListener("abort", onAbort, { once: true });
  });
  return controller.signal;
}

function withTimeoutSignal(
  timeoutMs: number,
  baseSignal?: AbortSignal
): { signal?: AbortSignal; cancel: () => void } {
  if (timeoutMs <= 0) {
    return { signal: baseSignal, cancel: () => undefined };
  }

  const timeoutController = new AbortController();
  const timeoutId = globalThis.setTimeout(() => timeoutController.abort(), timeoutMs);
  const signal = mergeAbortSignals([baseSignal, timeoutController.signal]);

  return {
    signal,
    cancel: () => globalThis.clearTimeout(timeoutId),
  };
}

async function parseApiError(response: Response): Promise<ApiError> {
  try {
    const error = (await response.json()) as ApiErrorEnvelope & {
      code?: string;
      message?: string;
      detail?: unknown;
    };
    const detailMessage =
      typeof error?.detail === "string"
        ? error.detail
        : Array.isArray(error?.detail)
        ? error.detail
            .map((item) => {
              if (typeof item === "string") return item;
              if (item && typeof item === "object" && "msg" in item) {
                const msg = String((item as { msg?: unknown }).msg ?? "");
                const locRaw = (item as { loc?: unknown }).loc;
                const loc = Array.isArray(locRaw) ? locRaw.map(String).join(".") : "";
                return loc ? `${loc}: ${msg}` : msg;
              }
              return "";
            })
            .filter(Boolean)
            .join("; ")
        : undefined;
    return new ApiError(
      error?.error?.code ?? error?.code ?? `HTTP_${response.status}`,
      error?.error?.message ??
        error?.message ??
        detailMessage ??
        `Request failed with status ${response.status}`,
      error?.error?.details ?? error?.detail
    );
  } catch {
    return new ApiError(`HTTP_${response.status}`, `Request failed with status ${response.status}`);
  }
}

type ApiRequestOptions = RequestInit & {
  timeoutMs?: number;
  retryCount?: number;
};

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

export async function apiRequest<T>(path: string, options?: ApiRequestOptions): Promise<T> {
  const token = getToken();
  const isFormData = options?.body instanceof FormData;
  const timeoutMs = options?.timeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS;
  const retryCount = options?.retryCount ?? 0;

  const { signal, cancel } = withTimeoutSignal(timeoutMs, options?.signal ?? undefined);

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...options,
      signal,
      headers: {
        ...(isFormData ? {} : { "Content-Type": "application/json" }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options?.headers,
      },
    });
  } catch (error) {
    cancel();
    if (error instanceof DOMException && error.name === "AbortError") {
      if (retryCount > 0) {
        return apiRequest<T>(path, { ...options, retryCount: retryCount - 1 });
      }
      throw new ApiError("REQUEST_TIMEOUT", "Request timed out. Please try again.");
    }
    if (retryCount > 0) {
      return apiRequest<T>(path, { ...options, retryCount: retryCount - 1 });
    }
    throw new ApiError("NETWORK_ERROR", "Could not reach server. Please check connection.");
  } finally {
    cancel();
  }

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
    throw await parseApiError(response);
  }

  const payload = (await response.json()) as ApiResponse<T>;
  return payload.data;
}

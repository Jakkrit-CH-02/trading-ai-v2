import axios, { AxiosError } from "axios";
import { useAuthStore } from "../stores/authStore";

/**
 * Cross-service wire envelope. Mirrors apps/backend/internal/api/response.go.
 *
 *   success: { data: T,    error: null }
 *   error:   { data: null, error: { code: string, message: string, details?: unknown } }
 *
 * Conventions enforced everywhere:
 *  - timestamps: int64 Unix milliseconds, UTC (number on the wire)
 *  - money:      decimal string, e.g. "0.00012345" (never JS number)
 *  - ids:        lowercase ULID
 *  - error.code: stable string (e.g. "risk_rejected", "not_found",
 *                "validation_failed", "forbidden", "internal")
 */
export interface ApiEnvelopeError {
  code: string;
  message: string;
  details?: unknown;
}

export type ApiEnvelope<T> =
  | { data: T; error: null }
  | { data: null; error: ApiEnvelopeError };

/** Money values are transported as decimal strings. */
export type MoneyString = string;

/** Unix milliseconds, UTC. */
export type TimestampMs = number;

/** Lowercase ULID. */
export type Ulid = string;

/** Normalized error surfaced to callers after the response interceptor. */
export interface ApiError {
  status: number;
  code?: string;
  message: string;
  details?: unknown;
}

const resolvedBaseURL =
  import.meta.env.VITE_API_BASE_URL !== undefined
    ? import.meta.env.VITE_API_BASE_URL
    : "http://localhost:8080";

export const api = axios.create({
  baseURL: resolvedBaseURL,
  timeout: 15_000,
  headers: {
    "Content-Type": "application/json",
  },
});

api.interceptors.request.use((cfg) => {
  const token = useAuthStore.getState().token;
  if (token) {
    cfg.headers.set("Authorization", `Bearer ${token}`);
  } else {
    cfg.headers.delete("Authorization");
  }
  return cfg;
});

api.interceptors.response.use(
  (res) => res,
  (err: AxiosError<ApiEnvelope<unknown>>) => {
    const data = err.response?.data;
    const envelopeError =
      data && typeof data === "object" && "error" in data ? data.error : null;
    const normalized: ApiError = {
      status: err.response?.status ?? 0,
      code: envelopeError?.code,
      message:
        envelopeError?.message ?? err.message ?? "Unknown network error",
      details: envelopeError?.details,
    };
    const reqPath = err.config?.url ?? "";
    if (normalized.status === 401 && !reqPath.includes("/api/auth/login")) {
      useAuthStore.getState().clear();
    }
    return Promise.reject(normalized);
  },
);

import axios, { AxiosError } from "axios";

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

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8080",
  timeout: 15_000,
  headers: {
    "Content-Type": "application/json",
  },
});

api.interceptors.request.use((cfg) => {
  const token = import.meta.env.VITE_API_TOKEN ?? "dev";
  cfg.headers.set("Authorization", `Bearer ${token}`);
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
    return Promise.reject(normalized);
  },
);

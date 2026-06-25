/**
 * Minimal API client. Injects the Clerk session token as a bearer on every call
 * and surfaces the backend's `{code, message, details}` error envelope as an
 * `ApiError`. In dev the Vite proxy forwards `/api` → FastAPI, so `API_BASE` is
 * empty (same-origin); set `VITE_API_BASE_URL` for split deployments.
 */

import type { Me } from '../session/session';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '';

export type TokenGetter = () => Promise<string | null>;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details: unknown = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export interface ApiRequest {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  /** JSON request body; serialised + sent with a JSON content-type. */
  body?: unknown;
}

/**
 * Make an API call, injecting the bearer token and surfacing the backend's
 * `{code, message, details}` envelope as an `ApiError`. A 204/empty body
 * resolves to `undefined`. This is the single fetch seam every feature reuses.
 */
export async function apiFetch<T>(
  path: string,
  getToken: TokenGetter,
  req: ApiRequest = {},
): Promise<T> {
  // Only same-origin relative paths: we attach a bearer token, so an absolute or
  // protocol-relative URL could exfiltrate it to another host.
  if (!path.startsWith('/') || path.startsWith('//') || /^[a-z]+:/i.test(path)) {
    throw new ApiError(0, 'invalid_path', 'API path must be a relative "/..." path');
  }
  const token = await getToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (req.body !== undefined) headers['Content-Type'] = 'application/json';
  const res = await fetch(`${API_BASE}${path}`, {
    method: req.method ?? 'GET',
    headers,
    body: req.body !== undefined ? JSON.stringify(req.body) : undefined,
  });
  if (!res.ok) {
    let code = 'error';
    let message = `Request failed (${res.status})`;
    let details: unknown = null;
    try {
      const body: unknown = await res.json();
      if (body && typeof body === 'object') {
        const env = body as { code?: unknown; message?: unknown; details?: unknown };
        if (typeof env.code === 'string') code = env.code;
        if (typeof env.message === 'string') message = env.message;
        if ('details' in env) details = env.details;
      }
    } catch {
      /* non-JSON error body — keep the generic message */
    }
    throw new ApiError(res.status, code, message, details);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Fetch the session bootstrap (`GET /api/me`). */
export function fetchMe(getToken: TokenGetter): Promise<Me> {
  return apiFetch<Me>('/api/me', getToken);
}

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

async function getJson<T>(path: string, getToken: TokenGetter): Promise<T> {
  const token = await getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
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
  return (await res.json()) as T;
}

/** Fetch the session bootstrap (`GET /api/me`). */
export function fetchMe(getToken: TokenGetter): Promise<Me> {
  return getJson<Me>('/api/me', getToken);
}

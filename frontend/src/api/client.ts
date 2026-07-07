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

/** Reject relative-only paths: we attach a bearer token, so an absolute or
 * protocol-relative URL could exfiltrate it to another host. */
function assertRelativePath(path: string): void {
  if (!path.startsWith('/') || path.startsWith('//') || /^[a-z]+:/i.test(path)) {
    throw new ApiError(0, 'invalid_path', 'API path must be a relative "/..." path');
  }
}

async function bearerHeader(getToken: TokenGetter): Promise<Record<string, string>> {
  const token = await getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Parse a success body, keeping the ApiError contract: 204/empty resolves to
 * `undefined`; a non-JSON body throws an `ApiError`, never a raw SyntaxError. */
async function parseJsonBody<T>(res: Response): Promise<T> {
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  if (!text) return undefined as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new ApiError(res.status, 'invalid_response', `Invalid JSON response (${res.status})`);
  }
}

/** Map a non-OK response onto the backend's `{code, message, details}` envelope. */
async function rejectFromResponse(res: Response): Promise<never> {
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

/**
 * Make a JSON API call, injecting the bearer token and surfacing the backend's
 * `{code, message, details}` envelope as an `ApiError`. A 204/empty body
 * resolves to `undefined`. This is the single fetch seam every feature reuses.
 */
export async function apiFetch<T>(
  path: string,
  getToken: TokenGetter,
  req: ApiRequest = {},
): Promise<T> {
  assertRelativePath(path);
  let res: Response;
  try {
    // Inside the try so a rejected token fetch (expired session / Clerk refresh
    // failure) is normalised to the ApiError contract, not thrown raw.
    const headers = await bearerHeader(getToken);
    if (req.body !== undefined) headers['Content-Type'] = 'application/json';
    res = await fetch(`${API_BASE}${path}`, {
      method: req.method ?? 'GET',
      headers,
      body: req.body !== undefined ? JSON.stringify(req.body) : undefined,
    });
  } catch (cause) {
    // Offline / DNS / CORS / token-fetch rejection — normalise to the ApiError
    // contract so every caller handles failures the same way.
    throw new ApiError(0, 'network_error', 'Network request failed', cause);
  }
  if (!res.ok) await rejectFromResponse(res);
  return parseJsonBody<T>(res);
}

/**
 * Upload via `multipart/form-data` (file uploads, M1.2). The browser sets the
 * `Content-Type` boundary itself, so we must NOT set it here.
 */
export async function apiUpload<T>(
  path: string,
  getToken: TokenGetter,
  formData: FormData,
): Promise<T> {
  assertRelativePath(path);
  let res: Response;
  try {
    const headers = await bearerHeader(getToken);
    res = await fetch(`${API_BASE}${path}`, { method: 'POST', headers, body: formData });
  } catch (cause) {
    throw new ApiError(0, 'network_error', 'Network request failed', cause);
  }
  if (!res.ok) await rejectFromResponse(res);
  return parseJsonBody<T>(res);
}

/** Fetch a binary response (file download, M1.2) as a `Blob`, with auth. */
export async function apiDownload(path: string, getToken: TokenGetter): Promise<Blob> {
  assertRelativePath(path);
  let res: Response;
  try {
    const headers = await bearerHeader(getToken);
    res = await fetch(`${API_BASE}${path}`, { headers });
  } catch (cause) {
    throw new ApiError(0, 'network_error', 'Network request failed', cause);
  }
  if (!res.ok) await rejectFromResponse(res);
  return res.blob();
}

/** Fetch the session bootstrap (`GET /api/me`). */
export function fetchMe(getToken: TokenGetter): Promise<Me> {
  return apiFetch<Me>('/api/me', getToken);
}

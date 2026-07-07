/**
 * Error → user-facing message mapping, localized. The single place every page
 * turns a caught error into display text: backend envelope messages pass
 * through; client-side fallbacks (offline, non-envelope responses, unexpected
 * throws) get translated instead of leaking hard-coded English.
 */

import type { TFunction } from 'i18next';

import { ApiError } from './client';

export function errorMessage(e: unknown, t: TFunction): string {
  if (e instanceof ApiError) {
    if (e.code === 'network_error') return t('errors.network');
    // 'error' is rejectFromResponse's fallback when the body wasn't the
    // backend's {code, message, details} envelope — its message is the
    // hard-coded English default, so translate instead of surfacing it.
    if (e.code === 'error' || e.code === 'invalid_response') {
      return t('errors.request_failed', { status: e.status });
    }
    return e.message;
  }
  return t('errors.unexpected');
}

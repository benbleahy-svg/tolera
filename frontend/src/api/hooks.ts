/**
 * Shared API-client hook scaffolding. Every feature's `useXxxApi` binds its call
 * table to the Clerk session token exactly once; this hook is that one seam, so
 * new features don't re-copy the `useAuth → useMemo` plumbing (and tests keep
 * mocking the feature module wholesale, no Clerk).
 */

import { useMemo } from 'react';
import { useAuth } from '@clerk/clerk-react';

import type { TokenGetter } from './client';

/**
 * Bind an API-client factory to the current Clerk session token. The factory
 * must be a stable (module-level) function — the client is memoised on it.
 */
export function useApiClient<T>(factory: (getToken: TokenGetter) => T): T {
  const { getToken } = useAuth();
  return useMemo(() => factory(() => getToken()), [factory, getToken]);
}

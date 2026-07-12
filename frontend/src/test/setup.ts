import '@testing-library/jest-dom/vitest';

import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// Some Node/jsdom combinations (e.g. Node 26 locally) ship a jsdom window
// without Web Storage. Polyfill a spec-shaped localStorage so storage-backed
// behaviors (viewer sidebar persistence, locale toggle) stay testable
// everywhere, not only in CI's environment.
if (typeof globalThis.localStorage === 'undefined' || globalThis.localStorage === null) {
  const store = new Map<string, string>();
  const storage: Storage = {
    get length() {
      return store.size;
    },
    clear: () => store.clear(),
    getItem: (key) => store.get(key) ?? null,
    key: (index) => [...store.keys()][index] ?? null,
    removeItem: (key) => {
      store.delete(key);
    },
    setItem: (key, value) => {
      store.set(key, String(value));
    },
  };
  Object.defineProperty(globalThis, 'localStorage', { value: storage, configurable: true });
  if (typeof window !== 'undefined') {
    Object.defineProperty(window, 'localStorage', { value: storage, configurable: true });
  }
}

// Without `globals: true`, Testing Library can't auto-register cleanup, so
// unmount after every test to keep the jsdom document from accumulating renders.
afterEach(() => {
  cleanup();
});

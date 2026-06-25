import '@testing-library/jest-dom/vitest';

import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// Without `globals: true`, Testing Library can't auto-register cleanup, so
// unmount after every test to keep the jsdom document from accumulating renders.
afterEach(() => {
  cleanup();
});

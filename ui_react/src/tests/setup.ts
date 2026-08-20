/**
 * @file setup.ts
 * @description 全域測試環境設定檔，載入 jest-dom 斷言庫並補齊 happy-dom 瀏覽器物件模擬。
 */
import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

// Automatically unmount React trees after each test
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// Polyfill DOM APIs in happy-dom
if (typeof window !== 'undefined') {
  window.scrollTo = vi.fn();
  window.matchMedia =
    window.matchMedia ||
    vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
}

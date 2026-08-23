/**
 * File: react_entrypoint_registry.test.ts
 * Description: 驗證 LINE successor 收斂後 12 個 canonical React entry 身分。
 */
import { describe, expect, it } from 'vitest';
import { NAV_ITEMS } from '../components/MasterLayout';

const EXPECTED_HASHES = [
  'order-tracker', 'orders', 'scheduling', 'staff', 'data-import',
  'line-management', 'reports', 'finance', 'anomalies', 'data-browser',
  'account-management', 'system-status',
] as const;

describe('React entrypoint registry', () => {
  it('保留 12 個 canonical 管理端 entry，且沒有重複 identity', () => {
    const pages = NAV_ITEMS.map((item) => item.id);
    expect(new Set(pages).size).toBe(pages.length);
    expect(new Set(pages)).toEqual(new Set(EXPECTED_HASHES));
  });
});

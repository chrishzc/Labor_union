/**
 * File: staff_directory_adapter.test.ts
 * Description: 驗證 Staff 摘要 adapter 只映射 id、name、phone 並保留 null unavailable 語意。
 */
import { describe, expect, it } from 'vitest';
import {
  adaptStaffDirectoryPage,
  adaptStaffDirectorySummary,
} from '../adapters/staff/staff_directory_adapter';
import { STAFF_PAGE_ONE } from './fixtures/staff/staff_directory_contract_fixtures';

describe('staff directory adapter', () => {
  it('maps only the approved summary fields', () => {
    expect(adaptStaffDirectorySummary(STAFF_PAGE_ONE.items[0])).toEqual({
      id: 11,
      name: '去敏人員甲',
      phone: '09********',
      displayName: '去敏人員甲',
      displayPhone: '09********',
    });
  });

  it('renders nullable fields as unavailable labels without business defaults', () => {
    const page = adaptStaffDirectoryPage(STAFF_PAGE_ONE);

    expect(page.items[1].displayName).toBe('服務人員摘要 #12');
    expect(page.items[1].displayPhone).toBe('後端未提供');
    expect(page.nextCursor).toBe(12);
    expect(Object.keys(page.items[1]).sort()).toEqual([
      'displayName',
      'displayPhone',
      'id',
      'name',
      'phone',
    ]);
  });
});


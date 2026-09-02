/**
 * File: staff_directory_adapter.test.ts
 * Description: 驗證 Staff 摘要 adapter 只映射名冊允許欄位，並中性呈現合法 null。
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
      education: '大學',
      displayName: '去敏人員甲',
      displayPhone: '09********',
      displayEducation: '大學',
    });
  });

  it('renders nullable fields neutrally without inventing business defaults', () => {
    const page = adaptStaffDirectoryPage(STAFF_PAGE_ONE);

    expect(page.items[1].displayName).toBe('服務人員摘要 #12');
    expect(page.items[1].displayPhone).toBe('—');
    expect(page.items[1].displayEducation).toBe('—');
    expect(page.nextCursor).toBe(12);
    expect(Object.keys(page.items[1]).sort()).toEqual([
      'displayEducation',
      'displayName',
      'displayPhone',
      'education',
      'id',
      'name',
      'phone',
    ]);
  });
});

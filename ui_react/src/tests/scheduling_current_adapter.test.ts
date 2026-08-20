/**
 * File: scheduling_current_adapter.test.ts
 * Description: 驗證 Scheduling adapter 只映射 server occupancy、日期與 lineage view。
 */
import { describe, expect, it } from 'vitest';
import { adaptStaffDirectorySummary } from '../adapters/staff/staff_directory_adapter';
import {
  adaptSchedulingProjection,
  matchesSchedulingFilter,
} from '../adapters/scheduling/scheduling_current_adapter';
import { SCHEDULING_PROJECTION_READY } from './fixtures/scheduling/scheduling_current_contract_fixtures';

describe('scheduling current adapter', () => {
  it('maps server days and occupancy kinds without computing business dates', () => {
    const staff = adaptStaffDirectorySummary({ id: 11, name: '去敏人員甲', phone: null });
    const row = adaptSchedulingProjection(staff, SCHEDULING_PROJECTION_READY);

    expect(row.displayName).toBe('去敏人員甲');
    expect(row.days.map((day) => day.tone)).toEqual(['active', 'buffer', 'available']);
    expect(row.days[0].caseLabels).toEqual(['CASE-SCH-001']);
    expect(row.projectionToken).toBe('a'.repeat(64));
    expect(matchesSchedulingFilter(row, 'active')).toBe(true);
    expect(matchesSchedulingFilter(row, 'waiting')).toBe(false);
    expect(matchesSchedulingFilter(row, 'leave')).toBe(false);
  });
});

/**
 * File: scheduling_current_adapter.test.ts
 * Description: 驗證 Scheduling adapter 映射 server occupancy、不可服務原因與 lineage view。
 */
import { describe, expect, it } from 'vitest';
import type { SchedulingCurrentProjection } from '../api/scheduling/scheduling_current_schemas';
import { adaptStaffDirectorySummary } from '../adapters/staff/staff_directory_adapter';
import {
  adaptSchedulingProjection,
  matchesSchedulingFilter,
} from '../adapters/scheduling/scheduling_current_adapter';
import { SCHEDULING_PROJECTION_READY } from './fixtures/scheduling/scheduling_current_contract_fixtures';

describe('scheduling current adapter', () => {
  it('maps server days and occupancy kinds without computing business dates', () => {
    const staff = adaptStaffDirectorySummary({ id: 11, name: '去敏人員甲', phone: null, education: null });
    const row = adaptSchedulingProjection(staff, SCHEDULING_PROJECTION_READY);

    expect(row.displayName).toBe('去敏人員甲');
    expect(row.days.map((day) => day.tone)).toEqual(['active', 'rest', 'available']);
    expect(row.days[0].caseLabels).toEqual(['CASE-SCH-001']);
    expect(row.projectionToken).toBe('a'.repeat(64));
    expect(matchesSchedulingFilter(row, 'active')).toBe(true);
    expect(matchesSchedulingFilter(row, 'waiting')).toBe(false);
    expect(matchesSchedulingFilter(row, 'leave')).toBe(false);
  });

  it('preserves server lifecycle status instead of labeling completed service as active', () => {
    const staff = adaptStaffDirectorySummary({ id: 11, name: '去敏人員甲', phone: null, education: null });
    const completedProjection = {
      ...SCHEDULING_PROJECTION_READY,
      assignments: SCHEDULING_PROJECTION_READY.assignments.map((assignment) => ({
        ...assignment,
        status: 'completed' as const,
      })),
      days: SCHEDULING_PROJECTION_READY.days.map((day) => ({
        ...day,
        entries: day.entries
          .filter((entry) => entry.occupancy_kind !== 'assignment_buffer')
          .map((entry) => ({ ...entry, assignment_status: 'completed' as const })),
        available: day.entries.every((entry) => entry.occupancy_kind === 'assignment_buffer')
          ? true
          : day.available,
      })),
    };

    const row = adaptSchedulingProjection(staff, completedProjection);

    expect(row.assignmentStatuses).toEqual(['completed']);
    expect(row.days[0].statusLabel).toBe('服務已結束');
    expect(matchesSchedulingFilter(row, 'active')).toBe(false);
  });

  it('includes assignment buffer occupancy in the waiting filter', () => {
    const staff = adaptStaffDirectorySummary({ id: 11, name: '去敏人員甲', phone: null, education: null });
    const bufferProjection = {
      ...SCHEDULING_PROJECTION_READY,
      days: SCHEDULING_PROJECTION_READY.days.map((day, index) => index === 0 ? {
        ...day,
        entries: day.entries.map((entry) => ({
          ...entry,
          occupancy_kind: 'assignment_buffer' as const,
          assignment_status: 'planned' as const,
        })),
      } : day),
    };

    const row = adaptSchedulingProjection(staff, bufferProjection);

    expect(row.occupancyKinds).toContain('assignment_buffer');
    expect(matchesSchedulingFilter(row, 'waiting')).toBe(true);
  });

  it('shows the typed unavailability kind and reason on calendar days', () => {
    const staff = adaptStaffDirectorySummary({ id: 11, name: '去敏人員甲', phone: null, education: null });
    const unavailableProjection: SchedulingCurrentProjection = {
      ...SCHEDULING_PROJECTION_READY,
      assignments: [],
      days: SCHEDULING_PROJECTION_READY.days.map((day, index) => index === 0 ? {
        ...day,
        entries: [{
          occupancy_kind: 'staff_unavailability' as const,
          case_no: null,
          assignment_id: null,
          assignment_status: null,
          lock_id: null,
          segment_id: null,
          availability_block_id: 91,
          unavailability_kind: 'long_leave',
          unavailability_reason: '返鄉休息',
        }],
      } : day),
    };

    const row = adaptSchedulingProjection(staff, unavailableProjection);

    expect(row.days[0].statusLabel).toBe('長假：返鄉休息');
    expect(row.loadedStatusLabel).toBe('長假：返鄉休息');
  });
});

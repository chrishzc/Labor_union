/**
 * File: scheduling_current_adapter.ts
 * Description: 將 server Scheduling projection 映射為甘特月曆 view model，禁止日期與資格推導。
 */
import type { StaffDirectoryCardViewModel } from '../staff/staff_directory_adapter';
import type {
  SchedulingCurrentDay,
  SchedulingCurrentProjection,
  SchedulingOccupancyKind,
} from '../../api/scheduling/scheduling_current_schemas';

export type SchedulingLoadedFilter = 'all' | 'active' | 'waiting' | 'leave';
export type SchedulingDayTone =
  | 'available'
  | 'active'
  | 'rest'
  | 'buffer'
  | 'waiting'
  | 'leave';

export interface SchedulingDayViewModel {
  date: string;
  dayLabel: string;
  weekdayLabel: string;
  available: boolean;
  tone: SchedulingDayTone;
  statusLabel: string;
  caseLabels: string[];
  occupancyKinds: SchedulingOccupancyKind[];
}

export interface SchedulingCalendarRowViewModel {
  staffId: number;
  displayName: string;
  evaluatedAt: string;
  projectionToken: string;
  projectionTokenLabel: string;
  days: SchedulingDayViewModel[];
  occupancyKinds: SchedulingOccupancyKind[];
  loadedStatusLabel: string;
}

const WEEKDAY_FORMATTER = new Intl.DateTimeFormat('zh-TW', {
  weekday: 'short',
  timeZone: 'UTC',
});

function presentationDate(isoDate: string): Date {
  return new Date(`${isoDate}T00:00:00Z`);
}

function unique<T>(values: readonly T[]): T[] {
  return [...new Set(values)];
}

function dayTone(kinds: readonly SchedulingOccupancyKind[]): SchedulingDayTone {
  if (kinds.includes('staff_unavailability')) return 'leave';
  if (kinds.includes('official_workday')) return 'active';
  if (kinds.includes('waiting_deposit_service')) return 'waiting';
  if (
    kinds.includes('assignment_buffer') ||
    kinds.includes('waiting_deposit_buffer')
  ) {
    return 'buffer';
  }
  if (kinds.includes('assignment_rest')) return 'rest';
  return 'available';
}

function toneLabel(tone: SchedulingDayTone): string {
  switch (tone) {
    case 'active':
      return '正式服務日';
    case 'rest':
      return '正式指派休息日';
    case 'buffer':
      return 'Server buffer 占用';
    case 'waiting':
      return '待成立檔期占用';
    case 'leave':
      return '服務人員不可服務';
    case 'available':
      return 'Server 顯示可用';
  }
}

export function adaptSchedulingDay(day: SchedulingCurrentDay): SchedulingDayViewModel {
  const date = presentationDate(day.calendar_date);
  const kinds = unique(day.entries.map((entry) => entry.occupancy_kind));
  const tone = dayTone(kinds);
  return {
    date: day.calendar_date,
    dayLabel: String(date.getUTCDate()),
    weekdayLabel: WEEKDAY_FORMATTER.format(date),
    available: day.available,
    tone,
    statusLabel: toneLabel(tone),
    caseLabels: unique(
      day.entries
        .map((entry) => entry.case_no)
        .filter((caseNo): caseNo is string => caseNo !== null)
    ).sort(),
    occupancyKinds: kinds,
  };
}

function loadedStatusLabel(kinds: readonly SchedulingOccupancyKind[]): string {
  if (kinds.includes('staff_unavailability')) return '請假／暫停服務';
  if (
    kinds.includes('waiting_deposit_service') ||
    kinds.includes('waiting_deposit_buffer')
  ) {
    return '待成立檔期占用';
  }
  if (
    kinds.includes('official_workday') ||
    kinds.includes('assignment_rest') ||
    kinds.includes('assignment_buffer')
  ) {
    return '正式指派占用';
  }
  return '目前區間無占用';
}

export function adaptSchedulingProjection(
  staff: StaffDirectoryCardViewModel,
  projection: SchedulingCurrentProjection
): SchedulingCalendarRowViewModel {
  const days = projection.days.map(adaptSchedulingDay);
  const kinds = unique(days.flatMap((day) => day.occupancyKinds));
  return {
    staffId: staff.id,
    displayName: staff.displayName,
    evaluatedAt: projection.evaluated_at,
    projectionToken: projection.projection_token,
    projectionTokenLabel: `${projection.projection_token.slice(0, 12)}…`,
    days,
    occupancyKinds: kinds,
    loadedStatusLabel: loadedStatusLabel(kinds),
  };
}

export function matchesSchedulingFilter(
  row: SchedulingCalendarRowViewModel,
  filter: SchedulingLoadedFilter
): boolean {
  if (filter === 'all') return true;
  if (filter === 'leave') {
    return row.occupancyKinds.includes('staff_unavailability');
  }
  if (filter === 'waiting') {
    return (
      row.occupancyKinds.includes('waiting_deposit_service') ||
      row.occupancyKinds.includes('waiting_deposit_buffer')
    );
  }
  return (
    row.occupancyKinds.includes('official_workday') ||
    row.occupancyKinds.includes('assignment_rest') ||
    row.occupancyKinds.includes('assignment_buffer')
  );
}

/**
 * File: scheduling_current_adapter.ts
 * Description: 映射 server Scheduling 甘特月曆並保留不可服務類別與原因，禁止日期或資格推導。
 */
import type { StaffDirectoryCardViewModel } from '../staff/staff_directory_adapter';
import type {
  SchedulingAssignmentStatus,
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
  assignmentStatuses: SchedulingAssignmentStatus[];
}

export interface SchedulingCalendarRowViewModel {
  staffId: number;
  displayName: string;
  evaluatedAt: string;
  projectionToken: string;
  projectionTokenLabel: string;
  days: SchedulingDayViewModel[];
  occupancyKinds: SchedulingOccupancyKind[];
  assignmentStatuses: SchedulingAssignmentStatus[];
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

function assignmentStatusLabel(
  statuses: readonly SchedulingAssignmentStatus[],
  rest: boolean
): string | null {
  if (statuses.includes('active')) return rest ? '服務中排休' : '服務中';
  if (statuses.includes('planned')) return rest ? '已排定休息日' : '已排定服務';
  if (statuses.includes('completed')) return rest ? '已結束排休' : '服務已結束';
  return null;
}

function toneLabel(
  tone: SchedulingDayTone,
  statuses: readonly SchedulingAssignmentStatus[],
  unavailabilityLabels: readonly string[]
): string {
  switch (tone) {
    case 'active':
      return assignmentStatusLabel(statuses, false) ?? '正式服務日';
    case 'rest':
      return assignmentStatusLabel(statuses, true) ?? '正式指派休息日';
    case 'buffer':
      return '7天防撞期 Buffer 鎖定';
    case 'waiting':
      return '待成立檔期占用';
    case 'leave':
      return unavailabilityLabels.join('、') || '服務人員不可服務';
    case 'available':
      return 'Server 顯示可用';
  }
}

function unavailabilityLabel(
  kind: string | null,
  reason: string | null
): string | null {
  if (reason === null) return null;
  if (kind === 'long_leave') return `長假：${reason}`;
  if (kind === 'paused_service') return `暫停接案：${reason}`;
  return `不可服務：${reason}`;
}

export function adaptSchedulingDay(day: SchedulingCurrentDay): SchedulingDayViewModel {
  const date = presentationDate(day.calendar_date);
  const kinds = unique(day.entries.map((entry) => entry.occupancy_kind));
  const statuses = unique(
    day.entries
      .map((entry) => entry.assignment_status)
      .filter((status): status is SchedulingAssignmentStatus => status !== null)
  );
  const unavailabilityLabels = unique(
    day.entries
      .map((entry) => unavailabilityLabel(
        entry.unavailability_kind,
        entry.unavailability_reason
      ))
      .filter((label): label is string => label !== null)
  );
  const tone = dayTone(kinds);
  return {
    date: day.calendar_date,
    dayLabel: String(date.getUTCDate()),
    weekdayLabel: WEEKDAY_FORMATTER.format(date),
    available: day.available,
    tone,
    statusLabel: toneLabel(tone, statuses, unavailabilityLabels),
    caseLabels: unique(
      day.entries
        .map((entry) => entry.case_no)
        .filter((caseNo): caseNo is string => caseNo !== null)
    ).sort(),
    occupancyKinds: kinds,
    assignmentStatuses: statuses,
  };
}

function loadedStatusLabel(
  kinds: readonly SchedulingOccupancyKind[],
  statuses: readonly SchedulingAssignmentStatus[],
  days: readonly SchedulingDayViewModel[]
): string {
  if (kinds.includes('staff_unavailability')) {
    const labels = unique(
      days
        .filter((day) => day.occupancyKinds.includes('staff_unavailability'))
        .map((day) => day.statusLabel)
    );
    return labels.join('、') || '請假／暫停服務';
  }
  if (
    kinds.includes('waiting_deposit_service') ||
    kinds.includes('waiting_deposit_buffer')
  ) {
    return '待成立檔期占用';
  }
  if (statuses.includes('active')) return '正常履約中';
  if (statuses.includes('planned')) return '已排定待開始';
  if (statuses.includes('completed')) return '服務已完成';
  if (kinds.includes('assignment_buffer')) return '七日防撞期占用';
  return '目前區間無占用';
}

export function adaptSchedulingProjection(
  staff: StaffDirectoryCardViewModel,
  projection: SchedulingCurrentProjection
): SchedulingCalendarRowViewModel {
  const days = projection.days.map(adaptSchedulingDay);
  const kinds = unique(days.flatMap((day) => day.occupancyKinds));
  const statuses = unique(projection.assignments.map((assignment) => assignment.status));
  return {
    staffId: staff.id,
    displayName: staff.displayName,
    evaluatedAt: projection.evaluated_at,
    projectionToken: projection.projection_token,
    projectionTokenLabel: `${projection.projection_token.slice(0, 12)}…`,
    days,
    occupancyKinds: kinds,
    assignmentStatuses: statuses,
    loadedStatusLabel: loadedStatusLabel(kinds, statuses, days),
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
      row.occupancyKinds.includes('assignment_buffer') ||
      row.occupancyKinds.includes('waiting_deposit_service') ||
      row.occupancyKinds.includes('waiting_deposit_buffer')
    );
  }
  return row.assignmentStatuses.includes('active');
}

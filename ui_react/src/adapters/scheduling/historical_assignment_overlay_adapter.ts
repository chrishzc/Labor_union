import type { StaffMonthlySchedule } from '../../api/scheduling/staff_monthly_schedule_client';
import type { SchedulingCurrentProjection } from '../../api/scheduling/scheduling_current_schemas';

type CalendarDay = StaffMonthlySchedule['days'][number];

/** Merge read projections by provenance and service interval, never by person/day alone. */
export function mergeStaffCalendarDays(
  monthly: StaffMonthlySchedule | undefined,
  canonical: SchedulingCurrentProjection | undefined,
  staffId: number,
  year: number,
  month: number,
): StaffMonthlySchedule {
  const statuses = {
    official_workday: 'working', assignment_rest: 'resting',
    historical_reservation: 'historical_reservation', assignment_buffer: 'buffer',
    waiting_deposit_service: 'waiting_deposit_lock', waiting_deposit_buffer: 'buffer',
    staff_unavailability: 'staff_unavailability',
  } as const;
  const days: CalendarDay[] = [];
  for (const day of canonical?.days ?? []) {
    for (const entry of day.entries) {
      days.push({
        work_date: day.calendar_date, staff_id: staffId,
        status: statuses[entry.occupancy_kind],
        assignment_id: entry.assignment_id, case_no: entry.case_no,
        lock_id: entry.lock_id, unavailability_block_id: entry.availability_block_id,
        unavailability_reason: entry.unavailability_reason,
        unavailability_kind: entry.unavailability_kind === 'long_leave' || entry.unavailability_kind === 'paused_service'
          ? entry.unavailability_kind : null,
        service_date: entry.service_start_at?.slice(0, 10) ?? day.calendar_date,
        starts_at: entry.service_start_at, ends_at: entry.service_end_at,
        service_hours_override: entry.service_hours_override,
        is_work_day: entry.occupancy_kind === 'official_workday'
          && (!entry.service_start_at || entry.service_start_at.slice(0, 10) === day.calendar_date),
        is_double_pay: false,
      });
    }
  }
  const sameSource = (left: CalendarDay, right: CalendarDay): boolean =>
    left.status === right.status && left.case_no === right.case_no
    && (left.assignment_id ?? null) === (right.assignment_id ?? null)
    && (left.lock_id ?? null) === (right.lock_id ?? null)
    && (left.unavailability_block_id ?? null) === (right.unavailability_block_id ?? null)
    && left.work_date === right.work_date
    && (left.service_date ?? left.work_date) === (right.service_date ?? right.work_date);
  for (const day of monthly?.days ?? []) {
    if (day.status === 'available') continue;
    const projectedDay = day.service_date && day.service_date !== day.work_date
      ? { ...day, is_work_day: false } : day;
    const existing = days.findIndex(candidate => sameSource(candidate, day)
      && (!candidate.starts_at || !day.starts_at || candidate.starts_at === day.starts_at)
      && (!candidate.ends_at || !day.ends_at || candidate.ends_at === day.ends_at));
    if (existing < 0) days.push(projectedDay);
    else days[existing] = { ...day, ...days[existing],
      starts_at: days[existing].starts_at ?? day.starts_at,
      ends_at: days[existing].ends_at ?? day.ends_at,
      service_hours_override: days[existing].service_hours_override ?? day.service_hours_override,
      is_double_pay: day.is_double_pay,
      client_name: day.client_name, staff_name: day.staff_name, order_status: day.order_status,
    };
  }
  const unique = new Map<string, CalendarDay>();
  for (const day of days) {
    const key = [day.status, day.case_no, day.assignment_id, day.lock_id,
      day.unavailability_block_id, day.work_date, day.service_date ?? day.work_date,
      day.starts_at, day.ends_at, day.service_hours_override].join('|');
    if (!unique.has(key)) unique.set(key, day);
  }
  return { staff_id: staffId, year, month, days: [...unique.values()], schedule_map: {} };
}

export interface HistoricalAssignmentOverlay {
  assignmentId: number;
  caseNo: string;
  clientName: string;
  startDate: string;
  endDate: string;
}

export function adaptHistoricalAssignmentOverlays(source: StaffMonthlySchedule): HistoricalAssignmentOverlay[] {
  const rows = source.days.filter((day) => day.status === 'historical_assignment' && day.assignment_id && day.case_no && day.client_name);
  return rows.reduce<HistoricalAssignmentOverlay[]>((overlays, day) => {
    const previous = overlays.at(-1);
    const nextExpectedDate = previous
      ? new Date(`${previous.endDate}T00:00:00Z`).getTime() + 86_400_000
      : null;
    if (previous
      && nextExpectedDate === new Date(`${day.work_date}T00:00:00Z`).getTime()
      && previous.assignmentId === day.assignment_id
      && previous.caseNo === day.case_no
      && previous.clientName === day.client_name) {
      previous.endDate = day.work_date;
    } else {
      overlays.push({ assignmentId: day.assignment_id!, caseNo: day.case_no!, clientName: day.client_name!, startDate: day.work_date, endDate: day.work_date });
    }
    return overlays;
  }, []);
}

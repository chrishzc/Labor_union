import type { StaffMonthlySchedule } from '../../api/scheduling/staff_monthly_schedule_client';

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

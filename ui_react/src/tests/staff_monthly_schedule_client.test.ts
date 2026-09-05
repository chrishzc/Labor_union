/**
 * File: staff_monthly_schedule_client.test.ts
 * Description: Guards the display-only historical assignment monthly read model.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { staffMonthlyScheduleClient, type StaffMonthlySchedule } from '../api/scheduling/staff_monthly_schedule_client';
import { adaptHistoricalAssignmentOverlays } from '../adapters/scheduling/historical_assignment_overlay_adapter';

const monthlyResponse = {
  success: true,
  message: 'monthly schedule',
  data: {
    staff_id: 11,
    year: 2026,
    month: 8,
    days: [
      { work_date: '2026-08-01', status: 'historical_assignment', assignment_id: 91, case_no: 'HIS-001', client_name: '歷史客戶', staff_id: 11, order_status: 'completed', is_work_day: false, is_double_pay: false },
      { work_date: '2026-08-02', status: 'historical_assignment', assignment_id: 91, case_no: 'HIS-001', client_name: '歷史客戶', staff_id: 11, order_status: 'completed', is_work_day: false, is_double_pay: false },
      { work_date: '2026-08-03', status: 'available', staff_id: 11, is_work_day: false, is_double_pay: false },
      { work_date: '2026-08-04', status: 'historical_assignment', assignment_id: 92, case_no: 'HIS-002', client_name: '另一歷史客戶', staff_id: 11, order_status: 'completed', is_work_day: false, is_double_pay: false },
      ...Array.from({ length: 27 }, (_, index) => ({
        work_date: `2026-08-${String(index + 5).padStart(2, '0')}`,
        status: 'available' as const,
        staff_id: 11,
        is_work_day: false,
        is_double_pay: false,
      })),
    ],
    schedule_map: {},
  },
  error: null,
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } });
}

describe('staff monthly schedule client', () => {
  beforeEach(() => {
    sessionClient.setSession('schedule-token', { id: 9, username: 'scheduler', display_name: '排班員', role: 'admin' });
  });

  afterEach(() => {
    sessionClient.clearSession();
    vi.restoreAllMocks();
  });

  it('strictly decodes the monthly display model and preserves contiguous historical intervals', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(monthlyResponse));

    const projection = await staffMonthlyScheduleClient.query(11, 2026, 8);

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/staff/11/monthly-schedule?year=2026&month=8',
      expect.objectContaining({ method: 'GET' }),
    );
    expect(adaptHistoricalAssignmentOverlays(projection)).toEqual([
      { assignmentId: 91, caseNo: 'HIS-001', clientName: '歷史客戶', startDate: '2026-08-01', endDate: '2026-08-02' },
      { assignmentId: 92, caseNo: 'HIS-002', clientName: '另一歷史客戶', startDate: '2026-08-04', endDate: '2026-08-04' },
    ]);
  });

  it('fails closed on unknown historical-day fields instead of accepting a drifting response', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({
      ...monthlyResponse,
      data: {
        ...monthlyResponse.data,
        days: [{ ...monthlyResponse.data.days[0], leaked_server_field: true }],
      },
    }));

    await expect(staffMonthlyScheduleClient.query(11, 2026, 8)).rejects.toThrow('歷史指派月曆回應結構異常');
  });

  it('fails closed when a historical row claims to be a canonical work day', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({
      ...monthlyResponse,
      data: {
        ...monthlyResponse.data,
        days: monthlyResponse.data.days.map((day, index) => index === 0 ? { ...day, is_work_day: true } : day),
      },
    }));

    await expect(staffMonthlyScheduleClient.query(11, 2026, 8)).rejects.toThrow('歷史指派月曆回應結構異常');
  });

  it('does not merge the same assignment across a missing calendar date', () => {
    const projection: StaffMonthlySchedule = {
      ...monthlyResponse.data,
      days: monthlyResponse.data.days.filter((day) => day.work_date !== '2026-08-02').map((day) => (
        day.work_date === '2026-08-04'
          ? { ...day, status: day.status as StaffMonthlySchedule['days'][number]['status'], assignment_id: 91, case_no: 'HIS-001', client_name: '歷史客戶' }
          : { ...day, status: day.status as StaffMonthlySchedule['days'][number]['status'] }
      )),
    };

    expect(adaptHistoricalAssignmentOverlays(projection)).toEqual([
      { assignmentId: 91, caseNo: 'HIS-001', clientName: '歷史客戶', startDate: '2026-08-01', endDate: '2026-08-01' },
      { assignmentId: 91, caseNo: 'HIS-001', clientName: '歷史客戶', startDate: '2026-08-04', endDate: '2026-08-04' },
    ]);
  });
});

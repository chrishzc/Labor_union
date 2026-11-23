import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { calendarOccupancyDetailsByDate } from '../../../../../../../../../line/static/service-date-calendar.js';
import { OrderServiceDatesPanel } from '../../../../../../../components/OrderServiceDatesPanel';
import { orderMutationFlowStore } from '../../../../../../../adapters/orders/order_mutation_flow_store';
import { OrderMutationConflictError } from '../../../../../../../api/orders/order_mutation_errors';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';
import type { ServiceDateConfirmationQueryView, ServiceDateConfirmationPreviewView } from '../../../../../../../api/orders/order_mutation_schemas';
import type { ordersMutationClient } from '../../../../../../../api/orders/order_mutation_client';
vi.mock('../../../../../../../api/scheduling/holiday_client', () => ({ holidayClient: { query: vi.fn(async () => ({ holidays: [] })) } }));

describe('月嫂月曆實際開始日', () => {
  const date = '2026-10-02';

  it.each([
    { currentStart: null, otherStart: null, confirmed: false },
    { currentStart: null, otherStart: undefined, confirmed: false },
    { currentStart: null, otherStart: date, confirmed: false },
    { currentStart: undefined, otherStart: null, confirmed: false },
    { currentStart: undefined, otherStart: undefined, confirmed: false },
    { currentStart: undefined, otherStart: date, confirmed: false },
    { currentStart: date, otherStart: null, confirmed: false },
    { currentStart: date, otherStart: undefined, confirmed: false },
    { currentStart: date, otherStart: date, confirmed: true },
  ])('本案 $currentStart、他案 $otherStart 時顯示對應檔期標籤', ({ currentStart, otherStart, confirmed }) => {
    const occupancy = calendarOccupancyDetailsByDate([
      { date, caseNo: 'OFFICIAL', kind: 'official_workday', actualStartDate: otherStart },
      { date, caseNo: 'HISTORICAL', kind: 'historical_reservation', actualStartDate: otherStart },
      { date, caseNo: 'CURRENT', kind: 'official_workday', actualStartDate: currentStart },
    ], { caseNo: 'CURRENT', actualStartDate: currentStart, firstDate: '2026-10-01', lastDate: '2026-10-31' });

    expect(occupancy.get(date)?.map(({ caseNo, label }) => ({ caseNo, label }))).toEqual([
      { caseNo: 'OFFICIAL', label: confirmed ? '已有排班' : '歷史／暫定' },
      { caseNo: 'HISTORICAL', label: confirmed ? '服務檔期' : '歷史／暫定' },
    ]);
  });
});

const mocks = vi.hoisted(() => ({
  getActualStart: vi.fn(), getOrderCalendarDetail: vi.fn(), calculate: vi.fn(),
  getServiceDates: vi.fn(), previewServiceDates: vi.fn(), applyServiceDates: vi.fn(),
  previewActualStart: vi.fn(), applyActualStart: vi.fn(),
  previewOfficeSchedule: vi.fn(), saveHistoricalSchedule: vi.fn(), getAssignmentPlan: vi.fn(),
  queryStaffCalendar: vi.fn(),
}));
vi.mock('../../../../../../../api/scheduling/scheduling_current_client', () => ({
  schedulingCurrentClient: { queryCurrentCalendar: mocks.queryStaffCalendar },
}));
vi.mock('../../../../../../../api/orders/order_query_client', () => ({ ordersQueryClient: {
  getActualStart: mocks.getActualStart, getOrderCalendarDetail: mocks.getOrderCalendarDetail,
  getAssignmentPlan: mocks.getAssignmentPlan,
} }));
vi.mock('../../../../../../../api/orders/order_mutation_client', () => ({
  previewOfficeSchedule: mocks.previewOfficeSchedule,
  saveHistoricalSchedule: mocks.saveHistoricalSchedule,
  ordersMutationClient: {
  getServiceDates: mocks.getServiceDates, previewServiceDates: mocks.previewServiceDates, applyServiceDates: mocks.applyServiceDates,
} }));
vi.mock('../../../../../../../api/orders/order_actual_start_client', () => ({ orderActualStartClient: {
  preview: mocks.previewActualStart, apply: mocks.applyActualStart,
} }));
vi.mock('../../../../../../../api/scheduling/schedule_precision_client', () => ({ schedulePrecisionClient: { calculate: mocks.calculate } }));

const CASE = 'CASE-SERVICE-DATES';
const initialDates = ['2026-10-01', '2026-10-02', '2026-10-04'];
const revisedDates = ['2026-10-01', '2026-10-03', '2026-10-04'];
const initialQuery: ServiceDateConfirmationQueryView = {
  case_no: CASE, order_version: 11, scheduling_version: 7, contracted_service_days: 3,
  suggested_dates: initialDates, selectable_dates: ['2026-10-01', '2026-10-02', '2026-10-03', '2026-10-04'],
  current_version: null, current_dates: [], bound_staff: [], arrangement_pending: false,
};
let currentQuery: ServiceDateConfirmationQueryView;
let actualStart: string | null;

function previewFor(dates: string[]): ServiceDateConfirmationPreviewView {
  return {
    case_no: CASE, order_version: currentQuery.order_version, scheduling_version: currentQuery.scheduling_version,
    current_version: currentQuery.current_version, service_dates: dates, weeks: [],
    preview_fingerprint: (currentQuery.current_version === null ? 'a' : 'b').repeat(64),
  };
}
function calculation(start: string) {
  const dates = start === '2026-10-01' ? initialDates : ['2026-09-28', '2026-09-29', '2026-09-30'];
  const calendarDates = start === '2026-10-01' ? initialQuery.selectable_dates : dates;
  return {
    actual_start_date: start, actual_end_date: dates.at(-1), target_service_days: 3,
    total_calendar_days: calendarDates.length, actual_work_days_count: 3, rest_days_count: calendarDates.length - 3,
    national_holidays_found: [], total_estimated_salary: null, weekly_stats: [],
    day_by_day: calendarDates.map((date, index) => ({ date, day_num: index + 1,
      is_work_day: dates.includes(date), is_rest_day: !dates.includes(date), holiday_name: null })),
  };
}
function changeFormalStart() {
  actualStart = '2026-09-28';
  currentQuery = { ...currentQuery, order_version: 12, scheduling_version: 8,
    selectable_dates: ['2026-09-28', '2026-09-29', '2026-09-30'] };
}
async function ready() {
  await waitFor(() => expect(screen.getByLabelText('此次選定服務日期摘要')).toHaveTextContent('3 / 3 天'));
  await waitFor(() => expect(screen.getByRole('button', { name: '儲存服務日期' })).toBeEnabled());
}
async function save() {
  await ready();
  fireEvent.click(screen.getByRole('button', { name: '儲存服務日期' }));
}
function changeSelection() {
  fireEvent.click(screen.getByRole('button', { name: '服務日期 2026-10-02' }));
  fireEvent.click(screen.getByRole('button', { name: '服務日期 2026-10-03' }));
}

// Keep the real Preview / Apply / receipt store; only owner API boundaries are simulated.
describe('服務日期自動讀取與單次儲存流程', () => {
  beforeEach(() => {
    Object.values(mocks).forEach(mock => mock.mockReset());
    orderMutationFlowStore.clearAll();
    currentQuery = structuredClone(initialQuery);
    actualStart = '2026-10-01';
    mocks.getActualStart.mockImplementation(async () => ({
      case_no: CASE, current_actual_start_date: actualStart, planned_start_date: '2026-10-01', service_data_locked: false,
      order_version: currentQuery.order_version, scheduling_version: currentQuery.scheduling_version,
      scheduling_generation: 1, client_finance_version: 3, payroll_version: 2,
    }));
    mocks.getOrderCalendarDetail.mockResolvedValue({ case_no: CASE, service_mode: '休周六' });
    mocks.getServiceDates.mockImplementation(async () => structuredClone(currentQuery));
    mocks.queryStaffCalendar.mockResolvedValue({ days: [] });
    mocks.calculate.mockImplementation(async ({ actual_start_date }: { actual_start_date: string }) => calculation(actual_start_date));
    mocks.previewServiceDates.mockImplementation(async (_case: string, { service_dates }: { service_dates: string[] }) => previewFor(service_dates));
    mocks.applyServiceDates.mockImplementation(async (_case: string, payload: Parameters<typeof ordersMutationClient.applyServiceDates>[1]) => {
      if (payload.expected_order_version !== currentQuery.order_version || payload.expected_scheduling_version !== currentQuery.scheduling_version) {
        throw new ApiHttpError(409, 'stale_preview', '日期或案件資料已更新');
      }
      currentQuery = { ...currentQuery, order_version: currentQuery.order_version + 1,
        current_version: (currentQuery.current_version ?? 0) + 1, current_dates: payload.service_dates };
      return { case_no: CASE, confirmed_version: currentQuery.current_version, order_version: currentQuery.order_version,
        scheduling_version: currentQuery.scheduling_version, service_dates: payload.service_dates, preview_fingerprint: payload.preview_fingerprint };
    });
  });

  it('自動精算但不寫入，儲存時依序 Preview、Apply 並回讀正式日期', async () => {
    const onObserved = vi.fn();
    const onOpenActualStart = vi.fn();
    render(<OrderServiceDatesPanel caseNo={CASE} onObserved={onObserved} onOpenActualStart={onOpenActualStart} />);
    await ready();
    expect(mocks.calculate).toHaveBeenCalledWith({ case_no: CASE, actual_start_date: '2026-10-01', target_service_days: 3, service_mode: '休周六' });
    expect(mocks.previewServiceDates).not.toHaveBeenCalled();
    expect(mocks.applyServiceDates).not.toHaveBeenCalled();
    const calendar = screen.getByRole('group', { name: '服務日期月曆' });
    expect(within(calendar).getByRole('button', { name: '服務日期 2026-10-02' })).toHaveAttribute('aria-pressed', 'true');
    expect(within(calendar).getByRole('button', { name: '服務日期 2026-10-03' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.queryByRole('button', { name: '預覽服務日期' })).not.toBeInTheDocument();
    changeSelection();
    await save();
    await screen.findByText('服務日期已確認。');
    expect(mocks.previewServiceDates).toHaveBeenCalledWith(CASE, { service_dates: revisedDates }, undefined);
    expect(mocks.applyServiceDates).toHaveBeenCalledWith(CASE, {
      service_dates: revisedDates, expected_order_version: 11, expected_scheduling_version: 7,
      preview_fingerprint: 'a'.repeat(64), reason: '',
    }, expect.objectContaining({ idempotencyKey: expect.any(String) }));
    expect(mocks.previewServiceDates.mock.invocationCallOrder[0]).toBeLessThan(mocks.applyServiceDates.mock.invocationCallOrder[0]);
    expect(mocks.getServiceDates.mock.invocationCallOrder.at(-1)).toBeGreaterThan(mocks.applyServiceDates.mock.invocationCallOrder[0]);
    expect(screen.queryByText('查看已保存日期與版本')).not.toBeInTheDocument();
    expect(onObserved).toHaveBeenCalledTimes(1);
    expect(onOpenActualStart).not.toHaveBeenCalled();
  });

  it('實際開始日重排後顯示目前排班，保留先前確認日期供查閱', async () => {
    actualStart = '2026-10-05';
    currentQuery = { ...currentQuery, order_version: 13, scheduling_version: 9, current_version: 2, current_dates: initialDates };
    render(<OrderServiceDatesPanel caseNo={CASE} currentAssignmentPlan={{
      case_no: CASE, order_version: 13, scheduling_version: 9, scheduling_generation: 3,
      client_finance_version: 3, payroll_version: 2, contracted_service_days: 3, service_hours_per_day: 8, service_started: true,
      assignments: [
        { assignment_id: 101, candidate_key: null, staff_id: 1, sequence: 1, assigned_start_date: '2026-10-05', assigned_end_date: '2026-10-06', official_service_dates: ['2026-10-05', '2026-10-06'], actual_hours: 16, lineage_source_assignment_ids: [91] },
        { assignment_id: 102, candidate_key: null, staff_id: 2, sequence: 2, assigned_start_date: '2026-10-07', assigned_end_date: '2026-10-07', official_service_dates: ['2026-10-07'], actual_hours: 8, lineage_source_assignment_ids: [92] },
      ],
    }} />);
    const calendar = await screen.findByRole('group', { name: '服務日期月曆' });
    for (const date of ['2026-10-05', '2026-10-06', '2026-10-07']) {
      expect(within(calendar).getByRole('button', { name: `服務日期 ${date}` })).toHaveAttribute('aria-pressed', 'true');
      expect(within(calendar).getByRole('button', { name: `服務日期 ${date}` })).toBeDisabled();
    }
    expect(within(calendar).getByRole('button', { name: '服務日期 2026-10-01' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.queryByText('查看已保存日期與版本')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '儲存服務日期' })).not.toBeInTheDocument();
    expect(mocks.calculate).not.toHaveBeenCalled();
    expect(mocks.applyServiceDates).not.toHaveBeenCalled();
  });

  it('合意延期後未載入月嫂指派時，仍從查詢顯示目前正式班表', async () => {
    currentQuery = {
      ...currentQuery,
      scheduling_version: 8,
      current_version: 2,
      current_dates: initialDates,
      effective_service_dates: revisedDates,
    };
    render(<OrderServiceDatesPanel caseNo={CASE} />);

    const calendar = await screen.findByRole('group', { name: '服務日期月曆' });
    const removedDay = within(calendar).getByRole('button', { name: '服務日期 2026-10-02' });
    const replacementDay = within(calendar).getByRole('button', { name: '服務日期 2026-10-03' });
    expect(removedDay).toHaveAttribute('aria-pressed', 'false');
    expect(replacementDay).toHaveAttribute('aria-pressed', 'true');
    expect(replacementDay).toBeDisabled();
    expect(screen.queryByText('查看已保存日期與版本')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '儲存服務日期' })).not.toBeInTheDocument();
    expect(mocks.applyServiceDates).not.toHaveBeenCalled();
  });

  it('任一 owner 回讀案件編號不一致時 fail closed，不執行精算或 Preview', async () => {
    mocks.getActualStart.mockResolvedValue({ case_no: 'OTHER-CASE' });
    render(<OrderServiceDatesPanel caseNo={CASE} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('服務日期精算回讀案件編號不一致。');
    expect(mocks.calculate).not.toHaveBeenCalled();
    expect(mocks.previewServiceDates).not.toHaveBeenCalled();
    expect(mocks.applyServiceDates).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: '儲存服務日期' })).not.toBeInTheDocument();
  });

  it('精算失敗時不保留上一輪可操作狀態，也不保存日期', async () => {
    mocks.calculate.mockRejectedValueOnce(new Error('正式精算暫時無法使用'));
    render(<OrderServiceDatesPanel caseNo={CASE} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('正式精算暫時無法使用');
    expect(screen.queryByLabelText('建議服務日期摘要')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '儲存服務日期' })).not.toBeInTheDocument();
    expect(mocks.previewServiceDates).not.toHaveBeenCalled();
    expect(mocks.applyServiceDates).not.toHaveBeenCalled();
  });

  it('保存後修改日期會清除舊 Preview，下一次儲存重新核對新選日與版本', async () => {
    render(<OrderServiceDatesPanel caseNo={CASE} />);
    await save();
    await screen.findByText('服務日期已確認。');
    changeSelection();
    expect(orderMutationFlowStore.getServiceDatesDraft(CASE)?.previewView).toBeNull();
    expect(mocks.applyServiceDates).toHaveBeenCalledTimes(1);
    await save();
    await screen.findByText('服務日期已確認。');
    expect(mocks.previewServiceDates).toHaveBeenCalledTimes(2);
    expect(mocks.previewServiceDates.mock.calls.map(call => call[1].service_dates)).toEqual([initialDates, revisedDates]);
    expect(mocks.applyServiceDates.mock.calls[1][1]).toMatchObject({ service_dates: revisedDates,
      expected_order_version: 12, expected_scheduling_version: 7, preview_fingerprint: 'b'.repeat(64) });
    expect(mocks.previewServiceDates.mock.invocationCallOrder[1]).toBeLessThan(mocks.applyServiceDates.mock.invocationCallOrder[1]);
  });

  it('歷史重啟用一次儲存確認實際開始日、服務日期並建立單一月嫂班表', async () => {
    actualStart = null;
    currentQuery.historical_schedule_pending = true;
    currentQuery.bound_staff = [{ staff_id: 12, staff_name: '王月嫂' }];
    mocks.getOrderCalendarDetail.mockResolvedValue({ case_no: CASE, service_mode: null });
    const fingerprint = 'c'.repeat(64);
    mocks.previewActualStart.mockResolvedValue({
      case_no: CASE, operation: 'date_only', before_actual_start_date: null, after_actual_start_date: initialDates[0],
      order_version: 11, scheduling_version: 7, preview_fingerprint: fingerprint,
    });
    mocks.saveHistoricalSchedule.mockImplementation(async () => {
      currentQuery = { ...currentQuery, order_version: 13, scheduling_version: 8,
        current_version: 1, current_dates: initialDates, bound_staff: [], historical_schedule_pending: false };
      return { case_no: CASE, scheduling_version: 8, generation_number: 2,
        preview_fingerprint: fingerprint, assignment_ids: [1] };
    });
    mocks.getAssignmentPlan.mockRejectedValueOnce(new Error('讀取失敗')).mockResolvedValue({
      case_no: CASE, scheduling_version: 8, scheduling_generation: 2,
      assignments: [{ staff_id: 12, assignment_id: 1, official_service_dates: initialDates }],
    });

    render(<OrderServiceDatesPanel caseNo={CASE} coordinatedStart />);
    const saveSchedule = await screen.findByRole('button', { name: '儲存班表' });
    await waitFor(() => expect(saveSchedule).toBeEnabled());
    expect(mocks.calculate).toHaveBeenCalledWith(expect.objectContaining({ service_mode: '休周日' }));
    expect(screen.queryByRole('button', { name: '儲存實際開始日' })).not.toBeInTheDocument();
    fireEvent.click(saveSchedule);
    const retry = await screen.findByRole('button', { name: '重新讀取班表' });
    fireEvent.click(retry);
    await screen.findByText('班表已儲存並回讀正式排班。');
    expect(mocks.applyActualStart).not.toHaveBeenCalled();
    expect(mocks.applyServiceDates).not.toHaveBeenCalled();
    expect(mocks.saveHistoricalSchedule).toHaveBeenCalledTimes(1);
    expect(mocks.saveHistoricalSchedule).toHaveBeenCalledWith(CASE, expect.objectContaining({
      actual_start_date: initialDates[0], expected_confirmed_version: null,
      segments: [{ staff_id: 12, service_dates: initialDates }],
    }), expect.objectContaining({ idempotencyKey: expect.any(String) }));
  });

  it('歷史班表儲存遇到月嫂檔期衝突，重新讀取後仍顯示阻擋原因', async () => {
    currentQuery = { ...currentQuery, current_version: 2, current_dates: initialDates,
      bound_staff: [{ staff_id: 12, staff_name: '王月嫂' }],
      arrangement_pending: true, historical_schedule_pending: true };
    const message = '月嫂檔期衝突，無法儲存班表。請核對月嫂的檔期並調整服務日期。';
    mocks.saveHistoricalSchedule.mockRejectedValue(new OrderMutationConflictError({
      code: 'historical_arrangement_occupancy_conflict', message,
    }));

    render(<OrderServiceDatesPanel caseNo={CASE} />);
    const saveSchedule = await screen.findByRole('button', { name: '儲存班表' });
    await waitFor(() => expect(saveSchedule).toBeEnabled());
    mocks.getServiceDates.mockClear();
    fireEvent.click(saveSchedule);

    await waitFor(() => expect(mocks.getServiceDates).toHaveBeenCalledWith(CASE, expect.anything()));
    expect(await screen.findByText(message)).toBeVisible();
  });

  it('歷史案件帶入已保存日期，依月嫂選好日期後才能一次儲存', async () => {
    currentQuery = { ...currentQuery, current_version: 2, current_dates: initialDates,
      bound_staff: [{ staff_id: 12, staff_name: '王月嫂' }, { staff_id: 13, staff_name: '林月嫂' }],
      arrangement_pending: true, historical_schedule_pending: true };
    render(<OrderServiceDatesPanel caseNo={CASE} />);
    const saveSchedule = await screen.findByRole('button', { name: '儲存班表' });
    expect(screen.queryByText('查看已保存日期與版本')).not.toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText('正在讀取當月國定假日…')).not.toBeInTheDocument());
    expect(saveSchedule).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: /王月嫂 2026-10-01/ }));
    expect(screen.getByRole('button', { name: /林月嫂 2026-10-01/ })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: /林月嫂 2026-10-02/ }));
    fireEvent.click(screen.getByRole('button', { name: /王月嫂 2026-10-04/ }));
    expect(saveSchedule).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: /王月嫂 2026-10-04/ }));
    fireEvent.click(screen.getByRole('button', { name: /林月嫂 2026-10-04/ }));
    expect(saveSchedule).toBeEnabled();
    expect(mocks.applyServiceDates).not.toHaveBeenCalled();
    expect(mocks.saveHistoricalSchedule).not.toHaveBeenCalled();
  });

  it('一般案件帶入已確認日期並從原頁送出工會正式排班', async () => {
    currentQuery = { ...currentQuery, current_version: 2, current_dates: initialDates };
    mocks.saveHistoricalSchedule.mockImplementation(async () => {
      currentQuery = { ...currentQuery, order_version: 12, scheduling_version: 8 };
      return { case_no: CASE, scheduling_version: 8, generation_number: 2, assignment_ids: [5] };
    });
    mocks.getAssignmentPlan.mockResolvedValue({
      case_no: CASE, scheduling_version: 8, scheduling_generation: 2,
      assignments: [{ assignment_id: 5, staff_id: 12, official_service_dates: initialDates }],
    });
    render(<OrderServiceDatesPanel caseNo={CASE} coordinatedStart
      officeScheduleStaff={[{ staff_id: 12, staff_name: '王月嫂' }]} />);
    const button = await screen.findByRole('button', { name: '儲存班表' });
    expect(screen.queryByText('查看已保存日期與版本')).not.toBeInTheDocument();
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    await screen.findByText('班表已儲存並回讀正式排班。');
    const calendar = within(screen.getByRole('group', { name: '服務日期月曆' }));
    expect(calendar.getByRole('button', { name: '服務日期 2026-10-02', pressed: true })).toBeDisabled();
    expect(calendar.getByRole('button', { name: '服務日期 2026-10-03', pressed: false })).toBeDisabled();
    expect(screen.queryByText(initialDates.join('、'))).not.toBeInTheDocument();
    expect(screen.queryByText('查看已保存日期與版本')).not.toBeInTheDocument();
    expect(mocks.saveHistoricalSchedule).toHaveBeenCalledExactlyOnceWith(CASE, expect.objectContaining({
      expected_confirmed_version: 2, segments: [{ staff_id: 12, service_dates: initialDates }],
    }), expect.anything(), true);
    expect(mocks.applyServiceDates).not.toHaveBeenCalled();
  });

  it('一般首排標示月嫂既有檔期，換月時不沿用舊標示或改變日期可選性', async () => {
    currentQuery = { ...currentQuery, current_version: 2, current_dates: initialDates };
    const entries = (calendar_date: string, occupancy_kind: string, case_no: string | null) => ({
      calendar_date, entries: [{ occupancy_kind, case_no }],
    });
    mocks.queryStaffCalendar.mockResolvedValueOnce({ days: [
      { calendar_date: '2026-09-30', entries: [{ occupancy_kind: 'official_workday', case_no: 'OVERNIGHT-CASE',
        actual_start_date: '2026-09-30', service_start_at: '2026-09-30T22:00:00+08:00', service_end_at: '2026-10-01T06:00:00+08:00' }] },
      { calendar_date: '2026-10-02', entries: [
        { occupancy_kind: 'official_workday', case_no: 'OTHER-CASE', actual_start_date: '2026-09-28',
          service_start_at: '2026-10-02T09:00:00+08:00', service_end_at: '2026-10-02T17:00:00+08:00' },
        { occupancy_kind: 'historical_reservation', case_no: 'ANOTHER-CASE', actual_start_date: null },
        { occupancy_kind: 'official_workday', case_no: 'EVENING-CASE', actual_start_date: '2026-10-01',
          service_start_at: '2026-10-02T18:00:00+08:00', service_end_at: '2026-10-02T21:00:00+08:00' },
      ] },
      entries('2026-10-03', 'official_workday', CASE),
      entries('2026-10-04', 'assignment_rest', 'OTHER-CASE'),
      entries('2026-10-05', 'waiting_deposit_service', 'OTHER-CASE'),
      entries('2026-10-06', 'staff_unavailability', null),
      { calendar_date: '2026-10-07', entries: [{ occupancy_kind: 'historical_reservation', case_no: 'ADOPTED-CASE',
        actual_start_date: '2026-10-01' }] },
    ] }).mockRejectedValueOnce(new Error('offline'));
    render(<OrderServiceDatesPanel caseNo={CASE} coordinatedStart
      officeScheduleStaff={[{ staff_id: 12, staff_name: '王月嫂' }]} />);

    const scheduled = await screen.findByRole('button', { name: '服務日期 2026-10-02，已有排班、歷史／暫定' });
    expect(scheduled).toBeEnabled();
    const occupied = screen.getByRole('button', { name: '查看 2026-10-02 檔期明細' });
    expect(scheduled.parentElement).toHaveClass('calendar-date-cell', 'selected');
    expect(occupied.parentElement).toBe(scheduled.parentElement);
    expect(within(occupied).getByText('3筆')).toBeInTheDocument();
    expect(occupied).toHaveAttribute('aria-expanded', 'false');
    expect(within(occupied).getByText('OTHER-CASE')).toBeVisible();
    expect(within(occupied).getByText('ANOTHER-CASE')).toBeVisible();
    expect(within(occupied).getByText('09:00–17:00')).toBeVisible();
    fireEvent.click(occupied);
    expect(occupied).toHaveAttribute('aria-expanded', 'true');
    expect(scheduled).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('案件 OTHER-CASE')).toBeVisible();
    expect(screen.getByText('案件 ANOTHER-CASE')).toBeVisible();
    expect(screen.getByText('案件 EVENING-CASE')).toBeVisible();
    expect(screen.getByText('服務時段待確認')).toBeVisible();
    expect(screen.getByText('2026-10-02 09:00 至 2026-10-02 17:00')).toBeVisible();
    expect(screen.getByText('2026-10-02 18:00 至 2026-10-02 21:00')).toBeVisible();
    const overnight = screen.getByRole('button', { name: '查看 2026-10-01 檔期明細' });
    expect(within(overnight).getByText('1筆')).toBeInTheDocument();
    expect(within(overnight).getByText('22:00–跨日 06:00')).toBeVisible();
    fireEvent.click(overnight);
    expect(screen.getByText('2026-09-30 22:00 至 2026-10-01 06:00')).toBeVisible();
    expect(scheduled).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '服務日期 2026-10-03' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: '查看 2026-10-03 檔期明細' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '服務日期 2026-10-04' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '服務日期 2026-10-05，檔期保留' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '服務日期 2026-10-06，不可服務' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '服務日期 2026-10-07，服務檔期' })).toBeDisabled();
    const disabledDateDetails = screen.getByRole('button', { name: '查看 2026-10-07 檔期明細' });
    fireEvent.click(disabledDateDetails);
    expect(screen.getByText('案件 ADOPTED-CASE')).toBeVisible();
    expect(screen.getByText('服務時段待確認')).toBeVisible();
    fireEvent.click(scheduled);
    expect(scheduled).toHaveAttribute('aria-pressed', 'false');
    expect(scheduled.parentElement).not.toHaveClass('selected');
    expect(disabledDateDetails).toHaveAttribute('aria-expanded', 'true');
    expect(mocks.applyServiceDates).not.toHaveBeenCalled();
    expect(mocks.saveHistoricalSchedule).not.toHaveBeenCalled();
    expect(mocks.queryStaffCalendar).toHaveBeenNthCalledWith(1,
      { staffId: 12, rangeStart: '2026-09-30', rangeEnd: '2026-10-31' }, { signal: expect.any(AbortSignal) });

    fireEvent.click(screen.getByRole('button', { name: '下一個月' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('無法讀取月嫂檔期。');
    expect(mocks.queryStaffCalendar).toHaveBeenNthCalledWith(2,
      { staffId: 12, rangeStart: '2026-10-31', rangeEnd: '2026-11-30' }, { signal: expect.any(AbortSignal) });
    expect(mocks.queryStaffCalendar.mock.calls[0][1].signal.aborted).toBe(true);
    expect(screen.queryByText('已有排班')).not.toBeInTheDocument();
  });

  it('多月嫂儲存受拒後可取消並重新讀取原日期', async () => {
    currentQuery = { ...currentQuery, current_version: 2, current_dates: initialDates };
    mocks.saveHistoricalSchedule.mockRejectedValue(new ApiHttpError(409, 'office_schedule_assignment_ownership_blocked', '請核對原指派'));
    render(<OrderServiceDatesPanel caseNo={CASE} coordinatedStart
      officeScheduleStaff={[{ staff_id: 12, staff_name: '王月嫂' }]} />);
    fireEvent.click(await screen.findByRole('button', { name: '多月嫂排班' }));
    expect(mocks.previewOfficeSchedule).not.toHaveBeenCalled();
    expect(mocks.saveHistoricalSchedule).not.toHaveBeenCalled();
    expect(screen.queryByLabelText('服務日期選擇')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '儲存班表' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('請核對原指派');
    fireEvent.click(screen.getByRole('button', { name: '取消多月嫂編輯' }));
    expect(await screen.findByRole('button', { name: '多月嫂排班' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '服務日期 2026-10-02' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '服務日期 2026-10-03' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(mocks.saveHistoricalSchedule).toHaveBeenCalledTimes(1);
    expect(mocks.getAssignmentPlan).not.toHaveBeenCalled();
    expect(mocks.applyServiceDates).not.toHaveBeenCalled();
  });

  it('多月嫂模式完成交錯日期分配後直接儲存，補上必要原因後保留原分配再送出', async () => {
    currentQuery = { ...currentQuery, current_version: 2, current_dates: initialDates };
    mocks.saveHistoricalSchedule
      .mockRejectedValueOnce(new ApiHttpError(409, 'office_schedule_reallocation_reason_required', '請填寫調整原因及協調依據'))
      .mockImplementation(async () => {
        currentQuery = { ...currentQuery, order_version: 12, scheduling_version: 8 };
        return { case_no: CASE, scheduling_version: 8, generation_number: 2, assignment_ids: [5, 6] };
      });
    mocks.getAssignmentPlan.mockResolvedValue({
      case_no: CASE, scheduling_version: 8, scheduling_generation: 2,
      assignments: [
        { assignment_id: 5, staff_id: 12, official_service_dates: [initialDates[0], initialDates[2]] },
        { assignment_id: 6, staff_id: 13, official_service_dates: [initialDates[1]] },
      ],
    });
    mocks.queryStaffCalendar.mockImplementation(async ({ staffId }) => ({ days: staffId === 13
      ? [{ calendar_date: '2026-10-02', entries: [{ occupancy_kind: 'official_workday', case_no: 'OTHER-CASE' }] }]
      : [] }));
    const view = render(<OrderServiceDatesPanel caseNo={CASE} coordinatedStart />);
    view.rerender(<OrderServiceDatesPanel caseNo={CASE} coordinatedStart officeScheduleStaff={[
      { staff_id: 12, staff_name: '王月嫂' }, { staff_id: 13, staff_name: '林月嫂' },
    ]} />);
    expect(await screen.findAllByRole('group', { name: '服務日期月曆' })).toHaveLength(2);
    expect(mocks.previewOfficeSchedule).not.toHaveBeenCalled();
    expect(mocks.saveHistoricalSchedule).not.toHaveBeenCalled();
    expect(screen.queryByLabelText('服務日期選擇')).not.toBeInTheDocument();
    const saveButton = screen.getByRole('button', { name: '儲存班表' });
    expect(screen.queryByRole('button', { name: '預覽班表及應付' })).not.toBeInTheDocument();
    expect(saveButton).toBeDisabled();
    const first = within(screen.getByRole('region', { name: /王月嫂/ }));
    const second = within(screen.getByRole('region', { name: /林月嫂/ }));
    expect(await second.findByRole('button', { name: '服務日期 2026-10-02，尚未分配，歷史／暫定' })).toBeEnabled();
    expect(first.queryByText('歷史／暫定')).not.toBeInTheDocument();
    fireEvent.click(first.getByRole('button', { name: /^服務日期 2026-10-01/ }));
    fireEvent.click(second.getByRole('button', { name: /^服務日期 2026-10-02/ }));
    fireEvent.click(first.getByRole('button', { name: /^服務日期 2026-10-04/ }));
    expect(saveButton).toBeEnabled();
    fireEvent.click(saveButton);
    expect(await screen.findByRole('alert')).toHaveTextContent('請填寫調整原因及協調依據');
    expect(saveButton).toBeDisabled();
    fireEvent.change(screen.getByLabelText('調整原因及協調依據（必填）'), { target: { value: '已與兩位月嫂確認' } });
    expect(saveButton).toBeEnabled();
    fireEvent.click(saveButton);
    await screen.findByText('班表已儲存並回讀正式排班。');
    const segments = [{ staff_id: 12, service_dates: [initialDates[0], initialDates[2]] }, { staff_id: 13, service_dates: [initialDates[1]] }];
    expect(mocks.previewOfficeSchedule).not.toHaveBeenCalled();
    expect(mocks.saveHistoricalSchedule).toHaveBeenCalledTimes(2);
    expect(mocks.saveHistoricalSchedule).toHaveBeenNthCalledWith(1, CASE, expect.objectContaining({ reason: '', segments }), expect.anything(), true);
    expect(mocks.saveHistoricalSchedule).toHaveBeenNthCalledWith(2, CASE, expect.objectContaining({ reason: '已與兩位月嫂確認', segments }), expect.anything(), true);
    expect(mocks.saveHistoricalSchedule.mock.calls[0][2].idempotencyKey).not.toBe(mocks.saveHistoricalSchedule.mock.calls[1][2].idempotencyKey);
  });

  it('正式實際開始日變更後自動重算，人工選日須明確採用新建議', async () => {
    const { rerender } = render(<OrderServiceDatesPanel caseNo={CASE} calculationRevision={0} />);
    await ready();
    changeSelection();
    changeFormalStart();
    rerender(<OrderServiceDatesPanel caseNo={CASE} calculationRevision={1} />);
    await screen.findByRole('button', { name: '採用新建議' });
    expect(screen.getByRole('button', { name: '儲存服務日期' })).toBeDisabled();
    expect(orderMutationFlowStore.getServiceDatesDraft(CASE)?.selectedDates).toEqual(revisedDates);
    expect(mocks.previewServiceDates).not.toHaveBeenCalled();
    expect(mocks.applyServiceDates).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '採用新建議' }));
    await ready();
    expect(mocks.calculate).toHaveBeenLastCalledWith({ case_no: CASE, actual_start_date: '2026-09-28', target_service_days: 3, service_mode: '休周六' });
    expect(orderMutationFlowStore.getServiceDatesDraft(CASE)?.selectedDates).toEqual(['2026-09-28', '2026-09-29', '2026-09-30']);
  });

  it('日期基準改變時，延遲舊 Preview 不能通過版本檢查或保存舊日期', async () => {
    let resolveLatePreview!: (value: ServiceDateConfirmationPreviewView) => void;
    mocks.previewServiceDates.mockImplementationOnce(() => new Promise(resolve => { resolveLatePreview = resolve; }));
    const onObserved = vi.fn();
    const { rerender } = render(<OrderServiceDatesPanel caseNo={CASE} calculationRevision={0} onObserved={onObserved} />);
    await ready();
    const oldPreview = previewFor(initialDates);
    await save();
    await waitFor(() => expect(mocks.previewServiceDates).toHaveBeenCalledTimes(1));
    changeFormalStart();
    rerender(<OrderServiceDatesPanel caseNo={CASE} calculationRevision={1} onObserved={onObserved} />);
    expect(await screen.findByText('日期基準已變更；待目前操作結果確認後，會接續更新。')).toBeInTheDocument();
    await act(async () => resolveLatePreview(oldPreview));
    await waitFor(() => expect(mocks.calculate).toHaveBeenLastCalledWith(expect.objectContaining({ actual_start_date: '2026-09-28' })));
    await screen.findByRole('button', { name: '採用新建議' });
    expect(screen.getByRole('button', { name: '儲存服務日期' })).toBeDisabled();
    expect(mocks.applyServiceDates).toHaveBeenCalledTimes(1);
    expect(mocks.applyServiceDates.mock.calls[0][1].expected_order_version).toBe(11);
    expect(currentQuery.current_dates).toEqual([]);
    expect(currentQuery.current_version).toBeNull();
    expect(onObserved).not.toHaveBeenCalled();
    expect(screen.queryByText(/^服務日期已確認。$/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '採用新建議' }));
    await ready();
    expect(orderMutationFlowStore.getServiceDatesDraft(CASE)?.selectedDates).toEqual(['2026-09-28', '2026-09-29', '2026-09-30']);
    expect(mocks.applyServiceDates).toHaveBeenCalledTimes(1);
  });

  it('Apply 後正式回讀失敗保留收據，不能通知成功或重送 Apply', async () => {
    const onObserved = vi.fn();
    mocks.getServiceDates.mockImplementation(async () => {
      if (mocks.applyServiceDates.mock.calls.length > 0) throw new Error('正式日期回讀失敗');
      return structuredClone(currentQuery);
    });
    render(<OrderServiceDatesPanel caseNo={CASE} onObserved={onObserved} />);
    await save();
    await screen.findByRole('button', { name: '只重新讀取服務日期結果' });
    expect(screen.getByRole('alert')).toHaveTextContent('正式日期回讀失敗');
    expect(orderMutationFlowStore.getServiceDatesDraft(CASE)).toMatchObject({ status: 'observation_failed', receiptView: { confirmed_version: 1 } });
    expect(mocks.applyServiceDates).toHaveBeenCalledTimes(1);
    expect(onObserved).not.toHaveBeenCalled();
    expect(screen.queryByText(/^服務日期已確認。$/)).not.toBeInTheDocument();
  });
});

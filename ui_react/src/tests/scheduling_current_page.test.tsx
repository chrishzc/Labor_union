/**
 * File: scheduling_current_page.test.tsx
 * Description: 驗證 Scheduling 投影、typed controls 與 bounded deep-link 行為。
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { publishStaffAvailabilityChange } from '../api/staff_availability/staff_availability_changes';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { serviceStartClient } from '../api/scheduling/service_start_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { schedulingCurrentClient } from '../api/scheduling/scheduling_current_client';
import { SchedulingCurrentError } from '../api/scheduling/scheduling_current_errors';
import { holidayClient } from '../api/scheduling/holiday_client';
import { staffMonthlyScheduleClient } from '../api/scheduling/staff_monthly_schedule_client';
import { schedulingEligibilityCollisionClient } from '../api/scheduling/eligibility_collision_client';
import { staffAssignmentOptionsClient } from '../api/scheduling/staff_assignment_options_client';
import { staffLeaveInboxClient } from '../api/scheduling/staff_leave_inbox_client';
import { leaveSubstitutionClient } from '../api/scheduling/leave_substitution_client';
import { sessionClient } from '../api/auth/session_client';
import { SchedulingPage, taipeiCalendarDate } from '../pages/SchedulingPage';
import { HOLIDAY_PREVIEW, HOLIDAY_RECEIPT } from './fixtures/holiday_contract_fixtures';
import {
  SCHEDULING_PROJECTION_EMPTY,
  SCHEDULING_PROJECTION_READY,
} from './fixtures/scheduling/scheduling_current_contract_fixtures';

const coreStageProjectionMocks = vi.hoisted(() => ({
  loadAll: vi.fn(),
}));

vi.mock('../api/orders/load_all_core_stage_timelines', () => ({
  loadAllCoreStageTimelines: coreStageProjectionMocks.loadAll,
}));

describe('SchedulingPage query-only presentation', () => {
  let observeNextPage: ReturnType<typeof vi.fn>;
  afterEach(() => { sessionClient.clearSession(); vi.unstubAllGlobals(); vi.useRealTimers(); });
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-08-23T04:00:00Z'));
    vi.spyOn(serviceStartClient, 'todos').mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
    vi.spyOn(serviceStartClient, 'options').mockResolvedValue({ items: [] });
    vi.spyOn(holidayClient, 'query').mockImplementation(async query => ({ planning_horizon: 'from_date' in query ? query : { from_date: query.fromDate, to_date: query.toDate }, source_identity: 'test-holidays', calendar_version: 'a'.repeat(64), holidays: [] }));
    coreStageProjectionMocks.loadAll.mockReset();
    observeNextPage = vi.fn();
    vi.stubGlobal('IntersectionObserver', class {
      observe = observeNextPage;
      disconnect = vi.fn();
    });
    window.location.hash = '#scheduling';
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({
      items: [
        { id: 11, name: '去敏人員甲', phone: null, education: null },
        { id: 12, name: '去敏人員乙', phone: null, education: null },
      ],
      next_cursor: null,
    });
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue({
      items: [
        {
          case_no: 'CASE-SCH-001', client_name: '排班客戶甲', order_status: '服務中',
          staff_name: '去敏人員甲', identity_status: 'verified', start_date: '2026-08-01',
          end_date: '2026-08-10', actual_start_date: '2026-08-01', actual_end_date: null,
          service_days: 10, total_employer_self_pay_payable: 10000,
        },
        {
          case_no: '115000003', client_name: '排查客戶乙', order_status: '洽談中',
          staff_name: '去敏人員乙', identity_status: 'verified', start_date: '2026-08-23',
          end_date: '2026-08-24', actual_start_date: null, actual_end_date: null,
          service_days: 2, total_employer_self_pay_payable: 2000,
        },
      ],
      next_cursor: null,
      etag: 'a'.repeat(64),
    });
    coreStageProjectionMocks.loadAll.mockResolvedValue({
      items: [
        { case_no: 'CASE-SCH-001', current_core_stage_ordinal: 10 },
        { case_no: '115000003', current_core_stage_ordinal: 7 },
      ],
    });
    vi.spyOn(staffAssignmentOptionsClient, 'getStaffAssignmentOptions').mockImplementation(async (staffId) => [
      {
        id: staffId * 10 + 1, case_no: 'CASE-SCH-001', staff_id: staffId, status: 'active',
        assigned_start_date: '2026-08-01', assigned_end_date: '2026-08-10', order_status: '服務中',
        actual_start_date: '2026-08-01', actual_end_date: null, staff_name: `月嫂 ${staffId}`,
      },
      {
        id: staffId * 10 + 2, case_no: '115000003', staff_id: staffId, status: 'planned',
        assigned_start_date: '2026-08-23', assigned_end_date: '2026-08-24', order_status: '洽談中',
        actual_start_date: null, actual_end_date: null, staff_name: `月嫂 ${staffId}`,
      },
    ]);
    vi.spyOn(schedulingCurrentClient, 'queryCurrentCalendar').mockImplementation(
      async (query) => ({
        ...SCHEDULING_PROJECTION_READY,
        staff_id: query.staffId,
        range_start: query.rangeStart,
        range_end: query.rangeEnd,
        assignments: SCHEDULING_PROJECTION_READY.assignments.map((item) => ({
          ...item,
          staff_id: query.staffId,
        })),
      })
    );
    vi.spyOn(staffLeaveInboxClient, 'list').mockResolvedValue([]);
    vi.spyOn(ordersQueryClient, 'getOrderDetail').mockRejectedValue(new Error('order unavailable'));
    vi.spyOn(staffMonthlyScheduleClient, 'query').mockImplementation(async (staffId, year, month) => ({
      staff_id: staffId, year, month, days: [], schedule_map: {},
    }));
  });

  it('在同一位月嫂的列中上下顯示兩個同日班次', async () => {
    vi.mocked(staffMonthlyScheduleClient.query).mockImplementation(async (staffId, year, month) => {
      const day = `${year}-${String(month).padStart(2, '0')}-12`;
      return {
        staff_id: staffId, year, month, schedule_map: {},
        days: staffId === 11 ? [
          { work_date: day, service_date: day, starts_at: `${day}T08:00:00+08:00`, ends_at: `${day}T12:00:00+08:00`, case_no: 'MORNING', assignment_id: 101, staff_id: staffId, status: 'working', is_work_day: true, is_double_pay: false },
          { work_date: day, service_date: day, starts_at: `${day}T13:00:00+08:00`, ends_at: `${day}T17:00:00+08:00`, case_no: 'AFTERNOON', assignment_id: 102, staff_id: staffId, status: 'working', is_work_day: true, is_double_pay: false },
        ] : [],
      };
    });
    render(<SchedulingPage />);
    const morning = await screen.findByRole('button', { name: /MORNING.*08:00–12:00/ });
    const afternoon = screen.getByRole('button', { name: /AFTERNOON.*13:00–17:00/ });
    expect(morning).toHaveAttribute('data-start-day', '12');
    expect(afternoon).toHaveAttribute('data-start-day', '12');
    expect(morning.style.top).not.toBe(afternoon.style.top);
    fireEvent.click(afternoon);
    expect(window.location.hash).toBe('#order-workbench-v2?case=AFTERNOON&work=service');
    expect(screen.queryByRole('dialog', { name: '排班與訂單明細' })).not.toBeInTheDocument();
  });

  it.each(['訂單成立', '服務中', '訂單完成', '訂單取消'])('按指派編號定位 %s 已保留的正式班次', async (orderStatus) => {
    const { year, month } = taipeiCalendarDate(new Date());
    const ym = `${year}-${String(month).padStart(2, '0')}`;
    vi.mocked(schedulingCurrentClient.queryCurrentCalendar).mockResolvedValue(SCHEDULING_PROJECTION_EMPTY);
    vi.mocked(staffAssignmentOptionsClient.getStaffAssignmentOptions).mockImplementation(async staffId => staffId === 11 ? [
      { id: 102, start: '12', end: '14' },
      { id: 101, start: '03', end: '05' },
    ].map(({ id, start, end }) => ({
      id, case_no: 'CASE-SCH-001', staff_id: staffId, status: 'completed', order_status: orderStatus,
      assigned_start_date: `${ym}-${start}`, assigned_end_date: `${ym}-${end}`,
      actual_start_date: `${ym}-01`, actual_end_date: `${ym}-25`, staff_name: '月嫂',
    })) : []);
    vi.mocked(staffMonthlyScheduleClient.query).mockImplementation(async (staffId, year, month) => ({
      staff_id: staffId, year, month, schedule_map: {},
      days: staffId === 11 ? [
        { id: 101, day: '04', start: '08', end: '10' },
        { id: 102, day: '13', start: '12', end: '14' },
        { id: 103, day: '23', start: '16', end: '18' },
      ].map(({ id, day, start, end }) => ({
        work_date: `${ym}-${day}`, service_date: `${ym}-${day}`,
        starts_at: `${ym}-${day}T${start}:00:00+08:00`, ends_at: `${ym}-${day}T${end}:00:00+08:00`,
        case_no: 'CASE-SCH-001', assignment_id: id, staff_id: staffId, order_status: orderStatus,
        status: 'working' as const, is_work_day: true, is_double_pay: false,
      })) : [],
    }));
    render(<SchedulingPage />);
    const [first, second, unmatched] = await screen.findAllByRole('button', { name: /CASE-SCH-001.*\d\d:00–/ });
    await waitFor(() => expect(first).toHaveTextContent(`${ym}-03 ～ ${ym}-05`));
    expect(second).toHaveTextContent(`${ym}-12 ～ ${ym}-14`);
    expect(unmatched).toHaveTextContent(`${ym}-23`);
    expect(unmatched).not.toHaveTextContent(`${ym}-12`);
    const monthColumn = (month - 1) * 3;
    expect(parseFloat(first.style.left)).toBeCloseTo((monthColumn + 0.2) / 36 * 100, 5);
    expect(parseFloat(second.style.left)).toBeCloseTo((monthColumn + 1.1) / 36 * 100, 5);
    fireEvent.click(first);
    expect(new URLSearchParams(window.location.hash.split('?')[1]).get('work')).toBe('service');
  });

  it('返回排班月曆沿用近期假日，政策儲存後重讀受影響月份且不改正式排班', async () => {
    const holidayDate = '2026-08-01';
    let holidayName = '測試國定假日';
    vi.mocked(holidayClient.query).mockImplementation(async query => {
      const horizon = 'from_date' in query ? query : { from_date: query.fromDate, to_date: query.toDate };
      return { planning_horizon: horizon, source_identity: 'test', calendar_version: 'a'.repeat(64), holidays: [{ holiday_date: holidayDate, holiday_name: holidayName, is_double_pay_default: false }] };
    });
    vi.spyOn(holidayClient, 'accountingResults').mockResolvedValue([]);
    const preview = vi.spyOn(holidayClient, 'preview').mockImplementation(async request => ({
      ...HOLIDAY_PREVIEW,
      command: { ...HOLIDAY_PREVIEW.command, ...request, holiday_date: holidayDate },
    }));
    const apply = vi.spyOn(holidayClient, 'apply').mockImplementation(async request => {
      holidayName = request.holiday_name ?? '';
      return { ...HOLIDAY_RECEIPT, holiday_date: holidayDate };
    });
    const monthReads = () => vi.mocked(holidayClient.query).mock.calls.filter(([query]) =>
      ('from_date' in query ? query.from_date : query.fromDate) === holidayDate,
    ).length;
    render(<SchedulingPage />);
    await waitFor(() => expect(document.querySelector('.gantt-day-header-col.holiday')).toHaveTextContent('測試國定假日'));
    await waitFor(() => expect(document.querySelector('.gantt-spans-layer .span-active')).toHaveTextContent('排班客戶甲'));
    const spans = document.querySelector('.gantt-spans-layer')?.innerHTML;
    fireEvent.click(screen.getByRole('button', { name: /國定假日政策/ }));
    await screen.findByRole('region', { name: '國定假日日曆' });
    expect(screen.queryByText(/預設雙薪|一般薪資/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /排班月曆/ }));
    expect(document.querySelector('.gantt-day-header-col.holiday')).toHaveTextContent('測試國定假日');
    await act(async () => {});
    expect(monthReads()).toBe(1);
    expect(preview).not.toHaveBeenCalled();
    expect(apply).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /國定假日政策/ }));
    const policy = await screen.findByRole('region', { name: '國定假日日曆' });
    fireEvent.click(within(policy).getByRole('button', { name: /編輯/ }));
    fireEvent.change(screen.getByLabelText('國定假日名稱'), { target: { value: '更新後的假日' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存國定假日變更' }));
    await screen.findByText('已重新查詢並確認最新國定假日政策。');
    expect(apply).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole('button', { name: /排班月曆/ }));
    await waitFor(() => expect(document.querySelector('.gantt-day-header-col.holiday')).toHaveTextContent('更新後的假日'));
    expect(monthReads()).toBe(2);
    expect(document.querySelector('.gantt-spans-layer')?.innerHTML).toBe(spans);
  });

  it('人員清單為空仍顯示完整日期列與國定假日', async () => {
    vi.mocked(staffDirectoryClient.queryPage).mockResolvedValue({ items: [], next_cursor: null });
    vi.mocked(holidayClient.query).mockImplementation(async query => {
      const horizon = 'from_date' in query ? query : { from_date: query.fromDate, to_date: query.toDate };
      return { planning_horizon: horizon, source_identity: 'test', calendar_version: 'a'.repeat(64), holidays: [{ holiday_date: horizon.from_date, holiday_name: '國慶日及補假測試名稱', is_double_pay_default: false }] };
    });
    render(<SchedulingPage />);
    await screen.findByText('目前沒有可顯示的服務人員摘要。');
    await waitFor(() => expect(document.querySelector('.gantt-day-header-col.holiday')).toHaveTextContent('國慶日及補假測試名稱'));
    expect(document.querySelectorAll('.gantt-day-header-col').length).toBeGreaterThanOrEqual(28);
  });

  it('篩選找不到人員仍保留假日日期列', async () => {
    vi.mocked(holidayClient.query).mockImplementation(async query => {
      const horizon = 'from_date' in query ? query : { from_date: query.fromDate, to_date: query.toDate };
      return { planning_horizon: horizon, source_identity: 'test', calendar_version: 'a'.repeat(64), holidays: [{ holiday_date: horizon.from_date, holiday_name: '測試國定假日', is_double_pay_default: false }] };
    });
    render(<SchedulingPage />);
    await waitFor(() => expect(document.querySelector('.gantt-day-header-col.holiday')).toHaveTextContent('測試國定假日'));
    fireEvent.change(screen.getByPlaceholderText('按月嫂姓名或編號...'), { target: { value: '不存在的人員' } });
    expect(document.querySelector('.gantt-day-header-col.holiday')).toHaveTextContent('測試國定假日');
    expect(document.querySelectorAll('.gantt-staff-matrix-row')).toHaveLength(0);
  });

  it('本月沒有匯入資料時明確提示，不冒稱查詢失敗', async () => {
    render(<SchedulingPage />);
    await screen.findByText('本月沒有已匯入的國定假日資料。');
    expect(screen.queryByText(/國定假日標示載入失敗/)).not.toBeInTheDocument();
    expect(document.querySelectorAll('.gantt-day-header-col').length).toBeGreaterThanOrEqual(28);
  });

  it('月曆假日查詢失敗有明確提示，可只重新讀取假日', async () => {
    vi.mocked(holidayClient.query).mockRejectedValueOnce(new Error('假日資料暫時無法讀取'));
    render(<SchedulingPage />);
    await screen.findByText(/國定假日標示載入失敗/);
    fireEvent.click(screen.getByRole('button', { name: '重新讀取假日' }));
    await waitFor(() => expect(screen.queryByText(/國定假日標示載入失敗/)).not.toBeInTheDocument());
    expect(holidayClient.query).toHaveBeenCalledTimes(2);
  });

  it('安全解碼舊代班連結，驗證案件與權限後帶往同案多月嫂排班', async () => {
    sessionClient.setSession('synthetic-token', {
      id: 1, username: 'fixture', display_name: 'Fixture', role: 'system_admin',
      capabilities: ['line.matching.override', 'system.administration'],
    });
    window.history.replaceState(null, '', '#scheduling?tab=leave_sub&case_no=%20CASE-SCH-001%20');
    const plan = vi.spyOn(ordersQueryClient, 'getAssignmentPlan').mockResolvedValue({
      case_no: 'CASE-SCH-001', order_version: 3, scheduling_version: 2, scheduling_generation: 1,
      client_finance_version: 1, payroll_version: 1, contracted_service_days: 1, service_hours_per_day: 8,
      service_started: false, assignments: [],
    });
    const apply = vi.spyOn(leaveSubstitutionClient, 'apply');

    render(<SchedulingPage />);

    await waitFor(() => expect(window.location.hash).toBe('#order-workbench-v2?case=CASE-SCH-001&work=service&staffing=upcoming'));
    expect(plan).toHaveBeenCalledWith('CASE-SCH-001', { signal: expect.any(AbortSignal) });
    expect(screen.queryByRole('button', { name: '代班待辦' })).not.toBeInTheDocument();
    expect(staffLeaveInboxClient.list).not.toHaveBeenCalled();
    expect(apply).not.toHaveBeenCalled();
  });

  it.each([
    ['#scheduling?tab=leave_sub', false],
    ['#scheduling?tab=leave_sub&case_no=A&case_no=B', false],
    ['#scheduling?tab=leave_sub&case_no=CASE-SCH-001', true],
  ] as const)('舊連結欠缺唯一案件或操作權限時拒絕導向（%s）', async (hash, validCase) => {
    window.history.replaceState(null, '', hash);
    const plan = vi.spyOn(ordersQueryClient, 'getAssignmentPlan').mockResolvedValue({
      case_no: 'CASE-SCH-001', order_version: 3, scheduling_version: 2, scheduling_generation: 1,
      client_finance_version: 1, payroll_version: 1, contracted_service_days: 1, service_hours_per_day: 8,
      service_started: false, assignments: [],
    });
    render(<SchedulingPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('無法確認案件或排班權限');
    expect(plan).toHaveBeenCalledTimes(validCase ? 1 : 0);
    expect(window.location.hash).toBe(hash);
    expect(staffLeaveInboxClient.list).not.toHaveBeenCalled();
  });

  it('未知 deep-link tab fail closed 回到 calendar 且不預填隱藏工作區', () => {
    window.location.hash = '#scheduling?tab=not_allowed&case_no=CASE-DL-002';

    render(<SchedulingPage />);

    expect(screen.getByRole('region', { name: '排班甘特月曆與服務人員檔期' })).toBeInTheDocument();
    expect(screen.queryByRole('combobox', { name: '請假代班訂單編號' })).not.toBeInTheDocument();
    expect(document.querySelector('[data-surface-id="scheduling.tab.calendar"]')).toHaveClass('active');

    expect(screen.queryByRole('button', { name: '代班待辦' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '開啟本案多月嫂排班' })).not.toBeInTheDocument();
  });

  it('loads a slow calendar in bounded batches without timeout retries or missing staff', async () => {
    vi.mocked(staffDirectoryClient.queryPage).mockResolvedValue({ items: Array.from({ length: 12 }, (_, index) => ({ id: index + 1, name: `測試人員${index + 1}`, phone: null, education: null })), next_cursor: null });
    let active = 0;
    let peak = 0;
    const releases: Array<() => void> = [];
    vi.mocked(schedulingCurrentClient.queryCurrentCalendar).mockImplementation(async query => {
      active += 1;
      peak = Math.max(peak, active);
      await new Promise<void>(resolve => { releases.push(resolve); });
      active -= 1;
      return { ...SCHEDULING_PROJECTION_EMPTY, staff_id: query.staffId, range_start: query.rangeStart, range_end: query.rangeEnd };
    });
    render(<SchedulingPage />);
    await waitFor(() => expect(schedulingCurrentClient.queryCurrentCalendar).toHaveBeenCalledTimes(3));
    for (let batch = 0; batch < 4; batch++) {
      releases.splice(0).forEach(resolve => resolve());
      if (batch < 3) await waitFor(() => expect(schedulingCurrentClient.queryCurrentCalendar).toHaveBeenCalledTimes((batch + 2) * 3));
      if (batch === 0) await waitFor(() => expect(screen.getAllByText(/本月無排班占用/)).toHaveLength(3));
    }
    await waitFor(() => expect(screen.getAllByText(/本月無排班占用/)).toHaveLength(12));
    expect(peak).toBe(3);
    expect(new Set(vi.mocked(schedulingCurrentClient.queryCurrentCalendar).mock.calls.map(([query]) => query.staffId)).size).toBe(12);
    expect(screen.queryByRole('button', { name: '重試月曆查詢' })).not.toBeInTheDocument();
  });

  it.each([
    ['malformed percent', '%E0%A4%A'],
    ['超過 50 字', 'A'.repeat(51)],
    ['控制字元', 'CASE%00DL-003'],
  ])('不以不合法的案件編號開啟多月嫂排班：%s', async (_scenario, encodedCaseNo) => {
    const hash = `#scheduling?tab=leave_sub&case_no=${encodedCaseNo}`;
    window.history.replaceState(null, '', hash);
    sessionClient.setSession('synthetic-token', {
      id: 1, username: 'fixture', display_name: 'Fixture', role: 'system_admin',
      capabilities: ['line.matching.override', 'system.administration'],
    });
    const getAssignmentPlan = vi.spyOn(ordersQueryClient, 'getAssignmentPlan');

    render(<SchedulingPage />);

    expect(await screen.findByRole('alert')).toHaveTextContent('無法確認案件或排班權限');
    expect(window.location.hash).toBe(hash);
    expect(getAssignmentPlan).not.toHaveBeenCalled();
    expect(staffLeaveInboxClient.list).not.toHaveBeenCalled();
    expect(screen.queryByRole('link', { name: '開啟本案多月嫂排班' })).not.toBeInTheDocument();
  });

  it('anchors calendar today to Asia/Taipei instead of the browser local timezone', () => {
    expect(taipeiCalendarDate(new Date('2026-08-22T16:30:00Z'))).toEqual({
      year: 2026,
      month: 8,
      day: 23,
    });
  });

  it('returns from another month and brings today into view with a synchronized date header', async () => {
    render(<SchedulingPage />);
    await waitFor(() => expect(document.querySelector('.gantt-matrix-scroll-wrapper')).toBeInTheDocument());
    const body = document.querySelector('.gantt-matrix-scroll-wrapper') as HTMLElement;
    const header = document.querySelector('.gantt-matrix-sticky-header') as HTMLElement;
    Object.defineProperty(body, 'clientWidth', { configurable: true, value: 600 });
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
      return {
        left: this.classList.contains('today') ? 1060 : 0,
        width: this.classList.contains('gantt-staff-header-cell') ? 260 : 40,
        top: 0, right: 0, bottom: 0, height: 0, x: 0, y: 0, toJSON: () => ({}),
      };
    });
    fireEvent.click(screen.getByRole('button', { name: '查看下個月' }));
    expect(header.querySelector('.today')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /今天/ }));
    await waitFor(() => expect(header.querySelector('.today')).not.toBeNull());
    expect(body.scrollLeft).toBe(650);
    expect(header.scrollLeft).toBe(650);
    body.scrollLeft = 0;
    header.scrollLeft = 0;
    fireEvent.click(screen.getByRole('button', { name: /今天/ }));
    expect(body.scrollLeft).toBe(650);
    expect(header.scrollLeft).toBe(650);
    expect(document.querySelector('.gantt-case-checks')).not.toHaveAttribute('open');
  });

  it('loads one current calendar for every visible staff row without a duplicate query', async () => {
    render(<SchedulingPage />);

    expect(screen.getByText(/正在載入服務人員摘要/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));
    expect(screen.getAllByText(/去敏人員甲/).length).toBeGreaterThan(0);
    expect(screen.getByText('正式服務履約')).toBeInTheDocument();
    expect(staffDirectoryClient.queryPage).toHaveBeenCalledTimes(1);
    expect(schedulingCurrentClient.queryCurrentCalendar).toHaveBeenCalledTimes(2);
    expect(staffAssignmentOptionsClient.getStaffAssignmentOptions).toHaveBeenCalledTimes(2);
    expect(ordersQueryClient.getOrderSummaries).toHaveBeenCalledWith(
      expect.objectContaining({ lifecycle_scope: 'unfinished' }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(coreStageProjectionMocks.loadAll).toHaveBeenCalledWith(
      { workbench_scope: 'in_progress', page_size: 200 },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );

    expect(schedulingCurrentClient.queryCurrentCalendar).toHaveBeenCalledWith(
      expect.objectContaining({ staffId: 12 }),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
  });

  it('keeps the fixed date header aligned with the horizontally scrolled calendar cells', async () => {
    render(<SchedulingPage />);

    await waitFor(() => expect(document.querySelector('[data-surface-id="scheduling.calendar.row"]')).toBeInTheDocument());
    const grid = document.querySelector('[data-surface-id="scheduling.calendar.grid"] .gantt-matrix-scroll-wrapper');
    const dateHeader = document.querySelector('[data-surface-id="scheduling.calendar.date-header"]');
    expect(grid).toBeInstanceOf(HTMLElement);
    expect(dateHeader).toBeInstanceOf(HTMLElement);

    (grid as HTMLElement).scrollLeft = 320;
    fireEvent.scroll(grid as HTMLElement);

    expect((dateHeader as HTMLElement).scrollLeft).toBe(320);
  });

  it('loads only viewport months and reuses each staff month after scrolling away and back', async () => {
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(function (this: HTMLElement) {
      return this.classList.contains('gantt-matrix-scroll-wrapper') ? 620 : 0;
    });
    vi.spyOn(HTMLElement.prototype, 'scrollWidth', 'get').mockImplementation(function (this: HTMLElement) {
      return this.classList.contains('gantt-matrix-scroll-wrapper') ? 260 + 36 * 136 : 0;
    });
    vi.mocked(schedulingCurrentClient.queryCurrentCalendar).mockImplementation(async query => ({
      ...SCHEDULING_PROJECTION_EMPTY,
      staff_id: query.staffId, range_start: query.rangeStart, range_end: query.rangeEnd,
    }));
    const canonical = vi.mocked(schedulingCurrentClient.queryCurrentCalendar);
    const monthly = vi.mocked(staffMonthlyScheduleClient.query);
    render(<SchedulingPage />);
    await waitFor(() => expect(canonical).toHaveBeenCalledTimes(4));
    await waitFor(() => expect(screen.queryByText('正在載入排班月曆…')).not.toBeInTheDocument());
    expect(new Set(canonical.mock.calls.map(([query]) => `${query.rangeStart}/${query.rangeEnd}`))).toEqual(new Set([
      '2026-07-01/2026-07-31', '2026-08-01/2026-08-31',
    ]));
    expect(new Set(monthly.mock.calls.map(([staffId, year, month]) => `${staffId}/${year}/${month}`))).toEqual(new Set([
      '11/2026/7', '12/2026/7', '11/2026/8', '12/2026/8',
    ]));

    const body = document.querySelector<HTMLElement>('.gantt-matrix-scroll-wrapper')!;
    body.scrollLeft = 400;
    fireEvent.scroll(body);
    await waitFor(() => expect(canonical).toHaveBeenCalledTimes(8));
    await waitFor(() => expect(screen.queryByText('正在載入排班月曆…')).not.toBeInTheDocument());
    expect(new Set(canonical.mock.calls.slice(4).map(([query]) => `${query.rangeStart}/${query.rangeEnd}`))).toEqual(new Set([
      '2026-01-01/2026-01-31', '2026-02-01/2026-02-28',
    ]));

    body.scrollLeft = 7 * 408 - 20;
    fireEvent.scroll(body);
    expect(screen.getByText(/目前可視：7月 ～ 8月/)).toBeInTheDocument();
    await act(async () => {});
    expect(canonical).toHaveBeenCalledTimes(8);
    expect(monthly).toHaveBeenCalledTimes(8);

    const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    fireEvent(document, new Event('visibilitychange'));
    expect(canonical).toHaveBeenCalledTimes(8);
    visibility.mockReturnValue('visible');
    fireEvent(document, new Event('visibilitychange'));
    await waitFor(() => expect(canonical).toHaveBeenCalledTimes(12));
    await waitFor(() => expect(screen.queryByText('正在載入排班月曆…')).not.toBeInTheDocument());
    expect(new Set(canonical.mock.calls.slice(8).map(([query]) => query.rangeStart))).toEqual(new Set([
      '2026-07-01', '2026-08-01',
    ]));
    body.scrollLeft = 400;
    fireEvent.scroll(body);
    await act(async () => {});
    expect(canonical).toHaveBeenCalledTimes(12);
  });

  it('discards late work from the old year and refetches that unfinished month on return', async () => {
    const canonical = vi.mocked(schedulingCurrentClient.queryCurrentCalendar);
    const pending: Array<(result: typeof SCHEDULING_PROJECTION_READY) => void> = [];
    canonical.mockImplementation(async query => ({
      ...SCHEDULING_PROJECTION_EMPTY,
      staff_id: query.staffId, range_start: query.rangeStart, range_end: query.rangeEnd,
    })).mockImplementationOnce(() => new Promise(resolve => pending.push(resolve)));
    render(<SchedulingPage />);
    await waitFor(() => expect(canonical).toHaveBeenCalledTimes(2));
    const [unfinished, options] = canonical.mock.calls[0];
    expect(screen.getByText('正在載入排班月曆…')).toBeInTheDocument();
    const healthyRow = document.querySelector<HTMLElement>('[data-staff-id="12"]')!;
    await waitFor(() => expect(within(healthyRow).getByText(/本月無排班占用/)).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: '查看下一年' }));
    await waitFor(() => expect(canonical).toHaveBeenCalledTimes(4));
    expect(options?.signal?.aborted).toBe(true);
    expect(canonical.mock.calls.slice(2).map(([query]) => query.rangeStart)).toEqual(['2027-08-01', '2027-08-01']);
    await act(async () => { pending[0](SCHEDULING_PROJECTION_READY); });
    expect(document.querySelectorAll('.gantt-span-bar')).toHaveLength(0);

    fireEvent.click(screen.getByRole('button', { name: '查看上一年' }));
    await waitFor(() => expect(canonical).toHaveBeenCalledTimes(5));
    expect(canonical.mock.calls[4][0]).toEqual(unfinished);
    await waitFor(() => expect(screen.queryByText('正在載入排班月曆…')).not.toBeInTheDocument());
    expect(document.querySelectorAll('.gantt-span-bar')).toHaveLength(0);
  });

  it.each(['待補件', '洽談中'])('未排班的%s案件只在訂金前供排查', async (orderStatus) => {
    const summary = (caseNo: string, clientName: string) => ({
      case_no: caseNo,
      client_name: clientName,
      order_status: orderStatus,
      staff_name: '去敏人員甲',
      identity_status: 'verified',
      start_date: '2026-08-01',
      end_date: '2026-08-10',
      actual_start_date: null,
      actual_end_date: null,
      service_days: 10,
      total_employer_self_pay_payable: 10000,
    });
    vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValue({
      items: [
        summary('CASE-STAGE-7', '簽署完成前'),
        summary('CASE-STAGE-8', '訂金階段'),
        summary('CASE-STAGE-9', '日期確認階段'),
        summary('CASE-STAGE-10', '排班服務階段'),
      ],
      next_cursor: null,
      etag: 'd'.repeat(64),
    });
    vi.mocked(staffAssignmentOptionsClient.getStaffAssignmentOptions).mockResolvedValue(
      ['CASE-STAGE-7', 'CASE-STAGE-8', 'CASE-STAGE-9', 'CASE-STAGE-10'].map((caseNo, index) => ({
        id: index + 1,
        case_no: caseNo,
        staff_id: 11,
        status: 'planned',
        assigned_start_date: '2026-08-01',
        assigned_end_date: '2026-08-10',
        order_status: orderStatus,
        actual_start_date: null,
        actual_end_date: null,
        staff_name: '去敏人員甲',
      })),
    );
    vi.mocked(schedulingCurrentClient.queryCurrentCalendar).mockResolvedValue(SCHEDULING_PROJECTION_EMPTY);
    coreStageProjectionMocks.loadAll.mockResolvedValue({
      items: [
        { case_no: 'CASE-STAGE-7', current_core_stage_ordinal: 7 },
        { case_no: 'CASE-STAGE-8', current_core_stage_ordinal: 8 },
        { case_no: 'CASE-STAGE-9', current_core_stage_ordinal: 9 },
        { case_no: 'CASE-STAGE-10', current_core_stage_ordinal: 10 },
      ],
    });

    render(<SchedulingPage />);

    const select = await screen.findByRole('combobox', { name: '資格查詢案件編號' });
    await waitFor(() => expect(select).toBeEnabled());
    expect(screen.getByRole('option', { name: /CASE-STAGE-7/ })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /CASE-STAGE-8/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /CASE-STAGE-9/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /CASE-STAGE-10/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /CASE-STAGE-/ })).not.toBeInTheDocument();
  });

  it('排查案件包含尚未建立月嫂指派的洽談中訂單', async () => {
    vi.mocked(staffAssignmentOptionsClient.getStaffAssignmentOptions).mockResolvedValue([]);

    render(<SchedulingPage />);

    const select = await screen.findByRole('combobox', { name: '資格查詢案件編號' });
    await waitFor(() => expect(select).toBeEnabled());
    expect(screen.getByRole('option', { name: /115000003.*排查客戶乙/ })).toBeInTheDocument();
  });

  it('loads all bounded staff pages and sorts union labels before rendering the complete month axis', async () => {
    vi.mocked(staffDirectoryClient.queryPage)
      .mockResolvedValueOnce({
        items: [{ id: 11, union_no: 'A10', name: '去敏人員甲', phone: null, education: null }],
        next_cursor: 11,
      })
      .mockResolvedValueOnce({
        items: [{ id: 12, union_no: 'A2', name: '去敏人員乙', phone: null, education: null }],
        next_cursor: null,
      });

    render(<SchedulingPage />);
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));
    expect(document.querySelectorAll('.gantt-month-group-col')).toHaveLength(12);
    expect(document.querySelectorAll('.gantt-day-header-col[data-date]')).toHaveLength(36);
    expect(staffDirectoryClient.queryPage).toHaveBeenNthCalledWith(
      1,
      { pageSize: 20, lifecycleState: 'active' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );

    expect(Array.from(document.querySelectorAll('.gantt-staff-matrix-row strong')).map(node => node.textContent)).toEqual(['A2 去敏人員乙', 'A10 去敏人員甲']);
    expect(screen.queryByText('STF-011')).not.toBeInTheDocument();
    expect(staffDirectoryClient.queryPage).toHaveBeenNthCalledWith(
      2,
      { pageSize: 20, afterId: 11, lifecycleState: 'active' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(screen.queryByRole('button', { name: '載入更多服務人員' })).not.toBeInTheDocument();
    expect(staffDirectoryClient.queryPage).toHaveBeenCalledTimes(2);
    expect(document.querySelector('[data-control-id="scheduling.staff.next-page"]')).not.toBeInTheDocument();
  });

  it('does not show a partial staff list if a later page fails and retries the complete list', async () => {
    const first = { items: [{ id: 11, union_no: 'A10', name: '去敏人員甲', phone: null, education: null }], next_cursor: 11 };
    const second = { items: [{ id: 12, union_no: 'A2', name: '去敏人員乙', phone: null, education: null }], next_cursor: null };
    vi.mocked(staffDirectoryClient.queryPage)
      .mockResolvedValueOnce(first).mockRejectedValueOnce(new Error('transport unavailable'))
      .mockResolvedValueOnce(first).mockResolvedValueOnce(second);
    render(<SchedulingPage />);
    const retry = await screen.findByRole('button', { name: '重試摘要查詢' });
    expect(document.querySelectorAll('.gantt-staff-matrix-row')).toHaveLength(0);
    expect(staffDirectoryClient.queryPage).toHaveBeenCalledTimes(2);
    fireEvent.click(retry);
    await screen.findByText('A2 去敏人員乙');
    expect(staffDirectoryClient.queryPage).toHaveBeenCalledTimes(4);
  });

  it('renders explicit empty and error states without fake occupancy spans', async () => {
    vi.mocked(schedulingCurrentClient.queryCurrentCalendar).mockResolvedValue(
      SCHEDULING_PROJECTION_EMPTY
    );
    const empty = render(<SchedulingPage />);
    await waitFor(() => expect(screen.getAllByText(/本月無排班占用/)).toHaveLength(2));
    expect(document.querySelectorAll('.gantt-span-bar')).toHaveLength(0);
    expect(screen.queryByText(/尚未查詢資格/)).not.toBeInTheDocument();
    empty.unmount();

    vi.mocked(schedulingCurrentClient.queryCurrentCalendar).mockRejectedValueOnce(
      new Error('typed scheduling failure')
    );
    render(<SchedulingPage />);
    await waitFor(() => expect(screen.getByTitle(/typed scheduling failure/)).toBeInTheDocument());
    expect(document.querySelectorAll('.gantt-span-bar')).toHaveLength(0);
    expect(screen.getByRole('alert')).toHaveTextContent('1 位服務人員的排班資料載入失敗');
  });

  it('renders a historical interval as a display-only overlay when the canonical calendar is empty', async () => {
    vi.mocked(schedulingCurrentClient.queryCurrentCalendar).mockResolvedValue(SCHEDULING_PROJECTION_EMPTY);
    vi.mocked(staffMonthlyScheduleClient.query).mockImplementation(async (staffId, year, month) => ({
      staff_id: staffId, year, month,
      days: [
        { work_date: `${year}-${String(month).padStart(2, '0')}-04`, status: 'historical_assignment', assignment_id: 81, case_no: 'HIS-081', client_name: '歷史客戶', staff_id: staffId, order_status: 'completed', is_work_day: false, is_double_pay: false },
        { work_date: `${year}-${String(month).padStart(2, '0')}-05`, status: 'historical_assignment', assignment_id: 81, case_no: 'HIS-081', client_name: '歷史客戶', staff_id: staffId, order_status: 'completed', is_work_day: false, is_double_pay: false },
      ],
      schedule_map: {},
    }));

    render(<SchedulingPage />);

    await waitFor(() => expect(document.querySelectorAll('.gantt-span-bar.span-historical')).toHaveLength(2));
    const overlay = document.querySelector('.gantt-span-bar.span-historical');
    expect(overlay).toHaveAttribute('data-start-day', '4');
    expect(overlay).toHaveAttribute('data-end-day', '5');
    expect(overlay).toHaveTextContent('歷史指派區間（不計入工時）');
    expect(overlay).toHaveTextContent('整案日期不可用');
    expect(overlay).not.toHaveClass('span-ghost-clickable');
    if (overlay) fireEvent.click(overlay);
    expect(window.location.hash).toBe('#order-workbench-v2?case=HIS-081&work=service');
  });

  it.each([
    { status: 'historical_reservation', label: '歷史預定', orderStatus: '歷史訂單－未服務', hasTime: false },
    { status: 'historical_reservation', label: '歷史預定', orderStatus: '訂單成立', hasTime: false },
    { status: 'historical_assignment', label: '歷史指派', orderStatus: '歷史訂單－服務中', hasTime: true },
    { status: 'historical_assignment', label: '歷史指派', orderStatus: '歷史訂單－服務完成', hasTime: true },
    { status: 'historical_assignment', label: '歷史指派區間', orderStatus: '歷史訂單－帳務完成', hasTime: false },
  ] as const)('shows full case dates for $orderStatus ($label)', async ({ status, label, orderStatus, hasTime }) => {
    const { year, month } = taipeiCalendarDate(new Date());
    const dayInMonth = `${year}-${String(month).padStart(2, '0')}`;
    const previousMonth = new Date(Date.UTC(year, month - 2, 5)).toISOString().slice(0, 10);
    const reservation = status === 'historical_reservation';
    const nextMonth = new Date(Date.UTC(year, month, 27)).toISOString().slice(0, 10);
    const plannedStart = reservation ? `${dayInMonth}-28` : `${previousMonth.slice(0, 7)}-19`;
    const plannedEnd = reservation ? nextMonth : `${dayInMonth}-10`;
    const actualStart = previousMonth;
    const finalDay = hasTime ? 2 : 3;
    const actualEnd = `${dayInMonth}-0${finalDay}`;
    const orderDetail = vi.spyOn(ordersQueryClient, 'getOrderDetail').mockResolvedValue({
      case_no: 'HIS-082', client_id: 1, staff_id: 11, client_name: '歷史摘要客戶',
      staff_name: '去敏人員甲', order_status: orderStatus, identity_status: 'verified',
      cancel_reason: null, line_group_id: null, contract_identity: null, deposit_date: null,
      start_date: plannedStart, end_date: plannedEnd,
      actual_start_date: actualStart, actual_end_date: actualEnd, service_days: 10,
      service_hours_per_day: 9, deposit_service_days: null, floor_fee: 0, custom_rest_dates: null,
    });
    vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValue({
      items: [{
        case_no: 'HIS-082', client_name: '歷史摘要客戶', order_status: orderStatus,
        staff_name: '去敏人員甲', identity_status: 'verified', start_date: `${dayInMonth}-01`,
        end_date: `${dayInMonth}-10`, actual_start_date: null, actual_end_date: null,
        service_days: 10, total_employer_self_pay_payable: null,
      }],
      next_cursor: null,
      etag: 'a'.repeat(64),
    });
    vi.mocked(schedulingCurrentClient.queryCurrentCalendar).mockResolvedValue(SCHEDULING_PROJECTION_EMPTY);
    vi.mocked(staffMonthlyScheduleClient.query).mockImplementation(async (staffId, year, month) => ({
      staff_id: staffId, year, month,
      days: staffId === 11 ? (reservation ? [28, new Date(Date.UTC(year, month, 0)).getUTCDate()] : [1, finalDay])
        .filter((day, index, days) => index === 0 || day !== days[0]).map(day => {
        const date = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        return {
          work_date: date, status, assignment_id: status === 'historical_assignment' ? 82 : null,
          case_no: 'HIS-082', client_name: '歷史月曆客戶', staff_id: staffId,
          order_status: orderStatus, is_work_day: false, is_double_pay: false,
          ...(hasTime && {
            service_date: date, starts_at: `${date}T09:00:00+08:00`, ends_at: `${date}T18:00:00+08:00`,
          }),
        };
      }) : [],
      schedule_map: {},
    }));

    render(<SchedulingPage />);

    const bar = await screen.findByRole('button', { name: /歷史(?:摘要|月曆)客戶.*HIS-082/ });
    const expectedDates = reservation ? `${plannedStart} ～ ${plannedEnd}` : `${actualStart} ～ ${actualEnd}`;
    const lastDayOfMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
    const lastDayOfNextMonth = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
    const startColumn = reservation
      ? (month - 1) * 3 + 2 + 7 / (lastDayOfMonth - 20)
      : month === 1 ? 0 : (month - 2) * 3 + 0.4;
    const endColumn = reservation
      ? month === 12 ? 36 : month * 3 + 2 + 7 / (lastDayOfNextMonth - 20)
      : (month - 1) * 3 + finalDay / 10;
    expect(bar).toHaveClass('span-historical');
    expect(bar).toHaveTextContent(label);
    expect(bar).toHaveTextContent(expectedDates);
    expect(bar.getAttribute('title')).toContain(expectedDates);
    expect(parseFloat(bar.style.left)).toBeCloseTo(startColumn / 36 * 100, 5);
    expect(parseFloat(bar.style.width)).toBeCloseTo((endColumn - startColumn) / 36 * 100, 5);
    fireEvent.click(bar);
    expect(window.location.hash).toContain('&work=service');
    expect(orderDetail).toHaveBeenCalledTimes(1);
  });

  it('keeps a historical overnight continuation separate from formal shifts for the same assignment', async () => {
    vi.mocked(schedulingCurrentClient.queryCurrentCalendar).mockResolvedValue(SCHEDULING_PROJECTION_EMPTY);
    vi.mocked(staffMonthlyScheduleClient.query).mockImplementation(async (staffId, year, month) => {
      const ym = `${year}-${String(month).padStart(2, '0')}`;
      const rows = [
        { serviceDay: 10, workDay: 10, status: 'working' },
        { serviceDay: 10, workDay: 11, status: 'working' },
        { serviceDay: 11, workDay: 11, status: 'historical_assignment' },
        { serviceDay: 11, workDay: 12, status: 'historical_assignment' },
      ] as const;
      return {
        staff_id: staffId, year, month, schedule_map: {},
        days: staffId === 11 ? rows.map(({ serviceDay, workDay, status }) => ({
          work_date: `${ym}-${workDay}`, service_date: `${ym}-${serviceDay}`,
          starts_at: `${ym}-${serviceDay}T22:00:00+08:00`, ends_at: `${ym}-${serviceDay + 1}T06:00:00+08:00`,
          case_no: 'HIS-OVERNIGHT', assignment_id: 83, staff_id: staffId, status,
          is_work_day: status === 'working', is_double_pay: false,
        })) : [],
      };
    });

    render(<SchedulingPage />);

    const formal = await screen.findByRole('button', { name: /HIS-OVERNIGHT.*排班/ });
    const continuation = screen.getByRole('button', { name: /HIS-OVERNIGHT.*歷史指派.*00:00–06:00 續班/ });
    expect(continuation).toHaveClass('span-historical');
    expect(continuation).toHaveAttribute('data-start-day', '12');
    expect(formal).toHaveAttribute('data-end-day', '11');
  });

  it('keeps canonical occupancy ahead on overlapping dates while retaining the remaining historical dates', async () => {
    vi.mocked(staffMonthlyScheduleClient.query).mockImplementation(async (staffId, year, month) => ({
      staff_id: staffId, year, month,
      days: [
        { work_date: `${year}-${String(month).padStart(2, '0')}-01`, status: 'historical_assignment', assignment_id: 81, case_no: 'HIS-081', client_name: '歷史客戶', staff_id: staffId, order_status: 'completed', is_work_day: false, is_double_pay: false },
        { work_date: `${year}-${String(month).padStart(2, '0')}-02`, status: 'historical_assignment', assignment_id: 81, case_no: 'HIS-081', client_name: '歷史客戶', staff_id: staffId, order_status: 'completed', is_work_day: false, is_double_pay: false },
        { work_date: `${year}-${String(month).padStart(2, '0')}-03`, status: 'historical_assignment', assignment_id: 81, case_no: 'HIS-081', client_name: '歷史客戶', staff_id: staffId, order_status: 'completed', is_work_day: false, is_double_pay: false },
      ],
      schedule_map: {},
    }));

    render(<SchedulingPage />);

    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));
    const remainingHistorical = document.querySelector('.gantt-span-bar.span-historical');
    expect(remainingHistorical).toHaveAttribute('data-start-day', '3');
    expect(remainingHistorical).toHaveAttribute('data-end-day', '3');
    expect(document.querySelectorAll('.gantt-span-bar:not(.span-historical)')).not.toHaveLength(0);
  });

  it('keeps canonical data visible and retries only the failed historical month for the affected row', async () => {
    const monthly = vi.mocked(staffMonthlyScheduleClient.query);
    monthly.mockRejectedValueOnce(new Error('歷史指派月曆回應結構異常。'));

    render(<SchedulingPage />);

    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));
    expect(screen.getByText(/歷史指派區間未載入：歷史指派月曆回應結構異常/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重試月曆查詢' }));
    expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0);
    await waitFor(() => expect(screen.queryByText(/歷史指派區間未載入/)).not.toBeInTheDocument());
    expect(monthly).toHaveBeenCalledTimes(3);
    expect(monthly.mock.calls[2].slice(0, 3)).toEqual(monthly.mock.calls[0].slice(0, 3));
    expect(schedulingCurrentClient.queryCurrentCalendar).toHaveBeenCalledTimes(2);
  });

  it('retries canonical terms-incomplete for the affected row without refetching its historical month', async () => {
    const canonical = vi.mocked(schedulingCurrentClient.queryCurrentCalendar);
    canonical.mockRejectedValueOnce(new SchedulingCurrentError('SCHEDULING_CONFLICT', '時段未確認。', {
      publicCode: 'service_time_terms_incomplete',
    }));
    render(<SchedulingPage />);

    const retry = await screen.findByRole('button', { name: '重試月曆查詢' });
    expect(screen.getByText(/訂單的每日服務時段尚未完整/)).toBeInTheDocument();
    fireEvent.click(retry);
    await waitFor(() => expect(screen.queryByText(/訂單的每日服務時段尚未完整/)).not.toBeInTheDocument());
    expect(canonical).toHaveBeenCalledTimes(3);
    expect(canonical.mock.calls[2][0]).toEqual(canonical.mock.calls[0][0]);
    expect(staffMonthlyScheduleClient.query).toHaveBeenCalledTimes(2);
  });

  it('still renders historical intervals when the canonical calendar query fails', async () => {
    vi.mocked(schedulingCurrentClient.queryCurrentCalendar).mockRejectedValue(new Error('canonical unavailable'));
    vi.mocked(staffMonthlyScheduleClient.query).mockImplementation(async (staffId, year, month) => ({
      staff_id: staffId, year, month,
      days: [{ work_date: `${year}-${String(month).padStart(2, '0')}-04`, status: 'historical_assignment', assignment_id: 81, case_no: 'HIS-081', client_name: '歷史客戶', staff_id: staffId, order_status: 'completed', is_work_day: false, is_double_pay: false }],
      schedule_map: {},
    }));

    render(<SchedulingPage />);

    await waitFor(() => expect(document.querySelectorAll('.gantt-span-bar.span-historical')).toHaveLength(2));
    expect(screen.getByRole('alert')).toHaveTextContent('2 位服務人員的排班資料載入失敗');
  });

  it('renders completed service from the server lifecycle without a service-in-progress label', async () => {
    vi.mocked(schedulingCurrentClient.queryCurrentCalendar).mockImplementation(async (query) => ({
      ...SCHEDULING_PROJECTION_READY,
      staff_id: query.staffId,
      range_start: query.rangeStart,
      range_end: query.rangeEnd,
      assignments: SCHEDULING_PROJECTION_READY.assignments.map((assignment) => ({
        ...assignment,
        staff_id: query.staffId,
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
    }));

    render(<SchedulingPage />);

    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));
    expect(screen.getAllByText('⚪ 服務已完成')).toHaveLength(2);
    expect(document.querySelector('.gantt-span-bar')).toHaveTextContent('服務已結束');
    expect(document.querySelector('.gantt-span-bar')).not.toHaveTextContent('服務中');
    expect(document.querySelector('.staff-diagnostic-tag')).not.toHaveTextContent('正常履約中');
  });

  it('fails closed when typed case options cannot load and recovers through retry', async () => {
    vi.mocked(staffAssignmentOptionsClient.getStaffAssignmentOptions)
      .mockRejectedValueOnce(new Error('typed assignment options failure'));

    render(<SchedulingPage />);

    await waitFor(() => expect(screen.getByText('重新載入案件選項')).toBeInTheDocument());
    expect(screen.getByRole('combobox', { name: '資格查詢案件編號' })).toBeDisabled();
    expect(screen.queryByRole('textbox', { name: '資格查詢案件編號' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '重新載入案件選項' }));
    await waitFor(() => expect(screen.getByRole('combobox', { name: '資格查詢案件編號' })).toBeEnabled());
    expect(screen.getByRole('option', { name: /115000003.*排查客戶乙/ })).toBeInTheDocument();
  });

  it('marks official workdays without assignment lifecycle as data requiring correction', async () => {
    vi.mocked(schedulingCurrentClient.queryCurrentCalendar).mockImplementation(async (query) => ({
      ...SCHEDULING_PROJECTION_READY,
      staff_id: query.staffId,
      range_start: query.rangeStart,
      range_end: query.rangeEnd,
      assignments: [],
      days: SCHEDULING_PROJECTION_READY.days.map((day) => ({
        ...day,
        entries: day.entries
          .filter((entry) => entry.occupancy_kind === 'official_workday')
          .map((entry) => ({ ...entry, assignment_status: null })),
        available: day.entries.some((entry) => entry.occupancy_kind === 'official_workday')
          ? false
          : true,
      })),
    }));

    render(<SchedulingPage />);

    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));
    expect(screen.queryByText(/服務已完成/)).not.toBeInTheDocument();
    expect(screen.getAllByText(/狀態未知.*資料待補正/).length).toBeGreaterThan(0);
  });

  it('shows qualification checks, collisions and data notes after the typed query click', async () => {
    const query = vi.spyOn(schedulingEligibilityCollisionClient, 'query').mockResolvedValue({
      case_no: '115000003',
      case_status: '洽談中',
      as_of: '2026-08-23',
      evaluated_at: '2026-08-23T09:00:00+08:00',
      scheduling_version: 7,
      staff: [{
        staff_id: 12,
        eligibility: 'partial',
        availability: 'requires_review',
        qualification_checks: [{
          code: 'service_qualification',
          status: 'unknown',
          owner: 'HCM',
          source_identity: 'staff-12',
          source_version: 4,
          detail: '接單資格根事實不完整',
        }],
        collisions: [{
          kind: 'data_integrity',
          severity: 'requires_review',
          staff_id: 12,
          case_no: '115000003',
          assignment_id: null,
          source_id: 91,
          collision_date: '2026-08-23',
          start_date: null,
          end_date: null,
          owner: 'Scheduling',
          source_identity: 'review-91',
          detail: '歷史排班 lineage 待人工確認',
        }],
        coverage: {
          start_date: '2026-08-23',
          end_date: '2026-08-24',
          required_day_count: 2,
          available_day_count: 1,
          missing_dates: [],
          review_dates: ['2026-08-24'],
          status: 'requires_review',
        },
        partial_data: ['service_time_terms_incomplete'],
      }],
      partial_data: [],
    });

    render(<SchedulingPage />);
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));
    fireEvent.change(screen.getByRole('combobox', { name: '資格查詢案件編號' }), {
      target: { value: '115000003' },
    });

    await waitFor(() => expect(query).toHaveBeenCalledWith(
      expect.objectContaining({ caseNo: '115000003', staffId: 11 }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
    await waitFor(() => expect(document.body).toHaveTextContent(
      /服務日期：\s*2026-08-23 ～ 2026-08-24/,
    ));

    fireEvent.click(screen.getByRole('button', { name: '檢查 去敏人員乙 的資格與檔期' }));

    await waitFor(() => expect(query).toHaveBeenCalledWith(
      expect.objectContaining({ caseNo: '115000003', staffId: 12 }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
    expect(await screen.findByText(/客戶需求 ✕ 月嫂偏好與條件比對/)).toBeInTheDocument();
    expect(screen.getAllByText('服務資格').length).toBeGreaterThan(0);
    expect(screen.getByText('資料待補正（無法判定）')).toBeInTheDocument();
    expect(screen.getByText('接單資格根事實不完整')).toBeInTheDocument();
    expect(screen.getByText(/檔期衝突與 7 天排班緩衝期判定/)).toBeInTheDocument();
    expect(screen.getByText(/資料待補正.*需人工確認/)).toBeInTheDocument();
    expect(document.body).toHaveTextContent(/歷史排班\s*來源關聯\s*待人工確認/);
    expect(screen.getByText(/需補齊：每日服務時段尚未完整；補齊後再查詢/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/service_qualification|data_integrity|service_time_terms_incomplete/);
  });

  it('保留完整需求期間並只標示已確認衝突的需求日', async () => {
    vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValue({
      items: [{
        case_no: '115000003', client_name: '排查客戶乙', order_status: '洽談中',
        staff_name: '去敏人員乙', identity_status: 'verified', start_date: '2026-08-01',
        end_date: '2026-08-03', actual_start_date: null, actual_end_date: null,
        service_days: 3, total_employer_self_pay_payable: 2000,
      }],
      next_cursor: null,
      etag: 'b'.repeat(64),
    });
    vi.spyOn(schedulingEligibilityCollisionClient, 'query').mockResolvedValue({
      case_no: '115000003',
      case_status: '洽談中',
      as_of: '2026-08-25',
      evaluated_at: '2026-08-25T09:00:00+08:00',
      scheduling_version: 8,
      staff: [{
        staff_id: 11,
        eligibility: 'eligible',
        availability: 'blocked',
        qualification_checks: [],
        collisions: [],
        coverage: {
          start_date: '2026-08-01',
          end_date: '2026-08-03',
          required_day_count: 3,
          available_day_count: 2,
          missing_dates: ['2026-08-02'],
          review_dates: [],
          status: 'incomplete',
        },
        partial_data: [],
      }],
      partial_data: [],
    });

    render(<SchedulingPage />);
    await waitFor(() => expect(screen.getByRole('combobox', { name: '資格查詢案件編號' })).toBeEnabled());
    fireEvent.change(screen.getByRole('combobox', { name: '資格查詢案件編號' }), {
      target: { value: '115000003' },
    });

    await waitFor(() => expect(screen.getAllByText('115000003 · 時段衝突').length).toBeGreaterThan(0));
    const conflictSpans = [...document.querySelectorAll('.gantt-span-bar.span-conflict')];
    expect(conflictSpans.length).toBeGreaterThan(0);
    conflictSpans.forEach((span) => {
      expect(span).toHaveAttribute('data-start-day', '2');
      expect(span).toHaveAttribute('data-end-day', '2');
    });
  });

  it('跨月案件只在發生衝突的月份和需求日顯示衝突', async () => {
    vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValue({
      items: [{
        case_no: '115000003', client_name: '跨月排查客戶', order_status: '洽談中',
        staff_name: null, identity_status: 'verified', start_date: '2026-08-30',
        end_date: '2026-09-03', actual_start_date: null, actual_end_date: null,
        service_days: 5, total_employer_self_pay_payable: 2000,
      }],
      next_cursor: null,
      etag: 'c'.repeat(64),
    });
    vi.mocked(schedulingCurrentClient.queryCurrentCalendar).mockImplementation(async (query) => ({
      ...SCHEDULING_PROJECTION_EMPTY,
      staff_id: query.staffId,
      range_start: query.rangeStart,
      range_end: query.rangeEnd,
    }));
    vi.spyOn(schedulingEligibilityCollisionClient, 'query').mockImplementation(async (query) => ({
      case_no: query.caseNo,
      case_status: '洽談中',
      as_of: query.asOf,
      evaluated_at: `${query.asOf}T09:00:00+08:00`,
      scheduling_version: 9,
      staff: [{
        staff_id: query.staffId,
        eligibility: 'eligible',
        availability: query.staffId === 11 ? 'blocked' : 'available',
        qualification_checks: [],
        collisions: query.staffId === 11 ? [{
          kind: 'assignment_interval',
          severity: 'hard_block',
          staff_id: query.staffId,
          case_no: 'OTHER-CASE',
          assignment_id: 99,
          source_id: 99,
          collision_date: '2026-09-02',
          start_date: '2026-09-02',
          end_date: '2026-09-02',
          owner: 'Scheduling',
          source_identity: 'assignment-99',
          detail: '跨月後段撞期',
        }] : [],
        coverage: {
          start_date: '2026-08-30',
          end_date: '2026-09-03',
          required_day_count: 5,
          available_day_count: query.staffId === 11 ? 4 : 5,
          missing_dates: query.staffId === 11 ? ['2026-09-02'] : [],
          review_dates: [],
          status: query.staffId === 11 ? 'incomplete' : 'complete',
        },
        partial_data: [],
      }],
      partial_data: [],
    }));

    render(<SchedulingPage />);
    await waitFor(() => expect(screen.getByRole('combobox', { name: '資格查詢案件編號' })).toBeEnabled());
    await waitFor(() => expect(screen.getAllByText(/本月無排班占用/)).toHaveLength(2));
    fireEvent.change(screen.getByRole('combobox', { name: '資格查詢案件編號' }), {
      target: { value: '115000003' },
    });

    const staffSpan = (staffId: number, selector: string) => document.querySelector(
      `[data-staff-id="${staffId}"] ${selector}`,
    );
    await waitFor(() => expect(document.querySelector('[data-staff-id="11"]')).toHaveAttribute('data-case-outcome', 'hard_conflict'));
    expect(document.querySelector('[data-staff-id="11"]')).toHaveAttribute('data-case-start-day', '30');
    expect(document.querySelector('[data-staff-id="11"]')).toHaveAttribute('data-case-end-day', '31');
    expect(staffSpan(11, '.span-conflict')).toBeNull();
    expect(staffSpan(11, '.span-free')).toHaveAttribute('data-start-day', '30');
    expect(staffSpan(12, '.span-free')).toHaveAttribute('data-start-day', '30');
    expect(staffSpan(12, '.span-free')).toHaveAttribute('data-end-day', '31');

    fireEvent.click(screen.getByRole('button', { name: '查看下個月' }));
    await waitFor(() => expect(staffSpan(11, '.span-conflict')).toHaveAttribute('data-start-day', '2'));
    expect(staffSpan(11, '.span-conflict')).toHaveAttribute('data-end-day', '2');
    expect(staffSpan(12, '.span-free')).toHaveAttribute('data-start-day', '1');
    expect(staffSpan(12, '.span-free')).toHaveAttribute('data-end-day', '3');
  });

  it('refreshes the changed staff calendar and case checks after availability changes', async () => {
    vi.spyOn(schedulingEligibilityCollisionClient, 'query').mockRejectedValue(new Error('synthetic unavailable query'));
    render(<SchedulingPage />);
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));
    fireEvent.change(screen.getByRole('combobox', { name: '資格查詢案件編號' }), { target: { value: '115000003' } });
    await waitFor(() => expect(schedulingEligibilityCollisionClient.query).toHaveBeenCalled());
    const beforeCalendar = vi.mocked(schedulingCurrentClient.queryCurrentCalendar).mock.calls.length;
    const beforeEligibility = vi.mocked(schedulingEligibilityCollisionClient.query).mock.calls.length;
    act(() => publishStaffAvailabilityChange(11));
    await waitFor(() => expect(schedulingCurrentClient.queryCurrentCalendar).toHaveBeenCalledTimes(beforeCalendar + 1));
    expect(vi.mocked(schedulingCurrentClient.queryCurrentCalendar).mock.calls.at(-1)?.[0].staffId).toBe(11);
    await waitFor(() => expect(vi.mocked(schedulingEligibilityCollisionClient.query).mock.calls.length).toBeGreaterThan(beforeEligibility));
    act(() => publishStaffAvailabilityChange(999999));
    expect(schedulingCurrentClient.queryCurrentCalendar).toHaveBeenCalledTimes(beforeCalendar + 1);
  });

  it('invalidates the changed staff month without interrupting another pending row', async () => {
    const pending: Array<(value: typeof SCHEDULING_PROJECTION_EMPTY) => void> = [];
    const canonical = vi.mocked(schedulingCurrentClient.queryCurrentCalendar);
    canonical.mockImplementationOnce(() => new Promise(resolve => pending.push(resolve)))
      .mockImplementationOnce(() => new Promise(resolve => pending.push(resolve)))
      .mockImplementation(async query => ({ ...SCHEDULING_PROJECTION_EMPTY, staff_id: query.staffId, range_start: query.rangeStart, range_end: query.rangeEnd }));
    render(<SchedulingPage />);
    await waitFor(() => expect(pending).toHaveLength(2));
    act(() => publishStaffAvailabilityChange(11));
    await waitFor(() => expect(canonical).toHaveBeenCalledTimes(3));
    for (const [query, options] of canonical.mock.calls.slice(0, 2)) {
      expect(options?.signal?.aborted).toBe(query.staffId === 11);
    }
    expect(canonical.mock.calls[2][0].staffId).toBe(11);
    await act(async () => { pending.forEach(resolve => resolve(SCHEDULING_PROJECTION_EMPTY)); });
    await waitFor(() => expect(screen.getAllByText(/本月無排班占用/)).toHaveLength(2));
  });

  it('只開放已具備業務輸入的排班與政策操作', async () => {
    render(<SchedulingPage />);
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));

    expect(document.querySelectorAll('main')).toHaveLength(0);
    expect(screen.getByRole('region', { name: '排班甘特月曆與服務人員檔期' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: '資格查詢案件編號' })).toBeEnabled();
    expect(document.querySelector('[data-control-id="scheduling.candidate-pool.add"]')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '代班待辦' })).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="scheduling.leave.query"]')).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="scheduling.leave.preview"]')).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="scheduling.leave.apply"]')).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="scheduling.leave.extension"]')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /國定假日政策/ }));
    await waitFor(() => expect(document.querySelector('[data-control-id="scheduling.holiday.query"]')).toBeEnabled());
    expect(document.querySelector('[data-control-id="scheduling.holiday.preview"]')).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="scheduling.holiday.apply"]')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /新增國定假日/ })).toBeEnabled();
    expect(screen.queryByRole('button', { name: '代班待辦' })).not.toBeInTheDocument();
    expect(screen.queryByText('歷史請假紀錄')).not.toBeInTheDocument();
    expect(staffLeaveInboxClient.list).not.toHaveBeenCalled();
  });

  it('顯示全年度 12 個月 × 上／中／下旬三等份表頭，並以底部滑軌同步捲動表頭與內容', async () => {
    render(<SchedulingPage />);
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));

    expect(document.querySelectorAll('.gantt-month-group-col')).toHaveLength(12);
    expect(document.querySelectorAll('.gantt-third-header-col')).toHaveLength(36);
    expect(screen.getByText('1月上旬')).toBeInTheDocument();
    expect(screen.getByText('12月下旬')).toBeInTheDocument();

    const grid = document.querySelector('[data-surface-id="scheduling.calendar.grid"] .gantt-matrix-scroll-wrapper') as HTMLElement;
    const header = document.querySelector('[data-surface-id="scheduling.calendar.date-header"]') as HTMLElement;
    const slider = screen.getByRole('slider', { name: '左右捲動排班日曆' });

    fireEvent.change(slider, { target: { value: '720' } });
    expect(grid.scrollLeft).toBe(720);
    expect(header.scrollLeft).toBe(720);
  });

  it('將同案服務與排休日合併為單一連續訂單條，並完整顯示客戶姓名、案件編號、起訖日期與每日時段', async () => {
    vi.mocked(schedulingCurrentClient.queryCurrentCalendar).mockImplementation(async query => ({
      ...SCHEDULING_PROJECTION_READY, staff_id: query.staffId,
      range_start: query.rangeStart, range_end: query.rangeEnd,
      days: SCHEDULING_PROJECTION_READY.days.map(day => ({ ...day, entries: day.entries.map(entry => ({
        ...entry,
        service_start_at: `${day.calendar_date}T09:00:00+08:00`,
        service_end_at: `${day.calendar_date}T18:00:00+08:00`,
      })) })),
    }));
    render(<SchedulingPage />);
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getAllByText('排班客戶甲').length).toBeGreaterThan(0));

    const firstRowSpans = document.querySelectorAll('[data-staff-id="11"] .gantt-span-bar');
    expect(firstRowSpans).toHaveLength(1);
    const orderBar = firstRowSpans[0];
    expect(orderBar).toHaveAttribute('data-start-day', '1');
    expect(orderBar).toHaveAttribute('data-end-day', '2');
    expect(orderBar).toHaveTextContent('排班客戶甲');
    expect(orderBar).toHaveTextContent('CASE-SCH-001');
    expect(orderBar).toHaveTextContent('2026-08-01 ～ 2026-08-10');
    expect(orderBar).toHaveTextContent('09:00–18:00');
  });
});

/**
 * File: scheduling_current_page.test.tsx
 * Description: 驗證 Scheduling 投影、typed controls 與 bounded deep-link 行為。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { schedulingCurrentClient } from '../api/scheduling/scheduling_current_client';
import { schedulingEligibilityCollisionClient } from '../api/scheduling/eligibility_collision_client';
import { staffAssignmentOptionsClient } from '../api/scheduling/staff_assignment_options_client';
import { staffLeaveInboxClient } from '../api/scheduling/staff_leave_inbox_client';
import { SchedulingPage, taipeiCalendarDate } from '../pages/SchedulingPage';
import {
  SCHEDULING_PROJECTION_EMPTY,
  SCHEDULING_PROJECTION_READY,
} from './fixtures/scheduling/scheduling_current_contract_fixtures';

describe('SchedulingPage query-only presentation', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.location.hash = '#scheduling';
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({
      items: [
        { id: 11, name: '去敏人員甲', phone: null },
        { id: 12, name: '去敏人員乙', phone: null },
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
  });

  it('從 allowlist deep-link 直接開啟請假代班並安全解碼案件編號', () => {
    window.location.hash = '#scheduling?tab=leave_sub&case_no=%20CASE-DL-001%20';

    render(<SchedulingPage />);

    expect(screen.getByRole('textbox', { name: '請假代班訂單編號' })).toHaveValue('CASE-DL-001');
    expect(document.querySelector('[data-surface-id="scheduling.tab.leave_sub"]')).toHaveClass('active');
    expect(document.querySelector('[data-surface-id="scheduling.calendar"]')).not.toBeInTheDocument();
  });

  it('未知 deep-link tab fail closed 回到 calendar 且不預填隱藏工作區', () => {
    window.location.hash = '#scheduling?tab=not_allowed&case_no=CASE-DL-002';

    render(<SchedulingPage />);

    expect(screen.getByRole('region', { name: '排班甘特月曆與服務人員檔期' })).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: '請假代班訂單編號' })).not.toBeInTheDocument();
    expect(document.querySelector('[data-surface-id="scheduling.tab.calendar"]')).toHaveClass('active');

    fireEvent.click(screen.getByRole('button', { name: /服務中請假與代班/ }));
    expect(screen.getByRole('textbox', { name: '請假代班訂單編號' })).toHaveValue('');
  });

  it.each([
    ['malformed percent', '%E0%A4%A'],
    ['超過 50 字', 'A'.repeat(51)],
    ['控制字元', 'CASE%00DL-003'],
  ])('不預填不合法 case_no：%s', (_scenario, encodedCaseNo) => {
    window.location.hash = `#scheduling?tab=leave_sub&case_no=${encodedCaseNo}`;

    render(<SchedulingPage />);

    expect(screen.getByRole('textbox', { name: '請假代班訂單編號' })).toHaveValue('');
  });

  it('anchors calendar today to Asia/Taipei instead of the browser local timezone', () => {
    expect(taipeiCalendarDate(new Date('2026-08-22T16:30:00Z'))).toEqual({
      year: 2026,
      month: 8,
      day: 23,
    });
  });

  it('loads one current calendar for every visible staff row without a duplicate query', async () => {
    render(<SchedulingPage />);

    expect(screen.getByText(/正在載入服務人員摘要/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));
    expect(screen.getAllByText('去敏人員甲').length).toBeGreaterThan(0);
    expect(screen.getByText('正式服務履約')).toBeInTheDocument();
    expect(staffDirectoryClient.queryPage).toHaveBeenCalledTimes(1);
    expect(schedulingCurrentClient.queryCurrentCalendar).toHaveBeenCalledTimes(2);
    expect(staffAssignmentOptionsClient.getStaffAssignmentOptions).toHaveBeenCalledTimes(2);
    expect(ordersQueryClient.getOrderSummaries).toHaveBeenCalledWith(
      expect.objectContaining({ lifecycle_scope: 'unfinished' }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );

    expect(schedulingCurrentClient.queryCurrentCalendar).toHaveBeenCalledWith(
      expect.objectContaining({ staffId: 12 }),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
  });

  it('uses page_size 20, continues the staff cursor and keeps a complete month axis', async () => {
    vi.mocked(staffDirectoryClient.queryPage)
      .mockResolvedValueOnce({
        items: [{ id: 11, name: '去敏人員甲', phone: null }],
        next_cursor: 11,
      })
      .mockResolvedValueOnce({
        items: [{ id: 12, name: '去敏人員乙', phone: null }],
        next_cursor: null,
      });

    render(<SchedulingPage />);
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));
    const now = new Date();
    const expectedDays = new Date(Date.UTC(now.getFullYear(), now.getMonth() + 1, 0)).getUTCDate();
    expect(document.querySelectorAll('.gantt-day-header-col[data-date]')).toHaveLength(expectedDays);
    expect(staffDirectoryClient.queryPage).toHaveBeenNthCalledWith(
      1,
      { pageSize: 20 },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );

    fireEvent.click(screen.getByRole('button', { name: '載入更多服務人員' }));
    await waitFor(() => expect(screen.getAllByText('去敏人員乙').length).toBeGreaterThan(0));
    expect(staffDirectoryClient.queryPage).toHaveBeenNthCalledWith(
      2,
      { pageSize: 20, afterId: 11 },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(screen.queryByRole('button', { name: '載入更多服務人員' })).not.toBeInTheDocument();
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
      /正式服務日期：\s*2026-08-23 ～ 2026-08-24/,
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
    expect(screen.getByText(/檔期衝突與 7 天防撞期判定/)).toBeInTheDocument();
    expect(screen.getByText(/資料待補正.*需人工確認/)).toBeInTheDocument();
    expect(document.body).toHaveTextContent(/歷史排班\s*來源關聯\s*待人工確認/);
    expect(screen.getByText(/需補齊：每日服務時段尚未完整；補齊後再查詢/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/service_qualification|data_integrity|service_time_terms_incomplete/);
  });

  it('選案後以完整檔期顯示衝突，不把投影切成零碎衝突日期', async () => {
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
          available_day_count: 1,
          missing_dates: [],
          review_dates: [],
          status: 'unavailable',
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

    await waitFor(() => expect(screen.getAllByText('整段檔期有衝突').length).toBeGreaterThan(0));
    const conflictSpans = [...document.querySelectorAll('.gantt-span-bar.span-conflict')];
    expect(conflictSpans.length).toBeGreaterThan(0);
    conflictSpans.forEach((span) => {
      expect(span).toHaveAttribute('data-start-day', '1');
      expect(span).toHaveAttribute('data-end-day', '3');
      expect(span).toHaveTextContent(/完整檔期 2026-08-01 ～ 2026-08-03 均標示衝突/);
    });
  });

  it('衝突發生在跨月檔期後段時，前後月份的可見整段都標示衝突', async () => {
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
          missing_dates: [],
          review_dates: [],
          status: 'complete',
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
    await waitFor(() => expect(staffSpan(11, '.span-conflict')).not.toBeNull());
    expect(staffSpan(11, '.span-conflict')).toHaveAttribute('data-start-day', '30');
    expect(staffSpan(11, '.span-conflict')).toHaveAttribute('data-end-day', '31');
    expect(staffSpan(12, '.span-free')).toHaveAttribute('data-start-day', '30');
    expect(staffSpan(12, '.span-free')).toHaveAttribute('data-end-day', '31');

    fireEvent.click(screen.getByRole('button', { name: '查看下個月' }));
    await waitFor(() => expect(staffSpan(11, '.span-conflict')).toHaveAttribute('data-start-day', '1'));
    expect(staffSpan(11, '.span-conflict')).toHaveAttribute('data-end-day', '3');
    expect(staffSpan(12, '.span-free')).toHaveAttribute('data-start-day', '1');
    expect(staffSpan(12, '.span-free')).toHaveAttribute('data-end-day', '3');
  });

  it('只開放已具備業務輸入的排班與政策操作', async () => {
    render(<SchedulingPage />);
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));

    expect(document.querySelectorAll('main')).toHaveLength(0);
    expect(screen.getByRole('region', { name: '排班甘特月曆與服務人員檔期' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: '資格查詢案件編號' })).toBeEnabled();
    expect(document.querySelector('[data-control-id="scheduling.candidate-pool.add"]')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /服務中請假與代班/ }));
    fireEvent.change(screen.getByRole('textbox', { name: '請假代班訂單編號' }), { target: { value: '115000051' } });
    await waitFor(() => expect(document.querySelector('[data-control-id="scheduling.leave.query"]')).toBeEnabled());
    expect(document.querySelector('[data-control-id="scheduling.leave.preview"]')).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="scheduling.leave.apply"]')).not.toBeInTheDocument();
    expect(screen.getByText(/尚未查詢；不顯示推測/)).toBeInTheDocument();
    expect(document.querySelector('[data-control-id="scheduling.leave.extension"]')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /國定假日政策/ }));
    expect(document.querySelector('[data-control-id="scheduling.holiday.query"]')).toBeEnabled();
    expect(document.querySelector('[data-control-id="scheduling.holiday.preview"]')).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="scheduling.holiday.apply"]')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /新增國定假日/ })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: /服務中請假與代班/ }));
    await waitFor(() => expect(screen.getByText(/目前此狀態沒有待處理的 LINE 請假申請/)).toBeInTheDocument());
    expect(staffLeaveInboxClient.list).toHaveBeenCalledWith('pending');
  });
});

/**
 * File: scheduling_current_page.test.tsx
 * Description: 驗證 Scheduling 名冊續頁、完整月軸、typed controls、request budget 與錯誤狀態。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { schedulingCurrentClient } from '../api/scheduling/scheduling_current_client';
import { schedulingEligibilityCollisionClient } from '../api/scheduling/eligibility_collision_client';
import { staffLeaveInboxClient } from '../api/scheduling/staff_leave_inbox_client';
import { SchedulingPage, taipeiCalendarDate } from '../pages/SchedulingPage';
import {
  SCHEDULING_PROJECTION_EMPTY,
  SCHEDULING_PROJECTION_READY,
} from './fixtures/scheduling/scheduling_current_contract_fixtures';

describe('SchedulingPage query-only presentation', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({
      items: [
        { id: 11, name: '去敏人員甲', phone: null },
        { id: 12, name: '去敏人員乙', phone: null },
      ],
      next_cursor: null,
    });
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

  it('anchors calendar today to Asia/Taipei instead of the browser local timezone', () => {
    expect(taipeiCalendarDate(new Date('2026-08-22T16:30:00Z'))).toEqual({
      year: 2026,
      month: 8,
      day: 23,
    });
  });

  it('loads one current calendar for every visible staff row and selection does not trigger a duplicate query', async () => {
    render(<SchedulingPage />);

    expect(screen.getByText(/正在載入服務人員摘要/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));
    expect(screen.getAllByText('去敏人員甲').length).toBeGreaterThan(0);
    expect(screen.getAllByText('正式服務日').length).toBeGreaterThan(0);
    expect(staffDirectoryClient.queryPage).toHaveBeenCalledTimes(1);
    expect(schedulingCurrentClient.queryCurrentCalendar).toHaveBeenCalledTimes(2);

    fireEvent.change(screen.getByRole('combobox', { name: '服務人員' }), { target: { value: '12' } });
    expect(schedulingCurrentClient.queryCurrentCalendar).toHaveBeenCalledTimes(2);
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
    await waitFor(() => expect(screen.getByRole('option', { name: /去敏人員乙/ })).toBeInTheDocument());
    expect(staffDirectoryClient.queryPage).toHaveBeenNthCalledWith(
      2,
      { pageSize: 20, afterId: 11 },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(screen.queryByRole('button', { name: '載入更多服務人員' })).not.toBeInTheDocument();
  });

  it('renders explicit empty and error states', async () => {
    vi.mocked(schedulingCurrentClient.queryCurrentCalendar).mockResolvedValueOnce(
      SCHEDULING_PROJECTION_EMPTY
    );
    const empty = render(<SchedulingPage />);
    await waitFor(() => expect(screen.getByText('本月無排班占用')).toBeInTheDocument());
    expect(screen.queryByText(/尚未查詢資格/)).not.toBeInTheDocument();
    empty.unmount();

    vi.mocked(schedulingCurrentClient.queryCurrentCalendar).mockRejectedValueOnce(
      new Error('typed scheduling failure')
    );
    render(<SchedulingPage />);
    await waitFor(() => expect(screen.getByTitle(/typed scheduling failure/)).toBeInTheDocument());
    expect(screen.getByRole('alert')).toHaveTextContent('1 位服務人員的排班投影載入失敗');
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
    fireEvent.change(screen.getByRole('textbox', { name: '資格查詢案件編號' }), {
      target: { value: '115000003' },
    });
    fireEvent.change(screen.getByRole('combobox', { name: '服務人員' }), {
      target: { value: '12' },
    });
    fireEvent.click(screen.getByRole('button', { name: '查詢資格與撞期' }));

    await waitFor(() => expect(query).toHaveBeenCalledWith(
      expect.objectContaining({ caseNo: '115000003', staffId: 12 }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
    expect(await screen.findByText('資格檢查')).toBeInTheDocument();
    expect(screen.getByText('service_qualification')).toBeInTheDocument();
    expect(screen.getByText('資料待補正（無法判定）')).toBeInTheDocument();
    expect(screen.getByText('接單資格根事實不完整')).toBeInTheDocument();
    expect(screen.getByText('衝突與人工審核')).toBeInTheDocument();
    expect(screen.getByText('資料待補正（需人工確認）')).toBeInTheDocument();
    expect(screen.getByText('歷史排班 lineage 待人工確認')).toBeInTheDocument();
    expect(screen.getByText('需補正資料：service_time_terms_incomplete；補齊後再查詢。')).toBeInTheDocument();
  });

  it('exposes typed scheduling controls and only locks actions that still require Preview input', async () => {
    render(<SchedulingPage />);
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));

    expect(document.querySelectorAll('main')).toHaveLength(0);
    expect(screen.getByRole('region', { name: '排班甘特月曆與服務人員 occupancy' })).toBeInTheDocument();
    const precisionButton = document.querySelector('[data-control-id="scheduling.precision.open"]');
    expect(precisionButton).toHaveClass('scheduling-precision-control');
    expect(precisionButton).toBeEnabled();
    fireEvent.change(screen.getByRole('textbox', { name: '洽談中案件編號' }), { target: { value: '115000015' } });
    expect(document.querySelector('[data-control-id="scheduling.projection.lock-preview"]')).toBeEnabled();
    expect(document.querySelector('[data-control-id="scheduling.projection.lock-apply"]')).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: /服務中請假與代班/ }));
    fireEvent.change(screen.getByRole('textbox', { name: '請假代班訂單編號' }), { target: { value: '115000051' } });
    expect(document.querySelector('[data-control-id="scheduling.leave.query"]')).toBeEnabled();
    expect(document.querySelector('[data-control-id="scheduling.leave.preview"]')).toBeDisabled();
    expect(document.querySelector('[data-control-id="scheduling.leave.apply"]')).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="scheduling.leave.apply-gate"]')).toHaveTextContent('建立安全預覽');
    expect(document.querySelector('[data-control-id="scheduling.leave.extension"]')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /國定假日政策/ }));
    expect(document.querySelector('[data-control-id="scheduling.holiday.query"]')).toBeEnabled();
    expect(document.querySelector('[data-control-id="scheduling.holiday.preview"]')).toBeDisabled();
    expect(document.querySelector('[data-control-id="scheduling.holiday.apply"]')).toBeDisabled();
    expect(document.querySelector('[data-control-id="scheduling.holiday.create"]')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /請假待辦收件匣/ }));
    await waitFor(() => expect(screen.getByText('此狀態目前沒有請假待辦。')).toBeInTheDocument());
    expect(staffLeaveInboxClient.list).toHaveBeenCalledWith('pending');
  });
});

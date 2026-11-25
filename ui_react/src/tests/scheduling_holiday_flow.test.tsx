/**
 * File: scheduling_holiday_flow.test.tsx
 * Description: 驗證國定假日政策的單擊儲存、選填原因與業務結果回讀。
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { holidayClient } from '../api/scheduling/holiday_client';
import { schedulingCurrentClient } from '../api/scheduling/scheduling_current_client';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { transport } from '../api/shared/transport';
import { SchedulingPage } from '../pages/SchedulingPage';
import {
  HOLIDAY_APPLY_REQUEST,
  HOLIDAY_CALENDAR,
  HOLIDAY_PREVIEW,
  HOLIDAY_RECEIPT,
} from './fixtures/holiday_contract_fixtures';
import { SCHEDULING_PROJECTION_READY } from './fixtures/scheduling/scheduling_current_contract_fixtures';

describe('SchedulingPage holiday policy flow', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(transport, 'get').mockRejectedValue(new Error('未提供非假日政策查詢資料'));
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({
      items: [{ id: 11, name: '去敏人員甲', phone: null, education: null }],
      next_cursor: null,
    });
    vi.spyOn(schedulingCurrentClient, 'queryCurrentCalendar').mockResolvedValue(
      SCHEDULING_PROJECTION_READY,
    );
    vi.spyOn(holidayClient, 'accountingResults').mockResolvedValue([]);
    vi.spyOn(holidayClient, 'query').mockResolvedValue(HOLIDAY_CALENDAR);
    vi.spyOn(holidayClient, 'preview').mockResolvedValue(HOLIDAY_PREVIEW);
    vi.spyOn(holidayClient, 'apply').mockResolvedValue(HOLIDAY_RECEIPT);
  });

  it('開啟國定假日頁自動查詢，並顯示政策區間而不暴露來源識別或雜湊版本', async () => {
    render(<SchedulingPage />);
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));

    fireEvent.click(screen.getByRole('button', { name: /國定假日政策/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: '查詢國定假日政策' })).toBeEnabled());
    expect(screen.getByText(/區間：/)).toHaveTextContent('2026-01-01 ～ 2026-12-31');
    expect(screen.queryByText(HOLIDAY_CALENDAR.source_identity)).not.toBeInTheDocument();
    expect(screen.queryByText(/^日曆版本：/)).not.toBeInTheDocument();
    expect(screen.getByText(/2026-02-17/)).toBeInTheDocument();
  });

  it.each(['', '   ', HOLIDAY_APPLY_REQUEST.reason])('單擊儲存並回讀最新政策，原因 %j 可省略', async (reason) => {
    render(<SchedulingPage />);
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole('button', { name: /國定假日政策/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: '查詢國定假日政策' })).toBeEnabled());

    fireEvent.click(screen.getByRole('button', { name: '➕ 新增國定假日' }));
    expect(screen.queryByLabelText('當日雙倍計價')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('國定假日日期'), {
      target: { value: HOLIDAY_APPLY_REQUEST.holiday_date },
    });
    fireEvent.change(screen.getByLabelText('國定假日名稱'), {
      target: { value: HOLIDAY_APPLY_REQUEST.holiday_name },
    });
    fireEvent.change(screen.getByLabelText('套用原因'), {
      target: { value: reason },
    });
    const queriesBeforeSave = vi.mocked(holidayClient.query).mock.calls.length;
    expect(screen.queryByRole('button', { name: '預覽國定假日變更' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '儲存國定假日變更' }));
    await waitFor(() => expect(holidayClient.apply).toHaveBeenCalledTimes(1));
    expect(holidayClient.preview).toHaveBeenCalledTimes(1);
    expect(holidayClient.apply).toHaveBeenCalledWith(
      { ...HOLIDAY_APPLY_REQUEST, reason: reason.trim() }, expect.anything(),
    );
    await waitFor(() => expect(holidayClient.query).toHaveBeenCalledTimes(queriesBeforeSave + 2));
    expect(screen.getByRole('heading', { name: '國定假日政策已更新' })).toBeInTheDocument();
    expect(screen.getByText('已重新查詢並確認最新國定假日政策。')).toBeInTheDocument();
    expect(screen.queryByText(HOLIDAY_RECEIPT.receipt_key)).not.toBeInTheDocument();
    expect(screen.queryByText(/Receipt Key|resulting_calendar_version/)).not.toBeInTheDocument();
  });

  it('必要名稱未填時禁止送出，UI 不自行推導薪資或排班結果', async () => {
    render(<SchedulingPage />);
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole('button', { name: /國定假日政策/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: '查詢國定假日政策' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '➕ 新增國定假日' }));
    expect(screen.getByRole('button', { name: '儲存國定假日變更' })).toBeDisabled();
    expect(screen.queryByText(/雙倍薪金額|coverage|eligibility|結束日/)).not.toBeInTheDocument();
    expect(holidayClient.preview).not.toHaveBeenCalled();
    expect(holidayClient.apply).not.toHaveBeenCalled();
  });

  it('查詢區間變更後，儲存自動讀取目前區間再計算並送出', async () => {
    render(<SchedulingPage />);
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole('button', { name: /國定假日政策/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: '查詢國定假日政策' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '➕ 新增國定假日' }));
    fireEvent.change(screen.getByLabelText('國定假日日期'), { target: { value: HOLIDAY_APPLY_REQUEST.holiday_date } });
    fireEvent.change(screen.getByLabelText('國定假日名稱'), { target: { value: HOLIDAY_APPLY_REQUEST.holiday_name } });
    fireEvent.change(screen.getByLabelText('國定假日查詢迄日'), { target: { value: '2026-11-30' } });
    const horizon = { from_date: '2026-01-01', to_date: '2026-11-30' };
    vi.mocked(holidayClient.query).mockResolvedValue({ ...HOLIDAY_CALENDAR, planning_horizon: horizon });
    vi.mocked(holidayClient.preview).mockResolvedValue({
      ...HOLIDAY_PREVIEW,
      command: { ...HOLIDAY_PREVIEW.command, ...horizon },
      planning_horizon: horizon,
    });
    vi.mocked(holidayClient.apply).mockResolvedValue({ ...HOLIDAY_RECEIPT, planning_horizon: horizon });
    fireEvent.click(screen.getByRole('button', { name: '儲存國定假日變更' }));
    await waitFor(() => expect(holidayClient.apply).toHaveBeenCalledTimes(1));
    expect(holidayClient.query).toHaveBeenLastCalledWith(horizon, undefined);
    expect(holidayClient.preview).toHaveBeenCalledWith(expect.objectContaining(horizon), expect.anything());
    expect(holidayClient.apply).toHaveBeenCalledWith(
      expect.objectContaining({ ...horizon, reason: '' }), expect.anything(),
    );
  });
  it('換年度直接查詢全年並顯示該年度假日', async () => {
    render(<SchedulingPage />);
    fireEvent.click(screen.getByRole('button', { name: /國定假日政策/ }));
    await screen.findByText(/2026-02-17/);
    const horizon = { from_date: '2027-01-01', to_date: '2027-12-31' };
    vi.mocked(holidayClient.query).mockResolvedValue({
      ...HOLIDAY_CALENDAR,
      planning_horizon: horizon,
      holidays: [{ holiday_date: '2027-01-01', holiday_name: '元旦', is_double_pay_default: false }],
    });
    fireEvent.change(screen.getByLabelText('國定假日年度'), { target: { value: '2027' } });
    await screen.findByText(/2027-01-01 ～ 2027-12-31/);
    expect(holidayClient.query).toHaveBeenLastCalledWith(horizon, undefined);
    expect(screen.getByRole('button', { name: '2027-01-01 啟用雙倍' })).toBeEnabled();
    expect(screen.queryByText(/2026-02-17/)).not.toBeInTheDocument();
  });

  it('年度清單兩日互不影響，直接啟用、關閉並重載後保留後端狀態', async () => {
    const first = HOLIDAY_CALENDAR.holidays[0]!;
    const second = { holiday_date: '2026-10-10', holiday_name: '國慶日', is_double_pay_default: false };
    let rows = [first, second];
    vi.mocked(holidayClient.query).mockImplementation(async () => ({ ...HOLIDAY_CALENDAR, holidays: rows }));
    vi.mocked(holidayClient.preview).mockImplementation(async request => ({ ...HOLIDAY_PREVIEW,
      command: { ...HOLIDAY_PREVIEW.command, ...request, expected_calendar_version: HOLIDAY_CALENDAR.calendar_version } }));
    vi.mocked(holidayClient.apply).mockImplementation(async request => {
      rows = rows.map(row => row.holiday_date === request.holiday_date ? { ...row, is_double_pay_default: request.is_double_pay_default ?? false } : row);
      return { ...HOLIDAY_RECEIPT, holiday_date: request.holiday_date };
    });
    const view = render(<SchedulingPage />);
    fireEvent.click(screen.getByRole('button', { name: /國定假日政策/ }));
    fireEvent.click(await screen.findByRole('button', { name: `${first.holiday_date} 啟用雙倍` }));
    await screen.findByRole('button', { name: `${first.holiday_date} 取消雙倍` });
    expect(holidayClient.apply).toHaveBeenCalledTimes(1);
    expect(holidayClient.apply).toHaveBeenLastCalledWith(expect.objectContaining({ holiday_date: first.holiday_date, is_double_pay_default: true }), expect.anything());
    expect(screen.getByRole('button', { name: `${second.holiday_date} 啟用雙倍` })).toBeEnabled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    view.unmount();
    render(<SchedulingPage />);
    fireEvent.click(screen.getByRole('button', { name: /國定假日政策/ }));
    fireEvent.click(await screen.findByRole('button', { name: `${first.holiday_date} 取消雙倍` }));
    await screen.findByRole('button', { name: `${first.holiday_date} 啟用雙倍` });
    expect(holidayClient.apply).toHaveBeenCalledTimes(2);
    expect(holidayClient.apply).toHaveBeenLastCalledWith(expect.objectContaining({ holiday_date: first.holiday_date, is_double_pay_default: false }), expect.anything());
    expect(rows[1]).toEqual(second);
  });

  it('送出僅鎖該列且連點不重送，失敗保留原狀並在該列重試同命令', async () => {
    const first = HOLIDAY_CALENDAR.holidays[0]!;
    const second = { holiday_date: '2026-10-10', holiday_name: '國慶日', is_double_pay_default: false };
    vi.mocked(holidayClient.query).mockResolvedValue({ ...HOLIDAY_CALENDAR, holidays: [first, second] });
    vi.mocked(holidayClient.preview).mockImplementation(async request => ({ ...HOLIDAY_PREVIEW,
      command: { ...HOLIDAY_PREVIEW.command, ...request, expected_calendar_version: HOLIDAY_CALENDAR.calendar_version } }));
    let fail: ((error: Error) => void) | undefined;
    vi.mocked(holidayClient.apply).mockImplementationOnce(() => new Promise((_, reject) => { fail = reject; }));
    render(<SchedulingPage />);
    fireEvent.click(screen.getByRole('button', { name: /國定假日政策/ }));
    const button = await screen.findByRole('button', { name: `${first.holiday_date} 啟用雙倍` });
    fireEvent.click(button);
    fireEvent.click(button);
    await waitFor(() => expect(holidayClient.apply).toHaveBeenCalledTimes(1));
    expect(button).toBeDisabled();
    expect(screen.getByRole('button', { name: `${second.holiday_date} 啟用雙倍` })).toBeEnabled();
    fail!(new Error('隔離 fixture 寫入失敗'));
    const error = await screen.findByRole('alert');
    expect(error).toHaveTextContent('隔離 fixture 寫入失敗');
    expect(button).toBeEnabled();
    expect(screen.queryByRole('button', { name: `${first.holiday_date} 取消雙倍` })).not.toBeInTheDocument();
    vi.mocked(holidayClient.apply).mockImplementationOnce(async () => {
      vi.mocked(holidayClient.query).mockResolvedValue({ ...HOLIDAY_CALENDAR, holidays: [{ ...first, is_double_pay_default: true }, second] });
      return { ...HOLIDAY_RECEIPT, holiday_date: first.holiday_date };
    });
    fireEvent.click(within(error).getByRole('button', { name: '重試' }));
    await screen.findByRole('button', { name: `${first.holiday_date} 取消雙倍` });
    expect(holidayClient.apply).toHaveBeenCalledTimes(2);
    expect(vi.mocked(holidayClient.apply).mock.calls[0]).toEqual(vi.mocked(holidayClient.apply).mock.calls[1]);
    expect(screen.getByRole('button', { name: `${second.holiday_date} 啟用雙倍` })).toBeEnabled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('編輯已開啟日期的名稱時保留雙倍', async () => {
    vi.mocked(holidayClient.query).mockResolvedValue({
      ...HOLIDAY_CALENDAR,
      holidays: HOLIDAY_CALENDAR.holidays.map(holiday => ({ ...holiday, is_double_pay_default: true })),
    });
    render(<SchedulingPage />);
    fireEvent.click(screen.getByRole('button', { name: /國定假日政策/ }));
    await screen.findByText(/2026-02-17/);
    fireEvent.click(screen.getByRole('button', { name: /編輯/ }));
    expect(screen.queryByLabelText('當日雙倍計價')).not.toBeInTheDocument();
    vi.mocked(holidayClient.preview).mockImplementation(async request => ({ ...HOLIDAY_PREVIEW,
      command: { ...HOLIDAY_PREVIEW.command, ...request, expected_calendar_version: HOLIDAY_CALENDAR.calendar_version } }));
    fireEvent.change(screen.getByLabelText('國定假日名稱'), { target: { value: '更正名稱' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存國定假日變更' }));
    await waitFor(() => expect(holidayClient.apply).toHaveBeenCalled());
    expect(holidayClient.preview).toHaveBeenCalledWith(expect.objectContaining({
      holiday_name: '更正名稱', is_double_pay_default: true,
    }), expect.anything());
    expect(holidayClient.apply).toHaveBeenCalledWith(expect.objectContaining({ is_double_pay_default: true }), expect.anything());
  });

});


describe('國定假日逐案帳務處理結果', () => {
  it('設定成功仍區分重算、正式收付保留及失敗，重載讀回同一紀錄', async () => {
    vi.restoreAllMocks();
    vi.spyOn(schedulingCurrentClient, 'queryCurrentCalendar').mockResolvedValue(SCHEDULING_PROJECTION_READY);
    const cases = [
      { case_no: 'REPRICE-OK', outcome: 'repriced', case_total_amount: 5600, staff_payable_amount: 5120 },
      { case_no: 'REPRICE-PAID', outcome: 'preserved_cash_history', case_total_amount: 2800, reason_code: 'formal_settlement_exists' },
      { case_no: 'REPRICE-FAIL', outcome: 'failed', case_total_amount: null, reason_code: 'holiday_service_attribution_ambiguous' },
    ] satisfies import('../api/scheduling/holiday_schemas').HolidayCaseRepricing[];
    vi.spyOn(transport, 'get').mockRejectedValue(new Error('無其他資料'));
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({ items: [], next_cursor: null });
    vi.spyOn(holidayClient, 'accountingResults').mockResolvedValue([]);
    vi.spyOn(holidayClient, 'query').mockResolvedValue(HOLIDAY_CALENDAR);
    vi.spyOn(holidayClient, 'preview').mockResolvedValue(HOLIDAY_PREVIEW);
    vi.spyOn(holidayClient, 'apply').mockResolvedValue({ ...HOLIDAY_RECEIPT, case_results: cases });
    const view = render(<SchedulingPage />);
    fireEvent.click(screen.getByRole('button', { name: /國定假日政策/ }));
    fireEvent.click(await screen.findByRole('button', { name: '2026-02-17 啟用雙倍' }));
    await screen.findByText('REPRICE-FAIL');
    expect(screen.getByText(/有案件未重算/)).toBeInTheDocument();
    expect(screen.getByText(/已有正式收付，保留原帳/)).toBeInTheDocument();
    expect(screen.getByText(/holiday_service_attribution_ambiguous/)).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    vi.mocked(holidayClient.accountingResults).mockResolvedValue([
      { holiday_date: '2026-02-17', receipt_key: 'same-receipt', case_results: cases },
    ]);
    view.unmount();
    render(<SchedulingPage />);
    fireEvent.click(screen.getByRole('button', { name: /國定假日政策/ }));
    expect(await screen.findByText('REPRICE-FAIL')).toBeInTheDocument();
  });
});

/**
 * File: scheduling_holiday_flow.test.tsx
 * Description: 驗證國定假日政策的單擊儲存、選填原因與業務結果回讀。
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
});

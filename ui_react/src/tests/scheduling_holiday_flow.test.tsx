/**
 * File: scheduling_holiday_flow.test.tsx
 * Description: 驗證 SchedulingPage 國定假日 tab 的 server-driven Query、Preview、Apply 與觀察 UI。
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { holidayClient } from '../api/scheduling/holiday_client';
import { schedulingCurrentClient } from '../api/scheduling/scheduling_current_client';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
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
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({
      items: [{ id: 11, name: '去敏人員甲', phone: null }],
      next_cursor: null,
    });
    vi.spyOn(schedulingCurrentClient, 'queryCurrentCalendar').mockResolvedValue(
      SCHEDULING_PROJECTION_READY,
    );
    vi.spyOn(holidayClient, 'query').mockResolvedValue(HOLIDAY_CALENDAR);
    vi.spyOn(holidayClient, 'preview').mockResolvedValue(HOLIDAY_PREVIEW);
    vi.spyOn(holidayClient, 'apply').mockResolvedValue(HOLIDAY_RECEIPT);
  });

  it('只在使用者開啟 holiday tab 後 Query，並以 server horizon/version 顯示候選', async () => {
    render(<SchedulingPage />);
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));
    expect(holidayClient.query).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /國定假日政策/ }));
    fireEvent.click(screen.getByRole('button', { name: '查詢國定假日政策' }));
    await waitFor(() => expect(holidayClient.query).toHaveBeenCalledTimes(1));
    expect(screen.getByText(HOLIDAY_CALENDAR.source_identity)).toBeInTheDocument();
    expect(screen.getByText(/^日曆版本：/)).toBeInTheDocument();
    expect(screen.getByText(/2026-02-17/)).toBeInTheDocument();
  });

  it('Preview 後才解鎖 Apply，Apply 完成後顯示 receipt 並 re-query，不顯示 optimistic success', async () => {
    render(<SchedulingPage />);
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole('button', { name: /國定假日政策/ }));
    fireEvent.click(screen.getByRole('button', { name: '查詢國定假日政策' }));
    await waitFor(() => expect(holidayClient.query).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText('國定假日日期'), {
      target: { value: HOLIDAY_APPLY_REQUEST.holiday_date },
    });
    fireEvent.change(screen.getByLabelText('國定假日名稱'), {
      target: { value: HOLIDAY_APPLY_REQUEST.holiday_name },
    });
    fireEvent.change(screen.getByLabelText('套用原因'), {
      target: { value: HOLIDAY_APPLY_REQUEST.reason },
    });
    const preview = screen.getByRole('button', { name: '預覽國定假日變更' });
    expect(screen.getByRole('button', { name: '套用國定假日變更' })).toBeDisabled();
    fireEvent.click(preview);
    await waitFor(() => expect(holidayClient.preview).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('heading', { name: '預覽已產生' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '套用國定假日變更' })).toBeEnabled();

    fireEvent.click(screen.getByRole('button', { name: '套用國定假日變更' }));
    await waitFor(() => expect(holidayClient.apply).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(holidayClient.query).toHaveBeenCalledTimes(2));
    expect(screen.getByRole('heading', { name: '已收到正式 receipt' })).toBeInTheDocument();
    expect(screen.getByText('已觀察最新後端日曆版本。')).toBeInTheDocument();
  });

  it('不得由 UI 推導雙倍薪、coverage、eligibility 或日期結果，未取得 server preview 前 controls 維持 disabled', async () => {
    render(<SchedulingPage />);
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole('button', { name: /國定假日政策/ }));
    expect(screen.getByRole('button', { name: '套用國定假日變更' })).toBeDisabled();
    expect(screen.queryByText(/雙倍薪金額|coverage|eligibility|結束日/)).not.toBeInTheDocument();
    expect(holidayClient.preview).not.toHaveBeenCalled();
    expect(holidayClient.apply).not.toHaveBeenCalled();
  });

  it('查詢區間變更後鎖住舊日曆 Preview，提示重新查詢而不送出 stale request', async () => {
    render(<SchedulingPage />);
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole('button', { name: /國定假日政策/ }));
    fireEvent.click(screen.getByRole('button', { name: '查詢國定假日政策' }));
    await waitFor(() => expect(holidayClient.query).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByLabelText('國定假日名稱'), { target: { value: '驗收假日' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽國定假日變更' }));
    await waitFor(() => expect(holidayClient.preview).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByLabelText('國定假日查詢迄日'), { target: { value: '2026-11-30' } });

    expect(screen.getByRole('button', { name: '預覽國定假日變更' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '套用國定假日變更' })).toBeDisabled();
    expect(screen.getByText('查詢區間已變更，請重新查詢日曆後再建立 Preview。')).toBeInTheDocument();
    expect(screen.getByText('Preview 後的查詢區間或變更欄位已調整；請重新查詢並建立新的 Preview，才能套用。')).toBeInTheDocument();
  });
});

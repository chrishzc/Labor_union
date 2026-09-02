/**
 * File: scheduling_holiday_flow.test.tsx
 * Description: 驗證國定假日政策的查詢、影響預覽、確認套用與業務結果回讀。
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

  it('只在使用者開啟國定假日頁後查詢，並顯示政策區間而不暴露來源識別或雜湊版本', async () => {
    render(<SchedulingPage />);
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));
    expect(holidayClient.query).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /國定假日政策/ }));
    fireEvent.click(screen.getByRole('button', { name: '查詢國定假日政策' }));
    await waitFor(() => expect(holidayClient.query).toHaveBeenCalledTimes(1));
    expect(screen.getByText(/區間：/)).toHaveTextContent('2026-01-01 ～ 2026-12-31');
    expect(screen.queryByText(HOLIDAY_CALENDAR.source_identity)).not.toBeInTheDocument();
    expect(screen.queryByText(/^日曆版本：/)).not.toBeInTheDocument();
    expect(screen.getByText(/2026-02-17/)).toBeInTheDocument();
  });

  it('影響預覽後才解鎖套用，完成後回讀最新政策且不顯示內部 receipt key', async () => {
    render(<SchedulingPage />);
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole('button', { name: /國定假日政策/ }));
    fireEvent.click(screen.getByRole('button', { name: '查詢國定假日政策' }));
    await waitFor(() => expect(holidayClient.query).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole('button', { name: '➕ 新增國定假日' }));
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
    expect(screen.getByRole('heading', { name: '國定假日政策已更新' })).toBeInTheDocument();
    expect(screen.getByText('已重新查詢並確認最新國定假日政策。')).toBeInTheDocument();
    expect(screen.queryByText(HOLIDAY_RECEIPT.receipt_key)).not.toBeInTheDocument();
    expect(screen.queryByText(/Receipt Key|resulting_calendar_version/)).not.toBeInTheDocument();
  });

  it('不得由 UI 推導雙倍薪、coverage、eligibility 或日期結果，未取得 server preview 前 controls 維持 disabled', async () => {
    render(<SchedulingPage />);
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole('button', { name: /國定假日政策/ }));
    fireEvent.click(screen.getByRole('button', { name: '➕ 新增國定假日' }));
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
    fireEvent.click(screen.getByRole('button', { name: '➕ 新增國定假日' }));
    fireEvent.change(screen.getByLabelText('國定假日名稱'), { target: { value: '驗收假日' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽國定假日變更' }));
    await waitFor(() => expect(holidayClient.preview).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByLabelText('國定假日查詢迄日'), { target: { value: '2026-11-30' } });

    expect(screen.getByRole('button', { name: '預覽國定假日變更' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '套用國定假日變更' })).toBeDisabled();
    expect(screen.getByText('查詢區間已變更，請重新查詢政策後再檢查變更影響。')).toBeInTheDocument();
    expect(screen.getByText('查詢區間或變更內容已調整；請重新查詢並檢查最新影響，才能套用。')).toBeInTheDocument();
  });
});

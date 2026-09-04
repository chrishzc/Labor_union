/**
 * File: official_holiday_csv_import_panel.test.tsx
 * Description: 驗證官方年度 CSV 的來源入口、預覽、略過與既有 Holiday Preview → Apply orchestration。
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { holidayClient } from '../api/scheduling/holiday_client';
import { holidayFlowStore } from '../adapters/scheduling/holiday_flow_adapter';
import { OfficialHolidayCsvImportPanel } from '../components/OfficialHolidayCsvImportPanel';
import {
  HOLIDAY_CALENDAR,
  HOLIDAY_PREVIEW,
  HOLIDAY_RECEIPT,
} from './fixtures/holiday_contract_fixtures';

const UPDATED_CALENDAR = {
  ...HOLIDAY_CALENDAR,
  calendar_version: 'c'.repeat(64),
  holidays: [
    ...HOLIDAY_CALENDAR.holidays,
    {
      holiday_date: '2026-09-28',
      holiday_name: '去敏教師節假日',
      is_double_pay_default: false,
    },
  ],
};

describe('OfficialHolidayCsvImportPanel', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    holidayFlowStore.clearAll();
    vi.spyOn(holidayClient, 'query')
      .mockResolvedValueOnce(HOLIDAY_CALENDAR)
      .mockResolvedValue(UPDATED_CALENDAR);
    vi.spyOn(holidayClient, 'preview').mockResolvedValue(HOLIDAY_PREVIEW);
    vi.spyOn(holidayClient, 'apply').mockResolvedValue(HOLIDAY_RECEIPT);
  });

  it('顯示官方來源，預覽後一次確認只匯入新假日並完成 fresh readback', async () => {
    const onHorizonChange = vi.fn();
    render(<OfficialHolidayCsvImportPanel disabled={false} onHorizonChange={onHorizonChange} />);

    expect(screen.getByRole('link', { name: '前往政府資料開放平臺下載年度 CSV' }))
      .toHaveAttribute('href', 'https://data.gov.tw/dataset/14718');
    expect(screen.getByRole('link', { name: '行政院人事行政總處辦公日曆公告' }))
      .toHaveAttribute('href', 'https://www.dgpa.gov.tw/informationlist?uid=41');

    const csv = [
      '西元日期,星期,是否放假,備註',
      '20260217,二,2,去敏春節假日',
      '20260221,六,2,',
      '20260928,一,2,去敏教師節假日',
    ].join('\r\n');
    const file = new File([csv], '2026-office-calendar.csv', { type: 'text/csv' });
    fireEvent.change(screen.getByLabelText('選擇官方辦公日曆 CSV'), { target: { files: [file] } });

    await waitFor(() => expect(holidayClient.query).toHaveBeenCalledTimes(1));
    expect(onHorizonChange).toHaveBeenCalledWith('2026-01-01', '2026-12-31');
    expect(screen.getByText('2026-office-calendar.csv')).toBeInTheDocument();
    expect(screen.getByText('2026', { selector: 'strong' })).toBeInTheDocument();
    expect(screen.getByText(/2026-02-17｜去敏春節假日｜已存在，略過/)).toBeInTheDocument();
    expect(screen.getByText(/2026-09-28｜去敏教師節假日｜待匯入/)).toBeInTheDocument();
    expect(screen.queryByText(/2026-02-21/)).not.toBeInTheDocument();
    expect(holidayClient.preview).not.toHaveBeenCalled();
    expect(holidayClient.apply).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '確認匯入官方國定假日' }));

    await waitFor(() => expect(holidayClient.apply).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(holidayClient.query).toHaveBeenCalledTimes(3));
    expect(holidayClient.preview).toHaveBeenCalledTimes(1);
    expect(holidayClient.preview).toHaveBeenCalledWith(
      expect.objectContaining({
        action: 'upsert',
        holiday_date: '2026-09-28',
        holiday_name: '去敏教師節假日',
        is_double_pay_default: false,
        from_date: '2026-01-01',
        to_date: '2026-12-31',
      }),
      expect.anything(),
    );
    expect(screen.getByText(/匯入完成：成功 1 筆、略過 1 筆、失敗 0 筆/)).toBeInTheDocument();
  });

  it('混合年度 CSV fail closed，0 write', async () => {
    render(<OfficialHolidayCsvImportPanel disabled={false} onHorizonChange={vi.fn()} />);
    const file = new File([
      [
        '西元日期,星期,是否放假,備註',
        '20261231,四,2,去敏年末假日',
        '20270101,五,2,去敏年初假日',
      ].join('\n'),
    ], 'mixed.csv', { type: 'text/csv' });

    fireEvent.change(screen.getByLabelText('選擇官方辦公日曆 CSV'), { target: { files: [file] } });

    expect(await screen.findByRole('alert')).toHaveTextContent('混合年度');
    expect(holidayClient.query).not.toHaveBeenCalled();
    expect(holidayClient.preview).not.toHaveBeenCalled();
    expect(holidayClient.apply).not.toHaveBeenCalled();
  });
});

/**
 * File: reports_weekly_batch_modal.test.tsx
 * Description: 測試營運週報方案 C 結算彈窗之渲染、待結算案件顯示與結算操作。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { WeeklyBatchModal } from '../components/reports/WeeklyBatchModal';
import * as batchClient from '../api/reports/weekly_report_batch_client';

describe('WeeklyBatchModal (Option C)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders unclosed cases and batch list, allows closing batch', async () => {
    vi.spyOn(batchClient, 'fetchWeeklyBatches').mockResolvedValue([
      {
        id: 1,
        year: 2026,
        week_code: '6-1',
        cutoff_at: '2026-06-03T10:00:00',
        promotion_count: 20,
        inquiry_count: 10,
        notes: null,
        case_count: 5,
        created_at: '2026-06-03T10:00:00',
        updated_at: '2026-06-03T10:00:00',
      },
    ]);

    vi.spyOn(batchClient, 'fetchUnclosedCases').mockResolvedValue([
      {
        case_no: 'NEW-CASE-01',
        applicant_name: '王小華',
        created_at: '2026-06-03T15:00:00',
        order_status: '訂單成立',
        service_days: 10,
        service_hours_per_day: 8,
      },
    ]);

    const closeBatchSpy = vi.spyOn(batchClient, 'closeWeeklyBatch').mockResolvedValue({
      id: 2,
      year: 2026,
      week_code: '6-2',
      cutoff_at: '2026-06-03T16:00:00',
      promotion_count: 15,
      inquiry_count: 8,
      notes: null,
      case_count: 1,
      created_at: '2026-06-03T16:00:00',
      updated_at: '2026-06-03T16:00:00',
    });

    const onBatchClosedMock = vi.fn();
    const onCloseMock = vi.fn();

    render(
      <WeeklyBatchModal
        isOpen={true}
        onClose={onCloseMock}
        year={2026}
        onBatchClosed={onBatchClosedMock}
      />
    );

    // 驗證標題與未結算案件池
    expect(screen.getByText('📑 週報結算與指標管理 (2026 年度)')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('NEW-CASE-01')).toBeInTheDocument();
      expect(screen.getByText('王小華')).toBeInTheDocument();
      expect(screen.getByText('6-1')).toBeInTheDocument();
    });

    // 驗證自動建議的下一週週別
    const weekInput = screen.getByPlaceholderText('例如 6-2') as HTMLInputElement;
    expect(weekInput.value).toBe('6-2');

    // 點擊確認結算
    const submitBtn = screen.getByRole('button', { name: /確認出具並結算 6-2 週報/ });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(closeBatchSpy).toHaveBeenCalledWith({
        year: 2026,
        week_code: '6-2',
        promotion_count: 0,
        inquiry_count: 0,
        notes: undefined,
      });
      expect(onBatchClosedMock).toHaveBeenCalled();
    });
  });
});
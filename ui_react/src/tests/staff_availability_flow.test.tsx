/**
 * File: staff_availability_flow.test.tsx
 * Description: 驗證不可服務期間新增、取消與 receipt 後重新觀察流程。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { staffAvailabilityClient } from '../api/staff_availability/staff_availability_client';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import {
  StaffAvailabilityConflictError,
  StaffAvailabilityUnavailableError,
} from '../api/staff_availability/staff_availability_errors';
import { StaffPage } from '../pages/StaffPage';
import {
  STAFF_AVAILABILITY_APPLY_PAYLOAD,
  STAFF_AVAILABILITY_BLOCK,
  STAFF_AVAILABILITY_CLOSED_PAUSE_BLOCK,
  STAFF_AVAILABILITY_END_PAUSE_PREVIEW_RESPONSE,
  STAFF_AVAILABILITY_END_PAUSE_RECEIPT_RESPONSE,
  STAFF_AVAILABILITY_PREVIEW_RESPONSE,
  STAFF_AVAILABILITY_RECEIPT_RESPONSE,
  STAFF_AVAILABILITY_SELECTED_PAUSE_BLOCK,
} from './fixtures/staff/staff_availability_contract_fixtures';
import { STAFF_PAGE_ONE } from './fixtures/staff/staff_directory_contract_fixtures';

describe('Staff availability flow', () => {
  beforeEach(() => {
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue(STAFF_PAGE_ONE);
    vi.spyOn(staffDirectoryClient, 'resetPagination').mockImplementation(() => undefined);
    vi.spyOn(staffAvailabilityClient, 'getBlocks').mockResolvedValue([STAFF_AVAILABILITY_BLOCK]);
    vi.spyOn(staffAvailabilityClient, 'previewChange').mockResolvedValue(STAFF_AVAILABILITY_PREVIEW_RESPONSE.data!);
    vi.spyOn(staffAvailabilityClient, 'applyChange').mockResolvedValue(STAFF_AVAILABILITY_RECEIPT_RESPONSE.data!);
  });

  afterEach(() => vi.restoreAllMocks());

  async function openAvailability(expectedRow = '2026-09-01 ～ 2026-09-30'): Promise<void> {
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /長假與暫停/ }));
    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });
    fireEvent.change(screen.getByLabelText('開始日期'), { target: { value: '2026-09-01' } });
    fireEvent.change(screen.getByLabelText('結束日期'), { target: { value: '2026-10-31' } });
    fireEvent.click(screen.getByRole('button', { name: '查詢不可服務期間' }));
    await waitFor(() => expect(screen.getByText(expectedRow)).toBeInTheDocument());
  }

  it('shows one error state with a direct retry instead of the idle placeholder', async () => {
    vi.mocked(staffAvailabilityClient.getBlocks)
      .mockRejectedValueOnce(new Error('不可服務期間暫時失敗'))
      .mockResolvedValueOnce([STAFF_AVAILABILITY_BLOCK]);
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /長假與暫停/ }));
    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });
    fireEvent.change(screen.getByLabelText('開始日期'), { target: { value: '2026-09-01' } });
    fireEvent.change(screen.getByLabelText('結束日期'), { target: { value: '2026-10-31' } });
    fireEvent.click(screen.getByRole('button', { name: '查詢不可服務期間' }));

    await waitFor(() => expect(screen.getByRole('button', { name: '重試不可服務期間' })).toBeInTheDocument());
    expect(screen.queryByText('請先設定日期範圍並查詢。')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重試不可服務期間' }));
    await waitFor(() => expect(screen.getByText('2026-09-01 ～ 2026-09-30')).toBeInTheDocument());
    expect(staffAvailabilityClient.getBlocks).toHaveBeenCalledTimes(2);
  });

  it('完成 create preview、apply、receipt 與 blocks requery，不計算本地業務值', async () => {
    vi.mocked(staffAvailabilityClient.getBlocks)
      .mockResolvedValueOnce([STAFF_AVAILABILITY_BLOCK])
      .mockResolvedValueOnce([{ ...STAFF_AVAILABILITY_BLOCK, block_id: 93 }]);
    await openAvailability();

    fireEvent.change(screen.getByLabelText('新增原因'), { target: { value: '去敏暫停接案' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽新增' }));
    await waitFor(() => expect(staffAvailabilityClient.previewChange).toHaveBeenCalledTimes(1));
    expect(staffAvailabilityClient.previewChange).toHaveBeenCalledWith(
      11,
      {
        action: 'create_pause',
        reason: '去敏暫停接案',
        start_date: '2026-09-01',
      },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(screen.getByText(/日數：—/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '套用新增' })).not.toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: '套用新增' }));
    await waitFor(() => expect(staffAvailabilityClient.applyChange).toHaveBeenCalledTimes(1));
    expect(staffAvailabilityClient.applyChange).toHaveBeenCalledWith(
      11,
      expect.objectContaining({
        action: 'create_pause',
        start_date: '2026-09-01',
        reason: '去敏暫停接案',
        expected_version: 2,
        preview_fingerprint: STAFF_AVAILABILITY_APPLY_PAYLOAD.preview_fingerprint,
      }),
      expect.objectContaining({ idempotencyKey: expect.any(String) }),
    );
    expect(vi.mocked(staffAvailabilityClient.applyChange).mock.calls[0][1]).not.toHaveProperty('end_date');
    await waitFor(() => expect(staffAvailabilityClient.getBlocks).toHaveBeenCalledTimes(2));
    expect(screen.getByText('已觀察最新不可服務期間')).toBeInTheDocument();
  });

  it('cancel 使用 append-only block identity，requery 失敗仍保留 receipt 觀察狀態', async () => {
    await openAvailability();
    fireEvent.change(screen.getByLabelText('取消原因'), { target: { value: '恢復可服務' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽取消' }));
    await waitFor(() => expect(staffAvailabilityClient.previewChange).toHaveBeenCalledWith(
      11,
      expect.objectContaining({ action: 'cancel', block_id: 91, reason: '恢復可服務' }),
      expect.anything(),
    ));
    expect(screen.getByRole('button', { name: '套用取消' })).not.toBeDisabled();

    vi.mocked(staffAvailabilityClient.getBlocks).mockRejectedValueOnce(
      new StaffAvailabilityUnavailableError({ code: 'STAFF_AVAILABILITY_NETWORK', message: '觀察失敗', retryable: true }),
    );
    fireEvent.click(screen.getByRole('button', { name: '套用取消' }));
    await waitFor(() => expect(screen.getByText(/receipt 已收到，但重新查詢失敗/)).toBeInTheDocument());
    expect(screen.getByText(/receipt 已收到/)).toBeInTheDocument();
  });

  it('stale 後必須先重新查詢，才能再次建立 preview', async () => {
    await openAvailability();
    vi.mocked(staffAvailabilityClient.previewChange).mockResolvedValue(STAFF_AVAILABILITY_PREVIEW_RESPONSE.data!);
    vi.mocked(staffAvailabilityClient.applyChange).mockRejectedValueOnce(
      new StaffAvailabilityConflictError({
        code: 'STAFF_AVAILABILITY_STALE',
        message: '版本已過期，請重新查詢。',
        retryable: false,
      }),
    );
    fireEvent.change(screen.getByLabelText('新增原因'), { target: { value: '去敏重試' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽新增' }));
    await waitFor(() => expect(staffAvailabilityClient.previewChange).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole('button', { name: '套用新增' }));
    await waitFor(() => expect(screen.getByText(/版本已過期/)).toBeInTheDocument());

    const previewButton = screen.getByRole('button', { name: '預覽新增' });
    expect(previewButton).toBeDisabled();
    fireEvent.click(previewButton);
    expect(staffAvailabilityClient.previewChange).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: '查詢不可服務期間' }));
    await waitFor(() => expect(staffAvailabilityClient.getBlocks).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByRole('button', { name: '預覽新增' }));
    await waitFor(() => expect(staffAvailabilityClient.previewChange).toHaveBeenCalledTimes(2));
  });

  it('outcome_unknown 只能以相同 payload 與 idempotency key 重試', async () => {
    await openAvailability();
    fireEvent.change(screen.getByLabelText('新增原因'), { target: { value: '去敏暫停接案' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽新增' }));
    await waitFor(() => expect(staffAvailabilityClient.previewChange).toHaveBeenCalledTimes(1));
    vi.mocked(staffAvailabilityClient.applyChange)
      .mockRejectedValueOnce(new StaffAvailabilityUnavailableError({
        code: 'STAFF_AVAILABILITY_TIMEOUT',
        message: '請求逾時',
        retryable: true,
      }))
      .mockResolvedValueOnce(STAFF_AVAILABILITY_RECEIPT_RESPONSE.data!);

    fireEvent.click(screen.getByRole('button', { name: '套用新增' }));
    await waitFor(() => expect(screen.getByText(/結果未知/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '以相同內容重試' }));
    await waitFor(() => expect(staffAvailabilityClient.applyChange).toHaveBeenCalledTimes(2));

    const first = vi.mocked(staffAvailabilityClient.applyChange).mock.calls[0];
    const second = vi.mocked(staffAvailabilityClient.applyChange).mock.calls[1];
    expect(second[1]).toEqual(first[1]);
    expect(second[2].idempotencyKey).toBe(first[2].idempotencyKey);
  });

  it('只對所選 Staff 的 active open-ended pause 執行 end_pause，receipt 後觀察 server 封閉區間', async () => {
    vi.mocked(staffAvailabilityClient.getBlocks)
      .mockResolvedValueOnce([STAFF_AVAILABILITY_SELECTED_PAUSE_BLOCK])
      .mockResolvedValueOnce([STAFF_AVAILABILITY_CLOSED_PAUSE_BLOCK]);
    vi.mocked(staffAvailabilityClient.previewChange)
      .mockResolvedValueOnce(STAFF_AVAILABILITY_END_PAUSE_PREVIEW_RESPONSE.data!);
    vi.mocked(staffAvailabilityClient.applyChange)
      .mockResolvedValueOnce(STAFF_AVAILABILITY_END_PAUSE_RECEIPT_RESPONSE.data!);
    await openAvailability('2026-10-01 ～ —');

    fireEvent.change(screen.getByLabelText('暫停接案紀錄'), { target: { value: '92' } });
    fireEvent.change(screen.getByLabelText('恢復接案日期'), { target: { value: '2026-10-15' } });
    fireEvent.change(screen.getByLabelText('結束暫停原因'), { target: { value: '恢復接受媒合' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽結束暫停' }));

    await waitFor(() => expect(staffAvailabilityClient.previewChange).toHaveBeenCalledWith(
      11,
      {
        action: 'end_pause',
        block_id: 92,
        resume_date: '2026-10-15',
        reason: '恢復接受媒合',
      },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
    expect(screen.getByRole('button', { name: '套用結束暫停' })).not.toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: '套用結束暫停' }));
    await waitFor(() => expect(staffAvailabilityClient.applyChange).toHaveBeenCalledWith(
      11,
      expect.objectContaining({
        action: 'end_pause',
        block_id: 92,
        resume_date: '2026-10-15',
        expected_version: 4,
        preview_fingerprint: 'b'.repeat(64),
      }),
      expect.objectContaining({ idempotencyKey: expect.any(String) }),
    ));
    await waitFor(() => expect(screen.getByText('已觀察 server 封閉暫停期間')).toBeInTheDocument());
  });

  it('另一 Staff、已封閉或非 paused_service block 不得啟用 end_pause Preview', async () => {
    vi.mocked(staffAvailabilityClient.getBlocks).mockResolvedValueOnce([
      { ...STAFF_AVAILABILITY_SELECTED_PAUSE_BLOCK, staff_id: 12 },
      { ...STAFF_AVAILABILITY_CLOSED_PAUSE_BLOCK, block_id: 93 },
      { ...STAFF_AVAILABILITY_BLOCK, staff_id: 11 },
    ]);
    await openAvailability();

    expect(screen.getByLabelText('暫停接案紀錄')).toBeDisabled();
    expect(screen.getByRole('button', { name: '預覽結束暫停' })).toBeDisabled();
    expect(staffAvailabilityClient.previewChange).not.toHaveBeenCalled();
  });

  it('server Preview 若未回同一 Staff 與 block，固定 fail closed 且不可 Apply', async () => {
    vi.mocked(staffAvailabilityClient.getBlocks).mockResolvedValueOnce([
      STAFF_AVAILABILITY_SELECTED_PAUSE_BLOCK,
    ]);
    vi.mocked(staffAvailabilityClient.previewChange).mockResolvedValueOnce({
      ...STAFF_AVAILABILITY_END_PAUSE_PREVIEW_RESPONSE.data!,
      staff_id: 12,
      target_block: {
        ...STAFF_AVAILABILITY_SELECTED_PAUSE_BLOCK,
        staff_id: 12,
      },
    });
    await openAvailability('2026-10-01 ～ —');

    fireEvent.change(screen.getByLabelText('暫停接案紀錄'), { target: { value: '92' } });
    fireEvent.change(screen.getByLabelText('恢復接案日期'), { target: { value: '2026-10-15' } });
    fireEvent.change(screen.getByLabelText('結束暫停原因'), { target: { value: '恢復接受媒合' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽結束暫停' }));

    await waitFor(() => expect(screen.getByText(/未回傳同一筆可結束/)).toBeInTheDocument());
    expect(screen.getByRole('button', { name: '套用結束暫停' })).toBeDisabled();
    expect(staffAvailabilityClient.applyChange).not.toHaveBeenCalled();
  });
});

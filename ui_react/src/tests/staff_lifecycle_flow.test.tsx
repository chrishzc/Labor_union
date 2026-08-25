/**
 * File: staff_lifecycle_flow.test.tsx
 * Description: 驗證 Staff lifecycle 退役與復職的 Preview、Apply、重查流程。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { staffQualificationMasterClient } from '../api/staff/qualification_master_client';
import { staffLifecycleClient } from '../api/staff_lifecycle/staff_lifecycle_client';
import { StaffLifecycleUnavailableError } from '../api/staff_lifecycle/staff_lifecycle_errors';
import { StaffPage } from '../pages/StaffPage';
import {
  STAFF_LIFECYCLE_APPLY_PAYLOAD,
  STAFF_LIFECYCLE_PREVIEW,
  STAFF_LIFECYCLE_PREVIEW_PAYLOAD,
  STAFF_LIFECYCLE_RECEIPT,
  STAFF_LIFECYCLE_VIEW,
} from './fixtures/staff/staff_lifecycle_contract_fixtures';
import { STAFF_PAGE_ONE } from './fixtures/staff/staff_directory_contract_fixtures';
import { STAFF_QUALIFICATION_MASTER } from './fixtures/staff/staff_qualification_contract_fixtures';

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe('Staff lifecycle flow', () => {
  beforeEach(() => {
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue(STAFF_PAGE_ONE);
    vi.spyOn(staffDirectoryClient, 'resetPagination').mockImplementation(() => undefined);
    vi.spyOn(staffLifecycleClient, 'query').mockResolvedValue(STAFF_LIFECYCLE_VIEW);
    vi.spyOn(staffLifecycleClient, 'preview').mockResolvedValue(STAFF_LIFECYCLE_PREVIEW);
    vi.spyOn(staffLifecycleClient, 'apply').mockResolvedValue(STAFF_LIFECYCLE_RECEIPT);
    vi.spyOn(staffQualificationMasterClient, 'query').mockResolvedValue(STAFF_QUALIFICATION_MASTER);
  });

  afterEach(() => vi.restoreAllMocks());

  async function openDrawer(): Promise<void> {
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });
    await waitFor(() => expect(screen.getAllByText(/在職|已退役/).length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByRole('button', { name: /檢視服務人員摘要/ })[0]);
    fireEvent.click(screen.getByRole('tab', { name: /接案狀態管理/ }));
    await waitFor(() => expect(screen.getByText(/人事任職狀態與異動辦理/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /辦理(退役|復職)登記/ }));
  }

  it('退役完成 preview、apply、receipt 與重新查詢並更新 server state', async () => {
    vi.mocked(staffLifecycleClient).query
      .mockResolvedValueOnce(STAFF_LIFECYCLE_VIEW)
      .mockResolvedValueOnce({ ...STAFF_LIFECYCLE_VIEW, state: 'retired', version: 3, effective_at: '2026-08-15T09:00:00+08:00' });
    await openDrawer();
    fireEvent.change(screen.getAllByLabelText('生效時間').at(-1)!, { target: { value: STAFF_LIFECYCLE_PREVIEW_PAYLOAD.effective_at } });
    fireEvent.change(screen.getAllByLabelText('異動原因').at(-1)!, { target: { value: STAFF_LIFECYCLE_PREVIEW_PAYLOAD.reason_code } });
    fireEvent.click(screen.getByRole('button', { name: /預覽退役/ }));

    await waitFor(() => expect(staffLifecycleClient.preview).toHaveBeenCalledWith(
      11,
      'retirement',
      STAFF_LIFECYCLE_PREVIEW_PAYLOAD,
      expect.anything(),
    ));
    expect(screen.getByRole('button', { name: /確認套用退役/ })).not.toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: /確認套用退役/ }));
    await waitFor(() => expect(staffLifecycleClient.apply).toHaveBeenCalledTimes(1));
    expect(staffLifecycleClient.apply).toHaveBeenCalledWith(
      11,
      'retirement',
      expect.objectContaining({
        ...STAFF_LIFECYCLE_APPLY_PAYLOAD,
        expected_version: 2,
      }),
      expect.objectContaining({ idempotencyKey: expect.any(String) }),
    );
    await waitFor(() => expect(staffLifecycleClient.query).toHaveBeenCalledTimes(2));
    expect(screen.getByText('已確認最新任職狀態')).toBeInTheDocument();
    expect(screen.getAllByText('已退役').length).toBeGreaterThan(0);
  });

  it('只依 server retired state 開啟復職，且 outcome_unknown 以同 key 重試', async () => {
    const retiredView = { ...STAFF_LIFECYCLE_VIEW, state: 'retired' as const };
    vi.mocked(staffLifecycleClient).query.mockResolvedValue(retiredView);
    vi.mocked(staffLifecycleClient).preview.mockResolvedValue({
      ...STAFF_LIFECYCLE_PREVIEW,
      state: 'retired',
      after_state: 'active',
    });
    vi.mocked(staffLifecycleClient).apply
      .mockRejectedValueOnce(new StaffLifecycleUnavailableError({ code: 'STAFF_LIFECYCLE_TIMEOUT', message: '請求逾時', retryable: true }))
      .mockResolvedValueOnce({ ...STAFF_LIFECYCLE_RECEIPT, state: 'active' });
    await openDrawer();
    expect(screen.queryByRole('button', { name: /預覽退役/ })).toBeNull();
    fireEvent.change(screen.getAllByLabelText('生效時間').at(-1)!, { target: { value: STAFF_LIFECYCLE_PREVIEW_PAYLOAD.effective_at } });
    fireEvent.change(screen.getAllByLabelText('異動原因').at(-1)!, { target: { value: 'return_active' } });
    fireEvent.click(screen.getByRole('button', { name: /預覽復職/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: /確認套用復職/ })).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', { name: /確認套用復職/ }));
    await waitFor(() => expect(screen.getByText(/結果未知/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '以相同內容重試' }));
    await waitFor(() => expect(staffLifecycleClient.apply).toHaveBeenCalledTimes(2));
    const first = vi.mocked(staffLifecycleClient.apply).mock.calls[0];
    const second = vi.mocked(staffLifecycleClient.apply).mock.calls[1];
    expect(first[1]).toBe('reactivation');
    expect(second[2]).toEqual(first[2]);
    expect(second[3].idempotencyKey).toBe(first[3].idempotencyKey);
  });

  it('apply_pending 與 outcome_unknown 都鎖定 tabs、selector、close 與 lifecycle inputs', async () => {
    const pendingApply = deferred<typeof STAFF_LIFECYCLE_RECEIPT>();
    vi.mocked(staffLifecycleClient.apply).mockReturnValueOnce(pendingApply.promise);
    await openDrawer();
    fireEvent.change(screen.getAllByLabelText('生效時間').at(-1)!, { target: { value: STAFF_LIFECYCLE_PREVIEW_PAYLOAD.effective_at } });
    fireEvent.change(screen.getAllByLabelText('異動原因').at(-1)!, { target: { value: STAFF_LIFECYCLE_PREVIEW_PAYLOAD.reason_code } });
    fireEvent.click(screen.getByRole('button', { name: /預覽退役/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: /確認套用退役/ })).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', { name: /確認套用退役/ }));
    await waitFor(() => expect(staffLifecycleClient.apply).toHaveBeenCalledTimes(1));

    const expectLocked = () => {
      for (const name of [/服務月嫂名冊/, /配對偏好/, /長假與暫停/]) {
        expect(screen.getByRole('button', { name })).toBeDisabled();
      }
      expect(screen.getByLabelText('查詢服務人員')).toBeDisabled();
      expect(screen.getByRole('button', { name: '關閉' })).toBeDisabled();
      expect(screen.getAllByLabelText('生效時間').at(-1)).toBeDisabled();
      expect(screen.getAllByLabelText('異動原因').at(-1)).toBeDisabled();
    };

    expectLocked();
    pendingApply.reject(new StaffLifecycleUnavailableError({
      code: 'STAFF_LIFECYCLE_TIMEOUT',
      message: '請求逾時',
      retryable: true,
    }));
    await waitFor(() => expect(screen.getByText(/結果未知/)).toBeInTheDocument());
    expectLocked();
  });
});

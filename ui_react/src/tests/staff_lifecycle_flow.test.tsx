/**
 * File: staff_lifecycle_flow.test.tsx
 * Description: 驗證 Staff lifecycle 退役與復職的 Preview、Apply、重查流程。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { staffQualificationMasterClient } from '../api/staff/qualification_master_client';
import { staffLifecycleClient } from '../api/staff_lifecycle/staff_lifecycle_client';
import { StaffLifecycleConflictError, StaffLifecycleUnavailableError } from '../api/staff_lifecycle/staff_lifecycle_errors';
import { StaffLifecycleApplyPayloadSchema, StaffLifecycleTransitionInputSchema } from '../api/staff_lifecycle/staff_lifecycle_schemas';
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
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({ ...STAFF_PAGE_ONE, next_cursor: null });
    vi.spyOn(staffDirectoryClient, 'resetPagination').mockImplementation(() => undefined);
    vi.spyOn(staffLifecycleClient, 'query').mockResolvedValue(STAFF_LIFECYCLE_VIEW);
    vi.spyOn(staffLifecycleClient, 'preview').mockImplementation(async (_id, _action, payload) => {
      StaffLifecycleTransitionInputSchema.parse(payload);
      return STAFF_LIFECYCLE_PREVIEW;
    });
    vi.spyOn(staffLifecycleClient, 'apply').mockImplementation(async (_id, _action, payload) => {
      StaffLifecycleApplyPayloadSchema.parse(payload);
      return STAFF_LIFECYCLE_RECEIPT;
    });
    vi.spyOn(staffQualificationMasterClient, 'query').mockResolvedValue(STAFF_QUALIFICATION_MASTER);
  });

  afterEach(() => vi.restoreAllMocks());

  async function openDrawer(): Promise<void> {
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole('button', { name: /查看 .* 的詳情/ })[0]);
    await waitFor(() => expect(screen.getByText(/人事任職狀態與異動辦理/)).toBeInTheDocument());
    fireEvent.click(await screen.findByRole('button', { name: /辦理(退役|復職)登記/ }));
  }

  it('退役完成 preview、apply、receipt 與重新查詢並更新 server state', async () => {
    vi.mocked(staffLifecycleClient).query
      .mockResolvedValueOnce(STAFF_LIFECYCLE_VIEW)
      .mockResolvedValueOnce({ ...STAFF_LIFECYCLE_VIEW, state: 'retired', version: 3, effective_at: '2026-08-15T09:00:00+08:00' });
    await openDrawer();
    fireEvent.change(screen.getAllByLabelText('生效日期').at(-1)!, { target: { value: '2026-08-15' } });
    fireEvent.change(screen.getAllByLabelText('異動原因（選填）').at(-1)!, { target: { value: STAFF_LIFECYCLE_PREVIEW_PAYLOAD.reason_code } });
    fireEvent.click(screen.getByRole('button', { name: /^辦理退役$/ }));

    await waitFor(() => expect(staffLifecycleClient.preview).toHaveBeenCalledWith(
      11,
      'retirement',
      { ...STAFF_LIFECYCLE_PREVIEW_PAYLOAD, effective_at: '2026-08-15T00:00:00+08:00' },
      expect.anything(),
    ));
    await waitFor(() => expect(staffLifecycleClient.apply).toHaveBeenCalledTimes(1));
    expect(staffLifecycleClient.apply).toHaveBeenCalledWith(
      11,
      'retirement',
      expect.objectContaining({
        ...STAFF_LIFECYCLE_APPLY_PAYLOAD,
        effective_at: '2026-08-15T00:00:00+08:00',
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
    expect(screen.queryByRole('button', { name: /^辦理退役$/ })).toBeNull();
    fireEvent.change(screen.getAllByLabelText('生效日期').at(-1)!, { target: { value: '2026-08-15' } });
    fireEvent.change(screen.getAllByLabelText('異動原因（選填）').at(-1)!, { target: { value: 'returned_to_service' } });
    fireEvent.click(screen.getByRole('button', { name: /^辦理復職$/ }));
    await waitFor(() => expect(screen.getByText(/結果未知/)).toBeInTheDocument());
    expect(staffLifecycleClient.preview).toHaveBeenCalledWith(11, 'reactivation', {
      effective_at: '2026-08-15T00:00:00+08:00',
      reason_code: 'returned_to_service',
    }, expect.anything());
    fireEvent.click(screen.getByRole('button', { name: '以相同內容重試' }));
    await waitFor(() => expect(staffLifecycleClient.apply).toHaveBeenCalledTimes(2));
    const first = vi.mocked(staffLifecycleClient.apply).mock.calls[0];
    const second = vi.mocked(staffLifecycleClient.apply).mock.calls[1];
    expect(first[1]).toBe('reactivation');
    expect(second[2]).toEqual(first[2]);
    expect(second[3].idempotencyKey).toBe(first[3].idempotencyKey);
  });

  it('apply_pending 與 outcome_unknown 都鎖定 selector、close 與 lifecycle inputs', async () => {
    const pendingApply = deferred<typeof STAFF_LIFECYCLE_RECEIPT>();
    vi.mocked(staffLifecycleClient.apply).mockReturnValueOnce(pendingApply.promise);
    await openDrawer();
    fireEvent.change(screen.getAllByLabelText('生效日期').at(-1)!, { target: { value: '2026-08-15' } });
    fireEvent.change(screen.getAllByLabelText('異動原因（選填）').at(-1)!, { target: { value: STAFF_LIFECYCLE_PREVIEW_PAYLOAD.reason_code } });
    fireEvent.click(screen.getByRole('button', { name: /^辦理退役$/ }));
    await waitFor(() => expect(staffLifecycleClient.apply).toHaveBeenCalledTimes(1));

    const expectLocked = () => {
      expect(screen.queryByRole('tablist', { name: '月嫂個人檔案分頁' })).not.toBeInTheDocument();
      expect(screen.getByLabelText('查詢服務人員')).toBeDisabled();
      expect(screen.getByRole('button', { name: '關閉' })).toBeDisabled();
      expect(screen.getAllByLabelText('生效日期').at(-1)).toBeDisabled();
      expect(screen.getAllByLabelText('異動原因（選填）').at(-1)).toBeDisabled();
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

  it('可不填原因，日期選擇後送出含台北時區的既有契約', async () => {
    await openDrawer();
    const date = screen.getByLabelText('生效日期');
    expect(date).toHaveAttribute('type', 'date');
    expect(screen.getByLabelText('異動原因（選填）').tagName).toBe('SELECT');
    fireEvent.change(date, { target: { value: '2026-08-15' } });
    fireEvent.click(screen.getByRole('button', { name: /^辦理退役$/ }));
    await waitFor(() => expect(staffLifecycleClient.apply).toHaveBeenCalledTimes(1));
    expect(staffLifecycleClient.preview).toHaveBeenCalledWith(11, 'retirement', {
      effective_at: '2026-08-15T00:00:00+08:00', reason_code: '',
    }, expect.anything());
  });

  it('未結束案件阻擋時顯示原因且不送出 Apply', async () => {
    const message = '此月嫂仍有未結束案件，請先完成案件或辦理改派，再辦理退役。';
    vi.mocked(staffLifecycleClient.preview).mockRejectedValueOnce(new StaffLifecycleConflictError({
      code: 'staff_retirement_open_assignments', message,
    }));
    await openDrawer();
    fireEvent.change(screen.getByLabelText('生效日期'), { target: { value: '2026-08-15' } });
    fireEvent.click(screen.getByRole('button', { name: /^辦理退役$/ }));
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(staffLifecycleClient.apply).not.toHaveBeenCalled();
  });
});

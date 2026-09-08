/**
 * File: staff_action_race_guards.test.tsx
 * Description: 驗證 Staff Preview 與 receipt 後重查不會被過期非同步結果污染。
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StaffPage } from '../../../../../../pages/StaffPage';
import { staffAvailabilityClient } from '../../../../../../api/staff_availability/staff_availability_client';
import { staffDirectoryClient } from '../../../../../../api/staff_directory/staff_directory_client';
import { staffLifecycleClient } from '../../../../../../api/staff_lifecycle/staff_lifecycle_client';
import { staffCasePreferenceManualClient } from '../../../../../../api/staff_case_preferences/staff_case_preferences_client';
import {
  STAFF_AVAILABILITY_BLOCK,
  STAFF_AVAILABILITY_PREVIEW_RESPONSE,
  STAFF_AVAILABILITY_RECEIPT_RESPONSE,
} from '../../../../../fixtures/staff/staff_availability_contract_fixtures';
import { STAFF_PAGE_ONE } from '../../../../../fixtures/staff/staff_directory_contract_fixtures';
import {
  STAFF_LIFECYCLE_PREVIEW,
  STAFF_LIFECYCLE_PREVIEW_PAYLOAD,
  STAFF_LIFECYCLE_RECEIPT,
  STAFF_LIFECYCLE_VIEW,
} from '../../../../../fixtures/staff/staff_lifecycle_contract_fixtures';

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

const manualRelations = (region: string) => ({
  service_regions: [{ value: region, detail: null }], service_periods: [], cooking_skills: [],
  holiday_availability: [], rest_schedule: [], baby_types: [],
});
const manualSnapshot = (staffId: number, region = '北區') => ({
  staff_id: staffId,
  before: manualRelations(region),
  after: manualRelations(region),
  snapshot_fingerprint: (staffId === 11 ? 'a' : 'b').repeat(64),
  preview_fingerprint: null,
});
const manualPreview = { ...manualSnapshot(11), preview_fingerprint: 'c'.repeat(64) };

async function renderReadyStaff(): Promise<void> {
  render(<StaffPage />);
  await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
}

async function openPreferences(): Promise<void> {
  await renderReadyStaff();
  fireEvent.click(screen.getByRole('button', { name: /配對偏好/ }));
  fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });
  await screen.findByRole('button', { name: '編輯六項偏好' });
}

async function openAvailability(): Promise<void> {
  await renderReadyStaff();
  fireEvent.click(screen.getByRole('button', { name: /長假與暫停/ }));
  fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });
  fireEvent.change(screen.getByLabelText('開始日期'), { target: { value: '2026-09-01' } });
  fireEvent.change(screen.getByLabelText('結束日期'), { target: { value: '2026-10-31' } });
  fireEvent.click(screen.getByRole('button', { name: '查詢不可服務期間' }));
  await waitFor(() => expect(screen.getByText('2026-09-01 ～ 2026-09-30')).toBeInTheDocument());
}

async function openLifecycle(): Promise<void> {
  await renderReadyStaff();
  fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });
  await waitFor(() => expect(screen.getByText('在職')).toBeInTheDocument());
  fireEvent.click(document.querySelector('[data-control-id="staff.drawer.open.11"]') as HTMLElement);
  fireEvent.click(screen.getByRole('tab', { name: /接案狀態管理/ }));
  await waitFor(() => expect(screen.getByText(/人事任職狀態與異動辦理/)).toBeInTheDocument());
  fireEvent.click(screen.getByRole('button', { name: /辦理退役登記/ }));
}

describe('Staff action async race guards', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue(STAFF_PAGE_ONE);
    vi.spyOn(staffDirectoryClient, 'resetPagination').mockImplementation(() => undefined);
    vi.spyOn(staffCasePreferenceManualClient, 'query').mockResolvedValue(manualSnapshot(11));
    vi.spyOn(staffCasePreferenceManualClient, 'preview').mockResolvedValue(manualPreview);
    vi.spyOn(staffCasePreferenceManualClient, 'apply').mockResolvedValue({
      staff_id: 11, relations: manualRelations('北區'), snapshot_fingerprint: 'd'.repeat(64),
      preview_fingerprint: 'c'.repeat(64), idempotency_key: 'staff-preference-race', replayed: false,
    });
    vi.spyOn(staffAvailabilityClient, 'getBlocks').mockResolvedValue([STAFF_AVAILABILITY_BLOCK]);
    vi.spyOn(staffAvailabilityClient, 'previewChange').mockResolvedValue(STAFF_AVAILABILITY_PREVIEW_RESPONSE.data!);
    vi.spyOn(staffAvailabilityClient, 'applyChange').mockResolvedValue(STAFF_AVAILABILITY_RECEIPT_RESPONSE.data!);
    vi.spyOn(staffLifecycleClient, 'query').mockResolvedValue(STAFF_LIFECYCLE_VIEW);
    vi.spyOn(staffLifecycleClient, 'preview').mockResolvedValue(STAFF_LIFECYCLE_PREVIEW);
    vi.spyOn(staffLifecycleClient, 'apply').mockResolvedValue(STAFF_LIFECYCLE_RECEIPT);
  });

  afterEach(() => vi.restoreAllMocks());

  it('preferences late Preview after unmount is aborted and cannot update the DOM', async () => {
    await openPreferences();
    const pending = deferred<typeof manualPreview>();
    vi.mocked(staffCasePreferenceManualClient.preview).mockReturnValueOnce(pending.promise);

    fireEvent.click(screen.getByRole('button', { name: '編輯六項偏好' }));
    fireEvent.click(screen.getByRole('button', { name: '預覽變更' }));
    await waitFor(() => expect(staffCasePreferenceManualClient.preview).toHaveBeenCalledTimes(1));
    const signal = vi.mocked(staffCasePreferenceManualClient.preview).mock.calls[0]?.[2]?.signal;
    expect(signal?.aborted).toBe(false);

    cleanup();
    expect(signal?.aborted).toBe(true);
    await act(async () => {
      pending.resolve(manualPreview);
      await Promise.resolve();
    });

    expect(screen.queryByTestId('staff-case-preference-manual-preview')).not.toBeInTheDocument();
  });

  it('availability late Preview after tab change cannot write the new tab', async () => {
    await openAvailability();
    const pending = deferred<NonNullable<typeof STAFF_AVAILABILITY_PREVIEW_RESPONSE.data>>();
    vi.mocked(staffAvailabilityClient.previewChange).mockReturnValueOnce(pending.promise);

    fireEvent.change(screen.getByLabelText('新增原因'), { target: { value: '去敏預覽競態' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽新增' }));
    await waitFor(() => expect(staffAvailabilityClient.previewChange).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole('button', { name: /服務月嫂名冊/ }));
    pending.resolve(STAFF_AVAILABILITY_PREVIEW_RESPONSE.data!);
    fireEvent.click(screen.getByRole('button', { name: /長假與暫停/ }));

    await waitFor(() => expect(screen.getByRole('button', { name: '套用新增' })).toBeDisabled());
    expect(screen.queryByText(/Preview 指紋/)).not.toBeInTheDocument();
  });

  it('availability field change aborts a pending Preview and discards its late response', async () => {
    await openAvailability();
    const pending = deferred<NonNullable<typeof STAFF_AVAILABILITY_PREVIEW_RESPONSE.data>>();
    vi.mocked(staffAvailabilityClient.previewChange).mockReturnValueOnce(pending.promise);

    fireEvent.change(screen.getByLabelText('新增原因'), { target: { value: '原始原因' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽新增' }));
    await waitFor(() => expect(staffAvailabilityClient.previewChange).toHaveBeenCalledTimes(1));
    const signal = vi.mocked(staffAvailabilityClient.previewChange).mock.calls[0]?.[2]?.signal;

    fireEvent.change(screen.getByLabelText('新增原因'), { target: { value: '新原因' } });
    expect(signal?.aborted).toBe(true);
    await act(async () => {
      pending.resolve(STAFF_AVAILABILITY_PREVIEW_RESPONSE.data!);
      await Promise.resolve();
    });

    expect(screen.getByRole('button', { name: '套用新增' })).toBeDisabled();
    expect(screen.queryByText(/Preview 指紋/)).not.toBeInTheDocument();
  });

  it('lifecycle pending Preview freezes the drawer identity against background selector changes', async () => {
    await openLifecycle();
    const pending = deferred<typeof STAFF_LIFECYCLE_PREVIEW>();
    vi.mocked(staffLifecycleClient.preview).mockReturnValueOnce(pending.promise);

    fireEvent.change(screen.getAllByLabelText('生效時間').at(-1)!, { target: { value: STAFF_LIFECYCLE_PREVIEW_PAYLOAD.effective_at } });
    fireEvent.change(screen.getAllByLabelText('異動原因').at(-1)!, { target: { value: STAFF_LIFECYCLE_PREVIEW_PAYLOAD.reason_code } });
    fireEvent.click(screen.getByRole('button', { name: /預覽退役/ }));
    await waitFor(() => expect(staffLifecycleClient.preview).toHaveBeenCalledTimes(1));

    const selector = screen.getByLabelText('查詢服務人員');
    expect(selector).toBeDisabled();
    fireEvent.change(selector, { target: { value: '12' } });
    expect(selector).toHaveValue('11');
    await act(async () => {
      pending.resolve(STAFF_LIFECYCLE_PREVIEW);
      await Promise.resolve();
    });

    expect(screen.getByText(/預覽已產生/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /確認套用退役/ })).toBeEnabled();
  });

  it('lifecycle Preview loading is disabled and rapid clicks create one request', async () => {
    await openLifecycle();
    const pending = deferred<typeof STAFF_LIFECYCLE_PREVIEW>();
    vi.mocked(staffLifecycleClient.preview).mockReturnValueOnce(pending.promise);

    fireEvent.change(screen.getAllByLabelText('生效時間').at(-1)!, { target: { value: STAFF_LIFECYCLE_PREVIEW_PAYLOAD.effective_at } });
    fireEvent.change(screen.getAllByLabelText('異動原因').at(-1)!, { target: { value: STAFF_LIFECYCLE_PREVIEW_PAYLOAD.reason_code } });
    const previewButton = screen.getByRole('button', { name: /預覽退役/ });
    fireEvent.click(previewButton);
    await waitFor(() => expect(previewButton).toBeDisabled());
    fireEvent.click(previewButton);
    fireEvent.click(previewButton);

    expect(staffLifecycleClient.preview).toHaveBeenCalledTimes(1);
    await act(async () => {
      pending.resolve(STAFF_LIFECYCLE_PREVIEW);
      await Promise.resolve();
    });
  });

  it('lifecycle pending Preview is aborted on unmount and its late response is discarded', async () => {
    await openLifecycle();
    const pending = deferred<typeof STAFF_LIFECYCLE_PREVIEW>();
    vi.mocked(staffLifecycleClient.preview).mockReturnValueOnce(pending.promise);

    fireEvent.change(screen.getAllByLabelText('生效時間').at(-1)!, { target: { value: STAFF_LIFECYCLE_PREVIEW_PAYLOAD.effective_at } });
    fireEvent.change(screen.getAllByLabelText('異動原因').at(-1)!, { target: { value: STAFF_LIFECYCLE_PREVIEW_PAYLOAD.reason_code } });
    fireEvent.click(screen.getByRole('button', { name: /預覽退役/ }));
    await waitFor(() => expect(staffLifecycleClient.preview).toHaveBeenCalledTimes(1));
    const signal = vi.mocked(staffLifecycleClient.preview).mock.calls[0]?.[3]?.signal;

    cleanup();
    expect(signal?.aborted).toBe(true);
    await act(async () => {
      pending.resolve(STAFF_LIFECYCLE_PREVIEW);
      await Promise.resolve();
    });

    expect(screen.queryByText(/預覽已產生/)).not.toBeInTheDocument();
  });

  it('stale preference refresh late response cannot overwrite a newly selected staff', async () => {
    const stale = deferred<ReturnType<typeof manualSnapshot>>();
    vi.mocked(staffCasePreferenceManualClient.query)
      .mockReturnValueOnce(stale.promise)
      .mockResolvedValueOnce(manualSnapshot(12, '南區'));
    await renderReadyStaff();
    fireEvent.click(screen.getByRole('button', { name: /配對偏好/ }));
    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });
    await waitFor(() => expect(staffCasePreferenceManualClient.query).toHaveBeenCalledTimes(1));
    const staleSignal = vi.mocked(staffCasePreferenceManualClient.query).mock.calls[0]?.[1]?.signal;
    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '12' } });
    expect(await screen.findByText('南區')).toBeInTheDocument();
    expect(staleSignal?.aborted).toBe(true);
    stale.resolve(manualSnapshot(11, '北區'));
    await waitFor(() => expect(screen.getByText('南區')).toBeInTheDocument());
    expect(screen.queryByText('北區')).not.toBeInTheDocument();
  });

  it('post-receipt lifecycle requery late response is ignored after unmount', async () => {
    const requery = deferred<typeof STAFF_LIFECYCLE_VIEW>();
    vi.mocked(staffLifecycleClient).query
      .mockResolvedValueOnce(STAFF_LIFECYCLE_VIEW)
      .mockReturnValueOnce(requery.promise);
    const view = render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });
    await waitFor(() => expect(screen.getByText('在職')).toBeInTheDocument());
    fireEvent.click(document.querySelector('[data-control-id="staff.drawer.open.11"]') as HTMLElement);
    fireEvent.click(screen.getByRole('tab', { name: /接案狀態管理/ }));
    await waitFor(() => expect(screen.getByText(/人事任職狀態與異動辦理/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /辦理退役登記/ }));
    fireEvent.change(screen.getAllByLabelText('生效時間').at(-1)!, { target: { value: STAFF_LIFECYCLE_PREVIEW_PAYLOAD.effective_at } });
    fireEvent.change(screen.getAllByLabelText('異動原因').at(-1)!, { target: { value: STAFF_LIFECYCLE_PREVIEW_PAYLOAD.reason_code } });
    fireEvent.click(screen.getByRole('button', { name: /預覽退役/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: /確認套用退役/ })).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', { name: /確認套用退役/ }));
    await waitFor(() => expect(staffLifecycleClient.apply).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(staffLifecycleClient.query).toHaveBeenCalledTimes(2));

    view.unmount();
    requery.resolve(STAFF_LIFECYCLE_VIEW);
  });
});

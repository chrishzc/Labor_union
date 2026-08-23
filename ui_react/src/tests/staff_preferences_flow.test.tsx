/**
 * File: staff_preferences_flow.test.tsx
 * Description: 驗證 Staff 偏好由查詢、預覽、套用到重新觀察的真實流程。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { staffPreferencesClient } from '../api/staff_preferences/staff_preferences_client';
import { StaffPreferencesConflictError, StaffPreferencesTimeoutError } from '../api/staff_preferences/staff_preferences_errors';
import { StaffPage } from '../pages/StaffPage';
import {
  STAFF_PREFERENCE_APPLY_RECEIPT,
  STAFF_PREFERENCE_DEFINITIONS,
  STAFF_PREFERENCE_PROFILE,
  STAFF_PREFERENCE_PROFILE_FOR_STAFF_11,
  STAFF_PREFERENCE_PREVIEW_FOR_STAFF_11,
  STAFF_PREFERENCE_RECEIPT_FOR_STAFF_11,
} from './fixtures/staff/staff_preferences_contract_fixtures';
import { STAFF_PAGE_ONE } from './fixtures/staff/staff_directory_contract_fixtures';

describe('Staff preferences flow', () => {
  beforeEach(() => {
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue(STAFF_PAGE_ONE);
    vi.spyOn(staffDirectoryClient, 'resetPagination').mockImplementation(() => undefined);
    vi.spyOn(staffPreferencesClient, 'queryDefinitions').mockResolvedValue(STAFF_PREFERENCE_DEFINITIONS);
    vi.spyOn(staffPreferencesClient, 'queryProfile').mockResolvedValue(STAFF_PREFERENCE_PROFILE_FOR_STAFF_11);
    vi.spyOn(staffPreferencesClient, 'previewProfile').mockResolvedValue(STAFF_PREFERENCE_PREVIEW_FOR_STAFF_11);
    vi.spyOn(staffPreferencesClient, 'applyProfile').mockResolvedValue(STAFF_PREFERENCE_RECEIPT_FOR_STAFF_11);
  });

  afterEach(() => vi.restoreAllMocks());

  async function openPreferences(): Promise<void> {
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /配對偏好/ }));
    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });
    await waitFor(() => expect(screen.getByDisplayValue('20–30')).toBeInTheDocument());
  }

  it('offers a direct preferences retry after a query error', async () => {
    vi.mocked(staffPreferencesClient.queryProfile)
      .mockRejectedValueOnce(new Error('偏好暫時失敗'))
      .mockResolvedValueOnce(STAFF_PREFERENCE_PROFILE_FOR_STAFF_11);
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /配對偏好/ }));
    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });

    fireEvent.click(await screen.findByRole('button', { name: '重試偏好資料' }));
    await waitFor(() => expect(screen.getByDisplayValue('20–30')).toBeInTheDocument());
    expect(staffPreferencesClient.queryProfile).toHaveBeenCalledTimes(2);
  });

  it('完成完整 snapshot 的 preview、apply、receipt 與 requery', async () => {
    const updatedProfile = {
      ...STAFF_PREFERENCE_PROFILE_FOR_STAFF_11,
      version: STAFF_PREFERENCE_APPLY_RECEIPT.version,
      values: STAFF_PREFERENCE_APPLY_RECEIPT.values,
    };
    vi.mocked(staffPreferencesClient.queryProfile)
      .mockResolvedValueOnce(STAFF_PREFERENCE_PROFILE_FOR_STAFF_11)
      .mockResolvedValueOnce(updatedProfile);

    await openPreferences();
    fireEvent.click(screen.getByRole('button', { name: '編輯核准偏好' }));
    fireEvent.change(screen.getByLabelText('服務天數下限'), { target: { value: '22' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽偏好變更' }));

    await waitFor(() => expect(staffPreferencesClient.previewProfile).toHaveBeenCalledTimes(1));
    expect(staffPreferencesClient.previewProfile).toHaveBeenCalledWith(
      11,
      {
        values: STAFF_PREFERENCE_PROFILE.values.map((item) =>
          item.preference_key === 'preferred_service_days'
            ? { ...item, value: { kind: 'integer_range', minimum: 22, maximum: 30 } }
            : item,
        ),
      },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );

    expect(screen.getByRole('button', { name: '套用偏好變更' })).not.toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '套用偏好變更' }));
    await waitFor(() => expect(staffPreferencesClient.applyProfile).toHaveBeenCalledTimes(1));
    expect(staffPreferencesClient.applyProfile).toHaveBeenCalledWith(
      11,
      expect.objectContaining({
        expected_version: 4,
        preview_fingerprint: 'a'.repeat(64),
        reason: '人工維護月嫂偏好',
        values: expect.arrayContaining([
          { preference_key: 'preferred_service_days', value: { kind: 'integer_range', minimum: 22, maximum: 30 } },
          { preference_key: 'daily_service_hours', value: { kind: 'integer_set', values: [4, 8] } },
        ]),
      }),
      expect.objectContaining({ idempotencyKey: expect.any(String) }),
    );
    await waitFor(() => expect(staffPreferencesClient.queryProfile).toHaveBeenCalledTimes(2));
    expect(screen.getByText('已觀察最新偏好')).toBeInTheDocument();
    expect(screen.getByDisplayValue('22–30')).toBeInTheDocument();
  });

  it('編輯 daily_service_hours integer_set 並將完整 snapshot 帶入 preview', async () => {
    await openPreferences();
    fireEvent.click(screen.getByRole('button', { name: '編輯核准偏好' }));

    const dailyHours = screen.getByLabelText('可承接每日服務時數');
    expect(dailyHours).toBeEnabled();
    fireEvent.change(dailyHours, { target: { value: '4,10' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽偏好變更' }));

    await waitFor(() => expect(staffPreferencesClient.previewProfile).toHaveBeenCalledTimes(1));
    expect(staffPreferencesClient.previewProfile).toHaveBeenCalledWith(
      11,
      {
        values: expect.arrayContaining([
          { preference_key: 'preferred_service_days', value: { kind: 'integer_range', minimum: 20, maximum: 30 } },
          { preference_key: 'daily_service_hours', value: { kind: 'integer_set', values: [4, 10] } },
        ]),
      },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it('尚未設定偏好時可建立完整 snapshot，不會送出空 Apply', async () => {
    vi.mocked(staffPreferencesClient.queryProfile).mockResolvedValue({ staff_id: 11, version: 0, values: [] });
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /配對偏好/ }));
    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });
    await waitFor(() => expect(screen.getByRole('button', { name: '編輯核准偏好' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '編輯核准偏好' }));
    fireEvent.change(screen.getByLabelText('服務天數下限'), { target: { value: '15' } });
    fireEvent.change(screen.getByLabelText('服務天數上限'), { target: { value: '30' } });
    fireEvent.change(screen.getByLabelText('可承接每日服務時數'), { target: { value: '24' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽偏好變更' }));

    await waitFor(() => expect(staffPreferencesClient.previewProfile).toHaveBeenCalledWith(
      11,
      {
        values: expect.arrayContaining([
          { preference_key: 'preferred_service_days', value: { kind: 'integer_range', minimum: 15, maximum: 30 } },
          { preference_key: 'daily_service_hours', value: { kind: 'integer_set', values: [24] } },
        ]),
      },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
  });

  it('編輯會使舊 preview 失效，409 不允許相同 key 重試', async () => {
    await openPreferences();
    fireEvent.click(screen.getByRole('button', { name: '編輯核准偏好' }));
    fireEvent.click(screen.getByRole('button', { name: '預覽偏好變更' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '套用偏好變更' })).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', { name: '編輯核准偏好' }));
    expect(screen.getByRole('button', { name: '套用偏好變更' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: '預覽偏好變更' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '套用偏好變更' })).not.toBeDisabled());
    vi.mocked(staffPreferencesClient.applyProfile).mockRejectedValueOnce(
      new StaffPreferencesConflictError('版本已過期'),
    );
    fireEvent.click(screen.getByRole('button', { name: '套用偏好變更' }));
    await waitFor(() => expect(screen.getByText(/版本已過期/)).toBeInTheDocument());
    expect(staffPreferencesClient.applyProfile).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: '以相同內容重試' })).toBeNull();
  });

  it('Apply timeout 只進 outcome_unknown 並以相同 payload/key 重試', async () => {
    await openPreferences();
    fireEvent.click(screen.getByRole('button', { name: '編輯核准偏好' }));
    fireEvent.click(screen.getByRole('button', { name: '預覽偏好變更' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '套用偏好變更' })).not.toBeDisabled());
    vi.mocked(staffPreferencesClient.applyProfile)
      .mockRejectedValueOnce(new StaffPreferencesTimeoutError('請求逾時'))
      .mockResolvedValueOnce(STAFF_PREFERENCE_RECEIPT_FOR_STAFF_11);
    fireEvent.click(screen.getByRole('button', { name: '套用偏好變更' }));
    await waitFor(() => expect(screen.getByText(/結果未知/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '以相同內容重試' }));
    await waitFor(() => expect(staffPreferencesClient.applyProfile).toHaveBeenCalledTimes(2));
    const first = vi.mocked(staffPreferencesClient.applyProfile).mock.calls[0];
    const second = vi.mocked(staffPreferencesClient.applyProfile).mock.calls[1];
    expect(second[1]).toEqual(first[1]);
    expect(second[2].idempotencyKey).toBe(first[2].idempotencyKey);
  });
});

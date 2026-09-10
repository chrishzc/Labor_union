/** Current Staff six-relation preference integration through the #staff page. */
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { staffCasePreferenceManualClient } from '../api/staff_case_preferences/staff_case_preferences_client';
import type { StaffCasePreferenceManualSnapshot, StaffCasePreferenceRelations } from '../api/staff_case_preferences/staff_case_preferences_schemas';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { StaffPage } from '../pages/StaffPage';
import { STAFF_PAGE_ONE } from './fixtures/staff/staff_directory_contract_fixtures';

const RELATIONS: StaffCasePreferenceRelations = {
  service_regions: [{ value: '北區', detail: '既有說明' }],
  service_periods: [{ value: '白天', detail: null }],
  cooking_skills: [{ value: '家常菜', detail: null }],
  holiday_availability: [{ value: '需確認', detail: null }],
  rest_schedule: [{ value: '週休二日', detail: null }],
  baby_types: [{ value: '單胞胎', detail: null }],
};
const SNAPSHOT: StaffCasePreferenceManualSnapshot = {
  staff_id: 11, before: RELATIONS, after: RELATIONS,
  snapshot_fingerprint: 'a'.repeat(64), preview_fingerprint: null,
};
const PREVIEW: StaffCasePreferenceManualSnapshot = {
  ...SNAPSHOT,
  after: { ...RELATIONS, service_regions: [{ value: '東區', detail: '新說明' }] },
  preview_fingerprint: 'b'.repeat(64),
};

async function openPreferences(): Promise<void> {
  render(<StaffPage />);
  await screen.findByText('去敏人員甲');
  fireEvent.click(screen.getByRole('button', { name: '查看 去敏人員甲 的詳情' }));
  fireEvent.click(screen.getByRole('tab', { name: /接案偏好設定/ }));
  await screen.findByRole('button', { name: '編輯六項偏好' });
}

describe('Staff current six-relation preference flow', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue(STAFF_PAGE_ONE);
    vi.spyOn(staffDirectoryClient, 'resetPagination').mockImplementation(() => undefined);
    vi.spyOn(staffCasePreferenceManualClient, 'query').mockResolvedValue(SNAPSHOT);
    vi.spyOn(staffCasePreferenceManualClient, 'preview').mockImplementation(async (_staffId, relations) => ({ ...PREVIEW, after: relations }));
    vi.spyOn(staffCasePreferenceManualClient, 'apply').mockResolvedValue({
      staff_id: 11, relations: PREVIEW.after, snapshot_fingerprint: 'c'.repeat(64),
      preview_fingerprint: 'b'.repeat(64), idempotency_key: 'staff-current-preference', replayed: false,
    });
  });
  afterEach(() => vi.restoreAllMocks());

  it('offers a direct retry after the owner Query fails', async () => {
    vi.mocked(staffCasePreferenceManualClient.query)
      .mockRejectedValueOnce(new Error('六項偏好暫時失敗'))
      .mockResolvedValueOnce(SNAPSHOT);
    render(<StaffPage />);
    await screen.findByText('去敏人員甲');
    fireEvent.click(screen.getByRole('button', { name: '查看 去敏人員甲 的詳情' }));
    fireEvent.click(screen.getByRole('tab', { name: /接案偏好設定/ }));
    expect(await screen.findByText('六項偏好暫時失敗')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重新查詢' }));
    expect(await screen.findByRole('button', { name: '編輯六項偏好' })).toBeEnabled();
    expect(staffCasePreferenceManualClient.query).toHaveBeenCalledTimes(2);
  });

  it('runs Query, Preview, confirmed Apply, and owner readback once each', async () => {
    const saved = { ...PREVIEW, before: PREVIEW.after, snapshot_fingerprint: 'c'.repeat(64), preview_fingerprint: null };
    vi.mocked(staffCasePreferenceManualClient.query).mockResolvedValueOnce(SNAPSHOT).mockResolvedValueOnce(saved);
    await openPreferences();
    fireEvent.click(screen.getByRole('button', { name: '編輯六項偏好' }));
    fireEvent.change(screen.getByLabelText('可承接區域值1'), { target: { value: '東區' } });
    fireEvent.change(screen.getByLabelText('可承接區域說明1'), { target: { value: '新說明' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽變更' }));
    const confirm = await screen.findByRole('button', { name: '確認儲存' });
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByLabelText('六大接案能力變更原因'), { target: { value: '人工維護月嫂偏好' } });
    fireEvent.click(confirm);
    await screen.findByText('已儲存並重新查詢六大接案能力。');
    expect(staffCasePreferenceManualClient.preview).toHaveBeenCalledTimes(1);
    expect(staffCasePreferenceManualClient.apply).toHaveBeenCalledWith(
      11,
      expect.objectContaining({ service_regions: [{ value: '東區', detail: '新說明' }], expected_snapshot_fingerprint: 'a'.repeat(64), preview_fingerprint: 'b'.repeat(64), reason: '人工維護月嫂偏好' }),
      expect.objectContaining({ idempotencyKey: expect.any(String), signal: expect.any(AbortSignal) }),
    );
    expect(staffCasePreferenceManualClient.query).toHaveBeenCalledTimes(2);
  });

  it('invalidates an existing Preview when an edited relation changes', async () => {
    await openPreferences();
    fireEvent.click(screen.getByRole('button', { name: '編輯六項偏好' }));
    fireEvent.change(screen.getByLabelText('六大接案能力變更原因'), { target: { value: '測試失效' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽變更' }));
    expect(await screen.findByRole('button', { name: '確認儲存' })).toBeEnabled();
    fireEvent.change(screen.getByLabelText('可承接區域值1'), { target: { value: '南區' } });
    expect(screen.queryByRole('button', { name: '確認儲存' })).not.toBeInTheDocument();
    expect(screen.queryByTestId('staff-case-preference-manual-preview')).not.toBeInTheDocument();
    expect(staffCasePreferenceManualClient.apply).not.toHaveBeenCalled();
  });

  it('fails closed on stale Apply and requires a fresh Query', async () => {
    vi.mocked(staffCasePreferenceManualClient.apply).mockRejectedValueOnce(new Error('stale_snapshot'));
    await openPreferences();
    fireEvent.click(screen.getByRole('button', { name: '編輯六項偏好' }));
    fireEvent.change(screen.getByLabelText('六大接案能力變更原因'), { target: { value: '測試 stale' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽變更' }));
    fireEvent.click(await screen.findByRole('button', { name: '確認儲存' }));
    expect(await screen.findByText('stale_snapshot')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新查詢' })).toBeInTheDocument();
    expect(screen.queryByText('已儲存並重新查詢六大接案能力。')).not.toBeInTheDocument();
  });
});

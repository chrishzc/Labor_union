/**
 * File: staff_request_budget.test.tsx
 * Description: 驗證 Staff 四 bounded slice 的固定 GET、Preview、Apply、requery 預算。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { staffAvailabilityClient } from '../../../../../../api/staff_availability/staff_availability_client';
import { staffDirectoryClient } from '../../../../../../api/staff_directory/staff_directory_client';
import { staffQualificationMasterClient } from '../../../../../../api/staff/qualification_master_client';
import { staffLifecycleClient } from '../../../../../../api/staff_lifecycle/staff_lifecycle_client';
import { staffCasePreferenceManualClient } from '../../../../../../api/staff_case_preferences/staff_case_preferences_client';
import { StaffPage } from '../../../../../../pages/StaffPage';
import { STAFF_PAGE_ONE } from '../../../../../fixtures/staff/staff_directory_contract_fixtures';
import {
  STAFF_AVAILABILITY_BLOCK,
  STAFF_AVAILABILITY_PREVIEW_RESPONSE,
  STAFF_AVAILABILITY_RECEIPT_RESPONSE,
} from '../../../../../fixtures/staff/staff_availability_contract_fixtures';
import {
  STAFF_LIFECYCLE_PREVIEW,
  STAFF_LIFECYCLE_RECEIPT,
  STAFF_LIFECYCLE_VIEW,
} from '../../../../../fixtures/staff/staff_lifecycle_contract_fixtures';
import { STAFF_QUALIFICATION_MASTER } from '../../../../../fixtures/staff/staff_qualification_contract_fixtures';

const manualRelations = {
  service_regions: [{ value: '北區', detail: null }], service_periods: [], cooking_skills: [],
  holiday_availability: [], rest_schedule: [], baby_types: [],
};
const manualSnapshot = {
  staff_id: 11, before: manualRelations, after: manualRelations,
  snapshot_fingerprint: 'a'.repeat(64), preview_fingerprint: null,
};

describe('Staff request budget', () => {
  beforeEach(() => {
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue(STAFF_PAGE_ONE);
    vi.spyOn(staffDirectoryClient, 'resetPagination').mockImplementation(() => undefined);
    vi.spyOn(staffQualificationMasterClient, 'query').mockResolvedValue(STAFF_QUALIFICATION_MASTER);
  });

  afterEach(() => vi.restoreAllMocks());

  it('preferences uses owner query/preview/apply/requery once each', async () => {
    vi.spyOn(staffCasePreferenceManualClient, 'query')
      .mockResolvedValueOnce(manualSnapshot)
      .mockResolvedValueOnce({ ...manualSnapshot, snapshot_fingerprint: 'c'.repeat(64) });
    vi.spyOn(staffCasePreferenceManualClient, 'preview').mockImplementation(async (_staff, relations) => ({
      ...manualSnapshot, after: relations, preview_fingerprint: 'b'.repeat(64),
    }));
    vi.spyOn(staffCasePreferenceManualClient, 'apply').mockResolvedValue({
      staff_id: 11, relations: manualRelations, snapshot_fingerprint: 'c'.repeat(64),
      preview_fingerprint: 'b'.repeat(64), idempotency_key: 'budget', replayed: false,
    });
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /配對偏好/ }));
    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });
    fireEvent.click(await screen.findByRole('button', { name: '編輯六項偏好' }));
    fireEvent.change(screen.getByLabelText('六大接案能力變更原因'), { target: { value: 'request budget' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽變更' }));
    fireEvent.click(await screen.findByRole('button', { name: '確認儲存' }));
    await waitFor(() => expect(staffCasePreferenceManualClient.query).toHaveBeenCalledTimes(2));
    expect(staffCasePreferenceManualClient.preview).toHaveBeenCalledTimes(1);
    expect(staffCasePreferenceManualClient.apply).toHaveBeenCalledTimes(1);
  });

  it('availability create uses one range GET plus preview/apply/requery', async () => {
    vi.spyOn(staffAvailabilityClient, 'getBlocks')
      .mockResolvedValueOnce([STAFF_AVAILABILITY_BLOCK])
      .mockResolvedValueOnce([STAFF_AVAILABILITY_BLOCK]);
    vi.spyOn(staffAvailabilityClient, 'previewChange').mockResolvedValue(STAFF_AVAILABILITY_PREVIEW_RESPONSE.data!);
    vi.spyOn(staffAvailabilityClient, 'applyChange').mockResolvedValue(STAFF_AVAILABILITY_RECEIPT_RESPONSE.data!);
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /長假與暫停/ }));
    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });
    fireEvent.change(screen.getByLabelText('開始日期'), { target: { value: '2026-09-01' } });
    fireEvent.change(screen.getByLabelText('結束日期'), { target: { value: '2026-10-31' } });
    fireEvent.change(screen.getByLabelText('新增原因'), { target: { value: '排定休假' } });
    fireEvent.click(screen.getByRole('button', { name: '查詢不可服務期間' }));
    await waitFor(() => expect(screen.getByText('2026-09-01 ～ 2026-09-30')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '預覽新增' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '套用新增' })).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', { name: '套用新增' }));
    await waitFor(() => expect(staffAvailabilityClient.getBlocks).toHaveBeenCalledTimes(2));
    expect(staffAvailabilityClient.previewChange).toHaveBeenCalledTimes(1);
    expect(staffAvailabilityClient.applyChange).toHaveBeenCalledTimes(1);
  });

  it('lifecycle uses one query plus preview/apply/requery', async () => {
    vi.spyOn(staffLifecycleClient, 'query')
      .mockResolvedValueOnce(STAFF_LIFECYCLE_VIEW)
      .mockResolvedValueOnce({ ...STAFF_LIFECYCLE_VIEW, state: 'retired', version: 3 });
    vi.spyOn(staffLifecycleClient, 'preview').mockResolvedValue(STAFF_LIFECYCLE_PREVIEW);
    vi.spyOn(staffLifecycleClient, 'apply').mockResolvedValue(STAFF_LIFECYCLE_RECEIPT);
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });
    await waitFor(() => expect(screen.getAllByText('在職').length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByRole('button', { name: /檢視服務人員摘要/ })[0]);
    fireEvent.click(screen.getByRole('tab', { name: /接案狀態管理/ }));
    await waitFor(() => expect(screen.getByText(/人事任職狀態與異動辦理/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /辦理退役登記/ }));
    fireEvent.change(screen.getAllByLabelText('生效時間').at(-1)!, { target: { value: '2026-09-01T09:00' } });
    fireEvent.change(screen.getAllByLabelText('異動原因').at(-1)!, { target: { value: 'voluntary_retirement' } });
    fireEvent.click(screen.getByRole('button', { name: /預覽退役/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: /確認套用退役/ })).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', { name: /確認套用退役/ }));
    await waitFor(() => expect(staffLifecycleClient.query).toHaveBeenCalledTimes(2));
    expect(staffLifecycleClient.preview).toHaveBeenCalledTimes(1);
    expect(staffLifecycleClient.apply).toHaveBeenCalledTimes(1);
  });
});

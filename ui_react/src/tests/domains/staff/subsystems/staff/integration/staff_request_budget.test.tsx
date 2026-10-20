/**
 * File: staff_request_budget.test.tsx
 * Description: 驗證 Staff 四 bounded slice 的固定 GET、Preview、Apply、requery 預算。
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { staffAvailabilityClient } from '../../../../../../api/staff_availability/staff_availability_client';
import { staffDirectoryClient } from '../../../../../../api/staff_directory/staff_directory_client';
import { staffQualificationMasterClient } from '../../../../../../api/staff/qualification_master_client';
import { staffLifecycleClient } from '../../../../../../api/staff_lifecycle/staff_lifecycle_client';
import { staffCasePreferenceManualClient } from '../../../../../../api/staff_case_preferences/staff_case_preferences_client';
import { STAFF_MANUAL_OPTIONS } from './fixtures/staff_manual_options';
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

const preferenceEditor = () => within(document.querySelector('[data-surface-id="staff.qualification.case-preference-manual"]') as HTMLElement);

describe('Staff request budget', () => {
  beforeEach(() => {
    vi.spyOn(staffCasePreferenceManualClient, 'queryOptions').mockResolvedValue(STAFF_MANUAL_OPTIONS);
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({ ...STAFF_PAGE_ONE, next_cursor: null });
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
    fireEvent.click(screen.getByRole('button', { name: /查看 去敏人員甲 的詳情/ }));
    await screen.findByRole('combobox', { name: '可承接區域值1' });
    fireEvent.change(screen.getByLabelText('接案條件備註（選填）'), { target: { value: 'request budget' } });
    fireEvent.click(preferenceEditor().getByRole('button', { name: '預覽變更' }));
    await screen.findByText('預覽已完成，尚未寫入。');
    fireEvent.click(preferenceEditor().getByRole('button', { name: '確認儲存' }));
    await waitFor(() => expect(staffCasePreferenceManualClient.query).toHaveBeenCalledTimes(2));
    expect(staffCasePreferenceManualClient.preview).toHaveBeenCalledTimes(1);
    expect(staffCasePreferenceManualClient.apply).toHaveBeenCalledTimes(1);
    expect(staffCasePreferenceManualClient.queryOptions).toHaveBeenCalledTimes(2);
  });

  it('availability create uses one range GET plus preview/apply/requery and refreshes the qualification summary', async () => {
    vi.mocked(staffQualificationMasterClient.query)
      .mockResolvedValueOnce(STAFF_QUALIFICATION_MASTER)
      .mockResolvedValueOnce({ ...STAFF_QUALIFICATION_MASTER, as_of: '2026-10-13', overall_availability: 'unavailable' });
    vi.spyOn(staffAvailabilityClient, 'getBlocks').mockResolvedValue([STAFF_AVAILABILITY_BLOCK]);
    vi.spyOn(staffAvailabilityClient, 'previewChange').mockResolvedValue(STAFF_AVAILABILITY_PREVIEW_RESPONSE.data!);
    vi.spyOn(staffAvailabilityClient, 'applyChange').mockResolvedValue(STAFF_AVAILABILITY_RECEIPT_RESPONSE.data!);
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /查看 去敏人員甲 的詳情/ }));
    fireEvent.change(screen.getByLabelText('新增原因'), { target: { value: '排定休假' } });
    await waitFor(() => expect(screen.getByText('2026-09-01 ～ 2026-09-30')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '預覽新增' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '套用新增' })).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', { name: '套用新增' }));
    await waitFor(() => expect(staffAvailabilityClient.getBlocks).toHaveBeenCalledTimes(2));
    expect(staffAvailabilityClient.previewChange).toHaveBeenCalledTimes(1);
    expect(staffAvailabilityClient.applyChange).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(staffQualificationMasterClient.query).toHaveBeenCalledTimes(2));
    const masterSection = screen.getByRole('region', { name: '完整資格主檔' });
    expect(await within(masterSection).findByText(/資料基準日：2026-10-13/)).toBeInTheDocument();
    expect(masterSection).toHaveTextContent('整體狀態：目前不可服務');
  });

  it('lifecycle uses one query plus preview/apply/requery', async () => {
    vi.spyOn(staffLifecycleClient, 'query')
      .mockResolvedValueOnce(STAFF_LIFECYCLE_VIEW)
      .mockResolvedValueOnce({ ...STAFF_LIFECYCLE_VIEW, state: 'retired', version: 3 });
    vi.spyOn(staffLifecycleClient, 'preview').mockResolvedValue(STAFF_LIFECYCLE_PREVIEW);
    vi.spyOn(staffLifecycleClient, 'apply').mockResolvedValue(STAFF_LIFECYCLE_RECEIPT);
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /查看 去敏人員甲 的詳情/ }));
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

/**
 * File: staff_no_fake_mutation.test.tsx
 * Description: 驗證 Staff 不呈現無契約控制，且合法動作維持輸入鎖與零隱式 mutation。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { staffAvailabilityClient } from '../../../../../../api/staff_availability/staff_availability_client';
import { staffDirectoryClient } from '../../../../../../api/staff_directory/staff_directory_client';
import { staffLifecycleClient } from '../../../../../../api/staff_lifecycle/staff_lifecycle_client';
import { staffCasePreferenceManualClient } from '../../../../../../api/staff_case_preferences/staff_case_preferences_client';
import { StaffPage } from '../../../../../../pages/StaffPage';
import { STAFF_PAGE_ONE } from '../../../../../fixtures/staff/staff_directory_contract_fixtures';
import { STAFF_AVAILABILITY_BLOCK } from '../../../../../fixtures/staff/staff_availability_contract_fixtures';
import { STAFF_LIFECYCLE_VIEW } from '../../../../../fixtures/staff/staff_lifecycle_contract_fixtures';

const manualRelations = {
  service_regions: [{ value: '北區', detail: null }], service_periods: [], cooking_skills: [],
  holiday_availability: [], rest_schedule: [], baby_types: [],
};

describe('StaffPage no fake mutation', () => {
  beforeEach(() => {
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue(STAFF_PAGE_ONE);
    vi.spyOn(staffDirectoryClient, 'resetPagination').mockImplementation(() => undefined);
    vi.spyOn(staffCasePreferenceManualClient, 'query').mockResolvedValue({
      staff_id: 11, before: manualRelations, after: manualRelations,
      snapshot_fingerprint: 'a'.repeat(64), preview_fingerprint: null,
    });
    vi.spyOn(staffCasePreferenceManualClient, 'preview');
    vi.spyOn(staffCasePreferenceManualClient, 'apply');
    vi.spyOn(staffAvailabilityClient, 'getBlocks').mockResolvedValue([STAFF_AVAILABILITY_BLOCK]);
    vi.spyOn(staffAvailabilityClient, 'previewChange');
    vi.spyOn(staffAvailabilityClient, 'applyChange');
    vi.spyOn(staffLifecycleClient, 'query').mockResolvedValue(STAFF_LIFECYCLE_VIEW);
  });

  afterEach(() => vi.restoreAllMocks());

  it('removes unsupported controls while server-gated actions keep zero implicit mutation', async () => {
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    expect(document.querySelector('[data-control-id="staff.master.create"]')).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '辦理退役／復職' })[0]).toBeEnabled();
    expect(staffCasePreferenceManualClient.preview).not.toHaveBeenCalled();
    expect(staffCasePreferenceManualClient.apply).not.toHaveBeenCalled();
    expect(staffAvailabilityClient.previewChange).not.toHaveBeenCalled();
    expect(staffAvailabilityClient.applyChange).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /配對偏好/ }));
    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });
    expect(await screen.findByRole('button', { name: '編輯六項偏好' })).toBeEnabled();
    expect(document.querySelector('[data-control-id="staff.preferences.cooking-skills"]')).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="staff.preferences.special-notes"]')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /長假與暫停/ }));
    expect(screen.getByRole('button', { name: '預覽結束暫停' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '套用取消' })).toBeDisabled();
  });
});

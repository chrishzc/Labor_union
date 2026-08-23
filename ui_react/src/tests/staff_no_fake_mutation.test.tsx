/**
 * File: staff_no_fake_mutation.test.tsx
 * Description: 驗證 Staff 不呈現無契約控制，且合法動作維持輸入鎖與零隱式 mutation。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { staffAvailabilityClient } from '../api/staff_availability/staff_availability_client';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { staffLifecycleClient } from '../api/staff_lifecycle/staff_lifecycle_client';
import { staffPreferencesClient } from '../api/staff_preferences/staff_preferences_client';
import { StaffPage } from '../pages/StaffPage';
import { STAFF_PAGE_ONE } from './fixtures/staff/staff_directory_contract_fixtures';
import { STAFF_PREFERENCE_DEFINITIONS, STAFF_PREFERENCE_PROFILE_FOR_STAFF_11 } from './fixtures/staff/staff_preferences_contract_fixtures';
import { STAFF_AVAILABILITY_BLOCK } from './fixtures/staff/staff_availability_contract_fixtures';
import { STAFF_LIFECYCLE_VIEW } from './fixtures/staff/staff_lifecycle_contract_fixtures';

describe('StaffPage no fake mutation', () => {
  beforeEach(() => {
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue(STAFF_PAGE_ONE);
    vi.spyOn(staffDirectoryClient, 'resetPagination').mockImplementation(() => undefined);
    vi.spyOn(staffPreferencesClient, 'queryDefinitions').mockResolvedValue(STAFF_PREFERENCE_DEFINITIONS);
    vi.spyOn(staffPreferencesClient, 'queryProfile').mockResolvedValue(STAFF_PREFERENCE_PROFILE_FOR_STAFF_11);
    vi.spyOn(staffPreferencesClient, 'previewProfile').mockResolvedValue({
      staff_id: 11,
      before: STAFF_PREFERENCE_PROFILE_FOR_STAFF_11.values,
      after: STAFF_PREFERENCE_PROFILE_FOR_STAFF_11.values,
      version: 4,
      preview_fingerprint: 'a'.repeat(64),
    });
    vi.spyOn(staffPreferencesClient, 'applyProfile').mockResolvedValue({
      staff_id: 11,
      version: 5,
      values: STAFF_PREFERENCE_PROFILE_FOR_STAFF_11.values,
      preview_fingerprint: 'a'.repeat(64),
      idempotency_key: 'no-fake-preferences',
    });
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
    expect(staffPreferencesClient.previewProfile).not.toHaveBeenCalled();
    expect(staffPreferencesClient.applyProfile).not.toHaveBeenCalled();
    expect(staffAvailabilityClient.previewChange).not.toHaveBeenCalled();
    expect(staffAvailabilityClient.applyChange).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /配對偏好/ }));
    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });
    await waitFor(() => expect(screen.getByDisplayValue('20–30')).toBeInTheDocument());
    expect(document.querySelector('[data-control-id="staff.preferences.cooking-skills"]')).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="staff.preferences.special-notes"]')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /長假與暫停/ }));
    expect(screen.getByRole('button', { name: '預覽結束暫停' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '套用取消' })).toBeDisabled();
  });
});

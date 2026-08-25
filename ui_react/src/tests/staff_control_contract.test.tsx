/**
 * File: staff_control_contract.test.tsx
 * Description: 驗證 Staff 合法控制項的 server-gated enablement 並排除永久假按鈕。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { staffAvailabilityClient } from '../api/staff_availability/staff_availability_client';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { staffQualificationMasterClient } from '../api/staff/qualification_master_client';
import { staffLifecycleClient } from '../api/staff_lifecycle/staff_lifecycle_client';
import { staffPreferencesClient } from '../api/staff_preferences/staff_preferences_client';
import { StaffPage } from '../pages/StaffPage';
import { STAFF_PAGE_ONE } from './fixtures/staff/staff_directory_contract_fixtures';
import { STAFF_PREFERENCE_DEFINITIONS, STAFF_PREFERENCE_PROFILE } from './fixtures/staff/staff_preferences_contract_fixtures';
import { STAFF_AVAILABILITY_BLOCK } from './fixtures/staff/staff_availability_contract_fixtures';
import { STAFF_LIFECYCLE_VIEW } from './fixtures/staff/staff_lifecycle_contract_fixtures';
import { STAFF_QUALIFICATION_MASTER } from './fixtures/staff/staff_qualification_contract_fixtures';

describe('Staff control contract', () => {
  beforeEach(() => {
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue(STAFF_PAGE_ONE);
    vi.spyOn(staffDirectoryClient, 'resetPagination').mockImplementation(() => undefined);
    vi.spyOn(staffPreferencesClient, 'queryDefinitions').mockResolvedValue(STAFF_PREFERENCE_DEFINITIONS);
    vi.spyOn(staffPreferencesClient, 'queryProfile').mockResolvedValue(STAFF_PREFERENCE_PROFILE);
    vi.spyOn(staffAvailabilityClient, 'getBlocks').mockResolvedValue([STAFF_AVAILABILITY_BLOCK]);
    vi.spyOn(staffLifecycleClient, 'query').mockResolvedValue(STAFF_LIFECYCLE_VIEW);
    vi.spyOn(staffQualificationMasterClient, 'query').mockResolvedValue(STAFF_QUALIFICATION_MASTER);
  });

  afterEach(() => vi.restoreAllMocks());

  it('keeps supported controls input-gated and omits unsupported fake mutations', async () => {
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    expect(document.querySelector('[data-control-id="staff.master.create"]')).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="staff.tab.roster"]')).toBeInTheDocument();
    expect(document.querySelector('[data-control-id="staff.tab.preferences"]')).toBeInTheDocument();
    expect(document.querySelector('[data-control-id="staff.tab.unavailability"]')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /配對偏好/ }));
    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });
    await waitFor(() => expect(screen.getByDisplayValue('20–30')).toBeInTheDocument());
    expect(screen.getByText(/目前為檢視模式/)).toBeInTheDocument();
    for (const id of ['staff.preferences.preview', 'staff.preferences.apply']) {
      expect(document.querySelector(`[data-control-id="${id}"]`)).toBeInTheDocument();
    }
    expect(document.querySelector('[data-control-id="staff.preferences.cooking-skills"]')).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="staff.preferences.special-notes"]')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /長假與暫停/ }));
    for (const id of ['staff.availability.create.preview', 'staff.availability.create.apply', 'staff.availability.cancel.apply', 'staff.availability.end-pause']) {
      expect(document.querySelector(`[data-control-id="${id}"]`)).toBeInTheDocument();
    }
    fireEvent.change(screen.getByLabelText('開始日期'), { target: { value: '2026-09-01' } });
    fireEvent.change(screen.getByLabelText('結束日期'), { target: { value: '2026-10-31' } });
    fireEvent.click(screen.getByRole('button', { name: '查詢不可服務期間' }));
    await waitFor(() => expect(document.querySelector('[data-control-id="staff.availability.cancel.preview"]')).toBeInTheDocument());
    expect(document.querySelector('[data-control-id="staff.availability.end-pause"]')).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: /服務月嫂名冊/ }));
    fireEvent.click(screen.getAllByRole('button', { name: /檢視服務人員摘要/ })[0]);
    fireEvent.click(screen.getByRole('tab', { name: /接案狀態管理/ }));
    await waitFor(() => expect(screen.getByText(/人事任職狀態與異動辦理/)).toBeInTheDocument());
    expect(screen.getByRole('tab', { name: /接案狀態管理/ })).toHaveAttribute('aria-selected', 'true');
    expect(document.querySelector('[data-control-id="staff.master.save"]')).not.toBeInTheDocument();
  });

  it('shows an explicit empty row and omits a meaningless cancel-preview button', async () => {
    vi.mocked(staffAvailabilityClient.getBlocks).mockResolvedValueOnce([]);
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /長假與暫停/ }));
    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });
    fireEvent.change(screen.getByLabelText('開始日期'), { target: { value: '2026-09-01' } });
    fireEvent.change(screen.getByLabelText('結束日期'), { target: { value: '2026-10-31' } });
    fireEvent.click(screen.getByRole('button', { name: '查詢不可服務期間' }));
    await waitFor(() => expect(screen.getByText('此範圍沒有不可服務紀錄。')).toBeInTheDocument());

    expect(screen.queryByRole('button', { name: '預覽取消' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '套用取消' })).toBeDisabled();
  });
});

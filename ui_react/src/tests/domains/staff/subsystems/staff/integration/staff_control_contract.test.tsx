/**
 * File: staff_control_contract.test.tsx
 * Description: 驗證 Staff 合法控制項的 server-gated enablement 並排除永久假按鈕。
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
import { STAFF_AVAILABILITY_BLOCK } from '../../../../../fixtures/staff/staff_availability_contract_fixtures';
import { STAFF_LIFECYCLE_VIEW } from '../../../../../fixtures/staff/staff_lifecycle_contract_fixtures';
import { STAFF_QUALIFICATION_MASTER } from '../../../../../fixtures/staff/staff_qualification_contract_fixtures';

const manualRelations = {
  service_regions: [{ value: '北區', detail: null }], service_periods: [], cooking_skills: [],
  holiday_availability: [], rest_schedule: [], baby_types: [],
};

const preferenceEditor = () => within(document.querySelector('[data-surface-id="staff.qualification.case-preference-manual"]') as HTMLElement);

describe('Staff control contract', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-08-20T10:00:00+08:00'));
    vi.spyOn(staffCasePreferenceManualClient, 'queryOptions').mockResolvedValue(STAFF_MANUAL_OPTIONS);
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({ ...STAFF_PAGE_ONE, next_cursor: null });
    vi.spyOn(staffDirectoryClient, 'resetPagination').mockImplementation(() => undefined);
    vi.spyOn(staffCasePreferenceManualClient, 'query').mockResolvedValue({
      staff_id: 11, before: manualRelations, after: manualRelations,
      snapshot_fingerprint: 'a'.repeat(64), preview_fingerprint: null,
    });
    vi.spyOn(staffAvailabilityClient, 'getAllBlocks').mockResolvedValue([STAFF_AVAILABILITY_BLOCK]);
    vi.spyOn(staffLifecycleClient, 'query').mockResolvedValue(STAFF_LIFECYCLE_VIEW);
    vi.spyOn(staffQualificationMasterClient, 'query').mockResolvedValue(STAFF_QUALIFICATION_MASTER);
  });

  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

  it('keeps supported controls input-gated and omits unsupported fake mutations', async () => {
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    expect(document.querySelector('[data-control-id="staff.master.create"]')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /查看 去敏人員甲 的詳情/ }));
    expect(await screen.findByRole('combobox', { name: '可承接區域值1' })).toBeEnabled();
    expect(preferenceEditor().getByRole('button', { name: '儲存服務偏好' })).toBeEnabled();
    expect(preferenceEditor().queryByRole('button', { name: '確認儲存' })).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="staff.preferences.cooking-skills"]')).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="staff.preferences.special-notes"]')).not.toBeInTheDocument();

    expect(screen.getByRole('button', { name: '新增' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: '新增' }));
    expect(document.querySelector('[data-control-id="staff.availability.create.preview"]')).toBeInTheDocument();
    for (const id of ['staff.availability.create.apply', 'staff.availability.cancel.apply', 'staff.availability.end-pause']) {
      expect(document.querySelector(`[data-control-id="${id}"]`)).not.toBeInTheDocument();
    }
    fireEvent.change(screen.getByLabelText('開始日期'), { target: { value: '2026-09-01' } });
    fireEvent.change(screen.getByLabelText('結束日期'), { target: { value: '2026-10-31' } });
    await waitFor(() => expect(document.querySelector('[data-control-id="staff.availability.cancel.preview"]')).toBeInTheDocument());
    expect(document.querySelector('[data-control-id="staff.availability.end-pause"]')).not.toBeInTheDocument();

    await waitFor(() => expect(screen.getByText(/人事任職狀態與異動辦理/)).toBeInTheDocument());
    expect(screen.getByRole('region', { name: '接案狀態管理' })).toBeInTheDocument();
    expect(document.querySelector('[data-control-id="staff.master.save"]')).not.toBeInTheDocument();
  });

  it('shows an explicit empty row and omits a meaningless cancel-preview button', async () => {
    vi.mocked(staffAvailabilityClient.getAllBlocks).mockResolvedValue([]);
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /查看 去敏人員甲 的詳情/ }));
    await waitFor(() => expect(within(screen.getByRole('region', { name: '接案狀態管理' })).getByText('無', { exact: true })).toBeInTheDocument());

    expect(screen.queryByRole('button', { name: '預覽取消' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '套用取消' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '取消此期間' })).not.toBeInTheDocument();
  });
});

/**
 * File: staff_case_preference_summary_flow.test.tsx
 * Description: 保留名冊唯讀摘要，驗證 Drawer 單一六母題編輯與 owner 回讀。
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { staffCasePreferenceSummaryClient } from '../../../../../../api/staff_case_preference_summary/staff_case_preference_summary_client';
import { staffDirectoryClient } from '../../../../../../api/staff_directory/staff_directory_client';
import { staffLifecycleClient } from '../../../../../../api/staff_lifecycle/staff_lifecycle_client';
import { staffQualificationMasterClient } from '../../../../../../api/staff/qualification_master_client';
import { staffCasePreferenceManualClient } from '../../../../../../api/staff_case_preferences/staff_case_preferences_client';
import type { StaffCasePreferenceManualSnapshot, StaffCasePreferenceRelations } from '../../../../../../api/staff_case_preferences/staff_case_preferences_schemas';
import { StaffCasePreferenceManualEditor, StaffPage } from '../../../../../../pages/StaffPage';
import { STAFF_CASE_PREFERENCE_SUMMARY } from '../../../../../fixtures/staff/staff_case_preference_summary_contract_fixtures';
import { STAFF_PAGE_ONE } from '../../../../../fixtures/staff/staff_directory_contract_fixtures';
import { STAFF_LIFECYCLE_VIEW } from '../../../../../fixtures/staff/staff_lifecycle_contract_fixtures';
import { STAFF_QUALIFICATION_MASTER } from '../../../../../fixtures/staff/staff_qualification_contract_fixtures';
import { STAFF_MANUAL_OPTIONS } from './fixtures/staff_manual_options';

const MANUAL_RELATIONS: StaffCasePreferenceRelations = {
  service_regions: [{ value: '北區', detail: '偏遠地區需先確認交通' }],
  service_periods: [],
  cooking_skills: [{ value: '家常菜', detail: null }],
  holiday_availability: [],
  rest_schedule: [],
  baby_types: [],
};
const MANUAL_SNAPSHOT: StaffCasePreferenceManualSnapshot = {
  staff_id: 11,
  before: MANUAL_RELATIONS,
  after: MANUAL_RELATIONS,
  snapshot_fingerprint: 'a'.repeat(64),
  preview_fingerprint: null,
};

describe('Staff case preference summary flow', () => {
  beforeEach(() => {
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({ ...STAFF_PAGE_ONE, next_cursor: null });
    vi.spyOn(staffDirectoryClient, 'resetPagination').mockImplementation(() => undefined);
    vi.spyOn(staffLifecycleClient, 'query').mockResolvedValue(STAFF_LIFECYCLE_VIEW);
    vi.spyOn(staffQualificationMasterClient, 'query').mockResolvedValue(STAFF_QUALIFICATION_MASTER);
    vi.spyOn(staffCasePreferenceSummaryClient, 'query').mockResolvedValue(STAFF_CASE_PREFERENCE_SUMMARY);
    vi.spyOn(staffCasePreferenceManualClient, 'query').mockResolvedValue(MANUAL_SNAPSHOT);
    vi.spyOn(staffCasePreferenceManualClient, 'queryOptions').mockResolvedValue(STAFF_MANUAL_OPTIONS);
    vi.spyOn(staffCasePreferenceManualClient, 'preview').mockImplementation(async (staffId, relations) => ({
      ...MANUAL_SNAPSHOT, staff_id: staffId, after: relations, preview_fingerprint: 'b'.repeat(64),
    }));
    vi.spyOn(staffCasePreferenceManualClient, 'apply').mockResolvedValue({
      staff_id: 11, relations: MANUAL_RELATIONS, snapshot_fingerprint: 'c'.repeat(64),
      preview_fingerprint: 'b'.repeat(64), idempotency_key: 'synthetic-staff-preference-apply', replayed: false,
    });
  });

  afterEach(() => vi.restoreAllMocks());

  it('keeps imported service information inside professional data and only two preferences in the drawer', async () => {
    render(<StaffPage />);
    await screen.findByText('去敏人員甲');
    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });
    const card = document.querySelector('[data-control-id="staff.row.11"]') as HTMLElement;
    fireEvent.click(within(card).getByRole('button', { name: /查看 .* 的詳情/ }));
    const area = document.querySelector('[data-surface-id="staff.qualification.preferences"]') as HTMLElement;
    await within(area).findByLabelText('可承接區域值1');
    const information = within(area).getByRole('region', { name: '匯入服務資訊' });
    expect(information.closest('[aria-label="專業資格與服務資料編輯"]')).not.toBeNull();
    expect(within(information).getByText('家常菜')).toBeInTheDocument();
    const preferences = within(within(area).getByRole('region', { name: '服務偏好' }));
    expect(preferences.getAllByRole('group')).toHaveLength(2);
    expect(preferences.queryByText('下廚能力')).not.toBeInTheDocument();
    expect(preferences.getByRole('button', { name: '儲存服務偏好' })).toBeEnabled();
    expect(staffCasePreferenceSummaryClient.query).not.toHaveBeenCalled();
  });

  it('shows an owner read failure without reporting success', async () => {
    vi.mocked(staffCasePreferenceManualClient.query).mockRejectedValueOnce(new Error('偏好讀取失敗'));
    render(<StaffCasePreferenceManualEditor staffId={11} directEditing />);
    expect(await screen.findByText('偏好讀取失敗')).toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(staffCasePreferenceManualClient.apply).not.toHaveBeenCalled();
  });

  it('saves two preferences through owner preview/apply and displays the fresh owner readback', async () => {
    const changed = { ...MANUAL_RELATIONS, service_regions: [{ value: '東區', detail: null }] };
    vi.mocked(staffCasePreferenceManualClient.query).mockResolvedValueOnce(MANUAL_SNAPSHOT).mockResolvedValue({ ...MANUAL_SNAPSHOT, after: changed });
    render(<StaffCasePreferenceManualEditor staffId={11} />);
    fireEvent.click(await screen.findByRole('button', { name: '編輯服務偏好' }));
    fireEvent.change(screen.getByLabelText('可承接區域值1'), { target: { value: '東區' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存服務偏好' }));
    await screen.findByText('已儲存並重新查詢服務偏好。');
    expect(staffCasePreferenceManualClient.preview).toHaveBeenCalledWith(11, changed, expect.anything());
    expect(staffCasePreferenceManualClient.apply).toHaveBeenCalledWith(11, expect.objectContaining(changed), expect.anything());
    expect(screen.getByRole('group', { name: '可承接區域' })).toHaveTextContent('東區');
    expect(screen.getByRole('region', { name: '匯入服務資訊' })).toHaveTextContent('家常菜');
  });

  it('obtains a new owner preview for each changed save', async () => {
    render(<StaffCasePreferenceManualEditor staffId={11} directEditing />);
    await screen.findByLabelText('可承接區域值1');
    fireEvent.click(screen.getByRole('button', { name: '儲存服務偏好' }));
    await screen.findByText('已儲存並重新查詢服務偏好。');
    fireEvent.change(screen.getByLabelText('可承接區域值1'), { target: { value: '東區' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存服務偏好' }));
    await waitFor(() => expect(staffCasePreferenceManualClient.apply).toHaveBeenCalledTimes(2));
    expect(staffCasePreferenceManualClient.preview).toHaveBeenCalledTimes(2);
    expect(staffCasePreferenceManualClient.preview).toHaveBeenLastCalledWith(11, expect.objectContaining({ service_regions: [{ value: '東區', detail: null }] }), expect.anything());
  });

  it('does not report success when the post-apply owner query fails', async () => {
    vi.mocked(staffCasePreferenceManualClient.query).mockResolvedValueOnce(MANUAL_SNAPSHOT).mockRejectedValueOnce(new Error('重新查詢失敗'));
    render(<StaffCasePreferenceManualEditor staffId={11} directEditing />);
    await screen.findByLabelText('可承接區域值1');
    fireEvent.click(screen.getByRole('button', { name: '儲存服務偏好' }));
    await screen.findByText('重新查詢失敗');
    expect(staffCasePreferenceManualClient.apply).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('已儲存並重新查詢服務偏好。')).not.toBeInTheDocument();
  });
});

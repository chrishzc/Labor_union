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

  it('preserves the roster summary and renders only the current six-topic editor in the Drawer', async () => {
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });
    const card = document.querySelector('[data-control-id="staff.row.11"]');
    expect(card).not.toBeNull();
    const cardView = within(card as HTMLElement);

    expect(cardView.getByRole('cell', { name: '去敏人員甲' })).toBeInTheDocument();
    expect(cardView.queryByRole('group')).not.toBeInTheDocument();

    fireEvent.click(cardView.getByRole('button', { name: /查看 .* 的詳情/ }));
    const drawer = document.querySelector('[data-surface-id="staff.qualification.preferences"]');
    expect(drawer).not.toBeNull();
    const drawerView = within(drawer as HTMLElement);
    await drawerView.findByRole('combobox', { name: '可承接區域值1' });

    expect(drawer?.querySelector('[data-surface-id="staff.drawer.case-preference-summary"]')).toBeNull();
    expect(drawer?.querySelectorAll('[data-surface-id="staff.qualification.case-preference-manual"]')).toHaveLength(1);
    expect(drawerView.getByRole('group', { name: '可承接區域' })).toHaveTextContent('偏遠地區需先確認交通');
    expect(drawerView.getByRole('group', { name: '下廚能力' })).toHaveTextContent('家常菜');
    expect(drawerView.queryByRole('group', { name: '交通方式' })).not.toBeInTheDocument();
    const manualView = within(drawer!.querySelector('[data-surface-id="staff.qualification.case-preference-manual"]') as HTMLElement);
    expect(manualView.getAllByRole('group')).toHaveLength(6);
    expect(drawerView.getByRole('button', { name: '預覽變更' })).toBeEnabled();
    expect(drawerView.getByRole('button', { name: '確認儲存' })).toBeDisabled();
    expect(screen.queryByText('查看接案偏好摘要')).not.toBeInTheDocument();
    expect(staffCasePreferenceSummaryClient.query).not.toHaveBeenCalled();
  });

  it('keeps the Staff row visible and shows the case-preference read failure in details', async () => {
    vi.mocked(staffCasePreferenceManualClient.query).mockRejectedValue(new Error('接案條件暫時不可讀'));
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });

    expect(screen.getByText('去敏人員甲')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '查看 去敏人員甲 的詳情' }));
    expect(await screen.findByText('接案條件暫時不可讀')).toBeInTheDocument();
    expect(within(screen.getByRole('table', { name: '月嫂名冊清單' })).getByText('去敏人員甲')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '🏖️ 接案狀態管理' })).toBeInTheDocument();
  });

  it('edits the same six cards, confirms a preview, and displays owner readback after saving', async () => {
    render(<StaffCasePreferenceManualEditor staffId={11} />);
    fireEvent.click(await screen.findByRole('button', { name: '編輯六項偏好' }));
    fireEvent.change(screen.getByLabelText('可承接區域值1'), { target: { value: '新竹縣' } });
    const confirm = screen.getByRole('button', { name: '確認儲存' });
    expect(confirm).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '預覽變更' }));
    await screen.findByText('預覽已完成，尚未寫入。');

    expect(confirm).toBeEnabled();
    expect(staffCasePreferenceManualClient.apply).not.toHaveBeenCalled();
    expect(screen.getByTestId('staff-case-preference-manual-preview')).toHaveTextContent('可承接區域（變更前）');
    expect(screen.getByTestId('staff-case-preference-manual-preview')).toHaveTextContent('可承接區域（變更後）');
    fireEvent.change(screen.getByLabelText('接案條件備註（選填）'), { target: { value: '測試六項編輯' } });
    expect(confirm).toBeEnabled();

    const savedRelations = {
      ...MANUAL_RELATIONS, service_regions: [{ value: '新竹縣', detail: null }],
    };
    vi.mocked(staffCasePreferenceManualClient.query).mockResolvedValueOnce({
      ...MANUAL_SNAPSHOT, before: savedRelations, after: savedRelations, snapshot_fingerprint: 'c'.repeat(64),
    });
    fireEvent.click(confirm);

    expect(await screen.findByText('已儲存並重新查詢六大接案能力。')).toBeInTheDocument();
    expect(staffCasePreferenceManualClient.apply).toHaveBeenCalledWith(11, {
      ...savedRelations, expected_snapshot_fingerprint: 'a'.repeat(64),
      preview_fingerprint: 'b'.repeat(64), reason: '測試六項編輯',
    }, expect.objectContaining({ idempotencyKey: expect.any(String), signal: expect.any(AbortSignal) }));
    expect(staffCasePreferenceManualClient.query).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('group', { name: '可承接區域' })).toHaveTextContent('新竹縣');
    expect(screen.getAllByRole('group')).toHaveLength(6);
    expect(screen.getByRole('button', { name: '編輯六項偏好' })).toBeInTheDocument();
    expect(screen.queryByLabelText('可承接區域值1')).not.toBeInTheDocument();
  });

  it('requires a new preview after changing a previewed field', async () => {
    render(<StaffCasePreferenceManualEditor staffId={11} />);
    fireEvent.click(await screen.findByRole('button', { name: '編輯六項偏好' }));
    fireEvent.change(screen.getByLabelText('接案條件備註（選填）'), { target: { value: '測試預覽失效' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽變更' }));
    await screen.findByText('預覽已完成，尚未寫入。');
    expect(await screen.findByRole('button', { name: '確認儲存' })).toBeEnabled();

    fireEvent.change(screen.getByLabelText('可承接區域值1'), { target: { value: '東區' } });
    expect(screen.getByRole('button', { name: '確認儲存' })).toBeDisabled();
    expect(screen.queryByTestId('staff-case-preference-manual-preview')).not.toBeInTheDocument();
    expect(staffCasePreferenceManualClient.apply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '預覽變更' }));
    await screen.findByText('預覽已完成，尚未寫入。');
    expect(await screen.findByRole('button', { name: '確認儲存' })).toBeEnabled();
    expect(staffCasePreferenceManualClient.preview).toHaveBeenLastCalledWith(
      11,
      { ...MANUAL_RELATIONS, service_regions: [{ value: '東區', detail: null }] },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it('does not report success when the post-apply owner query fails', async () => {
    render(<StaffCasePreferenceManualEditor staffId={11} />);
    fireEvent.click(await screen.findByRole('button', { name: '編輯六項偏好' }));
    fireEvent.change(screen.getByLabelText('接案條件備註（選填）'), { target: { value: '測試回讀失敗' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽變更' }));
    await screen.findByText('預覽已完成，尚未寫入。');
    const confirm = await screen.findByRole('button', { name: '確認儲存' });
    vi.mocked(staffCasePreferenceManualClient.query).mockRejectedValueOnce(new Error('回讀暫時失敗'));
    fireEvent.click(confirm);

    expect(await screen.findByText('回讀暫時失敗')).toBeInTheDocument();
    expect(screen.queryByText('已儲存並重新查詢六大接案能力。')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新查詢' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '確認儲存' })).not.toBeInTheDocument();
    expect(staffCasePreferenceManualClient.apply).toHaveBeenCalledTimes(1);
    expect(staffCasePreferenceManualClient.query).toHaveBeenCalledTimes(2);
  });
});

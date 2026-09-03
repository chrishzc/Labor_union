/**
 * File: staff_case_preference_summary_flow.test.tsx
 * Description: 驗證 canonical 接案偏好摘要在名冊 card / Drawer 的 bounded rendering 與失敗隔離。
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { staffCasePreferenceSummaryClient } from '../api/staff_case_preference_summary/staff_case_preference_summary_client';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { staffLifecycleClient } from '../api/staff_lifecycle/staff_lifecycle_client';
import { staffQualificationMasterClient } from '../api/staff/qualification_master_client';
import { StaffPage } from '../pages/StaffPage';
import { STAFF_CASE_PREFERENCE_SUMMARY } from './fixtures/staff/staff_case_preference_summary_contract_fixtures';
import { STAFF_PAGE_ONE } from './fixtures/staff/staff_directory_contract_fixtures';
import { STAFF_LIFECYCLE_VIEW } from './fixtures/staff/staff_lifecycle_contract_fixtures';
import { STAFF_QUALIFICATION_MASTER } from './fixtures/staff/staff_qualification_contract_fixtures';

describe('Staff case preference summary flow', () => {
  beforeEach(() => {
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue(STAFF_PAGE_ONE);
    vi.spyOn(staffDirectoryClient, 'resetPagination').mockImplementation(() => undefined);
    vi.spyOn(staffLifecycleClient, 'query').mockResolvedValue(STAFF_LIFECYCLE_VIEW);
    vi.spyOn(staffQualificationMasterClient, 'query').mockResolvedValue(STAFF_QUALIFICATION_MASTER);
    vi.spyOn(staffCasePreferenceSummaryClient, 'query').mockResolvedValue(STAFF_CASE_PREFERENCE_SUMMARY);
  });

  afterEach(() => vi.restoreAllMocks());

  it('renders all six topics on the selected roster card and full detail in the Drawer', async () => {
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });
    const card = document.querySelector('[data-control-id="staff.card.11"]');
    expect(card).not.toBeNull();
    const cardView = within(card as HTMLElement);

    await waitFor(() => expect(cardView.getByRole('group', { name: '希望服務地區' })).toHaveTextContent('北區、新竹縣'));
    expect(cardView.getByRole('group', { name: '希望服務地區' })).toHaveTextContent('其它：偏遠地區需先確認交通');
    expect(cardView.getByRole('group', { name: '服務時段' })).toHaveTextContent('尚未登錄');
    expect(cardView.getByRole('group', { name: '交通方式' })).toHaveTextContent('機車');
    expect(cardView.getByRole('group', { name: '交通方式' })).not.toHaveTextContent('其它來源尚未就緒');
    expect(cardView.getAllByRole('group')).toHaveLength(6);

    fireEvent.click(cardView.getByRole('button', { name: /檢視服務人員摘要/ }));
    fireEvent.click(screen.getByRole('tab', { name: /接案偏好設定/ }));
    const drawerSummary = document.querySelector('[data-surface-id="staff.drawer.case-preference-summary"]');
    expect(drawerSummary).not.toBeNull();
    const drawerView = within(drawerSummary as HTMLElement);

    expect(drawerView.getByRole('group', { name: '希望服務地區' })).toHaveTextContent('其它：偏遠地區需先確認交通');
    expect(drawerView.getByRole('group', { name: '服務時段' })).toHaveTextContent('尚未登錄');
    expect(drawerView.getByRole('group', { name: '交通方式' })).toHaveTextContent('其它來源尚未就緒');
    expect(drawerView.getAllByRole('group')).toHaveLength(6);
    expect(staffCasePreferenceSummaryClient.query).toHaveBeenCalledWith(
      11,
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it('keeps the Staff card visible when the case-preference read fails', async () => {
    vi.mocked(staffCasePreferenceSummaryClient.query).mockRejectedValueOnce(new Error('摘要暫時不可讀'));
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });

    expect(await screen.findByText('🎯 接案偏好目前無法讀取')).toBeInTheDocument();
    expect(screen.getByText('去敏人員甲')).toBeInTheDocument();
  });
});

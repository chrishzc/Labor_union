/** Verify the selected Staff drawer renders the bounded authenticated profile. */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { staffDirectoryClient } from '../../../../../../../api/staff_directory/staff_directory_client';
import { staffLifecycleClient } from '../../../../../../../api/staff_lifecycle/staff_lifecycle_client';
import { staffProfileClient } from '../../../../../../../api/staff_profile/staff_profile_client';
import { staffResumeClient } from '../../../../../../../api/staff_profile/staff_resume_client';
import { staffQualificationMasterClient } from '../../../../../../../api/staff/qualification_master_client';
import { staffCasePreferenceManualClient } from '../../../../../../../api/staff_case_preferences/staff_case_preferences_client';
import { STAFF_MANUAL_OPTIONS } from '../../integration/fixtures/staff_manual_options';
import { StaffPage } from '../../../../../../../pages/StaffPage';
import { STAFF_PAGE_ONE } from '../../../../../../fixtures/staff/staff_directory_contract_fixtures';
import { STAFF_LIFECYCLE_VIEW } from '../../../../../../fixtures/staff/staff_lifecycle_contract_fixtures';
import { STAFF_PROFILE } from './fixtures/staff_profile_contract_fixtures';
import { STAFF_QUALIFICATION_MASTER } from '../../../../../../fixtures/staff/staff_qualification_contract_fixtures';

describe('Staff roster profile flow', () => {
  beforeEach(() => {
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue(STAFF_PAGE_ONE);
    vi.spyOn(staffDirectoryClient, 'resetPagination').mockImplementation(() => undefined);
    vi.spyOn(staffLifecycleClient, 'query').mockResolvedValue(STAFF_LIFECYCLE_VIEW);
    vi.spyOn(staffProfileClient, 'query').mockResolvedValue(STAFF_PROFILE);
    vi.spyOn(staffResumeClient, 'current').mockResolvedValue(null);
    const relations = {
      service_regions: [{ value: '北區', detail: 'T01 six region final' }],
      service_periods: [], cooking_skills: [], holiday_availability: [], rest_schedule: [], baby_types: [],
    };
    vi.spyOn(staffCasePreferenceManualClient, 'query').mockResolvedValue({ staff_id: 11, before: relations, after: relations, snapshot_fingerprint: 'a'.repeat(64), preview_fingerprint: null });
    vi.spyOn(staffCasePreferenceManualClient, 'queryOptions').mockResolvedValue(STAFF_MANUAL_OPTIONS);
    vi.spyOn(staffQualificationMasterClient, 'query').mockResolvedValue({
      ...STAFF_QUALIFICATION_MASTER,
      service_profile: {
        ...STAFF_QUALIFICATION_MASTER.service_profile,
        service_regions: [{ value: '北區', detail: 'T01 six region final' }],
      },
      sections: STAFF_QUALIFICATION_MASTER.sections.map((section) => (
        section.kind === 'certifications'
          ? {
              ...section,
              availability: 'available',
              items: [{
                code: 'certification_1', value: '托育人員證照', detail: null,
                source_identity: 'staff_certifications:11:1', source_version: null,
                valid_from: null, valid_until: null, availability: 'available',
                availability_reason: 'staff_certification_record',
              }],
            }
          : section.kind === 'cooking'
            ? {
                ...section,
                items: section.items.map((item, index) => index === 0
                  ? { ...item, detail: 'T01 six cooking final' }
                  : item),
              }
          : section
      )),
    });
  });

  it('shows the search result count and restores the loaded count after clearing an empty search', async () => {
    vi.mocked(staffDirectoryClient.queryPage).mockResolvedValue({ ...STAFF_PAGE_ONE, next_cursor: null });
    render(<StaffPage />);
    await screen.findByText('去敏人員甲');
    const initialCount = document.querySelector('.staff-directory-count')?.textContent;
    expect(document.querySelector('.staff-quick-query')).not.toHaveAttribute('open');
    fireEvent.change(screen.getByLabelText('即時搜尋月嫂'), { target: { value: '沒有符合的人員' } });
    await screen.findByText('搜尋結果 0 位服務人員');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '✕ 清除搜尋' }));
    expect(document.querySelector('.staff-directory-count')?.textContent).toBe(initialCount);
    expect(screen.getByText('去敏人員甲')).toBeInTheDocument();
    expect(staffProfileClient.query).not.toHaveBeenCalled();
  });

  it('shows complete identity, contact facts, bank accounts, and canonical certifications', async () => {
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    expect(screen.queryByRole('tablist', { name: '服務人員管理分頁' })).not.toBeInTheDocument();
    expect(screen.queryByTestId('staff-profile-detail')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '查看 去敏人員甲 的詳情' }));

    expect(screen.queryByRole('tab', { name: '🎯 接案偏好設定' })).not.toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: '✏️ 個資與履歷管理' })).not.toBeInTheDocument();
    expect(screen.queryByRole('tablist', { name: '月嫂個人檔案分頁' })).not.toBeInTheDocument();
    const masterSection = screen.getByRole('region', { name: '完整資格主檔' });
    const statusSection = screen.getByRole('region', { name: '接案狀態管理' });
    expect(masterSection.compareDocumentPosition(statusSection) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(statusSection).getByRole('heading', { name: '🏖️ 接案狀態管理' })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: '月嫂履歷 PDF' })).toBeInTheDocument();
    const resumeSection = screen.getByRole('region', { name: '月嫂履歷 PDF' });
    expect(statusSection.compareDocumentPosition(resumeSection) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(resumeSection).toBe(document.querySelector('.staff-drawer-content')?.lastElementChild);
    expect(within(masterSection).queryByRole('heading', { name: '月嫂履歷 PDF' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('選擇 PDF')).toBeEnabled();
    expect(staffResumeClient.current).toHaveBeenCalledExactlyOnceWith(11);

    const profile = await screen.findByTestId('staff-profile-detail');
    expect(within(profile).getByRole('textbox', { name: '身分證' })).toHaveValue('A123456789');
    expect(screen.queryByText('查看已儲存個資摘要')).not.toBeInTheDocument();
    expect(within(profile).getByRole('textbox', { name: '生日' })).toHaveValue('1980-01-02');
    expect(within(profile).getByRole('textbox', { name: 'Email' })).toHaveValue('staff@example.test');
    expect(within(profile).getByRole('textbox', { name: '縣市' })).toHaveValue('新竹市');
    expect(within(profile).getByRole('textbox', { name: '郵遞區號' })).toHaveValue('300');
    expect(within(profile).getByRole('textbox', { name: '地址' })).toHaveValue('北區測試路 1 號');
    expect(within(profile).getByRole('textbox', { name: '緊急聯絡人' })).toHaveValue('王家人');
    expect(within(profile).getByRole('textbox', { name: '緊急聯絡電話' })).toHaveValue('0987654321');
    expect(within(profile).getByText('登錄日期：2025-05-06')).toBeInTheDocument();
    expect(within(profile).getByRole('list', { name: '銀行帳戶' })).toHaveTextContent('主要帳戶｜有效｜812／0012｜帳號末四碼 9012');
    expect(within(profile).getByRole('list', { name: '銀行帳戶' })).toHaveTextContent('備用帳戶｜已停用｜004／0001｜帳號末四碼 1098');
    expect(profile).not.toHaveTextContent('123456789012');
    expect(profile).not.toHaveTextContent('987654321098');
    expect(await screen.findByRole('combobox', { name: '可承接區域值1' })).toHaveValue('北區');
    expect(screen.getByText('來源資料：T01 six region final')).toBeInTheDocument();
    expect(within(screen.getByRole('table', { name: '月嫂名冊清單' })).getByText(/T01 six region final/)).toBeInTheDocument();
    expect(screen.getByRole('group', { name: '證照' })).toHaveTextContent('資格證明：托育人員證照');

  });
});

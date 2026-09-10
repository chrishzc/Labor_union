/** Verify the selected Staff drawer renders the bounded authenticated profile. */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { staffDirectoryClient } from '../../../../../../../api/staff_directory/staff_directory_client';
import { staffLifecycleClient } from '../../../../../../../api/staff_lifecycle/staff_lifecycle_client';
import { staffProfileClient } from '../../../../../../../api/staff_profile/staff_profile_client';
import { staffQualificationMasterClient } from '../../../../../../../api/staff/qualification_master_client';
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

  it('shows complete identity, contact facts, bank accounts, and canonical certifications', async () => {
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    expect(screen.queryByRole('tablist', { name: '服務人員管理分頁' })).not.toBeInTheDocument();
    expect(screen.queryByTestId('staff-profile-detail')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '查看 去敏人員甲 的詳情' }));

    const profile = await screen.findByTestId('staff-profile-detail');
    expect(within(profile).getByRole('group', { name: '身分證' })).toHaveTextContent('A123456789');
    expect(within(profile).getByRole('group', { name: '生日' })).toHaveTextContent('1980-01-02');
    expect(within(profile).getByRole('group', { name: 'Email' })).toHaveTextContent('staff@example.test');
    expect(within(profile).getByRole('group', { name: '居住地址' })).toHaveTextContent('300 新竹市 北區測試路 1 號');
    expect(within(profile).getByRole('group', { name: '緊急聯絡人' })).toHaveTextContent('王家人／0987654321');
    expect(within(profile).getByRole('list', { name: '銀行帳戶' })).toHaveTextContent('主要帳戶｜812／0012｜123456789012');
    expect(within(profile).getByRole('list', { name: '銀行帳戶' })).toHaveTextContent('備用帳戶｜004／0001｜987654321098');
    expect(screen.getByRole('group', { name: '可承接區域' })).toHaveTextContent('北區');
    // Canonical relation details remain available in the detail drawer, not roster cards.
    expect(screen.getByRole('group', { name: '可承接區域' })).toHaveTextContent('T01 six region final');
    expect(within(screen.getAllByRole('article')[0]).queryByText(/T01 six/)).not.toBeInTheDocument();
    expect(screen.getByRole('group', { name: '證照' })).toHaveTextContent('資格證明：托育人員證照');

  });
});

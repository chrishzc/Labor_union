/**
 * File: staff_page_real_data.test.tsx
 * Description: 驗證 StaffPage bounded clients、資格六區段與 Asia/Taipei 查詢日期邊界。
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { staffLifecycleClient } from '../api/staff_lifecycle/staff_lifecycle_client';
import { staffQualificationMasterClient } from '../api/staff/qualification_master_client';
import { StaffPage } from '../pages/StaffPage';
import { STAFF_PAGE_ONE } from './fixtures/staff/staff_directory_contract_fixtures';
import { STAFF_LIFECYCLE_VIEW } from './fixtures/staff/staff_lifecycle_contract_fixtures';
import { STAFF_QUALIFICATION_MASTER } from './fixtures/staff/staff_qualification_contract_fixtures';

describe('StaffPage real data boundary', () => {
  beforeEach(() => {
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue(STAFF_PAGE_ONE);
    vi.spyOn(staffDirectoryClient, 'resetPagination').mockImplementation(() => undefined);
    vi.spyOn(staffLifecycleClient, 'query').mockResolvedValue(STAFF_LIFECYCLE_VIEW);
    vi.spyOn(staffQualificationMasterClient, 'query').mockResolvedValue(STAFF_QUALIFICATION_MASTER);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('renders server summary and lifecycle values through bounded clients', async () => {
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });
    await waitFor(() => expect(screen.getAllByText('在職').length).toBeGreaterThan(0));
    expect(screen.getByText('📞 09******** ｜ 學歷：大學')).toBeInTheDocument();
    expect(screen.queryByText(/未開放|後端.*提供|unavailable|資料待補/)).not.toBeInTheDocument();
  });

  it('does not contain page-local mock facts, direct fetch, dialogs, or Date.now identities', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/pages/StaffPage.tsx'), 'utf8');
    expect(source).not.toContain('mockData');
    expect(source).not.toContain('MOCK_STAFF');
    expect(source).not.toContain('fetch(');
    expect(source).not.toContain('alert(');
    expect(source).not.toContain('confirm(');
    expect(source).not.toContain('Date.now');
  });

  it('queries qualification with the Asia/Taipei date at a UTC day boundary', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date('2026-08-22T16:30:00Z'));
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });
    await waitFor(() => expect(staffQualificationMasterClient.query).toHaveBeenCalled());
    expect(staffQualificationMasterClient.query).toHaveBeenCalledWith(
      11,
      '2026-08-23',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it('keeps all six qualification sections visible when their item lists are empty', async () => {
    vi.mocked(staffQualificationMasterClient.query).mockResolvedValue(STAFF_QUALIFICATION_MASTER);
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });

    for (const label of ['技能', '料理能力', '證照', '醫療／體檢', '資格有效期', '不可服務期間']) {
      await waitFor(() => expect(screen.getByRole('group', { name: label })).toBeInTheDocument());
    }
    expect(screen.getAllByText('尚未登錄。')).toHaveLength(6);
  });

  it('shows BeClass-adopted service capability facts in the selected staff drawer', async () => {
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole('button', { name: /檢視服務人員摘要/ })[0]);

    expect(await screen.findByRole('group', { name: '最多照顧寶寶數' })).toHaveTextContent('2 位');
    expect(screen.getByRole('group', { name: '可承接區域' })).toHaveTextContent('北區、其他（新竹市）');
    expect(screen.getByRole('group', { name: '可承接時段' })).toHaveTextContent('8小時');
    expect(screen.getByRole('group', { name: '交通方式' })).toHaveTextContent('機車');
    expect(screen.getByRole('group', { name: '週間服務／排休' })).toHaveTextContent('週休1日');
    expect(screen.getByRole('group', { name: '特殊節日意願' })).toHaveTextContent('中秋節');
    expect(screen.getByRole('group', { name: '可承接胎數' })).toHaveTextContent('單胞胎、雙胞胎');
    expect(screen.queryByText(/source_identity|fingerprint|preview_fingerprint/)).not.toBeInTheDocument();
    expect(screen.queryByText(/cooking_skill_|massage_certificate|special_skill_/)).not.toBeInTheDocument();
  });

  it('renders qualification facts with business labels instead of internal field codes', async () => {
    vi.mocked(staffQualificationMasterClient.query).mockResolvedValue({
      ...STAFF_QUALIFICATION_MASTER,
      sections: STAFF_QUALIFICATION_MASTER.sections.map((section) => {
        if (section.kind === 'cooking') {
          return {
            ...section,
            availability: 'available',
            source_identity: 'wp85-internal-test-identity',
            items: [{
              code: 'cooking_skill_1', value: '素食', detail: null,
              source_identity: 'staff_cooking_skills:11:1', source_version: null,
              valid_from: null, valid_until: null, availability: 'available',
              availability_reason: 'staff_cooking_skill_record',
            }],
          };
        }
        if (section.kind === 'certifications') {
          return {
            ...section,
            availability: 'available',
            items: [{
              code: 'massage_certificate', value: true, detail: null,
              source_identity: 'staff:11:has_massage_cert', source_version: null,
              valid_from: null, valid_until: null, availability: 'available',
              availability_reason: 'legacy_massage_certificate_ready',
            }],
          };
        }
        return section;
      }),
    });
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole('button', { name: /檢視服務人員摘要/ })[0]);

    expect(await screen.findByRole('group', { name: '料理能力' })).toHaveTextContent('料理類型：素食');
    expect(screen.getByRole('group', { name: '證照' })).toHaveTextContent('寶寶按摩證照：是');
    expect(screen.queryByText(/cooking_skill_1|massage_certificate/)).not.toBeInTheDocument();
    expect(screen.queryByText(/wp85|測試資料污染/i)).not.toBeInTheDocument();
  });

  it('offers a direct qualification retry after a query error', async () => {
    vi.mocked(staffQualificationMasterClient.query)
      .mockRejectedValueOnce(new Error('資格暫時失敗'))
      .mockResolvedValueOnce(STAFF_QUALIFICATION_MASTER);
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });

    fireEvent.click(await screen.findByRole('button', { name: '重試資格主檔' }));
    await waitFor(() => expect(screen.getByText(/整體狀態/)).toBeInTheDocument());
    expect(staffQualificationMasterClient.query).toHaveBeenCalledTimes(2);
  });

  it('offers a direct lifecycle retry inside the identity-bound drawer', async () => {
    vi.mocked(staffLifecycleClient.query)
      .mockRejectedValueOnce(new Error('Lifecycle 暫時失敗'))
      .mockResolvedValueOnce(STAFF_LIFECYCLE_VIEW);
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole('button', { name: /檢視服務人員摘要/ })[0]);
    fireEvent.click(screen.getByRole('tab', { name: /接案狀態管理/ }));

    fireEvent.click(await screen.findByRole('button', { name: '重試任職狀態' }));
    await waitFor(() => expect(screen.getAllByText('在職').length).toBeGreaterThan(0));
    expect(staffLifecycleClient.query).toHaveBeenCalledTimes(2);
  });
});

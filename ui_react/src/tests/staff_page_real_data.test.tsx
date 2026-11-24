/**
 * File: staff_page_real_data.test.tsx
 * Description: 驗證 StaffPage 名冊與兩欄編輯的獨立載入，以及 Asia/Taipei 查詢日期邊界。
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { staffLifecycleClient } from '../api/staff_lifecycle/staff_lifecycle_client';
import { staffQualificationMasterClient } from '../api/staff/qualification_master_client';
import { staffQualificationEditingClient } from '../api/staff/qualification_editing_client';
import { StaffPage } from '../pages/StaffPage';
import { STAFF_PAGE_ONE } from './fixtures/staff/staff_directory_contract_fixtures';
import { STAFF_LIFECYCLE_VIEW } from './fixtures/staff/staff_lifecycle_contract_fixtures';
import { STAFF_QUALIFICATION_MASTER } from './fixtures/staff/staff_qualification_contract_fixtures';

describe('StaffPage real data boundary', () => {
  beforeEach(() => {
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({ ...STAFF_PAGE_ONE, next_cursor: null });
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
    fireEvent.click(screen.getByRole('button', { name: /查看 去敏人員甲 的詳情/ }));
    await waitFor(() => expect(screen.getAllByText(/正常在職中/).length).toBeGreaterThan(0));
    const roster = within(screen.getByRole('table', { name: '月嫂名冊清單' }));
    expect(roster.getByRole('cell', { name: '09********' })).toBeInTheDocument();
    expect(roster.getByRole('cell', { name: '大學' })).toBeInTheDocument();
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
    fireEvent.click(screen.getByRole('row', { name: '開啟 去敏人員甲 的詳情' }));
    await waitFor(() => expect(staffQualificationMasterClient.query).toHaveBeenCalled());
    expect(staffQualificationMasterClient.query).toHaveBeenCalledWith(
      11,
      '2026-08-23',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it('shows BeClass-adopted service capability facts in the roster', async () => {
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole('button', { name: /查看 .* 的詳情/ })[0]);

    const roster = within(screen.getByRole('table', { name: '月嫂名冊清單' }));
    expect(await roster.findByRole('cell', { name: '2 位' })).toBeInTheDocument();
    for (const value of ['北區、其他（新竹市）', '8小時', '機車', '週休1日', '中秋節', '單胞胎、雙胞胎']) {
      expect(roster.getByRole('cell', { name: value })).toBeInTheDocument();
    }
    expect(screen.queryByText(/source_identity|fingerprint|preview_fingerprint/)).not.toBeInTheDocument();
    expect(screen.queryByText(/cooking_skill_|massage_certificate|special_skill_/)).not.toBeInTheDocument();
  });

  it('keeps canonical cooking information in the roster and hides the qualification summary', async () => {
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
    fireEvent.click(screen.getAllByRole('button', { name: /查看 .* 的詳情/ })[0]);

    const roster = within(screen.getByRole('table', { name: '月嫂名冊清單' }));
    expect(await roster.findByRole('cell', { name: '素食' })).toBeInTheDocument();
    const drawer = within(screen.getByRole('region', { name: '完整資格主檔' }));
    expect(drawer.queryByRole('heading', { name: /資格狀態與來源摘要/ })).not.toBeInTheDocument();
    expect(drawer.queryByRole('group', { name: '證照' })).not.toBeInTheDocument();
    expect(drawer.queryByText('寶寶按摩證照')).not.toBeInTheDocument();
    expect(screen.queryByText(/cooking_skill_1|massage_certificate/)).not.toBeInTheDocument();
    expect(screen.queryByText(/wp85|測試資料污染/i)).not.toBeInTheDocument();
  });

  it('loads the two-field editor even when the roster qualification lookup fails', async () => {
    vi.mocked(staffQualificationMasterClient.query).mockRejectedValueOnce(new Error('名冊資格暫時失敗'));
    const facts = {
      special_skills: ['哺乳協助'], certifications: ['托育證照'], transportation: ['公車'],
      has_massage_cert: true, care_babies: 2,
    };
    vi.spyOn(staffQualificationEditingClient, 'query').mockResolvedValue({
      staff_id: 11, before: facts, after: facts, snapshot_fingerprint: 'a'.repeat(64), preview_fingerprint: null,
    });
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('row', { name: '開啟 去敏人員甲 的詳情' }));

    const editor = within(screen.getByRole('region', { name: '交通與照顧人數' }));
    expect(await editor.findByRole('textbox', { name: '交通方式' })).toHaveValue('公車');
    expect(editor.getByRole('spinbutton', { name: '最多照顧寶寶數' })).toHaveValue(2);
    expect(editor.queryByText(/哺乳協助|托育證照|按摩證書/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '重試資格主檔' })).not.toBeInTheDocument();
  });

  it('offers a direct lifecycle retry inside the identity-bound drawer', async () => {
    vi.mocked(staffLifecycleClient.query)
      .mockRejectedValueOnce(new Error('Lifecycle 暫時失敗'))
      .mockResolvedValueOnce(STAFF_LIFECYCLE_VIEW);
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole('button', { name: /查看 .* 的詳情/ })[0]);

    fireEvent.click(await screen.findByRole('button', { name: '重試任職狀態' }));
    await waitFor(() => expect(screen.getAllByText(/正常在職中/).length).toBeGreaterThan(0));
    expect(staffLifecycleClient.query).toHaveBeenCalledTimes(2);
  });
});

/** HCM import keeps this receipt's review rows in the import card without querying the anomaly page. */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { hcmWorkbookPreviewClient } from '../api/case_import/hcm_workbook_client';
import { hcmResubmissionClient } from '../api/case_import/hcm_resubmission_client';
import { DataImportPage } from '../pages/DataImportPage';
import { HCM_WORKBOOK_PREVIEW_FIXTURE } from './fixtures/hcm_workbook_contract_fixtures';

function workbook(): File {
  return new File(['hcm-review'], 'hcm-current.xlsx', {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}

describe('DataImport HCM receipt review', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(hcmResubmissionClient, 'query').mockResolvedValue({ review_identity: 'review-2', case_no: '115000002', source_field: '行動電話', review_version: 0, resolved: false });
    vi.spyOn(hcmResubmissionClient, 'current').mockResolvedValue({ items: [], next_cursor: null });
    vi.spyOn(hcmWorkbookPreviewClient, 'preview').mockResolvedValue(HCM_WORKBOOK_PREVIEW_FIXTURE);
    vi.spyOn(hcmWorkbookPreviewClient, 'apply').mockResolvedValue({
      source_content_digest: HCM_WORKBOOK_PREVIEW_FIXTURE.source_content_digest,
      source_row_count: 4,
      inserted_count: 0,
      inserted_with_warning_count: 2,
      exact_replay_count: 0,
      review_required_count: 2,
      failed_count: 0,
      skipped_existing_count: 0,
      replayed_workbook: false,
      row_outcomes_available: true,
      legacy_summary_only: false,
      row_outcomes: [{
        source_row: 2,
        case_no: '115000002',
        outcome: 'inserted_with_warning',
        problem_identity: 'review-2',
        problem_fields: ['行動電話'],
        issue_codes: ['hcm_field_invalid:行動電話'],
        referral_occurrence_identities: [],
      }, {
        source_row: 3,
        case_no: '115000003',
        outcome: 'inserted_with_warning',
        problem_identity: 'review-3',
        problem_fields: ['hcm_identity'],
        issue_codes: ['hcm_identity:hcm_identity_ambiguous'],
        referral_occurrence_identities: [],
      }, {
        source_row: 4,
        case_no: '115000004',
        outcome: 'review_required',
        problem_identity: 'review-4',
        problem_fields: ['case_import'],
        issue_codes: ['hcm_case_import:case_import_bootstrap_blocked'],
        reason_codes: ['hcm_bootstrap_deposit_due_after_service_start'],
        referral_occurrence_identities: [],
      }, {
        source_row: 5,
        case_no: '115000005',
        outcome: 'review_required',
        problem_identity: 'review-5',
        problem_fields: ['case_import'],
        issue_codes: ['hcm_case_import:case_import_bootstrap_blocked'],
        referral_occurrence_identities: [],
      }],
    });
  });

  it('counts imported warning rows once and hides all problem details', async () => {
    render(<DataImportPage />);
    expect(screen.queryByText('HCM 目前待處理異常')).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: '目前 HCM 欄位待修正資料' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '讀取目前問題' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '重新整理結果' })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('選擇 HCM Current Workbook'), { target: { files: [workbook()] } });
    fireEvent.click(document.querySelector('[data-control-id="imports.hcm-current.preview"]') as HTMLButtonElement);
    await screen.findByText('預覽結果');
    fireEvent.click(screen.getByLabelText('我已核對檔案名稱與預覽筆數'));
    fireEvent.click(document.querySelector('[data-control-id="imports.hcm-current.apply"]') as HTMLButtonElement);

    expect(await screen.findByText('匯入結果')).toBeInTheDocument();
    expect(Array.from(document.querySelectorAll('dd > span')).map(node => node.textContent)).toEqual(['4', '2', '0', '2']);
    expect(screen.queryByText(/115000002|115000003|行動電話|需修改欄位|常見原因|含警示/)).not.toBeInTheDocument();
    expect(screen.queryByText('預覽結果')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /前往異常審核|處理.*待確認|在本頁提交修正/ })).not.toBeInTheDocument();
    expect(hcmResubmissionClient.query).not.toHaveBeenCalled();
    expect(hcmResubmissionClient.current).not.toHaveBeenCalled();
  });

  it('cancels the selected HCM workbook and clears preview confirmation without Apply', async () => {
    render(<DataImportPage />);
    const input = screen.getByLabelText('選擇 HCM Current Workbook');
    fireEvent.change(input, { target: { files: [workbook()] } });
    fireEvent.click(screen.getByRole('button', { name: '預覽檔案' }));
    await screen.findByText('預覽結果');
    fireEvent.click(screen.getByLabelText('我已核對檔案名稱與預覽筆數'));

    fireEvent.click(screen.getByRole('button', { name: '取消選取檔案' }));

    expect(screen.getByText('未選擇任何檔案')).toBeInTheDocument();
    expect(screen.queryByText('預覽結果')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('我已核對檔案名稱與預覽筆數')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '預覽檔案' })).toBeDisabled();
    expect(hcmWorkbookPreviewClient.apply).not.toHaveBeenCalled();
  });

  it('does not restore the current HCM review section when switching import types', () => {
    vi.spyOn(hcmResubmissionClient, 'current').mockResolvedValue({ items: [], next_cursor: null });
    render(<DataImportPage />);
    for (const name of ['客戶 BeClass', '月嫂歷史資料', '歷史訂單', 'HCM 案件']) {
      fireEvent.click(screen.getByRole('button', { name }));
      expect(screen.queryByText('目前 HCM 欄位待修正資料')).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: '讀取目前問題' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: '上一頁問題' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: '下一頁問題' })).not.toBeInTheDocument();
    }
    expect(screen.getByLabelText('選擇 HCM Current Workbook')).toBeInTheDocument();
    expect(hcmResubmissionClient.current).not.toHaveBeenCalled();
  });
});

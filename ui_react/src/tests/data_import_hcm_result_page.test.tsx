/** HCM import keeps this receipt's review rows in the import card without querying the anomaly page. */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { hcmWorkbookPreviewClient } from '../api/case_import/hcm_workbook_client';
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
    vi.spyOn(hcmWorkbookPreviewClient, 'preview').mockResolvedValue(HCM_WORKBOOK_PREVIEW_FIXTURE);
    vi.spyOn(hcmWorkbookPreviewClient, 'apply').mockResolvedValue({
      source_content_digest: HCM_WORKBOOK_PREVIEW_FIXTURE.source_content_digest,
      source_row_count: 3,
      inserted_count: 0,
      inserted_with_warning_count: 1,
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
        outcome: 'review_required',
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
        referral_occurrence_identities: [],
      }],
    });
  });

  it('removes the persistent lower HCM section and shows this run inside the HCM card', async () => {
    render(<DataImportPage />);
    expect(screen.queryByText('HCM 目前待處理異常')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '重新整理結果' })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('選擇 HCM Current Workbook'), { target: { files: [workbook()] } });
    fireEvent.click(document.querySelector('[data-control-id="imports.hcm-current.preview"]') as HTMLButtonElement);
    await screen.findByText('預覽結果');
    fireEvent.click(screen.getByLabelText('我已核對檔案名稱與預覽筆數'));
    fireEvent.click(document.querySelector('[data-control-id="imports.hcm-current.apply"]') as HTMLButtonElement);

    expect(await screen.findByText('案件 115000002')).toBeInTheDocument();
    expect(screen.getByText('需修改欄位：行動電話（格式或內容不符合規則）。')).toBeInTheDocument();
    expect(screen.getByText('需核對欄位：查詢序號(案件編號)、姓名、IP位址。系統無法唯一確認這筆資料與既有客戶的身分關聯。')).toBeInTheDocument();
    expect(screen.getByText('需核對欄位：服務時間、預計服務日期、希望服務天數、服務方式。這些資料目前無法組成可建立的訂單。')).toBeInTheDocument();
    expect(screen.queryByText(/case_import|hcm_identity/)).not.toBeInTheDocument();
    expect(screen.getByText(/既有案件跳過 0 筆（不覆寫既有案件與訂單資料）/)).toBeInTheDocument();
    expect(screen.queryByText(/前往異常審核/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /在本頁提交修正/ }));
    await waitFor(() => expect(screen.getByText('修正案件 115000002')).toBeInTheDocument());
  });
});

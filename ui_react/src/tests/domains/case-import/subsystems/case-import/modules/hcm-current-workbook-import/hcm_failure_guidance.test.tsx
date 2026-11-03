/** Receipt-based HCM failures explain the blocked field and who can resolve it. */
import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { adaptHcmImportResult } from '../../../../../../../adapters/workbook_import_result_adapter';
import { hcmWorkbookPreviewClient } from '../../../../../../../api/case_import/hcm_workbook_client';
import type { HcmWorkbookReceipt, HcmWorkbookRowOutcome } from '../../../../../../../api/case_import/hcm_workbook_schemas';
import { DataImportPage } from '../../../../../../../pages/DataImportPage';

afterEach(() => vi.restoreAllMocks());

const blocked: HcmWorkbookRowOutcome = {
  source_row: 1, case_no: 'SYNTH-BLOCKED', outcome: 'review_required', problem_identity: null,
  problem_fields: ['case_import'], issue_codes: ['hcm_case_import:case_import_bootstrap_blocked'],
  reason_codes: [], referral_occurrence_identities: [],
};

function receipt(rows: HcmWorkbookRowOutcome[]): HcmWorkbookReceipt {
  return {
    source_content_digest: 'a'.repeat(64), source_row_count: rows.length,
    inserted_count: 0, inserted_with_warning_count: 0, exact_replay_count: 0, skipped_existing_count: 0,
    review_required_count: rows.filter(row => row.outcome === 'review_required').length,
    failed_count: rows.filter(row => row.outcome === 'failed').length,
    replayed_workbook: false, row_outcomes_available: true, legacy_summary_only: false, row_outcomes: rows,
  };
}

describe('HCM failure guidance from terminal receipts', () => {
  it.each([
    ['hcm_bootstrap_rate_policy_missing', '薪資費率政策', '【檢查系統設定】'],
    ['hcm_bootstrap_rate_policy_not_effective', '薪資費率政策生效期間', '【核對資料／系統設定】'],
    ['hcm_bootstrap_identity_policy_unmapped', '身分資格／薪資政策對應', '【檢查系統設定】'],
    ['hcm_bootstrap_planned_start_missing', '預計服務日期', '【修正匯入資料】'],
    ['hcm_bootstrap_deposit_days_exceed_service_days', '希望服務天數／訂金天數', '若正確，請管理員確認短天數案件的訂金規則'],
    ['hcm_bootstrap_deposit_days_identity_mismatch', '身分資格／訂金設定', '【核對資料／系統設定】'],
    ['hcm_bootstrap_deposit_due_after_service_start', '訂金到期日／服務開始日', '【系統人員處理】'],
    ['hcm_bootstrap_payment_start_mismatch', '首期繳款日／服務開始日', '【系統人員處理】'],
    ['hcm_bootstrap_unexpected_second_payment', '第二期繳款設定', '【系統人員處理】'],
    ['hcm_bootstrap_payroll_policy_identity_mismatch', '身分資格／薪資政策', '【核對資料／系統設定】'],
    ['hcm_bootstrap_existing_state_conflict', '既有案件建檔資料', '【檢查既有資料】'],
    ['hcm_bootstrap_service_days_invalid', '希望服務天數', '【修正匯入資料】'],
    ['hcm_bootstrap_service_hours_invalid', '服務時間（每日時數）', '【核對資料／系統規則】'],
    ['hcm_bootstrap_rule_blocked', '案件建檔規則', '收據未保存更細原因'],
  ])('explains %s without the internal field category', (code, field, guidance) => {
    const row = adaptHcmImportResult(receipt([{ ...blocked, reason_codes: [code] }])).notImportedRows![0];
    expect(row.fields).toEqual([field]);
    expect(row.reasons).toHaveLength(1);
    expect(row.reasons[0]).toContain(guidance);
    expect(row.reasons[0]).not.toContain('資料未通過匯入檢查');
  });

  it.each([
    ['case_import_duplicate', '查詢序號(案件編號)／既有案件', '案件編號已存在'],
    ['case_import_existing_source_conflict', '案件編號／來源資料', '不同來源內容'],
    ['provisional_registration_not_found', '待核准需求關聯', '找不到對應的待核准需求'],
    ['provisional_registration_not_submitted', '待核准需求狀態', '尚未提交'],
    ['provisional_registration_identity_mismatch', '待核准需求身分／關聯', '身分或關聯資料不一致'],
    ['invalid_case_import_root_facts', '案件建檔資料', '內部一致性檢查'],
    ['transaction_failed', '系統寫入', '寫入失敗並已回滾'],
  ])('explains workflow issue %s', (code, field, reason) => {
    const row = adaptHcmImportResult(receipt([{ ...blocked, issue_codes: [`hcm_case_import:${code}`] }])).notImportedRows![0];
    expect(row.fields).toEqual([field]);
    expect(row.reasons[0]).toContain(reason);
  });

  it('retains unrelated field issues alongside detailed bootstrap failures', () => {
    const row = adaptHcmImportResult(receipt([{ ...blocked, problem_fields: ['case_import', 'email'],
      reason_codes: ['hcm_bootstrap_rate_policy_missing'],
      issue_codes: [...blocked.issue_codes, 'hcm_field_invalid:email'],
    }])).notImportedRows![0];
    expect(row.fields).toEqual(['電子郵件', '薪資費率政策']);
    expect(row.reasons).toHaveLength(2);
    expect(row.reasons[1]).toContain('【修正匯入資料】電子郵件');
  });

  it('does not guess the cause of historical, missing or unknown reasons, or mutate the receipt', () => {
    const original = receipt([
      { ...blocked, reason_codes: undefined },
      { ...blocked, source_row: 2, issue_codes: [], reason_codes: undefined },
      { ...blocked, source_row: 3, reason_codes: ['hcm_new_reason'], issue_codes: [] },
    ]);
    const snapshot = structuredClone(original);
    const rows = adaptHcmImportResult(original).notImportedRows!;
    expect(rows[0].reasons[0]).toContain('當時未保存詳細原因');
    expect(rows[1].reasons[0]).toContain('當時未保存詳細原因');
    expect(rows[2].reasons[0]).toContain('錯誤代碼：hcm_new_reason');
    for (const row of rows) {
      expect(row.fields).not.toContain('case_import');
      expect(row.reasons.join('')).toContain('無法判定應修資料或系統設定');
    }
    expect(original).toEqual(snapshot);
  });

  it('renders data fixes, system settings and historical uncertainty in the existing details table', async () => {
    vi.spyOn(hcmWorkbookPreviewClient, 'preview').mockResolvedValue({
      source_content_digest: 'a'.repeat(64), source_row_count: 3, ready_count: 0,
      ready_with_warning_count: 0, review_required_count: 3, preview_fingerprint: 'b'.repeat(64),
    });
    vi.spyOn(hcmWorkbookPreviewClient, 'apply').mockResolvedValue(receipt([
      { ...blocked, reason_codes: ['hcm_bootstrap_service_days_invalid'] },
      { ...blocked, source_row: 2, case_no: 'SYNTH-POLICY', reason_codes: ['hcm_bootstrap_rate_policy_missing'] },
      { ...blocked, source_row: 3, case_no: 'SYNTH-OLD', reason_codes: undefined },
    ]));
    render(<DataImportPage />);
    fireEvent.change(screen.getByLabelText('選擇 HCM Current Workbook'), {
      target: { files: [new File(['synthetic'], 'hcm.xlsx')] },
    });
    fireEvent.click(document.querySelector('[data-control-id="imports.hcm-current.preview"]')!);
    const details = await screen.findByRole('region', { name: '未匯入明細' });
    const rows = within(details).getAllByRole('row').slice(1);
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent('希望服務天數');
    expect(rows[0]).toHaveTextContent('【修正匯入資料】');
    expect(rows[1]).toHaveTextContent('薪資費率政策');
    expect(rows[1]).toHaveTextContent('【檢查系統設定】');
    expect(rows[2]).toHaveTextContent('當時未保存詳細原因');
    expect(details).not.toHaveTextContent('case_import');
    expect(details).not.toHaveTextContent('資料未通過匯入檢查');
    expect(Array.from(document.querySelectorAll('dd > span')).map(node => node.textContent)).toEqual(['3', '0', '0', '3']);
  });
});

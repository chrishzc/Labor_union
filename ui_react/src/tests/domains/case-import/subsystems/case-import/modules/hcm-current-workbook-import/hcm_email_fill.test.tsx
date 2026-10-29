import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { DataImportPage } from '../../../../../../../pages/DataImportPage';
import { hcmWorkbookPreviewClient } from '../../../../../../../api/case_import/hcm_workbook_client';
import { HcmWorkbookReceiptSchema } from '../../../../../../../api/case_import/hcm_workbook_schemas';
import { HcmImportResultRecordSchema } from '../../../../../../../api/case_import/hcm_import_result_schemas';
import { adaptHcmImportResult } from '../../../../../../../adapters/case_import/hcm_import_result_adapter';

afterEach(() => vi.restoreAllMocks());

const receipt = {
  source_content_digest: 'a'.repeat(64), source_row_count: 1,
  inserted_count: 0, inserted_with_warning_count: 0, exact_replay_count: 0,
  review_required_count: 0, failed_count: 0, skipped_existing_count: 0, email_filled_count: 1,
  replayed_workbook: false, row_outcomes_available: true, legacy_summary_only: false,
  row_outcomes: [{ source_row: 1, case_no: 'SYNTH-EMAIL', outcome: 'email_filled' as const,
    problem_identity: null, problem_fields: [], issue_codes: [], referral_occurrence_identities: [], reason_codes: [] }],
};

it('previews and reports email-only fills as a completed update without new cases', async () => {
  vi.spyOn(hcmWorkbookPreviewClient, 'preview').mockResolvedValue({
    source_content_digest: 'a'.repeat(64), source_row_count: 1, ready_count: 1,
    ready_with_warning_count: 0, review_required_count: 0, email_fill_count: 1,
    preview_fingerprint: 'b'.repeat(64),
  });
  vi.spyOn(hcmWorkbookPreviewClient, 'apply').mockResolvedValue(receipt);
  render(<DataImportPage />);
  expect(screen.queryByText(/既有案件只補入空白 HCM Email/)).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('選擇 HCM Current Workbook'), {
    target: { files: [new File(['synthetic'], 'hcm.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })] },
  });
  fireEvent.click(document.querySelector('[data-control-id="imports.hcm-current.preview"]')!);
  expect(screen.queryByLabelText('我已核對檔案名稱與預覽筆數')).not.toBeInTheDocument();
  await waitFor(() => expect(screen.getByText('匯入結果')).toBeInTheDocument());
  expect(Array.from(document.querySelectorAll('dd > span')).map(node => node.textContent)).toEqual(['1', '1', '0', '0']);
  expect(screen.queryByText(/補入既有案件 email|含警示|需檢查/)).not.toBeInTheDocument();
});

it('decodes and conserves email fills in both Apply and historical results', () => {
  expect(HcmWorkbookReceiptSchema.parse(receipt).email_filled_count).toBe(1);
  const record = HcmImportResultRecordSchema.parse({ ...receipt, receipt_id: 7, completed_at: '2026-10-13T09:00:00+08:00' });
  const model = adaptHcmImportResult(record);
  expect(model.summary).toContain('補入 email 1');
  expect(model.newOrders).toHaveLength(0);
});

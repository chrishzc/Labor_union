/**
 * File: finance_source_review_list.test.tsx
 * Description: 驗證 Finance Import Preview 的人工確認 KPI、清單與 batch identity 共用 owner readback。
 */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { financeImportMutationClient, type FinanceImportBatchPreview } from '../api/finance_import/finance_import_mutation_client';
import { financeImportQueryClient } from '../api/finance_import/finance_import_query_client';
import { transport } from '../api/shared/transport';
import { readFileSync } from 'node:fs';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { FinancePage } from '../pages/FinancePage';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { paymentReceiptClient } from '../api/line_order_groups/payment_receipt_notification_client';
import { clientReceiptQueryClient } from '../api/client_finance/client_receipt_query_client';
import { financeImportCorrectionClient } from '../api/finance_import/finance_import_correction_client';

const BATCH = 'BATCH-REVIEW-222';
const PREVIEW: FinanceImportBatchPreview = {
  batch_identity: BATCH,
  batch_version: 7,
  source_content_digest: 'a'.repeat(64),
  classifier_version: 'v1',
  fingerprint_version: 'v1',
  counts: {
    source_rows: 2,
    canonical_created: 1,
    duplicate_occurrences: 0,
    ready_dispatch: 0,
    existing: 0,
    manual_review: 0,
    business_pending: 0,
    blocked: 0,
  },
  dispatch_summaries: [],
  rows: [],
  blocking_codes: [],
  apply_allowed: true,
  preview_fingerprint: 'b'.repeat(64),
};

const MANIFEST = {
  batch_id: 222,
  batch_identity: BATCH,
  format_id: 'fixture',
  source_file: 'finance.xlsx',
  sheet_name: 'Sheet1',
  header_row: 1,
  source_row_count: 2,
  status: 'previewed',
  batch_version: 7,
  source_content_digest: 'a'.repeat(64),
  classifier_version: 'v1',
  fingerprint_version: 'v1',
  canonical_row_count: 1,
  occurrence_count: 2,
  review_count: 1,
  dispatch_event_count: 0,
  reconciliation_receipt_count: 0,
  created_at: '2026-09-07T00:00:00+08:00',
  completed_at: null,
};

const REVIEW_PAGE = {
  batch_identity: BATCH,
  source_reviews: [] as { review_id: number; review_identity: string; source_sheet: string; source_row: number; issue_codes: string[]; created_at: string }[],
  next_after_source_review_id: null as number | null,
  items: [{
    row_id: 301,
    row_identity: 'ROW-REVIEW-222',
    transaction_date: '2026-09-01',
    direction: 'credit',
    amount_ntd: 5000,
    classification_type: 'client_receipt',
    disposition: 'manual_review',
    reconciliation_status: 'unmatched',
    source_sheet: 'Sheet1',
    source_row: 3,
    occurrence_count: 1,
    available_actions: [],
    created_at: '2026-09-07T00:00:00+08:00',
  }],
  next_after_row_id: null,
};

async function showPreview() {
  render(<FinancePage />);
  fireEvent.click(screen.getByRole('button', { name: '銀行對帳' }));
  fireEvent.change(screen.getByLabelText('選擇銀行交易明細工作簿'), { target: { files: [new File(['finance-review'], 'finance.xlsx')] } });
  fireEvent.click(screen.getByRole('button', { name: '匯入銀行交易明細' }));
  await screen.findByText(/^未入帳明細 \d+ 筆$/);
}
function reviewCount() {
  return screen.getByText(/^未入帳明細 \d+ 筆$/).textContent?.match(/未入帳明細 (\d+)/)?.[1];
}

function previewRow(row: Awaited<ReturnType<typeof financeImportQueryClient.listReviewRows>>['items'][number], evidence: string[]): FinanceImportBatchPreview['rows'][number] {
  return { row_identity: row.row_identity, canonical_fact_version: 0, amount_ntd: row.amount_ntd,
    classification_type: row.classification_type, disposition: row.disposition, target_identities: [], evidence,
    available_actions: row.available_actions, integrity_violations: [], fingerprint_collision: false, formal_reference_conflict: false };
}

describe('Finance source-review owner readback', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    sessionClient.setSession('finance-review-test-session', {
      id: 7,
      username: 'finance-review',
      display_name: 'Finance Review',
      role: 'admin',
    });
    window.location.hash = '#finance?tab=bank';
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({ items: [], next_cursor: null });
    vi.spyOn(paymentReceiptClient, 'list').mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue({ items: [], next_cursor: null, etag: 'c'.repeat(64) });
    vi.spyOn(financeImportMutationClient, 'ingest').mockResolvedValue({
      batch_identity: BATCH,
      source_content_digest: 'a'.repeat(64),
      source_row_count: 2,
      canonical_created_count: 1,
      duplicate_occurrence_count: 0,
      source_warning_count: 1,
      source_warning_created_count: 1,
      replayed: false,
    });
    vi.spyOn(financeImportMutationClient, 'preview').mockResolvedValue(structuredClone(PREVIEW));
    vi.spyOn(financeImportMutationClient, 'apply').mockResolvedValue({ job_id: 'review-job', status_url: '/api/v1/jobs/review-job', replayed: false });
    vi.spyOn(financeImportMutationClient, 'queryBatchOutcome').mockResolvedValue({ job_id: 'review-job', status: 'succeeded', attempt_count: 1, max_attempts: 1, result_reference: 'finance_import_batch:fixture', receipt: { batch_identity: BATCH, resulting_batch_version: 8, preview_fingerprint: PREVIEW.preview_fingerprint, reconciled_count: 1, existing_count: 0, pending_count: 1 } });
    vi.spyOn(financeImportQueryClient, 'getManifest').mockResolvedValue(MANIFEST);
    vi.spyOn(financeImportQueryClient, 'listReviewRows').mockResolvedValue(REVIEW_PAGE);
  });

  afterEach(() => {
    cleanup();
    sessionClient.clearSession();
    window.location.hash = '';
    vi.restoreAllMocks();
  });

  it('settles manual-review KPI and list from the same batch owner fact and supports a consistent re-query', async () => {
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行對帳' }));

    const file = new File(['finance-review'], 'finance.xlsx');
    fireEvent.change(screen.getByLabelText('選擇銀行交易明細工作簿'), { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: '匯入銀行交易明細' }));

    const manualReviewSummary = await screen.findByText('未入帳明細 1 筆');
    expect(screen.getByLabelText('匯入結果')).toHaveTextContent('本次入帳 0 筆｜已存在略過 0 筆');
    expect(screen.getByText('Sheet1#3')).toBeInTheDocument();
    expect(financeImportMutationClient.apply).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '重新查詢未入帳明細' }));
    await waitFor(() => expect(financeImportQueryClient.getManifest).toHaveBeenCalledTimes(2));
    expect(financeImportQueryClient.listReviewRows).toHaveBeenCalledTimes(2);
    expect(manualReviewSummary).toHaveTextContent('未入帳明細 1 筆');
    expect(screen.getByText('Sheet1#3')).toBeInTheDocument();
  });

  it('offers exact-order correction for a business-pending client receipt', async () => {
    vi.mocked(financeImportQueryClient.listReviewRows).mockResolvedValue({
      ...REVIEW_PAGE,
      items: [{
        ...REVIEW_PAGE.items[0],
        classification_type: 'client_receipt',
        disposition: 'business_pending',
        available_actions: ['resolve_owning_domain_target'],
      }],
    });

    await showPreview();

    const entry = await screen.findByRole('button', { name: '指定正確訂單' });
    expect(screen.getByText(/尚未確認可自動核銷的案件及待收款項/)).toBeInTheDocument();
    entry.focus();
    fireEvent.click(entry);
    expect(screen.getByRole('dialog', { name: '指定銀行入款的正確訂單' })).toBeInTheDocument();
    expect(screen.getAllByText(/尚未確認可自動核銷的案件及待收款項/)).toHaveLength(2);
    expect(screen.getByLabelText('案件編號')).toBeInTheDocument();
    expect(screen.getByText('查詢待核銷款項')).toBeInTheDocument();
    fireEvent.keyDown(window, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(entry).toHaveFocus();
  });

  it.each([
    ['suspected_duplicate_business_match', '多筆銀行交易對應到同一筆待收款，需確認是否重複入款。'],
    ['sinopac_valid_virtual_account', '銷帳編號格式可辨識，但尚未唯一配對到金額相符的待收款項，請確認案件與入款金額。'],
  ])('shows the specific %s preview reason for the exact row in the list and drawer', async (code, reason) => {
    vi.mocked(financeImportQueryClient.listReviewRows).mockResolvedValue({ ...REVIEW_PAGE, items: [{ ...REVIEW_PAGE.items[0], disposition: 'business_pending', available_actions: ['resolve_owning_domain_target'] }] });
    vi.mocked(financeImportMutationClient.preview).mockResolvedValue({ ...PREVIEW, rows: [{ row_identity: REVIEW_PAGE.items[0].row_identity, canonical_fact_version: 0, amount_ntd: 5000, classification_type: 'client_receipt', disposition: 'business_pending', target_identities: [], evidence: [code], available_actions: [], integrity_violations: [], fingerprint_collision: false, formal_reference_conflict: false }] });
    await showPreview();
    expect(await screen.findByText(reason)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '指定正確訂單' }));
    expect(screen.getAllByText(reason, { exact: false })).toHaveLength(2);
  });

  it('paginates a full review page instead of treating its cursor as an inconsistency', async () => {
    const rows = Array.from({ length: 51 }, (_, i) => ({ ...REVIEW_PAGE.items[0], row_id: i + 1, row_identity: `row-${i + 1}`, source_row: i + 1 }));
    vi.mocked(financeImportQueryClient.getManifest).mockResolvedValue({ ...MANIFEST, review_count: 51 });
    vi.mocked(financeImportQueryClient.listReviewRows)
      .mockResolvedValueOnce({ ...REVIEW_PAGE, items: rows.slice(0, 50), next_after_row_id: 50 })
      .mockResolvedValueOnce({ ...REVIEW_PAGE, items: rows.slice(50) });
    await showPreview();
    await waitFor(() => expect(reviewCount()).toBe('51'));
    expect(screen.getByText('Sheet1#51')).toBeInTheDocument();
    expect(financeImportQueryClient.listReviewRows).toHaveBeenLastCalledWith(BATCH, expect.objectContaining({ afterRowId: 50 }));
  });

  it('keeps matched business-pending rows and discards unrelated source warnings', async () => {
    vi.mocked(financeImportQueryClient.getManifest).mockResolvedValue({ ...MANIFEST, review_count: 1 });
    vi.mocked(financeImportQueryClient.listReviewRows).mockResolvedValue({
      ...REVIEW_PAGE,
      items: [{ ...REVIEW_PAGE.items[0], disposition: 'business_pending' }],
      source_reviews: [{ review_id: 11, review_identity: 'source-review-11', source_sheet: '交易明細', source_row: 4, issue_codes: ['invalid:transaction_amount'], created_at: MANIFEST.created_at }],
    });
    await showPreview();
    await waitFor(() => expect(reviewCount()).toBe('1'));
    expect(screen.queryByText('交易明細#4')).not.toBeInTheDocument();
    expect(screen.queryByText('invalid:transaction_amount')).not.toBeInTheDocument();
    expect(screen.getByText('Sheet1#3')).toBeInTheDocument();
    expect(financeImportMutationClient.apply).not.toHaveBeenCalled();
  });

  it.each(['blocked', 'no-ready-rows'] as const)('never auto-submits %s', async policy => {
    const preview = structuredClone(PREVIEW);
    if (policy === 'blocked') { preview.apply_allowed = false; preview.counts.ready_dispatch = 1; preview.blocking_codes = ['fingerprint_collision']; }
    vi.mocked(financeImportMutationClient.preview).mockResolvedValue(preview);
    await showPreview();
    await waitFor(() => expect(reviewCount()).toBe('1'));
    expect(financeImportMutationClient.apply).not.toHaveBeenCalled();
  });

  it('automatically refreshes owner review after terminal Apply', async () => {
    vi.mocked(financeImportMutationClient.preview).mockResolvedValue({ ...PREVIEW, counts: { ...PREVIEW.counts, ready_dispatch: 1 } });
    await showPreview();
    await screen.findByText('本次入帳 1 筆｜已存在略過 0 筆');
    await waitFor(() => expect(financeImportQueryClient.listReviewRows).toHaveBeenCalledOnce());
    expect(financeImportMutationClient.apply).toHaveBeenCalledOnce();
    expect(reviewCount()).toBe('1');
    expect(screen.getByText('Sheet1#3')).toBeInTheDocument();
  });

  it('posts eligible rows without waiting for manual matching and shows only receipt counts plus remaining reasons', async () => {
    const manual = { ...REVIEW_PAGE.items[0], classification_type: 'non_business_review', available_actions: ['preview_manual_correction'] };
    const pending = { ...REVIEW_PAGE.items[0], row_id: 302, row_identity: 'ROW-302', source_row: 4, disposition: 'business_pending', available_actions: ['resolve_owning_domain_target'] };
    vi.mocked(financeImportMutationClient.preview).mockResolvedValue({ ...PREVIEW,
      counts: { ...PREVIEW.counts, ready_dispatch: 2, existing: 3, manual_review: 1, business_pending: 1 },
      rows: [previewRow(manual, ['counterparty_account_no_match']), previewRow(pending, ['sinopac_valid_virtual_account'])] });
    vi.mocked(financeImportQueryClient.getManifest).mockResolvedValue({ ...MANIFEST, review_count: 2 });
    vi.mocked(financeImportQueryClient.listReviewRows).mockResolvedValue({ ...REVIEW_PAGE, items: [manual, pending] });
    let finish!: (value: Awaited<ReturnType<typeof financeImportMutationClient.queryBatchOutcome>>) => void;
    vi.mocked(financeImportMutationClient.queryBatchOutcome).mockReturnValue(new Promise(resolve => { finish = resolve; }));
    render(<FinancePage />);
    fireEvent.change(screen.getByLabelText('選擇銀行交易明細工作簿'), { target: { files: [new File(['mixed'], 'mixed.xlsx')] } });
    fireEvent.click(screen.getByRole('button', { name: '匯入銀行交易明細' }));
    await waitFor(() => expect(financeImportMutationClient.queryBatchOutcome).toHaveBeenCalledOnce());
    expect(financeImportMutationClient.apply).toHaveBeenCalledOnce();
    expect(financeImportQueryClient.listReviewRows).not.toHaveBeenCalled();
    expect(screen.queryByLabelText('匯入結果')).not.toBeInTheDocument();
    await act(async () => finish({ job_id: 'review-job', status: 'succeeded', attempt_count: 1, max_attempts: 1, result_reference: 'batch', receipt: { batch_identity: BATCH, resulting_batch_version: 8, preview_fingerprint: PREVIEW.preview_fingerprint, reconciled_count: 1, existing_count: 4, pending_count: 2 } }));
    expect(await screen.findByText('本次入帳 1 筆｜已存在略過 4 筆')).toBeInTheDocument();
    expect(await screen.findByText('未入帳明細 2 筆')).toBeInTheDocument();
    expect(screen.getByText('交易帳號找不到對應的收付款對象。')).toBeInTheDocument();
    expect(screen.getByText(/銷帳編號格式可辨識/)).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '指定正確訂單' })).toHaveLength(2);
    expect(screen.queryByText(/可自動入帳|待業務配對|需人工處理 \d/)).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('skips existing rows without creating a new Apply', async () => {
    vi.mocked(financeImportMutationClient.preview).mockResolvedValue({ ...PREVIEW, counts: { ...PREVIEW.counts, existing: 3 } });
    vi.mocked(financeImportQueryClient.getManifest).mockResolvedValue({ ...MANIFEST, review_count: 0 });
    vi.mocked(financeImportQueryClient.listReviewRows).mockResolvedValue({ ...REVIEW_PAGE, items: [] });
    await showPreview();
    expect(await screen.findByText('本次入帳 0 筆｜已存在略過 3 筆')).toBeInTheDocument();
    expect(screen.getByText('目前沒有未入帳資料。')).toBeInTheDocument();
    expect(financeImportMutationClient.apply).not.toHaveBeenCalled();
  });

  it('lists a blocked transaction and its cause while reporting that automatic posting did not run', async () => {
    const blocked = { ...REVIEW_PAGE.items[0], disposition: 'business_pending', available_actions: ['resolve_owning_domain_target'] };
    const ready = { ...REVIEW_PAGE.items[0], row_id: 302, row_identity: 'ROW-302', source_row: 4, disposition: 'create' };
    vi.mocked(financeImportQueryClient.getManifest).mockResolvedValue({ ...MANIFEST, review_count: 2 });
    vi.mocked(financeImportQueryClient.listReviewRows).mockResolvedValue({ ...REVIEW_PAGE, items: [blocked, ready] });
    vi.mocked(financeImportMutationClient.preview).mockResolvedValue({ ...PREVIEW, apply_allowed: false, blocking_codes: ['fingerprint_collision'], counts: { ...PREVIEW.counts, ready_dispatch: 1, blocked: 1 }, rows: [{ ...previewRow(blocked, []), disposition: 'blocked', fingerprint_collision: true }, previewRow(ready, [])] });
    await showPreview();
    expect(await screen.findByText('本次入帳 0 筆｜已存在略過 0 筆')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('自動入帳未執行：存在可能重複的銀行交易');
    const row = within(screen.getByText('Sheet1#3').closest('tr')!);
    expect(row.getByText('存在可能重複的銀行交易，需先核對原始資料。')).toBeInTheDocument();
    expect(row.getByText('5000')).toBeInTheDocument();
    expect(row.queryByRole('button', { name: '指定正確訂單' })).not.toBeInTheDocument();
    expect(screen.getByText('未入帳明細 2 筆')).toBeInTheDocument();
    expect(within(screen.getByText('Sheet1#4').closest('tr')!).getByText('此筆符合自動入帳條件，但本次匯入有錯誤，尚未執行入帳。')).toBeInTheDocument();
    expect(financeImportMutationClient.apply).not.toHaveBeenCalled();
  });

  it('keeps the confirmed posting result when reading the remaining list fails, and retries only that query', async () => {
    vi.mocked(financeImportMutationClient.preview).mockResolvedValue({ ...PREVIEW, counts: { ...PREVIEW.counts, ready_dispatch: 1 } });
    vi.mocked(financeImportQueryClient.listReviewRows).mockRejectedValueOnce(new Error('read unavailable')).mockResolvedValue(REVIEW_PAGE);
    render(<FinancePage />);
    fireEvent.change(screen.getByLabelText('選擇銀行交易明細工作簿'), { target: { files: [new File(['mixed'], 'mixed.xlsx')] } });
    fireEvent.click(screen.getByRole('button', { name: '匯入銀行交易明細' }));
    expect(await screen.findByText('本次入帳 1 筆｜已存在略過 0 筆')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('未入帳明細載入失敗');
    fireEvent.click(screen.getByRole('button', { name: '重新查詢未入帳明細' }));
    await screen.findByText('未入帳明細 1 筆');
    expect(financeImportMutationClient.apply).toHaveBeenCalledOnce();
  });

  it('updates the posted count and removes the row after successful manual correction', async () => {
    vi.mocked(financeImportQueryClient.listReviewRows).mockResolvedValueOnce({ ...REVIEW_PAGE, items: [{ ...REVIEW_PAGE.items[0], available_actions: ['preview_manual_correction'] }] }).mockResolvedValue({ ...REVIEW_PAGE, items: [] });
    vi.mocked(financeImportQueryClient.getManifest).mockResolvedValueOnce(MANIFEST).mockResolvedValue({ ...MANIFEST, review_count: 0 });
    vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValue({ items: [{ case_no: '115000701', client_name: '測試客戶' }], next_cursor: null, etag: 'c'.repeat(64) } as never);
    vi.spyOn(clientReceiptQueryClient, 'query').mockResolvedValue({ case_no: '115000701', obligations: [{ obligation_identity: 'obligation:1', payment_stage: 'deposit', amount_due_ntd: 5000 }] } as never);
    vi.spyOn(financeImportCorrectionClient, 'preview').mockResolvedValue({ candidate: { row_identity: REVIEW_PAGE.items[0].row_identity, batch_identity: BATCH, classification_type: 'client_receipt', bank_amount_ntd: 5000, allocations: [{ obligation_identity: 'obligation:1', amount_ntd: 5000 }] }, preview_fingerprint: 'a'.repeat(64) } as never);
    vi.spyOn(financeImportCorrectionClient, 'apply').mockResolvedValue({ job_id: 'correction-job' } as never);
    vi.spyOn(financeImportCorrectionClient, 'queryOutcome').mockResolvedValue({ status: 'succeeded', receipt: { row_identity: REVIEW_PAGE.items[0].row_identity, batch_identity: BATCH, preview_fingerprint: 'a'.repeat(64) } } as never);
    await showPreview();
    fireEvent.click(screen.getByRole('button', { name: '指定正確訂單' }));
    await screen.findByRole('option', { name: '115000701｜測試客戶' });
    fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: '115000701' } });
    fireEvent.click(screen.getByRole('button', { name: '查詢待核銷款項' }));
    const obligation = await screen.findByRole('checkbox', { name: '115000701 · 訂金 · NT$ 5,000' });
    await waitFor(() => expect(obligation).toBeEnabled());
    fireEvent.click(obligation);
    await waitFor(() => expect(screen.getByRole('button', { name: '儲存更正並核銷' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '儲存更正並核銷' }));
    expect(await screen.findByText('本次入帳 1 筆｜已存在略過 0 筆')).toBeInTheDocument();
    expect(await screen.findByText('未入帳明細 0 筆')).toBeInTheDocument();
    expect(screen.queryByText('Sheet1#3')).not.toBeInTheDocument();
    expect(financeImportCorrectionClient.apply).toHaveBeenCalledOnce();
  });

  it('locks file selection while checking and discards a late response after unmount', async () => {
    let resolve!: (value: FinanceImportBatchPreview) => void;
    vi.mocked(financeImportMutationClient.preview).mockReturnValue(new Promise(done => { resolve = done; }));
    const { unmount } = render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行對帳' }));
    const input = screen.getByLabelText('選擇銀行交易明細工作簿');
    fireEvent.change(input, { target: { files: [new File(['first'], 'first.xlsx')] } });
    fireEvent.click(screen.getByRole('button', { name: '匯入銀行交易明細' }));
    await waitFor(() => expect(financeImportMutationClient.preview).toHaveBeenCalledOnce());
    expect(input).toBeDisabled();
    unmount();
    await act(async () => { resolve(PREVIEW); });
    expect(financeImportQueryClient.listReviewRows).not.toHaveBeenCalled();
    expect(financeImportMutationClient.apply).not.toHaveBeenCalled();
  });

  const exchangePath = process.env.FI_REVIEW_EXCHANGE;
  (exchangePath ? it : it.skip)('decodes same-run source-review owner envelopes through the real typed query client', async () => {
    const raw = JSON.parse(readFileSync(exchangePath!, 'utf-8')) as Record<string, any>;
    const batch = raw.ingestion.data.batch_identity as string;
    const matchedRow = raw.reviews.data.items[0] as { source_sheet: string; source_row: number };
    const sourceReview = raw.source_audit as { source_sheet: string; source_row: number; issue_codes: string[] };
    expect(raw.reviews.data.source_reviews).toEqual([]);
    vi.restoreAllMocks();
    vi.spyOn(paymentReceiptClient, 'list').mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue({ items: [], next_cursor: null, etag: 'c'.repeat(64) });
    vi.spyOn(financeImportMutationClient, 'ingest').mockResolvedValue(raw.ingestion.data);
    vi.spyOn(financeImportMutationClient, 'preview').mockResolvedValue(raw.preview.data);
    // The exchange proves real owner readback; later posting is an explicit test boundary.
    vi.spyOn(financeImportMutationClient, 'apply').mockResolvedValue({ job_id: 'review-proof', status_url: '/api/v1/jobs/review-proof', replayed: false });
    vi.spyOn(financeImportMutationClient, 'queryBatchOutcome').mockResolvedValue({ job_id: 'review-proof', status: 'cancelled', attempt_count: 0, max_attempts: 1, result_reference: null, receipt: null });
    const get = vi.spyOn(transport, 'get').mockImplementation(async (path: string) => {
      if (path.endsWith('/manifest')) return raw.manifest;
      if (path.endsWith('/review-rows')) return raw.reviews;
      throw new Error(`unexpected GET ${path}`);
    });

    await showPreview();
    await waitFor(() => expect(reviewCount()).toBe('1'));
    expect(financeImportQueryClient.listReviewRows).toHaveBeenCalledWith(batch, expect.anything());
    expect(screen.getByText(`${matchedRow.source_sheet}#${matchedRow.source_row}`)).toBeInTheDocument();
    expect(screen.queryByText(`${sourceReview.source_sheet}#${sourceReview.source_row}`)).not.toBeInTheDocument();
    expect(screen.queryByText(sourceReview.issue_codes[0])).not.toBeInTheDocument();
    expect(get.mock.calls.some(([path]) => String(path).endsWith('/manifest'))).toBe(true);
    expect(get.mock.calls.some(([path]) => String(path).endsWith('/review-rows'))).toBe(true);
  });

  const refundExchangePath = process.env.FI_REFUND_REVIEW_EXCHANGE;
  (refundExchangePath ? it : it.skip)('completes same-run refund-review entry, partial payment, balance refresh and top-up through real typed clients', async () => {
    const raw = JSON.parse(readFileSync(refundExchangePath!, 'utf-8')) as Record<string, any>;
    vi.restoreAllMocks();
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue({ items: [{ case_no: raw.case_no, client_name: '測試客戶' }], next_cursor: null, etag: 'c'.repeat(64) } as never);
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({ items: [], next_cursor: null });
    let phase: 'partial' | 'topup' = 'partial';
    let posted = false;
    const get = vi.spyOn(transport, 'get').mockImplementation(async (path: string) => {
      const evidence = raw[phase];
      if (path.endsWith('/correction-outcome')) { posted = true; return evidence.correction.outcome; }
      if (path.endsWith('/batch-outcome')) { posted = true; return evidence.outcome; }
      const state = evidence[posted ? 'after' : 'before'];
      if (path.endsWith('/manifest')) return state.manifest;
      if (path.endsWith('/review-rows')) return state.reviews;
      if (path.includes('/settlement-remediation')) return state.settlement;
      if (path.endsWith('/cash-requirements')) return state.cash;
      throw new Error(`unexpected GET ${path}`);
    });
    const post = vi.spyOn(transport, 'post').mockImplementation(async (path: string) => {
      const evidence = raw[phase];
      if (path.endsWith('/workbooks/ingest')) return evidence.ingestion;
      if (path.endsWith('/batches/preview')) return evidence.preview;
      if (path.endsWith('/corrections/preview')) return evidence.correction.preview;
      if (path.endsWith('/corrections/apply')) return evidence.correction.accepted;
      if (path.endsWith('/batches/apply')) return evidence.accepted;
      throw new Error(`unexpected POST ${path}`);
    });
    window.location.hash = '#finance?tab=bank';
    render(<FinancePage />);
    const workbook = (stage: 'partial' | 'topup') => new File([Uint8Array.from(atob(raw[stage].workbook_base64), char => char.charCodeAt(0))], `${stage}.xlsx`);
    fireEvent.change(screen.getByLabelText('選擇銀行交易明細工作簿'), { target: { files: [workbook('partial')] } });
    fireEvent.click(screen.getByRole('button', { name: '匯入銀行交易明細' }));
    const entry = await screen.findByRole('button', { name: '處理客戶退款' });
    expect(reviewCount()).toBe('1');
    expect(raw.partial.before.manifest.data.review_count).toBe(1);
    fireEvent.click(entry);
    expect(screen.getByLabelText('款項用途')).toHaveValue('client_refund');
    await screen.findByRole('option', { name: `${raw.case_no}｜測試客戶` });
    fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: raw.case_no } });
    fireEvent.click(screen.getByRole('button', { name: '查詢待核銷款項' }));
    fireEvent.click(await screen.findByRole('checkbox', { name: /待退 NT\$ 12,000/ }));
    fireEvent.change(screen.getByLabelText('退款核銷方式'), { target: { value: 'partial' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存更正並核銷' }));
    expect(await screen.findByText('更正已受理，請查詢處理結果；尚未完成核銷。')).toBeInTheDocument();
    const applied = post.mock.calls.find(([path]) => path.endsWith('/corrections/apply'))!;
    expect(applied[1]).toMatchObject({
      row_identity: raw.partial.before.reviews.data.items[0].row_identity,
      classification_type: 'client_refund', allow_partial_refund_recovery: true,
      target_obligation_identities: [raw.partial.before.settlement.data.refund_obligations[0].obligation_identity],
    });
    fireEvent.click(screen.getByRole('button', { name: '重新查詢更正結果' }));
    await waitFor(() => expect(reviewCount()).toBe('0'));
    expect(screen.queryByRole('button', { name: '處理客戶退款' })).not.toBeInTheDocument();
    expect(raw.partial.after.settlement.data.refund_obligations[0].amount_due_ntd).toBe(8000);
    fireEvent.click(screen.getByRole('button', { name: /^付款$/ }));
    fireEvent.change(screen.getByPlaceholderText('受款人或案件編號'), { target: { value: raw.case_no } });
    fireEvent.change(screen.getByLabelText('款項類型'), { target: { value: 'client_refund' } });
    expect(await screen.findByText('NT$ 8,000', { selector: 'td' })).toBeInTheDocument();

    phase = 'topup'; posted = false;
    fireEvent.click(screen.getByRole('button', { name: /^銀行對帳$/ }));
    fireEvent.change(screen.getByLabelText('選擇銀行交易明細工作簿'), { target: { files: [workbook('topup')] } });
    fireEvent.click(screen.getByRole('button', { name: '匯入銀行交易明細' }));
    fireEvent.click(await screen.findByRole('button', { name: '處理客戶退款' }));
    expect(reviewCount()).toBe('1');
    await screen.findByRole('option', { name: `${raw.case_no}｜測試客戶` });
    fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: raw.case_no } });
    fireEvent.click(screen.getByRole('button', { name: '查詢待核銷款項' }));
    fireEvent.click(await screen.findByRole('checkbox', { name: /待退 NT\$ 8,000/ }));
    expect(screen.getByLabelText('退款核銷方式')).toHaveValue('exact');
    fireEvent.click(screen.getByRole('button', { name: '儲存更正並核銷' }));
    expect(await screen.findByText('更正已受理，請查詢處理結果；尚未完成核銷。')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重新查詢更正結果' }));
    await waitFor(() => expect(reviewCount()).toBe('0'));
    expect(screen.queryByRole('button', { name: '處理客戶退款' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^付款$/ }));
    fireEvent.change(screen.getByPlaceholderText('受款人或案件編號'), { target: { value: raw.case_no } });
    fireEvent.change(screen.getByLabelText('款項類型'), { target: { value: 'client_refund' } });
    expect(await screen.findByText('NT$ 0', { selector: 'td' })).toBeInTheDocument();
    expect(screen.getByText('已付款', { selector: 'span' })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('付款狀態'), { target: { value: 'confirmed' } });
    expect(screen.getByText('沒有符合條件的付款項目。')).toBeInTheDocument();
    expect(post.mock.calls.filter(([path]) => path.endsWith('/corrections/apply'))).toHaveLength(2);
    expect(post.mock.calls.filter(([path]) => path.endsWith('/batches/apply'))).toHaveLength(0);
    expect(get.mock.calls.filter(([path]) => path.includes('/settlement-remediation'))).toHaveLength(4);
    window.location.hash = '';
  });

});

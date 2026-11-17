import { readFileSync } from 'node:fs';
/**
 * File: finance_query_page.test.tsx
 * Description: 驗證FinancePage active-tab query budget、server資料與正常單次操作匯入邊界。
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { FinanceWorkbookSnapshot, financeImportMutationClient, type FinanceImportBatchPreview, type FinanceImportBatchOutcome } from '../../../../../../../api/finance_import/finance_import_mutation_client';
import { ordersQueryClient } from '../../../../../../../api/orders/order_query_client';
import { orderCoreStageProjectionClient } from '../../../../../../../api/orders/order_core_stage_projection_client';
import { OrderCoreStageTimelinePageSchema, CORE_STAGE_CODES } from '../../../../../../../api/orders/order_core_stage_projection_schemas';
import { monthlyAccountingClient, type MonthlyAccountingReport } from '../../../../../../../api/finance_import/monthly_accounting_client';
import { financeImportQueryClient } from '../../../../../../../api/finance_import/finance_import_query_client';
import { accountsPayableQueryClient } from '../../../../../../../api/accounts_payable/accounts_payable_query_client';
import { accountsPayableExportClient } from '../../../../../../../api/accounts_payable/accounts_payable_export_client';
import { financeImportBlockerMessage } from '../../../../../../../adapters/finance/finance_import_query_adapter';
import { FinancePage } from '../../../../../../../pages/FinancePage';

const monthlyReport: MonthlyAccountingReport = {
  start_month: '2026-09', end_month: '2026-09', category: 'subsidy', as_of: '2026-09-30',
  excluded_cases: [], undated_item_count: 0,
  rows: [{
    month: '2026-09', expected_in_ntd: 0, received_ntd: 0, remaining_in_ntd: 0,
    expected_out_ntd: 42000, paid_ntd: 0, remaining_out_ntd: 42000,
    other_in_ntd: 0, other_out_ntd: 0, cash_in_ntd: 0, cash_out_ntd: 0, bank_facts: [],
    items: [{
      case_no: 'CASE-FIN-001', client_name: '去敏客戶', identity: 'OBL-S-1', direction: 'payable',
      label: '月嫂薪資', party: '去敏人員', due_date: '2026-09-15',
      expected_ntd: 42000, actual_ntd: 0, noncash_ntd: 0, remaining_ntd: 42000,
    }],
  }],
};

describe('FinancePage query and guarded import presentation', () => {
  afterEach(() => { cleanup(); window.history.replaceState(null, '', '#finance'); vi.unstubAllGlobals(); });
  beforeEach(() => {
    vi.restoreAllMocks();
    window.history.replaceState(null, '', '#finance?subtab=all');
    vi.spyOn(orderCoreStageProjectionClient, 'getCoreStageTimelines').mockResolvedValue(OrderCoreStageTimelinePageSchema.parse({
      items: [], next_cursor: null, etag: 'c'.repeat(64),
      stage_counts: Object.fromEntries(CORE_STAGE_CODES.map(code => [code, 0])),
      substatus_counts: {},
      historical_lifecycle_counts: { unserved: 0, in_service: 0, service_completed: 0, accounting_completed: 0 },
    }));
    vi.spyOn(monthlyAccountingClient, 'query').mockResolvedValue(monthlyReport);
    vi.spyOn(financeImportQueryClient, 'listBankTransactions').mockResolvedValue({ items: [], pending_count: 0, next_before_row_id: null });
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue({ items: [{ case_no: 'CASE-FIN-001', client_name: '去敏客戶', order_status: '服務中', staff_name: null, identity_status: null, start_date: null, end_date: null, actual_start_date: null, actual_end_date: null, service_days: null, total_employer_self_pay_payable: null }], next_cursor: null, etag: 'c'.repeat(64) });
    vi.spyOn(accountsPayableQueryClient, 'query');
  });

  it('maps import blockers to closed operator messages', () => {
    expect(financeImportBlockerMessage(['fingerprint_collision', 'future_blocker']))
      .toBe('存在可能重複的銀行交易、預覽資料仍有待確認項目');
    expect(financeImportBlockerMessage([])).toBe('預覽未通過，請重新檢查。');
  });

  it('keeps sensitive payment fields out of the list and downloads through the authenticated export endpoint', async () => {
    const item = { ...monthlyReport.rows[0].items[0], bank_account: '000012345678', recipient_identity_card: 'MOCK-ID-001' };
    vi.mocked(monthlyAccountingClient.query).mockResolvedValue({
      ...monthlyReport,
      rows: [{ ...monthlyReport.rows[0], items: [item] }],
    });
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('mock-download-token');
    const fetchMock = vi.fn().mockResolvedValue(new Response(new Blob(['mock-xlsx-bytes']), {
      headers: { 'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'content-disposition': 'attachment; filename="mock-payables.xlsx"' },
    }));
    vi.stubGlobal('fetch', fetchMock);
    const createUrl = vi.fn().mockReturnValue('blob:mock-payables');
    vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL: createUrl, revokeObjectURL: vi.fn() }));
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    window.history.replaceState(null, '', '#finance?tab=monthly');
    render(<FinancePage />);
    fireEvent.click(await screen.findByRole('button', { name: '展開明細' }));
    expect(screen.getByText('去敏人員')).toBeVisible();
    expect(screen.queryByText(/000012345678|MOCK-ID-001/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '匯出應付帳款 Excel（會計十欄版）' }));
    fireEvent.change(screen.getByLabelText('選擇出款月份'), { target: { value: '2026-09' } });
    fireEvent.click(screen.getByRole('button', { name: '確認匯出 Excel' }));
    expect(await screen.findByText('已送出下載：mock-payables.xlsx')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/accounts-payable/export?target_month='),
      expect.objectContaining({ headers: { Authorization: 'Bearer mock-download-token' } }));
    expect(createUrl).toHaveBeenCalledTimes(1);
    expect(anchorClick).toHaveBeenCalledTimes(1);
  });

  it('rejects unauthenticated, failed archive, and non-workbook downloads', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(sessionClient, 'getToken').mockReturnValue(null);
    await expect(accountsPayableExportClient.download('2026-09')).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).not.toHaveBeenCalled();
    vi.mocked(sessionClient.getToken).mockReturnValue('mock-token');
    fetchMock.mockResolvedValueOnce(new Response('', { status: 503 }));
    await expect(accountsPayableExportClient.download('2026-09')).rejects.toMatchObject({ status: 503 });
    fetchMock.mockResolvedValueOnce(new Response('{}', { headers: { 'content-type': 'application/json' } }));
    await expect(accountsPayableExportClient.download('2026-09')).rejects.toThrow('下載格式不正確');
  });

  it('loads only the active tab and requires a selected workbook before import controls appear', async () => {
    render(<FinancePage />);
    await screen.findByText('CASE-FIN-001');
    expect(ordersQueryClient.getOrderSummaries).toHaveBeenCalledTimes(1);
    expect(orderCoreStageProjectionClient.getCoreStageTimelines).toHaveBeenCalledTimes(1);
    expect(monthlyAccountingClient.query).not.toHaveBeenCalled();
    expect(financeImportQueryClient.listBankTransactions).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '每月帳務' }));
    expect(await screen.findByRole('button', { name: '匯出應付帳款 Excel（會計十欄版）' })).toBeEnabled();
    expect(monthlyAccountingClient.query).toHaveBeenCalledTimes(1);
    expect(financeImportQueryClient.listBankTransactions).not.toHaveBeenCalled();
    expect(accountsPayableQueryClient.query).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '銀行對帳' }));
    expect(await screen.findByRole('region', { name: '銀行對帳總表' })).toBeVisible();
    expect(financeImportQueryClient.listBankTransactions).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('已載入批次')).not.toBeInTheDocument();
    expect(screen.queryByText('歷史 Reprocess Run（loaded scope）')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '匯入銀行交易明細' })).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="finance.finance-import.apply"]')).toBeNull();
  });

  it.each(['payments', 'staff-payables'])('opens the monthly accounting workspace from the %s link', async tab => {
    window.history.replaceState(null, '', `#finance?tab=${tab}`);
    render(<FinancePage />);
    expect(await screen.findByRole('region', { name: '每月帳務' })).toBeVisible();
    expect(screen.queryByRole('button', { name: '客戶補助退款' })).not.toBeInTheDocument();
    fireEvent.click(await screen.findByRole('button', { name: '匯出應付帳款 Excel（會計十欄版）' }));
    fireEvent.change(screen.getByLabelText('選擇出款月份'), { target: { value: '2026-11' } });
    expect(screen.getByLabelText('選擇出款月份')).toHaveValue('2026-11');
  });

  it('searches all server pages so a new case can be selected for receipt review', async () => {
    render(<FinancePage />);
    await screen.findByText('CASE-FIN-001');

    fireEvent.change(screen.getByLabelText('搜尋案件或對象'), { target: { value: '116990824' } });
    fireEvent.click(screen.getByRole('button', { name: '查詢案件' }));

    await waitFor(() => expect(ordersQueryClient.getOrderSummaries).toHaveBeenLastCalledWith(
      { page_size: 100, query_text: '116990824' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
  });

  it('accumulates every case page for the all-cases workspace', async () => {
    const orderItem = {
      case_no: 'CASE-FIN-001', client_name: '去敏客戶', order_status: '服務中', staff_name: null,
      identity_status: null, start_date: null, end_date: null, actual_start_date: null,
      actual_end_date: null, service_days: null, total_employer_self_pay_payable: null,
    };
    vi.mocked(ordersQueryClient.getOrderSummaries)
      .mockResolvedValueOnce({ items: [orderItem], next_cursor: orderItem.case_no, etag: 'a'.repeat(64) })
      .mockResolvedValueOnce({ items: [{ ...orderItem, case_no: 'CASE-FIN-002', client_name: '第二頁客戶' }], next_cursor: null, etag: 'b'.repeat(64) });
    render(<FinancePage />);
    expect(await screen.findByText('CASE-FIN-001')).toBeVisible();
    expect(screen.getByText('CASE-FIN-002')).toBeVisible();
    expect(screen.getByText('第二頁客戶')).toBeVisible();
    expect(ordersQueryClient.getOrderSummaries).toHaveBeenCalledTimes(2);
  });
});

const IMPORT_FILE = new File(['finance query fixture'], 'finance.xlsx');

async function importPreview(fingerprint = 'b'.repeat(64), file = IMPORT_FILE): Promise<FinanceImportBatchPreview> {
  const snapshot = await FinanceWorkbookSnapshot.fromFile(file);
  return {
    batch_identity: `finance-import-batch:${fingerprint[0]}`, batch_version: 13,
    source_content_digest: snapshot.sha256, classifier_version: 'v1', fingerprint_version: 'v1',
    counts: { source_rows: 10, canonical_created: 10, duplicate_occurrences: 0,
      ready_dispatch: 3, existing: 2, manual_review: 1, business_pending: 4, blocked: 0 },
    dispatch_summaries: [], rows: [], blocking_codes: [], apply_allowed: true,
    preview_fingerprint: fingerprint,
  };
}

function importResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify({ success: true, message: 'ok', data, error: null }), {
    status, headers: { 'content-type': 'application/json' },
  });
}

function installImportHttp(
  plans: FinanceImportBatchPreview[],
  options: {
    loseFirstApply?: boolean;
    firstApplyStatus?: 408 | 429 | 503;
    loseFirstOutcome?: boolean;
    outcomeReceiptOverride?: Partial<NonNullable<FinanceImportBatchOutcome['receipt']>>;
    statuses?: FinanceImportBatchOutcome['status'][];
  } = {},
) {
  const applyRequests: { body: unknown; key: string | null; correlation: string | null }[] = [];
  let index = -1;
  let observed = 0;
  const fetchSpy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path.endsWith('/workbooks/ingest')) {
      const plan = plans[++index];
      return importResponse({ batch_identity: plan.batch_identity, source_content_digest: plan.source_content_digest,
        source_row_count: 10, canonical_created_count: 10, duplicate_occurrence_count: 0,
        source_warning_count: 0, source_warning_created_count: 0, replayed: index > 0 });
    }
    const plan = plans[index];
    if (path.endsWith('/batches/preview')) {
      expect(JSON.parse(String(init?.body))).toEqual({ batch_identity: plan.batch_identity, automatic: true });
      return importResponse(plan);
    }
    if (path.includes('/manifest')) {
      return importResponse({
        batch_id: 901,
        batch_identity: plan.batch_identity,
        format_id: 'fixture',
        source_file: 'finance.xlsx',
        sheet_name: 'Sheet1',
        header_row: 1,
        source_row_count: plan.counts.source_rows,
        status: 'previewed',
        batch_version: plan.batch_version,
        source_content_digest: plan.source_content_digest,
        classifier_version: plan.classifier_version,
        fingerprint_version: plan.fingerprint_version,
        canonical_row_count: plan.counts.canonical_created,
        occurrence_count: plan.counts.source_rows,
        review_count: plan.counts.manual_review,
        dispatch_event_count: 0,
        reconciliation_receipt_count: 0,
        created_at: '2026-09-07T00:00:00+08:00',
        completed_at: null,
      });
    }
    if (path.includes('/review-rows')) {
      return importResponse({
        batch_identity: plan.batch_identity, source_reviews: [], next_after_source_review_id: null,
        items: Array.from({ length: plan.counts.manual_review }, (_, offset) => ({
          row_id: 901 + offset,
          row_identity: `ROW-REVIEW-${901 + offset}`,
          transaction_date: '2026-09-01',
          direction: 'credit',
          amount_ntd: 1000 + offset,
          classification_type: 'client_receipt',
          disposition: 'manual_review',
          reconciliation_status: 'unmatched',
          source_sheet: 'Sheet1',
          source_row: 2 + offset,
          occurrence_count: 1,
          available_actions: [],
          created_at: '2026-09-07T00:00:00+08:00',
        })),
        next_after_row_id: null,
      });
    }
    if (path.endsWith('/batches/apply')) {
      const headers = new Headers(init?.headers);
      applyRequests.push({ body: JSON.parse(String(init?.body)),
        key: headers.get('Idempotency-Key'), correlation: headers.get('X-Correlation-ID') });
      if (options.loseFirstApply && applyRequests.length === 1) throw new TypeError('Failed to fetch');
      if (options.firstApplyStatus && applyRequests.length === 1) {
        return importResponse({ detail: { code: 'finance_import_temporarily_unavailable', message: 'temporary', retryable: true } }, options.firstApplyStatus);
      }
      return importResponse({ job_id: 'finance-test-job', status_url: '/api/v1/jobs/finance-test-job',
        replayed: applyRequests.length > 1 }, 202);
    }
    if (path.endsWith('/jobs/finance-test-job/batch-outcome')) {
      const attempt = observed++;
      if (options.loseFirstOutcome && attempt === 0) throw new TypeError('Failed to fetch');
      const statuses = options.statuses ?? ['succeeded'];
      const status = statuses[Math.min(attempt, statuses.length - 1)];
      return importResponse({ job_id: 'finance-test-job', status, attempt_count: 1, max_attempts: 3,
        result_reference: status === 'succeeded' ? 'finance_import_batch:fixture' : null,
        receipt: status === 'succeeded' ? { batch_identity: plan.batch_identity,
          resulting_batch_version: 14, preview_fingerprint: plan.preview_fingerprint,
          reconciled_count: 3, existing_count: 2, pending_count: 5,
          ...options.outcomeReceiptOverride } : null });
    }
    throw new Error(`Unexpected Finance test request: ${path}`);
  });
  vi.stubGlobal('fetch', fetchSpy);
  return { applyRequests, fetchSpy };
}

async function importWorkbook(file = IMPORT_FILE): Promise<void> {
  const preview = vi.spyOn(financeImportMutationClient, 'preview');
  const previousCalls = preview.mock.calls.length;
  if (!screen.queryByRole('button', { name: '匯入銀行交易明細' })) {
    fireEvent.click(screen.getByRole('button', { name: '匯入永豐對帳單' }));
  }
  fireEvent.change(screen.getByLabelText('選擇銀行交易明細工作簿'), { target: { files: [file] } });
  fireEvent.click(screen.getByRole('button', { name: '匯入銀行交易明細' }));
  await waitFor(() => expect(preview).toHaveBeenCalledTimes(previousCalls + 1));
  await expect(preview.mock.results[previousCalls].value).resolves.toMatchObject({ batch_identity: expect.any(String) });
}

function assertPreviewCounts(plan: Pick<FinanceImportBatchPreview, 'counts'>, reviewCount: number): void {
  const summary = document.querySelector('.finance-scope-note');
  expect(summary).toHaveTextContent(`可自動入帳 ${plan.counts.ready_dispatch}`);
  expect(summary).toHaveTextContent(`已存在 ${plan.counts.existing}`);
  expect(summary).toHaveTextContent(`需人工處理 ${reviewCount}`);
  expect(summary).toHaveTextContent(`待業務配對 ${plan.counts.business_pending}`);
  expect(summary).toHaveTextContent(`阻擋 ${plan.counts.blocked}`);
}

describe('Finance import preview and replay boundary', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.history.replaceState(null, '', '#finance');
    sessionClient.setSession('finance-test-session', { id: 7, username: 'finance-test', display_name: 'Test', role: 'admin' });
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue({ items: [], next_cursor: null, etag: 'a'.repeat(64) });
    vi.spyOn(financeImportQueryClient, 'listBankTransactions').mockResolvedValue({ items: [], pending_count: 0, next_before_row_id: null });
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    sessionClient.clearSession();
  });

  it('uses one click and forwards unchanged Preview values without asking for a reason', async () => {
    const plan = await importPreview();
    const { applyRequests } = installImportHttp([plan]);
    const previewSpy = vi.spyOn(financeImportMutationClient, 'preview');
    window.history.replaceState(null, '', '#finance?tab=finance-import');
    render(<FinancePage />);
    await importWorkbook();
    await screen.findByText(/本次自動核銷 3 筆/);
    expect(previewSpy).toHaveBeenCalledOnce();
    await expect(previewSpy.mock.results[0].value).resolves.toEqual(plan);
    expect(screen.getByText(/新增流水 10 筆.*重複來源列 0 筆/)).toBeVisible();
    expect(applyRequests).toHaveLength(1);
    expect(applyRequests[0].body).toEqual({ batch_identity: plan.batch_identity,
      expected_batch_version: plan.batch_version, preview_fingerprint: plan.preview_fingerprint, reason: '', automatic: true });
    const workflow = document.querySelector<HTMLElement>('[data-surface-id="finance.finance-import.upload-panel"]');
    expect(workflow).not.toBeNull();
    expect(within(workflow!).queryByRole('checkbox')).not.toBeInTheDocument();
    expect(within(workflow!).queryByLabelText(/入帳原因/)).not.toBeInTheDocument();
  });

  it.each(['blocked', 'no-ready-rows'] as const)('does not submit %s', async policy => {
    const plan = await importPreview();
    if (policy === 'blocked') { plan.apply_allowed = false; plan.blocking_codes = ['fingerprint_collision']; plan.counts.blocked = 2; }
    else plan.counts.ready_dispatch = 0;
    const { applyRequests } = installImportHttp([plan]);
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行對帳' }));
    await importWorkbook();
    await screen.findByText(/本次自動核銷 0 筆/);
    if (policy === 'blocked') expect(screen.getByText(/自動核銷受阻：存在可能重複的銀行交易/)).toBeVisible();
    expect(applyRequests).toHaveLength(0);
  });

  it('retries a lost response with the same command and locks the original file', async () => {
    const { applyRequests } = installImportHttp([await importPreview()], { loseFirstApply: true });
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行對帳' }));
    await importWorkbook();
    const retry = await screen.findByRole('button', { name: '以原操作確認匯入結果' });
    expect(screen.getByLabelText('選擇銀行交易明細工作簿')).toBeDisabled();
    fireEvent.click(retry);
    await screen.findByText(/本次自動核銷 3 筆/);
    expect(applyRequests).toHaveLength(2);
    expect(applyRequests[1]).toEqual(applyRequests[0]);
  });

  it('explains pending subsidy funding and does not submit an ineligible payout', async () => {
    const plan = await importPreview();
    plan.counts.ready_dispatch = 0;
    plan.rows = [{ row_identity: 'finance-import-row:1', canonical_fact_version: 0,
      amount_ntd: 12000, classification_type: 'client_subsidy_return', disposition: 'business_pending',
      target_identities: ['client:7'], evidence: ['subsidy_advance_not_due'], pending_reason: 'subsidy_advance_not_due', available_actions: [],
      integrity_violations: [], fingerprint_collision: false, formal_reference_conflict: false }];
    const { applyRequests } = installImportHttp([plan]);
    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({
      pending_count: 1, next_before_row_id: null, items: [{
        row_id: 1, row_identity: plan.rows[0].row_identity, transaction_date: '2026-09-02',
        bank: 'taishin', direction: 'outgoing', amount_ntd: 12000,
        classification_type: 'client_subsidy_return', status: 'pending', disposition: 'business_pending',
        review_reason: null, recorded_pending_reason: 'subsidy_advance_not_due', available_actions: [],
        reference: 'S-001', counterparty_name: null, cases: [],
      }],
    });
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行對帳' }));
    await importWorkbook();
    await screen.findByText(/早於本筆正式到期日/);
    expect(applyRequests).toHaveLength(0);
  });

  it('allows a new workbook only after the previous result is known', async () => {
    const other = new File(['other finance fixture'], 'other.xlsx');
    const { applyRequests } = installImportHttp([await importPreview(), await importPreview('c'.repeat(64), other)]);
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行對帳' }));
    await importWorkbook();
    await screen.findByText(/本次自動核銷 3 筆/);
    expect(screen.getByLabelText('選擇銀行交易明細工作簿')).toBeEnabled();
    fireEvent.change(screen.getByLabelText('選擇銀行交易明細工作簿'), { target: { files: [other] } });
    fireEvent.click(screen.getByRole('button', { name: '匯入銀行交易明細' }));
    await waitFor(() => expect(applyRequests).toHaveLength(2));
    expect(applyRequests[1].body).toMatchObject({ batch_identity: 'finance-import-batch:c', reason: '' });
    expect(applyRequests[1].key).not.toBe(applyRequests[0].key);
    await screen.findByText(/本次自動核銷 3 筆/);
  });

  it('does not show completion while queued or running', async () => {
    const { applyRequests, fetchSpy } = installImportHttp([await importPreview()], { statuses: ['queued', 'running', 'succeeded'] });
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行對帳' }));
    await importWorkbook();
    await waitFor(() => expect(fetchSpy.mock.calls.filter(([path]) => String(path).endsWith('/batch-outcome'))).toHaveLength(1));
    expect(screen.queryByText(/本次自動核銷 3 筆/)).not.toBeInTheDocument();
    await screen.findByText(/本次自動核銷 3 筆/, {}, { timeout: 3000 });
    expect(fetchSpy.mock.calls.filter(([path]) => String(path).endsWith('/batch-outcome'))).toHaveLength(3);
    expect(applyRequests).toHaveLength(1);
  });

  it.each(['failed', 'cancelled'] as const)('%s never becomes a successful receipt', async status => {
    installImportHttp([await importPreview()], { statuses: [status] });
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行對帳' }));
    await importWorkbook();
    await screen.findByText('未完成銷帳，請查看未銷帳明細與原因。');
    expect(screen.getByRole('region', { name: '銀行對帳總表' })).toBeVisible();
    expect(screen.queryByText(/本次自動核銷 3 筆/)).not.toBeInTheDocument();
  });

  it.each([{ batch_identity: 'another-batch' }, { preview_fingerprint: 'f'.repeat(64) }])('rejects a terminal receipt with mismatched identity %j', async outcomeReceiptOverride => {
    installImportHttp([await importPreview()], { outcomeReceiptOverride });
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行對帳' }));
    await importWorkbook();
    await screen.findByText('匯入結果與原批次預覽不一致；請勿重新提交，請重新查詢結果。');
    expect(screen.queryByText(/本次自動核銷 3 筆/)).not.toBeInTheDocument();
  });

  it('queries an uncertain outcome without submitting another Apply', async () => {
    const { applyRequests } = installImportHttp([await importPreview()], { loseFirstOutcome: true });
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行對帳' }));
    await importWorkbook();
    fireEvent.click(await screen.findByRole('button', { name: '重新查詢匯入結果' }));
    await screen.findByText(/本次自動核銷 3 筆/);
    expect(applyRequests).toHaveLength(1);
  });

  // Supplied only by the append-only Python test; normal React CI does not claim MySQL coverage.
  it.skipIf(!process.env.FI_PREVIEW_EXCHANGE)('same-run MySQL Preview reaches the real client and rendered panel unchanged', async () => {
    const exchange = JSON.parse(readFileSync(process.env.FI_PREVIEW_EXCHANGE!, 'utf8')) as {
      workbook_path: string; ingestion_response: { data: unknown };
      preview_response: { data: FinanceImportBatchPreview };
      manifest_response: { data: { review_count: number } }; review_response: { data: { items: unknown[] } };
      expected: Pick<FinanceImportBatchPreview, 'batch_version' | 'preview_fingerprint' | 'counts' | 'blocking_codes'>;
    };
    const bytes = new Uint8Array(readFileSync(exchange.workbook_path));
    const file = new File([bytes], 'mysql-preview.xlsx');
    const snapshot = await FinanceWorkbookSnapshot.fromFile(file);
    expect(snapshot.sha256).toBe(exchange.preview_response.data.source_content_digest);
    const requests: string[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      requests.push(path);
      if (path === '/api/v1/staff/summaries?page_size=200') return importResponse({ items: [], next_cursor: null });
      if (path.endsWith('/workbooks/ingest')) return importResponse(exchange.ingestion_response.data);
      if (path.endsWith('/batches/preview')) return importResponse(exchange.preview_response.data);
      if (path.includes('/manifest')) return importResponse(exchange.manifest_response.data);
      if (path.includes('/review-rows')) return importResponse(exchange.review_response.data);
      throw new Error(`Unexpected request in Preview-only proof: ${path}`);
    }));
    vi.spyOn(financeImportMutationClient, 'apply').mockResolvedValue({ job_id: 'preview-proof', status_url: '/api/v1/jobs/preview-proof', replayed: false });
    vi.spyOn(financeImportMutationClient, 'queryBatchOutcome').mockResolvedValue({ job_id: 'preview-proof', status: 'cancelled', attempt_count: 0, max_attempts: 1, result_reference: null, receipt: null });
    const previewSpy = vi.spyOn(financeImportMutationClient, 'preview');
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行對帳' }));
    await importWorkbook(file);
    expect(previewSpy).toHaveBeenCalledOnce();
    const decoded = await previewSpy.mock.results[0].value;
    expect(decoded).toEqual(exchange.preview_response.data);
    expect(decoded).toMatchObject(exchange.expected);
    // The worklist excludes unmatched bank facts; the untouched Preview still
    // describes every staged row. Read the displayed count from the real query.
    expect(exchange.review_response.data.items).toHaveLength(exchange.manifest_response.data.review_count);
    assertPreviewCounts(exchange.expected, exchange.manifest_response.data.review_count);
    if (!exchange.preview_response.data.apply_allowed) {
      expect(screen.getByText(new RegExp(financeImportBlockerMessage(exchange.expected.blocking_codes)))).toBeInTheDocument();
    }
    const importRequests = requests.filter((path) => path.startsWith('/api/v1/finance-import/'));
    expect(requests.filter((path) => !path.startsWith('/api/v1/finance-import/'))).toEqual(['/api/v1/staff/summaries?page_size=200']);
    expect(importRequests.slice(0, 2)).toEqual(['/api/v1/finance-import/workbooks/ingest', '/api/v1/finance-import/batches/preview']);
    const batchPath = `/api/v1/finance-import/batches/${encodeURIComponent(exchange.preview_response.data.batch_identity)}`;
    expect(importRequests.slice(2, 4)).toEqual([`${batchPath}/manifest`, `${batchPath}/review-rows?limit=50`]);
    expect(screen.queryByText(/匯入完成：核銷/)).not.toBeInTheDocument();
  });
});

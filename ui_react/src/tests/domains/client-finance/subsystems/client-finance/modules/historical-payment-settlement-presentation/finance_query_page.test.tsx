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
import { staffDirectoryClient } from '../../../../../../../api/staff_directory/staff_directory_client';
import { clientReceiptQueryClient } from '../../../../../../../api/client_finance/client_receipt_query_client';
import { staffPayablesQueryClient } from '../../../../../../../api/staff_payables/staff_payables_query_client';
import { accountsPayableQueryClient } from '../../../../../../../api/accounts_payable/accounts_payable_query_client';
import { accountsPayableExportClient } from '../../../../../../../api/accounts_payable/accounts_payable_export_client';
import { cashRequirementsQueryClient } from '../../../../../../../api/accounts_payable/cash_requirements_query_client';
import { clientFinanceHistoryClient } from '../../../../../../../api/client_finance/client_finance_history_client';
import { clientSubsidyReturnQueryClient } from '../../../../../../../api/client_finance/client_subsidy_return_query_client';
import { financeImportBlockerMessage } from '../../../../../../../adapters/finance/finance_import_query_adapter';
import { FinancePage } from '../../../../../../../pages/FinancePage';
import { RECEIPT_RESPONSE, STAFF_PAYABLES_RESPONSE, ACCOUNTS_PAYABLE_RESPONSE } from '../../../../../../fixtures/finance/finance_query_contract_fixtures';

describe('FinancePage query and guarded import presentation', () => {
  afterEach(() => { cleanup(); window.location.hash = ''; vi.unstubAllGlobals(); });
  beforeEach(() => {
    vi.restoreAllMocks();
    window.location.hash = '#finance?tab=client-receipts&case_no=CASE-FIN-001';
    vi.spyOn(clientFinanceHistoryClient, 'query').mockResolvedValue({ case_no: 'CASE-FIN-001', account_version: '0', obligations: [], ledger_entries: [] });
    vi.spyOn(cashRequirementsQueryClient, 'queryAll').mockResolvedValue([]);
    vi.spyOn(clientSubsidyReturnQueryClient, 'query').mockResolvedValue({ rows: [], next_cursor: null });
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue({ items: [{ case_no: 'CASE-FIN-001', client_name: '去敏客戶', order_status: '服務中', staff_name: null, identity_status: null, start_date: null, end_date: null, actual_start_date: null, actual_end_date: null, service_days: null, total_employer_self_pay_payable: null }], next_cursor: null, etag: 'c'.repeat(64) });
    vi.spyOn(ordersQueryClient, 'getAssignmentPlan').mockResolvedValue({
      case_no: 'CASE-FIN-001', order_version: 1, scheduling_version: 1,
      scheduling_generation: 1, client_finance_version: 1, payroll_version: 1,
      contracted_service_days: 1, service_hours_per_day: 8, service_started: true,
      assignments: [{
        sequence: 1, staff_id: 11, assignment_id: 101, actual_hours: 8,
        assigned_start_date: '2026-09-01', assigned_end_date: '2026-09-01',
        official_service_dates: ['2026-09-01'], candidate_key: null,
        lineage_source_assignment_ids: [],
      }],
    });
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({ items: [{ id: 11, name: '去敏人員', phone: null, education: null }], next_cursor: null });
    vi.spyOn(clientReceiptQueryClient, 'query').mockResolvedValue(RECEIPT_RESPONSE.data);
    vi.spyOn(staffPayablesQueryClient, 'query').mockResolvedValue(STAFF_PAYABLES_RESPONSE.data);
    vi.spyOn(accountsPayableQueryClient, 'query').mockResolvedValue(ACCOUNTS_PAYABLE_RESPONSE.data);
    vi.spyOn(accountsPayableQueryClient, 'queryCase').mockResolvedValue({
      case_no: 'CASE-FIN-001',
      target_payment_date: '2026-09-15',
      items: [{
        case_no: 'CASE-FIN-001', staff_id: 11, recipient_name: '去敏人員',
        obligation_identity: 'OBL-S-1', amount_due_ntd: 42000, balance_ntd: 42000,
        order_due_date: '2026-10-15', effective_due_date: '2026-10-15',
        source: 'formal_obligation', disposition: 'other_month',
        reason: '案件屬於其他付款月份。',
      }],
    });
  });

  it('maps import blockers to closed operator messages', () => {
    expect(financeImportBlockerMessage(['fingerprint_collision', 'future_blocker']))
      .toBe('存在可能重複的銀行交易、預覽資料仍有待確認項目');
    expect(financeImportBlockerMessage([])).toBe('預覽未通過，請重新檢查。');
  });

  it('keeps sensitive payment fields out of the list and downloads through the authenticated export endpoint', async () => {
    const data = ACCOUNTS_PAYABLE_RESPONSE.data;
    vi.mocked(accountsPayableQueryClient.query).mockResolvedValue({ ...data, rows: data.rows.map(row => ({
      ...row, bank_account: '000012345678', recipient_identity_card: 'MOCK-ID-001',
    })) });
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('mock-download-token');
    const fetchMock = vi.fn().mockResolvedValue(new Response(new Blob(['mock-xlsx-bytes']), {
      headers: { 'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'content-disposition': 'attachment; filename="mock-payables.xlsx"' },
    }));
    vi.stubGlobal('fetch', fetchMock);
    const createUrl = vi.fn().mockReturnValue('blob:mock-payables');
    vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL: createUrl, revokeObjectURL: vi.fn() }));
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '付款' }));
    await screen.findByRole('region', { name: '付款清單' });
    expect(screen.queryByText(/000012345678|MOCK-ID-001/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '下載應付帳款 Excel' }));
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
    await waitFor(() => expect(document.querySelector('[data-obligation-id="OBL-C-1"]')).toBeInTheDocument());
    expect(ordersQueryClient.getOrderSummaries).toHaveBeenCalledTimes(1);
    expect(clientReceiptQueryClient.query).toHaveBeenCalledTimes(1);
    const casePayable = await screen.findByRole('region', { name: '本案月嫂應付查核' });
    expect(casePayable).toHaveTextContent('NT$ 42,000');
    expect(Array.from(casePayable.querySelectorAll('th')).map(item => item.textContent)).toEqual(['月嫂', '應付', '待付', '應付日期']);
    expect(casePayable).not.toHaveTextContent('已建立的應付項目');
    expect(casePayable).not.toHaveTextContent('案件屬於其他付款月份。');
    expect(screen.getByText('此為正常案件；歷史人工收款確認只會在歷史案件顯示。')).toBeInTheDocument();
    expect(screen.queryByText(/Account Version|Account version/)).not.toBeInTheDocument();
    expect(staffDirectoryClient.queryPage).not.toHaveBeenCalled();
    expect(screen.queryByText(/未開放/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '付款' }));
    fireEvent.click(screen.getByRole('button', { name: '人員與歷史付款' }));
    await waitFor(() => expect(document.querySelector('[data-obligation-id="OBL-S-1"]')).toBeInTheDocument());
    expect(screen.getByRole('columnheader', { name: '應付日' })).toBeInTheDocument();
    expect(staffDirectoryClient.queryPage).toHaveBeenCalledTimes(1);
    expect(staffPayablesQueryClient.query).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/^Version$|｜Version/)).not.toBeInTheDocument();
    expect(screen.queryByText(/未開放/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '付款' }));
    await waitFor(() => expect(cashRequirementsQueryClient.queryAll).toHaveBeenCalledTimes(1));
    expect(accountsPayableQueryClient.query).not.toHaveBeenCalled();
    expect(screen.queryByText('123456789012')).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="finance.accounts-payable.export-xlsx"]')).toBeEnabled();
    expect(screen.queryByText(/敏感資料已遮罩|去敏保護啟用/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '銀行對帳' }));
    expect(screen.getByRole('heading', { name: '銀行對帳' })).toBeInTheDocument();
    expect(screen.queryByText('已載入批次')).not.toBeInTheDocument();
    expect(screen.queryByText('歷史 Reprocess Run（loaded scope）')).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="finance.finance-import.upload"]')).toBeDisabled();
    expect(document.querySelector('[data-control-id="finance.finance-import.apply"]')).toBeNull();
  });

  it('merges old subsidy/payable deep links into the payment workspace', async () => {
    window.location.hash = '#finance?tab=cross-order';
    render(<FinancePage />);
    expect(await screen.findByRole('region', { name: '付款清單' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '客戶補助退款' })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('會計清冊月份'), { target: { value: '2026-11' } });
    expect(screen.getByLabelText('會計清冊月份')).toHaveValue('2026-11');
  });

  it('searches all server pages so a new case can be selected for receipt review', async () => {
    render(<FinancePage />);
    await waitFor(() => expect(document.querySelector('[data-obligation-id="OBL-C-1"]')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText('搜尋案件'), { target: { value: '116990824' } });

    await waitFor(() => expect(ordersQueryClient.getOrderSummaries).toHaveBeenLastCalledWith(
      { page_size: 200, query_text: '116990824' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
  });

  it('accumulates every case and staff page for finance selectors', async () => {
    const orderItem = {
      case_no: 'CASE-FIN-001', client_name: '去敏客戶', order_status: '服務中', staff_name: null,
      identity_status: null, start_date: null, end_date: null, actual_start_date: null,
      actual_end_date: null, service_days: null, total_employer_self_pay_payable: null,
    };
    vi.mocked(ordersQueryClient.getOrderSummaries)
      .mockResolvedValueOnce({ items: [orderItem], next_cursor: orderItem.case_no, etag: 'a'.repeat(64) })
      .mockResolvedValueOnce({ items: [{ ...orderItem, case_no: 'CASE-FIN-002', client_name: '第二頁客戶' }], next_cursor: null, etag: 'b'.repeat(64) });
    vi.mocked(staffDirectoryClient.queryPage)
      .mockResolvedValueOnce({ items: [{ id: 11, union_no: 'A10', name: '第一頁人員', phone: null, education: null }], next_cursor: 11 })
      .mockResolvedValueOnce({ items: [{ id: 12, union_no: 'A2', name: '第二頁人員', phone: null, education: null }], next_cursor: null });

    render(<FinancePage />);
    expect(await screen.findByRole('option', { name: /CASE-FIN-002｜第二頁客戶/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '付款' }));
    fireEvent.click(screen.getByRole('button', { name: '人員與歷史付款' }));
    expect(await screen.findByRole('option', { name: 'A2 第二頁人員' })).toBeInTheDocument();
    expect(Array.from((screen.getByRole('option', { name: 'A2 第二頁人員' }).parentElement as HTMLSelectElement).options).filter(option => option.value).map(option => option.textContent)).toEqual(['A2 第二頁人員', 'A10 第一頁人員']);
    expect(staffDirectoryClient.queryPage).toHaveBeenCalledTimes(2);
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
      expect(JSON.parse(String(init?.body))).toEqual({ batch_identity: plan.batch_identity });
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
  fireEvent.change(screen.getByLabelText('選擇銀行交易明細工作簿'), { target: { files: [file] } });
  fireEvent.click(screen.getByRole('button', { name: '匯入銀行交易明細' }));
  await waitFor(() => expect(document.querySelector('.finance-scope-note')).toHaveTextContent(/需人工處理 \d+/));
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
    sessionClient.setSession('finance-test-session', { id: 7, username: 'finance-test', display_name: 'Test', role: 'admin' });
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue({ items: [], next_cursor: null, etag: 'a'.repeat(64) });
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    sessionClient.clearSession();
  });

  it('uses one click and forwards unchanged Preview values with an optional blank reason', async () => {
    const plan = await importPreview();
    const { applyRequests } = installImportHttp([plan]);
    const previewSpy = vi.spyOn(financeImportMutationClient, 'preview');
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行對帳' }));
    await importWorkbook();
    await screen.findByText('匯入完成：核銷 3、既有 2、待處理 5');
    expect(previewSpy).toHaveBeenCalledOnce();
    await expect(previewSpy.mock.results[0].value).resolves.toEqual(plan);
    assertPreviewCounts(plan, plan.counts.manual_review);
    expect(applyRequests).toHaveLength(1);
    expect(applyRequests[0].body).toEqual({ batch_identity: plan.batch_identity,
      expected_batch_version: plan.batch_version, preview_fingerprint: plan.preview_fingerprint, reason: '' });
    const workflow = document.querySelector<HTMLElement>('[data-surface-id="finance.finance-import.workflow"]');
    expect(workflow).not.toBeNull();
    expect(within(workflow!).queryByRole('checkbox')).not.toBeInTheDocument();
  });

  it.each(['blocked', 'no-ready-rows'] as const)('does not submit %s', async policy => {
    const plan = await importPreview();
    if (policy === 'blocked') { plan.apply_allowed = false; plan.blocking_codes = ['fingerprint_collision']; plan.counts.blocked = 2; }
    else plan.counts.ready_dispatch = 0;
    const { applyRequests } = installImportHttp([plan]);
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行對帳' }));
    await importWorkbook();
    assertPreviewCounts(plan, plan.counts.manual_review);
    if (policy === 'blocked') expect(screen.getByText(/目前不可匯入：存在可能重複的銀行交易/)).toBeInTheDocument();
    expect(applyRequests).toHaveLength(0);
  });

  it('retries a lost response with the same command and locks its original reason and file', async () => {
    const { applyRequests } = installImportHttp([await importPreview()], { loseFirstApply: true });
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行對帳' }));
    fireEvent.change(screen.getByLabelText('正式入帳原因（選填）'), { target: { value: '原始原因' } });
    await importWorkbook();
    const retry = await screen.findByRole('button', { name: '以原操作確認匯入結果' });
    expect(screen.getByLabelText('正式入帳原因（選填）')).toBeDisabled();
    expect(screen.getByLabelText('正式入帳原因（選填）')).toHaveValue('原始原因');
    expect(screen.getByLabelText('選擇銀行交易明細工作簿')).toBeDisabled();
    fireEvent.click(retry);
    await screen.findByText('匯入完成：核銷 3、既有 2、待處理 5');
    expect(applyRequests).toHaveLength(2);
    expect(applyRequests[1]).toEqual(applyRequests[0]);
  });

  it('explains pending subsidy funding and does not submit an ineligible payout', async () => {
    const plan = await importPreview();
    plan.counts.ready_dispatch = 0;
    plan.rows = [{ row_identity: 'finance-import-row:1', canonical_fact_version: 0,
      amount_ntd: 12000, classification_type: 'client_subsidy_return', disposition: 'business_pending',
      target_identities: ['client:7'], evidence: ['subsidy_advance_not_due'], available_actions: [],
      integrity_violations: [], fingerprint_collision: false, formal_reference_conflict: false }];
    const { applyRequests } = installImportHttp([plan]);
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行對帳' }));
    await importWorkbook();
    await screen.findByText('補助退款尚未符合政府入款或工會代墊條件，已保留待處理。');
    expect(applyRequests).toHaveLength(0);
  });

  it('allows a new workbook only after the previous result is known', async () => {
    const other = new File(['other finance fixture'], 'other.xlsx');
    const { applyRequests } = installImportHttp([await importPreview(), await importPreview('c'.repeat(64), other)]);
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行對帳' }));
    await importWorkbook();
    await screen.findByText('匯入完成：核銷 3、既有 2、待處理 5');
    expect(screen.getByLabelText('選擇銀行交易明細工作簿')).toBeEnabled();
    fireEvent.change(screen.getByLabelText('選擇銀行交易明細工作簿'), { target: { files: [other] } });
    expect(screen.getByLabelText('正式入帳原因（選填）')).toBeEnabled();
    fireEvent.change(screen.getByLabelText('正式入帳原因（選填）'), { target: { value: '第二批原因' } });
    fireEvent.click(screen.getByRole('button', { name: '匯入銀行交易明細' }));
    await waitFor(() => expect(applyRequests).toHaveLength(2));
    expect(applyRequests[1].body).toMatchObject({ reason: '第二批原因' });
    expect(applyRequests[1].key).not.toBe(applyRequests[0].key);
    await screen.findByText('匯入完成：核銷 3、既有 2、待處理 5');
  });

  it('does not show completion while queued or running', async () => {
    const { applyRequests, fetchSpy } = installImportHttp([await importPreview()], { statuses: ['queued', 'running', 'succeeded'] });
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行對帳' }));
    await importWorkbook();
    await screen.findByText('正在完成匯入，系統會自動顯示正式結果。');
    expect(screen.queryByText(/匯入完成：核銷/)).not.toBeInTheDocument();
    await screen.findByText('匯入完成：核銷 3、既有 2、待處理 5', {}, { timeout: 3000 });
    expect(fetchSpy.mock.calls.filter(([path]) => String(path).endsWith('/batch-outcome'))).toHaveLength(3);
    expect(applyRequests).toHaveLength(1);
  });

  it.each(['failed', 'cancelled'] as const)('%s never becomes a successful receipt', async status => {
    installImportHttp([await importPreview()], { statuses: [status] });
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行對帳' }));
    await importWorkbook();
    await screen.findByText('未完成正式入帳；請查看本頁人工核對清單，確認原因後重新選檔匯入。');
    expect(document.getElementById('finance-import-review')).toBeInTheDocument();
    expect(screen.queryByText(/匯入完成：核銷/)).not.toBeInTheDocument();
  });

  it.each([{ batch_identity: 'another-batch' }, { preview_fingerprint: 'f'.repeat(64) }])('rejects a terminal receipt with mismatched identity %j', async outcomeReceiptOverride => {
    installImportHttp([await importPreview()], { outcomeReceiptOverride });
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行對帳' }));
    await importWorkbook();
    await screen.findByText('匯入結果與原批次預覽不一致；請勿重新提交，請重新查詢結果。');
    expect(screen.queryByText(/匯入完成：核銷/)).not.toBeInTheDocument();
  });

  it('queries an uncertain outcome without submitting another Apply', async () => {
    const { applyRequests } = installImportHttp([await importPreview()], { loseFirstOutcome: true });
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行對帳' }));
    await importWorkbook();
    fireEvent.click(await screen.findByRole('button', { name: '重新查詢匯入結果' }));
    await screen.findByText('匯入完成：核銷 3、既有 2、待處理 5');
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

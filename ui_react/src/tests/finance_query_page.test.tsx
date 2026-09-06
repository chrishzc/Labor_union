/**
 * File: finance_query_page.test.tsx
 * Description: 驗證FinancePage active-tab query budget、server資料與正常三步匯入邊界。
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { sessionClient } from '../api/auth/session_client';
import { FinanceWorkbookSnapshot, financeImportMutationClient, type FinanceImportBatchPreview, type FinanceImportBatchOutcome } from '../api/finance_import/finance_import_mutation_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { clientReceiptQueryClient } from '../api/client_finance/client_receipt_query_client';
import { staffPayablesQueryClient } from '../api/staff_payables/staff_payables_query_client';
import { accountsPayableQueryClient } from '../api/accounts_payable/accounts_payable_query_client';
import { financeImportBlockerMessage } from '../adapters/finance/finance_import_query_adapter';
import { FinancePage } from '../pages/FinancePage';
import { RECEIPT_RESPONSE, STAFF_PAYABLES_RESPONSE, ACCOUNTS_PAYABLE_RESPONSE } from './fixtures/finance/finance_query_contract_fixtures';

describe('FinancePage query and guarded import presentation', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue({ items: [{ case_no: 'CASE-FIN-001', client_name: '去敏客戶', order_status: '服務中', staff_name: null, identity_status: null, start_date: null, end_date: null, actual_start_date: null, actual_end_date: null, service_days: null, total_employer_self_pay_payable: null }], next_cursor: null, etag: 'c'.repeat(64) });
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({ items: [{ id: 11, name: '去敏人員', phone: null, education: null }], next_cursor: null });
    vi.spyOn(clientReceiptQueryClient, 'query').mockResolvedValue(RECEIPT_RESPONSE.data);
    vi.spyOn(staffPayablesQueryClient, 'query').mockResolvedValue(STAFF_PAYABLES_RESPONSE.data);
    vi.spyOn(accountsPayableQueryClient, 'query').mockResolvedValue(ACCOUNTS_PAYABLE_RESPONSE.data);
  });

  it('maps import blockers to closed operator messages', () => {
    expect(financeImportBlockerMessage(['fingerprint_collision', 'future_blocker']))
      .toBe('存在可能重複的銀行交易、預覽資料仍有待確認項目');
    expect(financeImportBlockerMessage([])).toBe('預覽未通過，請重新檢查。');
  });

  it('loads only the active tab and requires a selected workbook before import controls appear', async () => {
    render(<FinancePage />);
    await waitFor(() => expect(screen.getByText('OBL-C-1')).toBeInTheDocument());
    expect(ordersQueryClient.getOrderSummaries).toHaveBeenCalledTimes(1);
    expect(clientReceiptQueryClient.query).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/Account Version|Account version/)).not.toBeInTheDocument();
    expect(staffDirectoryClient.queryPage).not.toHaveBeenCalled();
    expect(screen.queryByText(/未開放/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '月嫂應付款' }));
    await waitFor(() => expect(screen.getByText('OBL-S-1')).toBeInTheDocument());
    expect(staffDirectoryClient.queryPage).toHaveBeenCalledTimes(1);
    expect(staffPayablesQueryClient.query).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/^Version$|｜Version/)).not.toBeInTheDocument();
    expect(screen.queryByText(/未開放/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '應付帳款' }));
    await waitFor(() => expect(screen.getByText(/\*{8}9012/)).toBeInTheDocument());
    expect(accountsPayableQueryClient.query).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('123456789012')).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="finance.accounts-payable.export-xlsx"]')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '銀行流水匯入' }));
    expect(screen.getByText('上傳檔案 → 預覽 → 匯入完成')).toBeInTheDocument();
    expect(screen.queryByText('已載入批次')).not.toBeInTheDocument();
    expect(screen.queryByText('歷史 Reprocess Run（loaded scope）')).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="finance.finance-import.upload"]')).toBeDisabled();
    expect(document.querySelector('[data-control-id="finance.finance-import.apply"]')).toBeNull();
  });

  it('searches all server pages so a new case can be selected for receipt review', async () => {
    render(<FinancePage />);
    await waitFor(() => expect(screen.getByText('OBL-C-1')).toBeInTheDocument());

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
      .mockResolvedValueOnce({ items: [{ id: 11, name: '第一頁人員', phone: null, education: null }], next_cursor: 11 })
      .mockResolvedValueOnce({ items: [{ id: 12, name: '第二頁人員', phone: null, education: null }], next_cursor: null });

    render(<FinancePage />);
    expect(await screen.findByRole('option', { name: /CASE-FIN-002｜第二頁客戶/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '月嫂應付款' }));
    expect(await screen.findByRole('option', { name: '第二頁人員' })).toBeInTheDocument();
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
  options: { loseFirstApply?: boolean; statuses?: FinanceImportBatchOutcome['status'][] } = {},
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
    if (path.endsWith('/batches/apply')) {
      const headers = new Headers(init?.headers);
      applyRequests.push({ body: JSON.parse(String(init?.body)),
        key: headers.get('Idempotency-Key'), correlation: headers.get('X-Correlation-ID') });
      if (options.loseFirstApply && applyRequests.length === 1) throw new TypeError('Failed to fetch');
      return importResponse({ job_id: 'finance-test-job', status_url: '/api/v1/jobs/finance-test-job',
        replayed: applyRequests.length > 1 }, 202);
    }
    if (path.endsWith('/jobs/finance-test-job/batch-outcome')) {
      const statuses = options.statuses ?? ['succeeded'];
      const status = statuses[Math.min(observed++, statuses.length - 1)];
      return importResponse({ job_id: 'finance-test-job', status, attempt_count: 1, max_attempts: 3,
        result_reference: status === 'succeeded' ? 'finance_import_batch:fixture' : null,
        receipt: status === 'succeeded' ? { batch_identity: plan.batch_identity,
          resulting_batch_version: 14, preview_fingerprint: plan.preview_fingerprint,
          reconciled_count: 3, existing_count: 2, pending_count: 5 } : null });
    }
    throw new Error(`Unexpected Finance test request: ${path}`);
  });
  vi.stubGlobal('fetch', fetchSpy);
  return { applyRequests, fetchSpy };
}

async function uploadAndPreview(file = IMPORT_FILE): Promise<void> {
  fireEvent.change(screen.getByLabelText('選擇銀行流水工作簿'), { target: { files: [file] } });
  fireEvent.click(screen.getByRole('button', { name: '上傳檔案' }));
  await waitFor(() => expect(screen.getByRole('button', { name: '預覽匯入結果' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: '預覽匯入結果' }));
  await screen.findByText('可自動入帳', { selector: '.finance-kpi-label' });
}

function assertPreviewCounts(plan: Pick<FinanceImportBatchPreview, 'counts'>): void {
  for (const [label, key] of [
    ['可自動入帳', 'ready_dispatch'], ['已存在', 'existing'], ['待人工確認', 'manual_review'],
    ['待業務配對', 'business_pending'], ['阻擋筆數', 'blocked'],
  ] as const) {
    const item = screen.getByText(label, { selector: '.finance-kpi-label' }).parentElement;
    expect(item?.querySelector('.finance-kpi-value')?.textContent).toBe(String(plan.counts[key]));
  }
}

function confirmImport(): void {
  const checkbox = screen.getByRole('checkbox');
  if (!(checkbox as HTMLInputElement).checked) fireEvent.click(checkbox);
  fireEvent.click(screen.getByRole('button', { name: '確認匯入' }));
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

  it('keeps decoded Preview values and forwards its version and fingerprint without rewriting', async () => {
    const plan = await importPreview();
    const { applyRequests } = installImportHttp([plan]);
    const previewSpy = vi.spyOn(financeImportMutationClient, 'preview');
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行流水匯入' }));
    await uploadAndPreview();
    expect(previewSpy).toHaveBeenCalledOnce();
    await expect(previewSpy.mock.results[0].value).resolves.toEqual(plan);
    assertPreviewCounts(plan);
    confirmImport();
    await screen.findByText('匯入完成：核銷 3、既有 2、待處理 5');
    expect(applyRequests[0].body).toEqual({ batch_identity: plan.batch_identity,
      expected_batch_version: plan.batch_version, preview_fingerprint: plan.preview_fingerprint,
      reason: '已核對銀行流水預覽，確認匯入' });
  });

  it('renders server blockers and never offers Apply for a blocked Preview', async () => {
    const plan = await importPreview();
    plan.apply_allowed = false;
    plan.blocking_codes = ['fingerprint_collision'];
    plan.counts.blocked = 2;
    installImportHttp([plan]);
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行流水匯入' }));
    await uploadAndPreview();
    assertPreviewCounts(plan);
    expect(screen.getByText(/目前不可匯入：存在可能重複的銀行交易/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '確認匯入' })).not.toBeInTheDocument();
  });

  it('replays the exact first command after a lost response and binds the displayed reason', async () => {
    const { applyRequests } = installImportHttp([await importPreview()], { loseFirstApply: true });
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行流水匯入' }));
    await uploadAndPreview();
    fireEvent.change(screen.getByLabelText('正式入帳原因'), { target: { value: '原始原因' } });
    confirmImport();
    await screen.findByText('服務暫時無法使用，請稍後再試。');
    expect(screen.getByLabelText('正式入帳原因')).toBeDisabled();
    expect(screen.getByLabelText('正式入帳原因')).toHaveValue('原始原因');
    confirmImport();
    await screen.findByText('匯入完成：核銷 3、既有 2、待處理 5');
    expect(applyRequests).toHaveLength(2);
    expect(applyRequests[1]).toEqual(applyRequests[0]);
  });

  it('returning to a submitted Preview does not use another Preview draft, even when that draft is blank', async () => {
    const plan = await importPreview();
    const otherFile = new File(['other finance fixture'], 'other.xlsx');
    const { applyRequests } = installImportHttp([plan, await importPreview('c'.repeat(64), otherFile), plan], { loseFirstApply: true });
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行流水匯入' }));
    await uploadAndPreview();
    fireEvent.change(screen.getByLabelText('正式入帳原因'), { target: { value: '第一份原因' } });
    confirmImport();
    await screen.findByText('服務暫時無法使用，請稍後再試。');
    await uploadAndPreview(otherFile);
    expect(screen.getByLabelText('正式入帳原因')).toBeEnabled();
    fireEvent.change(screen.getByLabelText('正式入帳原因'), { target: { value: '' } });
    await uploadAndPreview();
    expect(screen.getByLabelText('正式入帳原因')).toBeDisabled();
    expect(screen.getByLabelText('正式入帳原因')).toHaveValue('第一份原因');
    fireEvent.click(screen.getByRole('checkbox'));
    expect(screen.getByRole('button', { name: '確認匯入' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: '確認匯入' }));
    await screen.findByText('匯入完成：核銷 3、既有 2、待處理 5');
    expect(applyRequests).toHaveLength(2);
    expect(applyRequests[1]).toEqual(applyRequests[0]);
  });

  it('does not show a completion receipt during queued or running observations', async () => {
    const { applyRequests, fetchSpy } = installImportHttp([await importPreview()], { statuses: ['queued', 'running', 'succeeded'] });
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行流水匯入' }));
    await uploadAndPreview();
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    await act(async () => { confirmImport(); });
    expect(screen.getByText('正在完成匯入，系統會自動顯示正式結果。')).toBeInTheDocument();
    expect(screen.queryByText(/匯入完成：核銷/)).not.toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(500); });
    expect(screen.queryByText(/匯入完成：核銷/)).not.toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(500); });
    expect(screen.getByText('匯入完成：核銷 3、既有 2、待處理 5')).toBeInTheDocument();
    expect(fetchSpy.mock.calls.filter(([path]) => String(path).endsWith('/batch-outcome'))).toHaveLength(3);
    expect(applyRequests).toHaveLength(1);
  });

  it.each(['failed', 'cancelled'] as const)('%s never becomes a successful import receipt', async (status) => {
    installImportHttp([await importPreview()], { statuses: [status] });
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行流水匯入' }));
    await uploadAndPreview();
    confirmImport();
    await screen.findByText('未完成正式入帳；請重新預覽，或至帳務異常處理查看業務原因。');
    expect(screen.queryByText(/匯入完成：核銷/)).not.toBeInTheDocument();
  });

  // Supplied only by the append-only Python test; normal React CI does not claim MySQL coverage.
  it.skipIf(!process.env.FI_PREVIEW_EXCHANGE)('same-run MySQL Preview reaches the real client and rendered panel unchanged', async () => {
    const exchange = JSON.parse(readFileSync(process.env.FI_PREVIEW_EXCHANGE!, 'utf8')) as {
      workbook_path: string; ingestion_response: { data: unknown };
      preview_response: { data: FinanceImportBatchPreview };
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
      if (path.endsWith('/workbooks/ingest')) return importResponse(exchange.ingestion_response.data);
      if (path.endsWith('/batches/preview')) return importResponse(exchange.preview_response.data);
      throw new Error(`Unexpected request in Preview-only proof: ${path}`);
    }));
    const previewSpy = vi.spyOn(financeImportMutationClient, 'preview');
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行流水匯入' }));
    await uploadAndPreview(file);
    expect(previewSpy).toHaveBeenCalledOnce();
    const decoded = await previewSpy.mock.results[0].value;
    expect(decoded).toEqual(exchange.preview_response.data);
    expect(decoded).toMatchObject(exchange.expected);
    assertPreviewCounts(exchange.expected);
    if (!exchange.preview_response.data.apply_allowed) {
      expect(screen.getByText(new RegExp(financeImportBlockerMessage(exchange.expected.blocking_codes)))).toBeInTheDocument();
    }
    expect(requests).toEqual(['/api/v1/finance-import/workbooks/ingest', '/api/v1/finance-import/batches/preview']);
    expect(screen.queryByText(/匯入完成：核銷/)).not.toBeInTheDocument();
  });
});

/**
 * File: FinancePage.tsx
 * Description: 呈現Finance查詢與受控銀行流水 Upload、Preview、durable Apply、terminal receipt 工作區。
 */
import React, { useEffect, useRef, useState } from 'react';
import { FinanceImportCorrectionForm } from '../components/FinanceImportCorrectionForm';
import './FinancePage.css';
import './OrderWorkbenchV2Page.css';
import { loadAllOrderSummaries, ordersQueryClient } from '../api/orders/order_query_client';
import { adaptOrderSummaryPage } from '../adapters/orders/order_summary_adapter';
import { loadAllStaffDirectoryPages, staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { adaptStaffDirectoryPage } from '../adapters/staff/staff_directory_adapter';
import { clientReceiptQueryClient } from '../api/client_finance/client_receipt_query_client';
import { adaptClientReceiptQuery } from '../adapters/finance/client_receipt_query_adapter';
import { staffPayablesQueryClient } from '../api/staff_payables/staff_payables_query_client';
import { adaptStaffPayablesQuery } from '../adapters/finance/staff_payables_query_adapter';
import { accountsPayableQueryClient } from '../api/accounts_payable/accounts_payable_query_client';
import { accountsPayableExportClient } from '../api/accounts_payable/accounts_payable_export_client';
import { adaptAccountsPayablePreview } from '../adapters/finance/accounts_payable_query_adapter';
import { financeImportBlockerMessage } from '../adapters/finance/finance_import_query_adapter';
import { FinanceWorkbookSnapshot, financeImportMutationClient, type FinanceImportBatchOutcome, type FinanceImportBatchPreview, type FinanceImportJobAccepted, type FinanceWorkbookIngestionReceipt } from '../api/finance_import/finance_import_mutation_client';
import { financeImportQueryClient } from '../api/finance_import/finance_import_query_client';
import { HistoricalClientPaymentWorkbench } from '../components/HistoricalClientPaymentWorkbench';
import { HistoricalStaffPayoutWorkbench } from '../components/HistoricalStaffPayoutWorkbench';
import { OrderGovernmentSubsidyLane } from '../components/OrderGovernmentSubsidyLane';
import { OrderTerminalAggregateLane } from '../components/OrderTerminalAggregateLane';
import { PaymentDestinationConfigurationPanel } from '../components/PaymentDestinationConfigurationPanel';

type FinanceTab = 'client-receipts' | 'staff-payables' | 'accounts-payable' | 'cross-order' | 'finance-import' | 'payment-destination';
type LoadState<T> = { kind: 'idle' | 'loading' } | { kind: 'ready'; data: T } | { kind: 'empty' } | { kind: 'error'; message: string } | { kind: 'unavailable'; message: string };
type FinanceImportReviewSnapshot = {
  batchIdentity: string;
  reviewCount: number;
  items: Awaited<ReturnType<typeof financeImportQueryClient.listReviewRows>>['items'];
  sourceReviews: Awaited<ReturnType<typeof financeImportQueryClient.listReviewRows>>['source_reviews'];
};
const FINANCE_OUTCOME_POLL_LIMIT = 10;
const FINANCE_OUTCOME_POLL_DELAY_MS = 500;

function currentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

function StateMessage<T>({ state, empty }: { state: LoadState<T>; empty: string }) {
  if (state.kind === 'loading') return <div className="finance-state" role="status">正在載入真實資料…</div>;
  if (state.kind === 'empty') return <div className="finance-state">{empty}</div>;
  if (state.kind === 'error') return <div className="finance-state error" role="alert">{state.message}</div>;
  if (state.kind === 'unavailable') return <div className="finance-state unavailable" role="status">{state.message}</div>;
  return null;
}

function financeErrorMessage(error: unknown, fallback: string): string {
  const detail = error !== null && typeof error === 'object'
    ? error as Record<string, unknown>
    : {};
  const code = String(detail.code ?? detail.name ?? '').toLowerCase();
  const status = Number(detail.status ?? detail.statusCode ?? 0);

  if (status === 401 || code.includes('unauthenticated')) return '請先登入後再執行此操作。';
  if (status === 403 || code.includes('forbidden')) return '目前帳號無法執行此操作，請洽系統管理員。';
  if (status === 409 || code.includes('stale') || code.includes('conflict') || code.includes('mismatch')) {
    return '資料已變更，請重新整理並再次預覽。';
  }
  if (status >= 500 || code.includes('unavailable') || code.includes('network') || code.includes('timeout')) {
    return '服務暫時無法使用，請稍後再試。';
  }
  if (code.includes('file_type')) return '檔案格式不符，請選擇 .xlsx 銀行流水工作簿。';
  if (code.includes('file_empty')) return '選擇的工作簿沒有內容，請重新選擇檔案。';
  if (code.includes('file_too_large')) return '選擇的工作簿超過允許大小，請改用較小的檔案。';
  if (code.includes('file_changed')) return '工作簿內容已變更，請重新選擇並上傳。';
  if (code.includes('sha256_unavailable')) return '目前無法核對工作簿內容，請重新選擇檔案後再試。';
  return fallback;
}

export const FinancePage: React.FC = () => {
  const [entry] = useState(() => {
    const params = new URLSearchParams(window.location.hash.split('?')[1] ?? '');
    return { tab: params.get('tab'), caseNo: (params.get('case_no') ?? '').slice(0, 50) };
  });
  const [activeTab, setActiveTab] = useState<FinanceTab>(entry.tab === 'staff-payables' ? 'staff-payables' : 'client-receipts');
  const [expandedLane, setExpandedLane] = useState<'subsidy' | 'closure' | null>(null);
  const [cases, setCases] = useState<{ id: string; label: string; orderStatus: string }[]>([]);
  const [selectedCase, setSelectedCase] = useState(entry.caseNo);
  const [caseQuery, setCaseQuery] = useState(entry.caseNo);
  const [receipt, setReceipt] = useState<LoadState<ReturnType<typeof adaptClientReceiptQuery>>>({ kind: 'idle' });
  const [staff, setStaff] = useState<{ id: number; label: string }[]>([]);
  const [selectedStaff, setSelectedStaff] = useState<number | null>(null);
  const [payables, setPayables] = useState<LoadState<ReturnType<typeof adaptStaffPayablesQuery>>>({ kind: 'idle' });
  const [historicalStaffCase, setHistoricalStaffCase] = useState('');
  const [targetMonth, setTargetMonth] = useState(currentMonth);
  const [accountsPayable, setAccountsPayable] = useState<LoadState<ReturnType<typeof adaptAccountsPayablePreview>>>({ kind: 'idle' });
  const [payableDownload, setPayableDownload] = useState<LoadState<string>>({ kind: 'idle' });
  const [financeWorkbook, setFinanceWorkbook] = useState<File | null>(null);
  const [ingestion, setIngestion] = useState<LoadState<FinanceWorkbookIngestionReceipt>>({ kind: 'idle' });
  const [batchPreview, setBatchPreview] = useState<LoadState<FinanceImportBatchPreview>>({ kind: 'idle' });
  const [sourceReview, setSourceReview] = useState<LoadState<FinanceImportReviewSnapshot>>({ kind: 'idle' });
  const [applyReason, setApplyReason] = useState('已核對銀行流水預覽，確認匯入');
  const [applyConfirmed, setApplyConfirmed] = useState(false);
  const [applyJob, setApplyJob] = useState<LoadState<FinanceImportJobAccepted>>({ kind: 'idle' });
  const [batchOutcome, setBatchOutcome] = useState<LoadState<FinanceImportBatchOutcome>>({ kind: 'idle' });
  const [reload, setReload] = useState(0);
  const controllers = useRef(new Map<string, AbortController>());
  const sequences = useRef(new Map<string, number>());
  const financeApplyCommandByPreview = useRef(new Map<string, { correlationId: string; reason: string }>());
  const submittedFinanceCommand = batchPreview.kind === 'ready'
    ? financeApplyCommandByPreview.current.get(batchPreview.data.preview_fingerprint)
    : undefined;
  const displayedApplyReason = submittedFinanceCommand?.reason ?? applyReason;

  useEffect(() => () => controllers.current.forEach((controller) => controller.abort()), []);

  const start = (key: string) => {
    controllers.current.get(key)?.abort();
    const controller = new AbortController();
    controllers.current.set(key, controller);
    const sequence = (sequences.current.get(key) ?? 0) + 1;
    sequences.current.set(key, sequence);
    return { controller, sequence };
  };
  const current = (key: string, sequence: number, controller: AbortController) =>
    sequences.current.get(key) === sequence && !controller.signal.aborted;
  useEffect(() => {
    controllers.current.get('payable-download')?.abort();
    setPayableDownload({ kind: 'idle' });
  }, [targetMonth, activeTab]);

  const downloadPayables = async () => {
    const { controller, sequence } = start('payable-download');
    setPayableDownload({ kind: 'loading' });
    try {
      const artifact = await accountsPayableExportClient.download(targetMonth, controller.signal);
      if (!current('payable-download', sequence, controller)) return;
      const url = URL.createObjectURL(artifact.blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = artifact.filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setPayableDownload({ kind: 'ready', data: artifact.filename });
    } catch (error) {
      if (current('payable-download', sequence, controller)) {
        setPayableDownload({ kind: 'error', message: financeErrorMessage(error, '應付帳款下載失敗，請稍後再試。') });
      }
    }
  };
  const schedule = (
    key: string,
    execute: (request: { controller: AbortController; sequence: number }) => void,
  ) => {
    let cancelled = false;
    let request: { controller: AbortController; sequence: number } | null = null;
    queueMicrotask(() => {
      if (cancelled) return;
      request = start(key);
      execute(request);
    });
    return () => {
      cancelled = true;
      request?.controller.abort();
    };
  };

  useEffect(() => {
    if (activeTab !== 'client-receipts') return;
    return schedule('cases', (request) => {
      const queryText = caseQuery.trim();
      void loadAllOrderSummaries(
        ordersQueryClient.getOrderSummaries.bind(ordersQueryClient),
        { page_size: 200, ...(queryText ? { query_text: queryText } : {}) },
        { signal: request.controller.signal },
      )
      .then((page) => {
        if (!current('cases', request.sequence, request.controller)) return;
        const adapted = adaptOrderSummaryPage(page).items.map((item) => ({ id: item.id, label: `${item.id}｜${item.clientName}`, orderStatus: item.orderStatus }));
        setCases(adapted);
        setSelectedCase((value) => adapted.some((item) => item.id === value) ? value : entry.caseNo && queryText === entry.caseNo ? '' : adapted[0]?.id ?? '');
        if (adapted.length === 0) setReceipt({ kind: 'empty' });
      })
      .catch((error: unknown) => {
        if (current('cases', request.sequence, request.controller)) setReceipt({ kind: 'error', message: financeErrorMessage(error, '案件清單載入失敗，請重新整理。') });
      });
    });
  }, [activeTab, caseQuery, reload]);

  useEffect(() => {
    if (activeTab !== 'client-receipts' || !selectedCase) return;
    return schedule('receipt', (request) => {
      setReceipt({ kind: 'loading' });
      void clientReceiptQueryClient.query(selectedCase, { signal: request.controller.signal })
        .then((data) => { if (current('receipt', request.sequence, request.controller)) setReceipt({ kind: 'ready', data: adaptClientReceiptQuery(data) }); })
        .catch((error: unknown) => { if (current('receipt', request.sequence, request.controller)) setReceipt({ kind: 'error', message: financeErrorMessage(error, '客戶收款查詢失敗，請重新整理。') }); });
    });
  }, [activeTab, selectedCase, reload]);

  useEffect(() => {
    if (activeTab !== 'staff-payables' && activeTab !== 'finance-import') return;
    return schedule('staff', (request) => {
      setPayables({ kind: 'loading' });
      void loadAllStaffDirectoryPages(
        staffDirectoryClient.queryPage.bind(staffDirectoryClient),
        { pageSize: 200 },
        { signal: request.controller.signal },
      )
      .then((page) => {
        if (!current('staff', request.sequence, request.controller)) return;
        const adapted = adaptStaffDirectoryPage(page).items.map((item) => ({ id: item.id, label: item.displayName }));
        setStaff(adapted);
        setSelectedStaff((value) => value !== null && adapted.some((item) => item.id === value) ? value : adapted[0]?.id ?? null);
        if (adapted.length === 0) setPayables({ kind: 'empty' });
      })
      .catch((error: unknown) => { if (current('staff', request.sequence, request.controller)) setPayables({ kind: 'error', message: financeErrorMessage(error, '服務人員清單載入失敗，請重新整理。') }); });
    });
  }, [activeTab, reload]);

  useEffect(() => {
    if (activeTab !== 'staff-payables' || selectedStaff === null) return;
    return schedule('payables', (request) => {
      setPayables({ kind: 'loading' });
      void staffPayablesQueryClient.query(selectedStaff, { signal: request.controller.signal })
        .then((data) => { if (current('payables', request.sequence, request.controller)) setPayables({ kind: 'ready', data: adaptStaffPayablesQuery(data) }); })
        .catch((error: unknown) => { if (current('payables', request.sequence, request.controller)) setPayables({ kind: 'error', message: financeErrorMessage(error, '月嫂應付款查詢失敗，請重新整理。') }); });
    });
  }, [activeTab, selectedStaff, reload]);

  useEffect(() => {
    if (payables.kind !== 'ready') { setHistoricalStaffCase(''); return; }
    const caseNos = [...new Set(payables.data.obligations.map((item) => item.caseNo))];
    setHistoricalStaffCase((value) => caseNos.includes(value) ? value : caseNos[0] ?? '');
  }, [payables]);

  useEffect(() => {
    if (activeTab !== 'accounts-payable') return;
    return schedule('accounts-payable', (request) => {
      setAccountsPayable({ kind: 'loading' });
      void accountsPayableQueryClient.query(targetMonth, { signal: request.controller.signal })
        .then((data) => { if (current('accounts-payable', request.sequence, request.controller)) setAccountsPayable(data.rows.length ? { kind: 'ready', data: adaptAccountsPayablePreview(data) } : { kind: 'empty' }); })
        .catch((error: unknown) => { if (current('accounts-payable', request.sequence, request.controller)) setAccountsPayable({ kind: 'error', message: financeErrorMessage(error, '應付帳款查詢失敗，請重新整理。') }); });
    });
  }, [activeTab, targetMonth, reload]);

  const loadSourceReview = async (batchIdentity: string) => {
    const request = start('source-review');
    setSourceReview({ kind: 'loading' });
    try {
      const [manifest, firstPage] = await Promise.all([
        financeImportQueryClient.getManifest(batchIdentity, { signal: request.controller.signal }),
        financeImportQueryClient.listReviewRows(batchIdentity, { signal: request.controller.signal }),
      ]);
      if (!current('source-review', request.sequence, request.controller)) return;
      let page = firstPage;
      const items = [...page.items];
      const sourceReviews = [...page.source_reviews];
      while (page.next_after_row_id !== null || page.next_after_source_review_id !== null) {
        page = await financeImportQueryClient.listReviewRows(batchIdentity, {
          signal: request.controller.signal,
          afterRowId: items.at(-1)?.row_id,
          afterSourceReviewId: sourceReviews.at(-1)?.review_id,
        });
        if (!current('source-review', request.sequence, request.controller)) return;
        items.push(...page.items);
        sourceReviews.push(...page.source_reviews);
      }
      if (items.length + sourceReviews.length !== manifest.review_count) {
        setSourceReview({ kind: 'error', message: '人工確認清單與批次統計不一致，請重新查詢。' });
        return;
      }
      const manualItems = items.filter((row) => row.disposition === 'manual_review');
      setSourceReview({
        kind: 'ready',
        data: { batchIdentity: manifest.batch_identity, reviewCount: manualItems.length + sourceReviews.length, items: manualItems, sourceReviews },
      });
    } catch (error) {
      if (current('source-review', request.sequence, request.controller)) {
        setSourceReview({ kind: 'error', message: financeErrorMessage(error, '人工確認清單載入失敗，請重新查詢。') });
      }
    }
  };

  const ingestWorkbook = async () => {
    if (financeWorkbook === null) { setIngestion({ kind: 'error', message: '請先選擇 .xlsx 銀行流水工作簿。' }); return; }
    setIngestion({ kind: 'loading' }); setBatchPreview({ kind: 'idle' }); setSourceReview({ kind: 'idle' }); setApplyConfirmed(false); setApplyJob({ kind: 'idle' }); setBatchOutcome({ kind: 'idle' });
    try {
      const snapshot = await FinanceWorkbookSnapshot.fromFile(financeWorkbook);
      const receipt = await financeImportMutationClient.ingest(snapshot, { idempotencyKey: `ui-finance-ingest-${snapshot.sha256}`, correlationId: `ui-finance-ingest-${crypto.randomUUID()}` });
      setIngestion({ kind: 'ready', data: receipt });
    } catch (error) { setIngestion({ kind: 'error', message: financeErrorMessage(error, '銀行流水上傳失敗，請重新選擇檔案。') }); }
  };
  const previewImportedBatch = async () => {
    if (ingestion.kind !== 'ready') return;
    const request = start('batch-preview');
    controllers.current.get('source-review')?.abort();
    setBatchPreview({ kind: 'loading' }); setSourceReview({ kind: 'idle' }); setApplyConfirmed(false); setApplyJob({ kind: 'idle' }); setBatchOutcome({ kind: 'idle' });
    try {
      const preview = await financeImportMutationClient.preview(ingestion.data.batch_identity, request.controller.signal);
      if (!current('batch-preview', request.sequence, request.controller)) return;
      setBatchPreview({ kind: 'ready', data: preview });
      await loadSourceReview(preview.batch_identity);
    }
    catch (error) { if (current('batch-preview', request.sequence, request.controller)) setBatchPreview({ kind: 'error', message: financeErrorMessage(error, '匯入預覽未完成，請重新執行預覽。') }); }
  };
  const applyImportedBatch = async () => {
    if (batchPreview.kind !== 'ready' || !applyConfirmed || !batchPreview.data.apply_allowed || batchPreview.data.counts.ready_dispatch <= 0) return;
    setApplyJob({ kind: 'loading' }); setBatchOutcome({ kind: 'idle' });
    try {
      const previewFingerprint = batchPreview.data.preview_fingerprint;
      const command = financeApplyCommandByPreview.current.get(previewFingerprint)
        ?? { correlationId: `ui-finance-apply-${crypto.randomUUID()}`, reason: applyReason.trim() };
      financeApplyCommandByPreview.current.set(previewFingerprint, command);
      const accepted = await financeImportMutationClient.apply(batchPreview.data, command.reason, { idempotencyKey: `ui-finance-apply-${previewFingerprint}`, correlationId: command.correlationId });
      setApplyJob({ kind: 'ready', data: accepted });
      await observeApplyOutcome(accepted.job_id, {
        batchIdentity: batchPreview.data.batch_identity,
        previewFingerprint: batchPreview.data.preview_fingerprint,
      });
    } catch (error) { setApplyJob({ kind: 'error', message: financeErrorMessage(error, '正式匯入未受理，請重新預覽後再試。') }); }
  };
  const observeApplyOutcome = async (
    jobId: string,
    expected?: { batchIdentity: string; previewFingerprint: string },
  ) => {
    const request = start('batch-outcome');
    setBatchOutcome({ kind: 'loading' });
    try {
      for (let attempt = 0; attempt < FINANCE_OUTCOME_POLL_LIMIT; attempt += 1) {
        const outcome = await financeImportMutationClient.queryBatchOutcome(jobId, request.controller.signal);
        if (!current('batch-outcome', request.sequence, request.controller)) return;
        if (outcome.status === 'succeeded' || outcome.status === 'failed' || outcome.status === 'cancelled') {
          if (
            outcome.status === 'succeeded'
            && (!outcome.receipt
              || (expected !== undefined && (
                outcome.receipt.batch_identity !== expected.batchIdentity
                || outcome.receipt.preview_fingerprint !== expected.previewFingerprint
              )))
          ) {
            setBatchOutcome({ kind: 'error', message: '匯入結果與原批次預覽不一致；請勿重新提交，請重新查詢結果。' });
            return;
          }
          setBatchOutcome({ kind: 'ready', data: outcome });
          setReload((value) => value + 1);
          if (batchPreview.kind === 'ready') await loadSourceReview(batchPreview.data.batch_identity);
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, FINANCE_OUTCOME_POLL_DELAY_MS));
      }
      if (current('batch-outcome', request.sequence, request.controller)) {
        setBatchOutcome({ kind: 'error', message: '正式入帳仍在處理中；可重新查詢結果，不需重複上傳。' });
      }
    } catch (error) {
      if (current('batch-outcome', request.sequence, request.controller)) setBatchOutcome({ kind: 'error', message: financeErrorMessage(error, '正式匯入結果查詢失敗，請稍後重新查詢。') });
    }
  };

  return (
    <div data-surface-id="finance.page">
      <header className="page-header-banner finance-page-header">
        <div>
          <h1 className="page-title">💰 財務查詢與對帳工作台</h1>
          <p className="page-subtitle">查詢客戶收款、逐人薪資與每月付款，或核對銀行流水。</p>
        </div>
        <div className="finance-header-actions">
          <span className="finance-status-pill">
            {activeTab === 'finance-import' ? '● 預覽確認後正式匯入' : '● 即時查詢｜不自動輪詢'}
          </span>
        </div>
      </header>

      <nav className="finance-tab-bar" aria-label="財務查詢工作區">
        {([
          ['client-receipts', '客戶收款'],
          ['staff-payables', '月嫂應付款'],
          ['accounts-payable', '應付帳款'],
          ['cross-order', '補助與結案查詢'],
          ['finance-import', '銀行流水匯入'],
        ] as const).map(([id, label]) => (
          <button
            key={id}
            data-surface-id={`finance.tab.${id}`}
            className={activeTab === id ? 'active' : ''}
            onClick={() => setActiveTab(id)}
          >
            {label}
            {id === 'staff-payables' && <small aria-hidden="true">逐人薪資明細</small>}
            {id === 'accounts-payable' && <small aria-hidden="true">每月付款清單</small>}
          </button>
        ))}
        <div className="finance-settings-nav" role="group" aria-label="帳務設定">
          <span>設定</span>
          <button type="button" data-surface-id="finance.tab.payment-destination" className={activeTab === 'payment-destination' ? 'active' : ''} onClick={() => setActiveTab('payment-destination')}>契約收款帳戶</button>
        </div>
      </nav>

      <div className="finance-toolbar">
        <span>{activeTab === 'finance-import'
          ? '上傳檔案 → 預覽 → 匯入完成'
          : activeTab === 'cross-order'
            ? '選擇帳務查詢後載入跨訂單結果'
            : '查詢結果以目前選取頁籤為準'}</span>
        {activeTab !== 'finance-import' && activeTab !== 'cross-order' && (
          <button className="finance-reload-btn" onClick={() => setReload((value) => value + 1)}>
            重新載入
          </button>
        )}
      </div>

      {activeTab === 'client-receipts' && (
        <section className="finance-workspace">
          <div className="finance-section-heading">
            <div>
              <h2>客戶收款資料</h2>
              <p>正常收款由銀行流水匯入自動核銷；不唯一或金額不符時，請到「銀行流水匯入」查看該批次的人工核對清單。</p>
            </div>
          </div>

          <div className="finance-filter-bar">
            <label>
              搜尋案件
              <input
                className="finance-input"
                data-control-id="finance.client-receipts.case-search"
                value={caseQuery}
                maxLength={100}
                placeholder="案件編號或客戶名稱"
                onChange={(event) => setCaseQuery(event.target.value)}
              />
            </label>
            <label>
              案件
              <select
                className="finance-select"
                value={selectedCase}
                onChange={(event) => setSelectedCase(event.target.value)}
              >
                {cases.map((item) => (
                  <option key={item.id} value={item.id}>{item.label}</option>
                ))}
              </select>
            </label>
          </div>

          <StateMessage state={receipt} empty="目前沒有可顯示的收款資料。" />

          {receipt.kind === 'ready' && (
            <>
              <div className="finance-kpi-grid">
                <div className="finance-kpi-item">
                  <span className="finance-kpi-label">案件識別</span>
                  <span className="finance-kpi-value" style={{ fontSize: '1.15rem' }}>{receipt.data.caseNo}</span>
                </div>
                <div className="finance-kpi-item">
                  <span className="finance-kpi-label">收款義務筆數</span>
                  <span className="finance-kpi-value orange">{receipt.data.obligations.length} 筆</span>
                </div>
                <div className="finance-kpi-item">
                  <span className="finance-kpi-label">銀行交易筆數</span>
                  <span className="finance-kpi-value green">{receipt.data.bankFacts.length} 筆</span>
                </div>
              </div>

              <div className="finance-meta">
                <span>案件 {receipt.data.caseNo} 的收款資料</span>
                <span className="finance-badge finance-badge-paid">收款資料已載入</span>
              </div>

              <table className="finance-table">
                <thead>
                  <tr>
                    <th>義務</th>
                    <th>階段</th>
                    <th>應收</th>
                    <th>到期日</th>
                  </tr>
                </thead>
                <tbody>
                  {receipt.data.obligations.map((item) => (
                    <tr key={item.id}>
                      <td><code>{item.id}</code></td>
                      <td><span className="finance-badge finance-badge-stage">{item.stage}</span></td>
                      <td><strong>{item.amountDue}</strong></td>
                      <td>{item.dueDate}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="finance-detail-block">
                <h3>已載入銀行交易</h3>
                <div className="finance-table-container">
                  <table className="finance-table">
                    <thead>
                      <tr>
                        <th>序號</th>
                        <th>交易日期</th>
                        <th>金額</th>
                      </tr>
                    </thead>
                    <tbody>
                      {receipt.data.bankFacts.map((item) => (
                        <tr key={item.id}>
                          <td><code>#{item.id}</code></td>
                          <td>{item.transactionDate}</td>
                          <td><strong style={{ color: '#16a34a' }}>{item.amount}</strong></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              {cases.find((item) => item.id === selectedCase)?.orderStatus.startsWith('歷史訂單－') ? (
                <HistoricalClientPaymentWorkbench caseNo={selectedCase} />
              ) : (
                <div className="finance-state">此為正常案件；歷史人工收款確認只會在歷史案件顯示。</div>
              )}
            </>
          )}
        </section>
      )}
      {activeTab === 'payment-destination' && <PaymentDestinationConfigurationPanel reload={reload} />}

      {activeTab === 'cross-order' && (
        <section className="finance-workspace" aria-labelledby="cross-order-finance-heading">
          <div className="finance-section-heading">
            <div>
              <h2 id="cross-order-finance-heading">補助與結案查詢</h2>
              <p>查詢政府補助結算與完全結案狀態；結果涵蓋各類訂單。</p>
            </div>
          </div>
          <div className="order-v2-side-lanes">
            <OrderGovernmentSubsidyLane expanded={expandedLane === 'subsidy'} onExpandedChange={(open) => setExpandedLane(open ? 'subsidy' : null)} />
            <OrderTerminalAggregateLane expanded={expandedLane === 'closure'} onExpandedChange={(open) => setExpandedLane(open ? 'closure' : null)} />
          </div>
        </section>
      )}

      {activeTab === 'staff-payables' && (
        <section className="finance-workspace">
          <div className="finance-section-heading">
            <div>
              <h2>月嫂應付款與付款事件</h2>
              <p>正常付款由銀行流水匯入自動核銷；不唯一或金額不符時，請到「銀行流水匯入」查看該批次的人工核對清單。</p>
            </div>
          </div>

          <div className="finance-filter-bar">
            <label>
              服務人員
              <select
                className="finance-select"
                value={selectedStaff ?? ''}
                onChange={(event) => setSelectedStaff(Number(event.target.value))}
              >
                {staff.map((item) => (
                  <option key={item.id} value={item.id}>{item.label}</option>
                ))}
              </select>
            </label>
          </div>

          <StateMessage state={payables} empty="目前沒有可顯示的應付款。" />

          {payables.kind === 'ready' && (
            <>
              <div className="finance-kpi-grid">
                <div className="finance-kpi-item">
                  <span className="finance-kpi-label">月嫂編號</span>
                  <span className="finance-kpi-value" style={{ fontSize: '1.15rem' }}>Staff #{payables.data.staffId}</span>
                </div>
                <div className="finance-kpi-item">
                  <span className="finance-kpi-label">應付義務筆數</span>
                  <span className="finance-kpi-value orange">{payables.data.obligations.length} 筆</span>
                </div>
                <div className="finance-kpi-item">
                  <span className="finance-kpi-label">已付款事件</span>
                  <span className="finance-kpi-value green">{payables.data.events.length} 筆</span>
                </div>
              </div>

              <div className="finance-meta">
                <span>Staff #{payables.data.staffId} 的應付款資料</span>
                <span className="finance-badge finance-badge-paid">應付款資料已載入</span>
              </div>

              <table className="finance-table">
                <thead>
                  <tr>
                    <th>義務</th>
                    <th>案件</th>
                    <th>應付</th>
                    <th>已付</th>
                    <th>餘額</th>
                    <th>付款狀態</th>
                  </tr>
                </thead>
                <tbody>
                  {payables.data.obligations.map((item) => (
                    <tr key={item.id}>
                      <td><code>{item.id}</code></td>
                      <td><strong>{item.caseNo}</strong></td>
                      <td>{item.amountDue}</td>
                      <td style={{ color: '#16a34a' }}>{item.netPaid}</td>
                      <td style={{ color: '#ea580c', fontWeight: 700 }}>{item.balance}</td>
                      <td><span className={`finance-badge ${item.payoutCompleted ? 'finance-badge-paid' : 'finance-badge-unpaid'}`}>{item.payoutStatus}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="finance-detail-block">
                <h3>付款事件</h3>
                <div className="finance-table-container">
                  <table className="finance-table">
                    <thead>
                      <tr>
                        <th>序號</th>
                        <th>類型</th>
                        <th>金額</th>
                        <th>發生日期</th>
                        <th>憑證參考號</th>
                      </tr>
                    </thead>
                    <tbody>
                      {payables.data.events.map((item) => (
                        <tr key={item.id}>
                          <td><code>#{item.id}</code></td>
                          <td><span className="finance-badge finance-badge-stage">{item.type}</span></td>
                          <td><strong style={{ color: '#16a34a' }}>{item.amount}</strong></td>
                          <td>{item.occurredOn}</td>
                          <td><code>{item.reference}</code></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              <div className="finance-filter-bar">
                <label>
                  歷史付款案件
                  <select value={historicalStaffCase} onChange={(event) => setHistoricalStaffCase(event.target.value)}>
                    {[...new Set(payables.data.obligations.map((item) => item.caseNo))].map((caseNo) => (
                      <option key={caseNo} value={caseNo}>{caseNo}</option>
                    ))}
                  </select>
                </label>
              </div>
              {selectedStaff !== null && historicalStaffCase && (
                <HistoricalStaffPayoutWorkbench caseNo={historicalStaffCase} staffId={selectedStaff} />
              )}
            </>
          )}
        </section>
      )}

      {activeTab === 'accounts-payable' && (
        <section className="finance-workspace">
          <div className="finance-section-heading">
            <div>
              <h2>應付帳款預覽</h2>
              <p>核對當月付款資料，下載 Excel 交給會計。下載時會保存一份相同檔案，不會執行付款。</p>
            </div>
          </div>

          <div className="finance-filter-bar">
            <label>
              月份
              <input
                className="finance-input"
                type="month"
                value={targetMonth}
                onChange={(event) => setTargetMonth(event.target.value)}
              />
            </label>
            <button type="button" className="finance-btn-primary" data-control-id="finance.accounts-payable.export-xlsx"
              disabled={accountsPayable.kind !== 'ready' || payableDownload.kind === 'loading'}
              onClick={() => void downloadPayables()}>
              {payableDownload.kind === 'loading' ? '正在準備下載…' : '下載應付帳款 Excel'}
            </button>
          </div>

          {payableDownload.kind === 'error' && <div role="alert" className="finance-state error">{payableDownload.message}</div>}
          {payableDownload.kind === 'ready' && <div role="status">已送出下載：{payableDownload.data}</div>}

          <StateMessage state={accountsPayable} empty="本月沒有應付帳款。" />

          {accountsPayable.kind === 'ready' && (
            <>
              <div className="finance-kpi-grid">
                <div className="finance-kpi-item">
                  <span className="finance-kpi-label">目標付款日</span>
                  <span className="finance-kpi-value" style={{ fontSize: '1.15rem' }}>{accountsPayable.data.targetPaymentDate}</span>
                </div>
                <div className="finance-kpi-item">
                  <span className="finance-kpi-label">應付總筆數</span>
                  <span className="finance-kpi-value orange">{accountsPayable.data.rowCount} 筆</span>
                </div>
                <div className="finance-kpi-item">
                  <span className="finance-kpi-label">應付總金額</span>
                  <span className="finance-kpi-value" style={{ color: '#a43c12' }}>{accountsPayable.data.totalAmount}</span>
                </div>
              </div>

              <div className="finance-meta">
                <span>付款日 {accountsPayable.data.targetPaymentDate}｜{accountsPayable.data.rowCount}筆｜{accountsPayable.data.totalAmount}</span>
              </div>

              <table className="finance-table">
                <thead>
                  <tr>
                    <th>日期</th>
                    <th>類型</th>
                    <th>受款人</th>
                    <th>銀行代號／帳號</th>
                    <th>身分證字號</th>
                    <th>金額</th>
                    <th>案件</th>
                  </tr>
                </thead>
                <tbody>
                  {accountsPayable.data.rows.map((row) => (
                    <tr key={row.id}>
                      <td>{row.paymentDate}</td>
                      <td><span className="finance-badge finance-badge-stage">{row.paymentType}</span></td>
                      <td><strong>{row.recipientName}</strong></td>
                      <td><code>{row.bankDisplay}</code></td>
                      <td><code>{row.identityDisplay}</code></td>
                      <td><strong style={{ color: '#a43c12' }}>{row.amount}</strong></td>
                      <td>{row.caseNumbers.join('、') || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </section>
      )}

      {activeTab === 'finance-import' && (
        <section className="finance-workspace">
          <div className="finance-section-heading">
            <div>
              <h2>銀行流水匯入</h2>
              <p>選擇銀行流水工作簿、核對預覽，再確認匯入；完成結果會自動顯示。</p>
            </div>
          </div>

          {/* 一般操作固定為上傳、預覽、匯入完成三步。 */}
          <div className="finance-stepper">
            <div className={`finance-step-item ${ingestion.kind === 'loading' || financeWorkbook ? 'active' : ''}`}>
              <div className="finance-step-num">1</div>
              <div>
                <div className="finance-step-title">上傳檔案</div>
                <div className="finance-step-desc">選擇銀行流水工作簿</div>
              </div>
            </div>
            <div className={`finance-step-item ${batchPreview.kind === 'ready' || batchPreview.kind === 'loading' ? 'active' : ''}`}>
              <div className="finance-step-num">2</div>
              <div>
                <div className="finance-step-title">預覽</div>
                <div className="finance-step-desc">核對匹配與阻擋原因</div>
              </div>
            </div>
            <div className={`finance-step-item ${applyJob.kind === 'ready' || applyJob.kind === 'loading' || batchOutcome.kind === 'ready' ? 'active' : ''}`}>
              <div className="finance-step-num">3</div>
              <div>
                <div className="finance-step-title">匯入完成</div>
                <div className="finance-step-desc">系統自動確認正式結果</div>
              </div>
            </div>
          </div>

          <section className="finance-detail-block finance-dropzone" data-surface-id="finance.finance-import.workflow">
            <div style={{ fontSize: '2rem' }}>📥</div>
            <h3>選擇銀行流水工作簿</h3>
            <p>上傳後先核對筆數與配對結果，再確認正式匯入。</p>

            <div style={{ display: 'flex', justifyContent: 'center', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
              <input
                type="file"
                accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                aria-label="選擇銀行流水工作簿"
                className="finance-input"
                onChange={(event) => {
                  controllers.current.get('batch-preview')?.abort();
                  controllers.current.get('source-review')?.abort();
                  controllers.current.get('batch-outcome')?.abort();
                  setApplyConfirmed(false);
                  setFinanceWorkbook(event.target.files?.[0] ?? null);
                  setIngestion({ kind: 'idle' });
                  setBatchPreview({ kind: 'idle' });
                  setSourceReview({ kind: 'idle' });
                  setApplyJob({ kind: 'idle' });
                  setBatchOutcome({ kind: 'idle' });
                }}
              />
              <button
                className="finance-btn-primary"
                data-control-id="finance.finance-import.upload"
                disabled={financeWorkbook === null || ingestion.kind === 'loading'}
                onClick={() => void ingestWorkbook()}
              >
                {ingestion.kind === 'loading' ? '上傳中…' : '上傳檔案'}
              </button>
              <button
                className="finance-btn-secondary"
                data-control-id="finance.finance-import.preview"
                disabled={ingestion.kind !== 'ready' || batchPreview.kind === 'loading'}
                onClick={() => void previewImportedBatch()}
              >
                {batchPreview.kind === 'loading' ? '預覽中…' : '預覽匯入結果'}
              </button>
            </div>

            <StateMessage state={ingestion} empty="" />

            {ingestion.kind === 'ready' && (
              <div className="finance-meta" style={{ marginTop: '14px', textAlign: 'left' }}>
                <span>
                  {ingestion.data.replayed ? '同一工作簿已上傳過，將沿用原上傳結果。' : '檔案上傳完成，可以執行預覽。'}
                  {' '}共讀取 {ingestion.data.source_row_count} 列，其中 {ingestion.data.canonical_created_count} 列已建立待處理資料。
                </span>
              </div>
            )}

            <StateMessage state={batchPreview} empty="" />

            {batchPreview.kind === 'ready' && (
              <div style={{ marginTop: '14px', padding: '16px', background: '#fffaf7', border: '1px solid #fed9b8', borderRadius: '12px', textAlign: 'left' }}>
                <div className="finance-kpi-grid" style={{ marginBottom: '12px' }}>
                  <div className="finance-kpi-item">
                    <span className="finance-kpi-label">可自動入帳</span>
                    <span className="finance-kpi-value green">{batchPreview.data.counts.ready_dispatch}</span>
                  </div>
                  <div className="finance-kpi-item">
                    <span className="finance-kpi-label">已存在</span>
                    <span className="finance-kpi-value">{batchPreview.data.counts.existing}</span>
                  </div>
                  <div className="finance-kpi-item">
                    <span className="finance-kpi-label">待人工確認</span>
                    <span className="finance-kpi-value orange">{sourceReview.kind === 'ready' ? sourceReview.data.reviewCount : '—'}</span>
                  </div>
                  <div className="finance-kpi-item">
                    <span className="finance-kpi-label">待業務配對</span>
                    <span className="finance-kpi-value orange">{batchPreview.data.counts.business_pending}</span>
                  </div>
                  <div className="finance-kpi-item">
                    <span className="finance-kpi-label">阻擋筆數</span>
                    <span className="finance-kpi-value" style={{ color: '#dc2626' }}>{batchPreview.data.counts.blocked}</span>
                  </div>
                </div>

                <div className="finance-scope-note">
                  可自動入帳 {batchPreview.data.counts.ready_dispatch}｜已存在 {batchPreview.data.counts.existing}｜待人工確認 {sourceReview.kind === 'ready' ? sourceReview.data.reviewCount : '讀取中'}｜待業務配對 {batchPreview.data.counts.business_pending}｜阻擋 {batchPreview.data.counts.blocked}。
                  {batchPreview.data.apply_allowed && batchPreview.data.counts.ready_dispatch > 0
                    ? '可進入匯入確認。'
                    : batchPreview.data.apply_allowed
                      ? '目前沒有可自動入帳的筆數；請先從帳務異常處理完成配對。'
                    : `目前不可匯入：${financeImportBlockerMessage(batchPreview.data.blocking_codes)}`}
                </div>

                <StateMessage state={sourceReview} empty="目前沒有待人工確認資料。" />
                {sourceReview.kind === 'ready' && (
                  <div id="finance-import-review" className="finance-detail-block" data-surface-id="finance.finance-import.manual-review" style={{ marginTop: '12px' }}>
                    <div className="finance-meta">
                      <span>批次 <code>{sourceReview.data.batchIdentity}</code>｜待人工確認 {sourceReview.data.reviewCount} 筆</span>
                      <button
                        className="finance-btn-secondary"
                        data-control-id="finance.finance-import.review-reload"
                        onClick={() => void loadSourceReview(sourceReview.data.batchIdentity)}
                      >
                        重新查詢人工確認
                      </button>
                    </div>
                    {sourceReview.data.reviewCount === 0 ? (
                      <div className="finance-state">目前沒有待人工確認資料。</div>
                    ) : (
                      <div className="finance-table-container">
                        <table className="finance-table">
                          <thead>
                            <tr>
                              <th>來源列</th>
                              <th>交易日期</th>
                              <th>方向</th>
                              <th>金額</th>
                              <th>分類</th>
                              <th>處置</th>
                            </tr>
                          </thead>
                          <tbody>
                            {sourceReview.data.sourceReviews.map((row) => (
                              <tr key={row.review_identity}>
                                <td><code>{row.source_sheet}#{row.source_row}</code></td>
                                <td colSpan={3}>來源資料未形成銀行交易</td>
                                <td>來源資料待人工確認</td>
                                <td>{row.issue_codes.join('、')}</td>
                              </tr>
                            ))}
                            {sourceReview.data.items.map((row) => (
                              <tr key={row.row_id}>
                                <td><code>{row.source_sheet}#{row.source_row}</code></td>
                                <td>{row.transaction_date ?? '—'}</td>
                                <td>{row.direction}</td>
                                <td><strong>{row.amount_ntd}</strong></td>
                                <td>{row.classification_type}</td>
                                <td>{row.disposition}{row.available_actions.includes('preview_manual_correction') && <details><summary>更正收款／付款對象</summary><FinanceImportCorrectionForm key={row.row_identity} rowIdentity={row.row_identity} sourceLabel={`${row.source_sheet} 第 ${row.source_row} 列`} staff={staff} /></details>}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}

                {sourceReview.kind === 'error' && (
                  <button
                    className="finance-btn-secondary"
                    style={{ marginTop: '10px' }}
                    data-control-id="finance.finance-import.review-reload"
                    onClick={() => void loadSourceReview(batchPreview.data.batch_identity)}
                  >
                    重新查詢人工確認
                  </button>
                )}

                {batchPreview.data.apply_allowed && batchPreview.data.counts.ready_dispatch > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '12px' }}>
                    <label style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '0.84rem', fontWeight: 700 }}>
                      正式入帳原因
                      <input
                        className="finance-input"
                        value={displayedApplyReason}
                        disabled={submittedFinanceCommand !== undefined}
                        maxLength={500}
                        onChange={(event) => {
                          setApplyReason(event.target.value);
                          setApplyConfirmed(false);
                        }}
                      />
                    </label>
                    <label style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '0.84rem' }}>
                      <input
                        type="checkbox"
                        checked={applyConfirmed}
                        onChange={(event) => setApplyConfirmed(event.target.checked)}
                      />
                      我已核對預覽結果，理解系統會在匯入後自動顯示正式結果。
                    </label>
                    <button
                      className="finance-btn-primary"
                      style={{ alignSelf: 'flex-start' }}
                      data-control-id="finance.finance-import.apply"
                      disabled={!applyConfirmed || !displayedApplyReason.trim() || applyJob.kind === 'loading' || batchOutcome.kind === 'loading'}
                      onClick={() => void applyImportedBatch()}
                    >
                      {applyJob.kind === 'loading' || batchOutcome.kind === 'loading' ? '正式匯入中…' : '確認匯入'}
                    </button>
                  </div>
                )}
              </div>
            )}

            <StateMessage state={applyJob} empty="" />

            {applyJob.kind === 'ready' && (
              <div className="finance-meta" style={{ marginTop: '12px' }}>
                <span>{applyJob.data.replayed ? '同一匯入已受理；正在查回原結果。' : '正在完成匯入，系統會自動顯示正式結果。'}</span>
                {batchOutcome.kind === 'error' && (
                  <button
                    className="finance-btn-secondary"
                    data-control-id="finance.finance-import.receipt"
                    onClick={() => void observeApplyOutcome(applyJob.data.job_id, batchPreview.kind === 'ready' ? {
                      batchIdentity: batchPreview.data.batch_identity,
                      previewFingerprint: batchPreview.data.preview_fingerprint,
                    } : undefined)}
                  >
                    重新查詢匯入結果
                  </button>
                )}
              </div>
            )}

            <StateMessage state={batchOutcome} empty="" />

            {batchOutcome.kind === 'ready' && (
              <div className="finance-meta" style={{ marginTop: '12px', background: '#f0fdf4', borderColor: '#bbf7d0' }}>
                <span>
                  {batchOutcome.data.receipt
                    ? `匯入完成：核銷 ${batchOutcome.data.receipt.reconciled_count}、既有 ${batchOutcome.data.receipt.existing_count}、待處理 ${batchOutcome.data.receipt.pending_count}`
                    : '未完成正式入帳；請重新預覽並查看本頁人工核對清單。'}
                </span>
                {batchOutcome.data.receipt && batchOutcome.data.receipt.pending_count > 0 && (
                  <a href="#finance-import-review" className="finance-btn-secondary">查看人工核對清單</a>
                )}
              </div>
            )}
          </section>

        </section>
      )}
    </div>
  );
};

export default FinancePage;

import { useUnsavedDraft, useUnsavedNavigation } from '../components/UnsavedChanges';
import { useStaffIdentityDirectory, useStaffIdentityLabels } from '../components/StaffIdentityProvider';
/**
 * File: FinancePage.tsx
 * Description: 呈現Finance查詢與受控銀行交易明細 Upload、Preview、durable Apply、terminal receipt 工作區。
 */
import React, { useEffect, useRef, useState } from 'react';
import { FinanceImportCorrectionForm } from '../components/FinanceImportCorrectionForm';
import { Drawer } from '../components/Drawer';
import './FinancePage.css';
import { loadAllOrderSummaries, ordersQueryClient } from '../api/orders/order_query_client';
import { adaptOrderSummaryPage } from '../adapters/orders/order_summary_adapter';
import { loadAllStaffDirectoryPages, staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { adaptStaffDirectoryPage, compareStaffUnionNumbers, staffDisplayLabel } from '../adapters/staff/staff_directory_adapter';
import { clientReceiptQueryClient } from '../api/client_finance/client_receipt_query_client';
import { adaptClientReceiptQuery } from '../adapters/finance/client_receipt_query_adapter';
import { staffPayablesQueryClient } from '../api/staff_payables/staff_payables_query_client';
import { adaptStaffPayablesQuery } from '../adapters/finance/staff_payables_query_adapter';
import { accountsPayableQueryClient } from '../api/accounts_payable/accounts_payable_query_client';
import { financeImportBlockerMessage, financeImportReviewReason, financeImportSkipsUnidentifiedOutgoing } from '../adapters/finance/finance_import_query_adapter';
import { FinanceWorkbookSnapshot, financeImportMutationClient, type FinanceImportBatchOutcome, type FinanceImportBatchPreview, type FinanceImportJobAccepted, type FinanceWorkbookIngestionReceipt } from '../api/finance_import/finance_import_mutation_client';
import { financeImportQueryClient } from '../api/finance_import/finance_import_query_client';
import type { FinanceImportBatchSummary } from '../api/finance_import/finance_import_query_schemas';
import { HistoricalClientPaymentWorkbench } from '../components/HistoricalClientPaymentWorkbench';
import { HistoricalStaffPayoutWorkbench } from '../components/HistoricalStaffPayoutWorkbench';
import { HistoricalCompletionPanel } from '../components/HistoricalCompletionPanel';

import { FinanceReceiptsWorkspace } from '../components/FinanceReceiptsWorkspace';
import { FinancePaymentsWorkspace } from '../components/FinancePaymentsWorkspace';
import { FinanceCaseList } from '../components/FinanceCaseList';
import { FinanceGovernmentSubsidyList } from '../components/FinanceGovernmentSubsidyList';
import { FinanceCaseHistory } from '../components/FinanceCaseHistory';
import { FinanceMonthlyAccounting } from '../components/FinanceMonthlyAccounting';
import type { AccountingRange } from '../api/finance_import/monthly_accounting_client';
import { FinanceReceivableItems, type ReceivableFilters } from '../components/FinanceReceivableItems';
import { FinanceCaseAccounting } from '../components/FinanceCaseAccounting';
import { FinanceWarningWorkspace } from '../components/FinanceWarningWorkspace';
import { PaymentReceiptNoticeWorkbench } from '../components/PaymentReceiptNoticeWorkbench';
import { FinancePostedBankTransactions } from '../components/FinancePostedBankTransactions';
import { FinanceStatementArchive } from '../components/FinanceStatementArchive';

type FinanceTab = 'government-list' | 'monthly' | 'receipt-notices' | 'pending' | 'receipts' | 'payments' | 'client-receipts' | 'staff-payables' | 'finance-import' | 'case-accounting' | 'accounting-warnings';
type LoadState<T> = { kind: 'idle' | 'loading' } | { kind: 'ready'; data: T } | { kind: 'empty' } | { kind: 'error'; message: string } | { kind: 'unavailable'; message: string };
type FinanceImportReviewSnapshot = {
  batchIdentity: string;
  reviewCount: number;
  items: Awaited<ReturnType<typeof financeImportQueryClient.listReviewRows>>['items'];
  sourceReviews: Awaited<ReturnType<typeof financeImportQueryClient.listReviewRows>>['source_reviews'];
};
type CaseStaffPayable = Awaited<ReturnType<typeof accountsPayableQueryClient.queryCase>>['items'][number];
const FINANCE_CORRECTION_ACTIONS = new Set([
  'preview_manual_correction',
  'resolve_owning_domain_target',
  'review_suspected_duplicate_business_match',
]);

function canCorrectFinanceImportRow(row: FinanceImportReviewSnapshot['items'][number], preview?: FinanceImportBatchPreview['rows'][number]): boolean {
  return !financeImportSkipsUnidentifiedOutgoing(row, preview) && row.disposition !== 'blocked' && preview?.disposition !== 'blocked'
    && !preview?.fingerprint_collision && !preview?.formal_reference_conflict && !preview?.integrity_violations.length
    && ['client_receipt', 'staff_payout', 'client_refund', 'non_business_review'].includes(row.classification_type)
    && row.available_actions.some((action) => FINANCE_CORRECTION_ACTIONS.has(action));
}
const FINANCE_OUTCOME_POLL_LIMIT = 10;
const FINANCE_OUTCOME_POLL_DELAY_MS = 500;

function currentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

function StateMessage<T>({ state, empty }: { state: LoadState<T>; empty: string }) {
  if (state.kind === 'loading') return <div className="finance-state" role="status">正在載入資料…</div>;
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
    return '資料已變更，請重新整理後再儲存。';
  }
  if (status >= 500 || code.includes('unavailable') || code.includes('network') || code.includes('timeout')) {
    return '服務暫時無法使用，請稍後再試。';
  }
  if (code.includes('file_type')) return '檔案格式不符，請選擇 .xlsx 銀行交易明細工作簿。';
  if (code.includes('file_empty')) return '選擇的工作簿沒有內容，請重新選擇檔案。';
  if (code.includes('file_too_large')) return '選擇的工作簿超過允許大小，請改用較小的檔案。';
  if (code.includes('file_changed')) return '工作簿內容已變更，請重新選擇並上傳。';
  if (code.includes('sha256_unavailable')) return '目前無法核對工作簿內容，請重新選擇檔案後再試。';
  return fallback;
}

export const FinancePage: React.FC = () => {
  const { requestLeave } = useUnsavedNavigation();
  const staffIdentity = useStaffIdentityLabels();
  const sharedStaffDirectory = useStaffIdentityDirectory();
  const [entry] = useState(() => {
    const params = new URLSearchParams(window.location.hash.split('?')[1] ?? '');
    return { tab: params.get('tab'), overdue: params.get('view') === 'overdue', caseNo: (params.get('case_no') ?? '').slice(0, 50), fromWorkbench: params.get('from') === 'workbench' };
  });
  const [activeTab, setActiveTab] = useState<FinanceTab>(entry.overdue ? 'accounting-warnings' : entry.tab === 'case-accounting' || entry.tab === 'client-receipts' ? 'case-accounting' : entry.tab === 'accounting-warnings' ? 'accounting-warnings' : entry.tab === 'finance-import' || entry.tab === 'bank' ? 'finance-import' : entry.tab === 'receipt-notices' ? 'receipt-notices' : entry.tab === 'pending' ? 'pending' : entry.tab === 'staff-payables' ? 'staff-payables' : entry.tab === 'payments' || entry.tab === 'accounts-payable' || entry.tab === 'cross-order' ? 'payments' : entry.caseNo && entry.tab !== 'subsidy-advance' ? 'case-accounting' : entry.tab === 'receipts' || entry.tab === 'subsidy-advance' ? 'receipts' : entry.tab === 'government-list' ? 'government-list' : entry.tab === 'monthly' ? 'monthly' : 'case-accounting');
  const [detailReturn, setDetailReturn] = useState<'receipts' | 'payments' | 'monthly' | 'pending'>('monthly');
  const [caseDrawer,setCaseDrawer]=useState(entry.caseNo);
  const [caseClientName,setCaseClientName]=useState('');
  const [caseNotice,setCaseNotice]=useState<'deposit'|'first'|'second'|undefined>();
  const setSubsidyCase=(caseNo:string)=>{if(caseNo)openCase(caseNo);};
  const activeWorkspace = activeTab === 'client-receipts' ? 'case-accounting' : activeTab;
  const [monthlyRange,setMonthlyRange] = useState<AccountingRange>(()=>({start_month:currentMonth(),end_month:currentMonth(),category:'all'}));
  const [receivableFilters,setReceivableFilters] = useState<ReceivableFilters>(()=>({month:currentMonth(),category:'subsidy',status:'all',search:''}));
  const openCase = (caseNo: string,noticeStage?:'deposit'|'first'|'second') => { setCaseClientName(''); setCaseNotice(noticeStage); setSelectedCase(caseNo); setCaseQuery(caseNo); setDetailReturn(activeTab === 'pending' ? 'pending' : activeTab === 'monthly' ? 'monthly' : activeTab === 'payments' || activeTab === 'staff-payables' ? 'payments' : 'receipts'); setCaseDrawer(caseNo); };
  const openBank = () => { setSubsidyCase(''); setActiveTab('finance-import'); };

  const [cases, setCases] = useState<{ id: string; label: string; orderStatus: string }[]>([]);
  const [selectedCase, setSelectedCase] = useState(entry.caseNo);
  const [caseQuery, setCaseQuery] = useState(entry.caseNo);
  const [receipt, setReceipt] = useState<LoadState<ReturnType<typeof adaptClientReceiptQuery>>>({ kind: 'idle' });
  const [caseStaffPayables, setCaseStaffPayables] = useState<LoadState<CaseStaffPayable[]>>({ kind: 'idle' });
  const [staff, setStaff] = useState<{ id: number; label: string }[]>([]);
  const [selectedStaff, setSelectedStaff] = useState<number | null>(null);
  const [payables, setPayables] = useState<LoadState<ReturnType<typeof adaptStaffPayablesQuery>>>({ kind: 'idle' });
  const [historicalStaffCase, setHistoricalStaffCase] = useState('');
  const [targetMonth, setTargetMonth] = useState(currentMonth);
  const [financeWorkbook, setFinanceWorkbook] = useState<File | null>(null);
  const [batches, setBatches] = useState<FinanceImportBatchSummary[]>([]);
  const [selectedBatchIdentity, setSelectedBatchIdentity] = useState<string>('');
  const [ingestion, setIngestion] = useState<LoadState<FinanceWorkbookIngestionReceipt>>({ kind: 'idle' });
  const [batchPreview, setBatchPreview] = useState<LoadState<FinanceImportBatchPreview>>({ kind: 'idle' });
  const [sourceReview, setSourceReview] = useState<LoadState<FinanceImportReviewSnapshot>>({ kind: 'idle' });
  const [correctionRow, setCorrectionRow] = useState<FinanceImportReviewSnapshot['items'][number] | null>(null);
  const [correctionBusy, setCorrectionBusy] = useState(false);
  const [manuallyPostedRows, setManuallyPostedRows] = useState<ReadonlySet<string>>(new Set());
  const [applyReason, setApplyReason] = useState('');
  const [importBusy, setImportBusy] = useState(false);
  const [applyJob, setApplyJob] = useState<LoadState<FinanceImportJobAccepted>>({ kind: 'idle' });
  const [batchOutcome, setBatchOutcome] = useState<LoadState<FinanceImportBatchOutcome>>({ kind: 'idle' });
  const [reload, setReload] = useState(0);
  const staffReload = useRef(reload);
  const controllers = useRef(new Map<string, AbortController>());
  const sequences = useRef(new Map<string, number>());
  const financeApplyCommandByPreview = useRef(new Map<string, { idempotencyKey: string; correlationId: string; reason: string }>());
  const submittedFinanceCommand = batchPreview.kind === 'ready'
    ? financeApplyCommandByPreview.current.get(batchPreview.data.preview_fingerprint)
    : undefined;
  const displayedApplyReason = submittedFinanceCommand?.reason ?? applyReason;
  const confirmedImportReceipt = batchOutcome.kind === 'ready' && batchOutcome.data.status === 'succeeded' ? batchOutcome.data.receipt : null;
  const postingStopped = (batchPreview.kind === 'ready' && !batchPreview.data.apply_allowed) || (batchOutcome.kind === 'ready' && batchOutcome.data.status !== 'succeeded');

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
  }, [activeTab, caseQuery, reload, entry.caseNo]);

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
    if (activeTab !== 'client-receipts' || !selectedCase) return;
    return schedule('case-staff-payables', (request) => {
      setCaseStaffPayables({ kind: 'loading' });
      void accountsPayableQueryClient.queryCase(selectedCase, targetMonth, { signal: request.controller.signal })
        .then((audit) => {
          if (!current('case-staff-payables', request.sequence, request.controller)) return;
          setCaseStaffPayables(audit.items.length > 0
            ? { kind: 'ready', data: audit.items }
            : { kind: 'empty' });
        })
        .catch((error: unknown) => {
          if (current('case-staff-payables', request.sequence, request.controller)) {
            setCaseStaffPayables({ kind: 'error', message: financeErrorMessage(error, '本案月嫂應付款查核失敗，請重新整理。') });
          }
        });
    });
  }, [activeTab, selectedCase, targetMonth, reload]);

  useEffect(() => {
    if (activeTab !== 'staff-payables' && activeTab !== 'finance-import') return;
    if (sharedStaffDirectory !== null) {
      if (staffReload.current !== reload) {
        staffReload.current = reload;
        sharedStaffDirectory.refresh();
        return;
      }
      if (sharedStaffDirectory.status === 'loading') setPayables({ kind: 'loading' });
      else if (sharedStaffDirectory.status === 'error') setPayables({ kind: 'error', message: '服務人員清單載入失敗，請重新整理。' });
      else {
        const people = [...sharedStaffDirectory.people.values()].sort(compareStaffUnionNumbers)
          .map(person => ({ id: person.id, label: staffDisplayLabel(person.unionNo, person.name ?? `服務人員摘要 #${person.id}`) }));
        setStaff(people);
        setSelectedStaff(value => value !== null && people.some(person => person.id === value) ? value : people[0]?.id ?? null);
        if (people.length === 0) setPayables({ kind: 'empty' });
      }
      return;
    }
    return schedule('staff', (request) => {
      setPayables({ kind: 'loading' });
      void loadAllStaffDirectoryPages(
        staffDirectoryClient.queryPage.bind(staffDirectoryClient),
        { pageSize: 200 },
        { signal: request.controller.signal },
      )
      .then((page) => {
        if (!current('staff', request.sequence, request.controller)) return;
        const adapted = adaptStaffDirectoryPage(page).items.sort(compareStaffUnionNumbers).map((item) => ({ id: item.id, label: staffDisplayLabel(item.unionNo, item.displayName) }));
        setStaff(adapted);
        setSelectedStaff((value) => value !== null && adapted.some((item) => item.id === value) ? value : adapted[0]?.id ?? null);
        if (adapted.length === 0) setPayables({ kind: 'empty' });
      })
      .catch((error: unknown) => { if (current('staff', request.sequence, request.controller)) setPayables({ kind: 'error', message: financeErrorMessage(error, '服務人員清單載入失敗，請重新整理。') }); });
    });
  }, [activeTab, reload, sharedStaffDirectory]);

  useEffect(() => {
    if (activeTab !== 'staff-payables' || selectedStaff === null) return;
    if (sharedStaffDirectory !== null && sharedStaffDirectory.status !== 'ready') return;
    return schedule('payables', (request) => {
      setPayables({ kind: 'loading' });
      void staffPayablesQueryClient.query(selectedStaff, { signal: request.controller.signal })
        .then((data) => { if (current('payables', request.sequence, request.controller)) setPayables({ kind: 'ready', data: adaptStaffPayablesQuery(data) }); })
        .catch((error: unknown) => { if (current('payables', request.sequence, request.controller)) setPayables({ kind: 'error', message: financeErrorMessage(error, '月嫂應付款查詢失敗，請重新整理。') }); });
    });
  }, [activeTab, selectedStaff, reload, sharedStaffDirectory]);

  useEffect(() => {
    if (payables.kind !== 'ready') { setHistoricalStaffCase(''); return; }
    const caseNos = [...new Set(payables.data.obligations.map((item) => item.caseNo))];
    setHistoricalStaffCase((value) => caseNos.includes(value) ? value : caseNos[0] ?? '');
  }, [payables]);

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
      while (page.next_after_row_id !== null) {
        page = await financeImportQueryClient.listReviewRows(batchIdentity, {
          signal: request.controller.signal,
          afterRowId: items.at(-1)?.row_id,
        });
        if (!current('source-review', request.sequence, request.controller)) return;
        items.push(...page.items);
      }
      if (items.length !== manifest.review_count) {
        setSourceReview({ kind: 'error', message: '未銷帳明細與統計不一致，請重新查詢。' });
        return;
      }
      setSourceReview({
        kind: 'ready',
        data: { batchIdentity: manifest.batch_identity, reviewCount: items.length, items, sourceReviews: [] },
      });
      setCorrectionRow((currentRow) => currentRow && items.some((row) => row.row_identity === currentRow.row_identity) ? currentRow : null);
    } catch (error) {
      if (current('source-review', request.sequence, request.controller)) {
        setSourceReview({ kind: 'error', message: financeErrorMessage(error, '未銷帳明細載入失敗，請重新查詢。') });
      }
    }
  };

  useEffect(() => {
    if (activeTab !== 'finance-import') return;
    let active = true;
    void (async () => {
      try {
        const list = await financeImportQueryClient.listBatches({ limit: 50 });
        if (!active) return;
        setBatches(list);
        const valid = list.filter((b) => b.batch_identity && b.batch_identity.trim() !== '');
        if (valid.length > 0) {
          setSelectedBatchIdentity((currentId) => {
            const chosen = currentId && valid.some((b) => b.batch_identity === currentId) ? currentId : valid[0].batch_identity!;
            if (sourceReview.kind === 'idle' && batchPreview.kind === 'idle') {
              void loadSourceReview(chosen);
            }
            return chosen;
          });
        }
      } catch {
        // Fallback for offline / unmocked test contexts
      }
    })();
    return () => { active = false; };
  }, [activeTab]);

  const handleSelectBatch = (identity: string) => {
    setSelectedBatchIdentity(identity);
    setBatchPreview({ kind: 'idle' });
    setBatchOutcome({ kind: 'idle' });
    setCorrectionRow(null);
    void loadSourceReview(identity);
  };

  const ingestWorkbook = async () => {
    if (importBusy) return;
    if (financeWorkbook === null) { setIngestion({ kind: 'error', message: '請先選擇 .xlsx 銀行交易明細工作簿。' }); return; }
    setImportBusy(true);
    setIngestion({ kind: 'loading' }); setBatchPreview({ kind: 'idle' }); setSourceReview({ kind: 'idle' }); setApplyJob({ kind: 'idle' }); setBatchOutcome({ kind: 'idle' });
    try {
      const snapshot = await FinanceWorkbookSnapshot.fromFile(financeWorkbook);
      const receipt = await financeImportMutationClient.ingest(snapshot, { idempotencyKey: `ui-finance-ingest-${crypto.randomUUID()}`, correlationId: `ui-finance-ingest-${crypto.randomUUID()}` });
      setIngestion({ kind: 'ready', data: receipt });
      await previewImportedBatch(receipt);
    } catch (error) { setIngestion({ kind: 'error', message: financeErrorMessage(error, '銀行交易明細上傳失敗，請重新選擇檔案。') }); }
    finally { setImportBusy(false); }
  };
  const previewImportedBatch = async (ingested: FinanceWorkbookIngestionReceipt) => {
    const request = start('batch-preview');
    controllers.current.get('source-review')?.abort();
    setBatchPreview({ kind: 'loading' }); setSourceReview({ kind: 'idle' }); setApplyJob({ kind: 'idle' }); setBatchOutcome({ kind: 'idle' });
    try {
      const preview = await financeImportMutationClient.preview(ingested.batch_identity, request.controller.signal);
      if (!current('batch-preview', request.sequence, request.controller)) return;
      setBatchPreview({ kind: 'ready', data: preview });
      if (preview.apply_allowed && preview.counts.ready_dispatch > 0) await applyImportedBatch(preview);
      else await loadSourceReview(preview.batch_identity);
    }
    catch (error) { if (current('batch-preview', request.sequence, request.controller)) setBatchPreview({ kind: 'error', message: financeErrorMessage(error, '銀行交易檢查未完成，請重新按「匯入銀行交易明細」。') }); }
  };
  const applyImportedBatch = async (checked: FinanceImportBatchPreview) => {
    if (!checked.apply_allowed || checked.counts.ready_dispatch <= 0) return;
    if (applyJob.kind === 'loading' || batchOutcome.kind === 'loading') return;
    setApplyJob({ kind: 'loading' }); setBatchOutcome({ kind: 'idle' });
    try {
      const previewFingerprint = checked.preview_fingerprint;
      const command = financeApplyCommandByPreview.current.get(previewFingerprint)
        ?? { idempotencyKey: `ui-finance-apply-${crypto.randomUUID()}`, correlationId: `ui-finance-apply-${crypto.randomUUID()}`, reason: applyReason.trim() };
      financeApplyCommandByPreview.current.set(previewFingerprint, command);
      const accepted = await financeImportMutationClient.apply(checked, command.reason, { idempotencyKey: command.idempotencyKey, correlationId: command.correlationId });
      setApplyJob({ kind: 'ready', data: accepted });
      await observeApplyOutcome(accepted.job_id, {
        batchIdentity: checked.batch_identity,
        previewFingerprint: checked.preview_fingerprint,
      });
    } catch (error) { setApplyJob({ kind: 'error', message: financeErrorMessage(error, '匯入是否受理尚未確認，請按「以原操作確認匯入結果」。') }); }
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
          if (expected && outcome.status !== 'succeeded') {
            financeApplyCommandByPreview.current.delete(expected.previewFingerprint);
          }
          setBatchOutcome({ kind: 'ready', data: outcome });
          setReload((value) => value + 1);
          if (expected) await loadSourceReview(expected.batchIdentity);
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, FINANCE_OUTCOME_POLL_DELAY_MS));
      }
      if (current('batch-outcome', request.sequence, request.controller)) {
        setBatchOutcome({ kind: 'error', message: '正式銷帳仍在處理中；可重新查詢結果，不需重複上傳。' });
      }
    } catch (error) {
      if (current('batch-outcome', request.sequence, request.controller)) setBatchOutcome({ kind: 'error', message: financeErrorMessage(error, '正式匯入結果查詢失敗，請稍後重新查詢。') });
    }
  };
  useUnsavedDraft('銀行交易匯入', { '待匯入檔案': financeWorkbook?.name ?? '', '原因': applyReason }, { baseline: { '待匯入檔案': '', '原因': '' }, enabled: batchOutcome.kind !== 'ready' && !(ingestion.kind === 'ready' && batchPreview.kind === 'ready' && (!batchPreview.data.apply_allowed || batchPreview.data.counts.ready_dispatch <= 0)), busy: importBusy || applyJob.kind === 'loading' || batchOutcome.kind === 'loading' || (submittedFinanceCommand !== undefined && batchOutcome.kind !== 'ready'), save: ingestWorkbook, discard: () => { setFinanceWorkbook(null); setBatchPreview({ kind: 'idle' }); setApplyReason(''); } });


  return (
    <div data-surface-id="finance.page">
      {entry.fromWorkbench && entry.caseNo && <a className="finance-case-return" href={`#order-workbench-v2?case=${encodeURIComponent(entry.caseNo)}`}>← 返回案件處理</a>}
      <header className="page-header-banner finance-page-header">
        <div><h1 className="page-title">帳務工作台</h1><p className="page-subtitle">第8步起追蹤客戶收款與補助退款方案確認，銀行對帳及月報沿原作業處理。</p></div>

      </header>
      <nav className="finance-tab-bar finance-primary-tabs" aria-label="帳務工作區">
        {([['case-accounting','進行中案件'],['finance-import','銀行對帳'],['government-list','政府補助清單'],['monthly','每月帳務']] as const).map(([id,label])=><button key={id} type="button" data-surface-id={`finance.tab.${id}`} className={activeWorkspace===id?'active':''} aria-current={activeWorkspace===id?'page':undefined} onClick={()=>requestLeave(()=>setActiveTab(id))}>{label}</button>)}
      </nav>
      {activeTab==='receipt-notices'&&<PaymentReceiptNoticeWorkbench revision={reload} expanded/>}
      {activeTab==='monthly'&&<FinanceMonthlyAccounting revision={reload} initialRange={monthlyRange} onRangeChange={setMonthlyRange} onCase={openCase}/>}
      {activeTab==='pending'&&<><FinanceReceivableItems revision={reload} undatedOnly onCase={openCase}/><FinancePaymentsWorkspace pendingOnly revision={reload} targetMonth={targetMonth} onMonthChange={setTargetMonth} onOpenCase={openCase} onOpenStaff={staffId=>{if(staffId!==undefined)setSelectedStaff(staffId);setActiveTab('staff-payables');}} onOpenSubsidy={setSubsidyCase} onOpenBank={openBank}/></>}
      {(activeTab === 'client-receipts' || activeTab === 'staff-payables') && <div className="finance-toolbar"><button type="button" className="finance-reload-btn" onClick={() => { requestLeave(() => setActiveTab(activeTab === 'staff-payables' ? 'payments' : detailReturn)); }}>← 返回{activeTab === 'staff-payables' || detailReturn === 'payments' ? '付款' : '收款'}清單</button><div className="finance-row-actions">{selectedCase && activeTab === 'client-receipts' && <button type="button" onClick={() => setSubsidyCase(selectedCase)}>案件補助明細</button>}<button type="button" onClick={() => setReload(value => value + 1)}>重新整理</button></div></div>}
      {activeTab === 'receipts' && <FinanceReceiptsWorkspace revision={reload} initialFilters={receivableFilters} onFiltersChange={setReceivableFilters} initialView={entry.overdue?'overdue':'all'} onOpenBank={caseNo=>{setSelectedCase(caseNo);setCaseQuery(caseNo);openBank();}} initialSource={entry.tab === 'subsidy-advance' ? 'government' : 'client'} initialRecovery={entry.tab === 'subsidy-advance'} onOpenCase={openCase} onOpenSubsidy={setSubsidyCase} />}
      {activeTab === 'payments' && <FinancePaymentsWorkspace revision={reload} targetMonth={targetMonth} onMonthChange={setTargetMonth} onOpenCase={openCase} onOpenStaff={staffId => { if (staffId !== undefined) setSelectedStaff(staffId); setActiveTab('staff-payables'); }} onOpenSubsidy={setSubsidyCase} onOpenBank={openBank} />}

      {activeTab === 'client-receipts' && (
        <section className="finance-workspace">
          <div className="finance-section-heading">
            <div>
              <h2>客戶收款資料</h2>
              <p>各期應付由完整案件資料自動計算；請至「銀行對帳」核對實際入款並確認核銷，金額或歸屬不符時先核對原因。</p>
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
                onChange={(event) => { const value = event.target.value; requestLeave(() => setSelectedCase(value)); }}
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
              <table className="finance-table">
                <thead>
                  <tr>
                    <th>階段</th>
                    <th>應收</th>
                    <th>到期日</th>
                  </tr>
                </thead>
                <tbody>
                  {receipt.data.obligations.map((item) => (
                    <tr key={item.id} data-obligation-id={item.id}>
                      <td><span className="finance-badge finance-badge-stage">{{ deposit: '訂金', first: '第一期', second: '第二期', adjustment: '調整款' }[item.stage]}</span></td>
                      <td><strong>{item.amountDue}</strong></td>
                      <td>{item.dueDate}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="finance-detail-block" role="region" aria-label="本案月嫂應付查核">
                <h3>本案月嫂應付</h3>
                <p>依案件帳務或歷史服務資料顯示應付金額；尚未確認的金額與日期以「未確認」顯示。</p>
                <StateMessage state={caseStaffPayables} empty="找不到本案可核對的月嫂應付來源。" />
                {caseStaffPayables.kind === 'ready' && (
                  <div className="finance-table-container">
                    <table className="finance-table">
                      <thead><tr><th>月嫂</th><th>應付</th><th>待付</th><th>應付日期</th></tr></thead>
                      <tbody>{caseStaffPayables.data.map((item, index) => {
                        return <tr key={item.obligation_identity ?? `${item.case_no}:${item.staff_id ?? 'unknown'}:${index}`}>
                          <td>{staffIdentity.label(item.staff_id, item.recipient_name)}</td>
                          <td>{item.amount_due_ntd === null ? '未確認' : `NT$ ${item.amount_due_ntd.toLocaleString()}`}</td>
                          <td>{item.balance_ntd === null ? '未確認' : `NT$ ${item.balance_ntd.toLocaleString()}`}</td>
                          <td>{item.effective_due_date ?? item.order_due_date ?? '未確認'}</td>
                        </tr>;
                      })}</tbody>
                    </table>
                  </div>
                )}
              </div>

              <div className="finance-detail-block">
                <h3>待核對銀行交易</h3>
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
                <>
                  <HistoricalClientPaymentWorkbench caseNo={selectedCase} />
                  {cases.find((item) => item.id === selectedCase)?.orderStatus === '歷史訂單－服務完成' && <div className="finance-detail-block"><h3>歷史案件帳務完成</h3><HistoricalCompletionPanel key={`${selectedCase}:${reload}`} caseNo={selectedCase} onCompleted={() => setReload(value => value + 1)} /></div>}
                </>
              ) : (
                <div className="finance-state">此為正常案件；歷史人工收款確認只會在歷史案件顯示。</div>
              )}
            </>
          )}
        </section>
      )}
      {activeTab === 'client-receipts' && selectedCase && <FinanceCaseHistory caseNo={selectedCase} revision={reload} />}
      {activeTab === 'staff-payables' && (
        <section className="finance-workspace">
          <div className="finance-section-heading">
            <div>
              <h2>月嫂應付款與付款事件</h2>
              <p>正常付款由銀行交易明細匯入自動核銷；不唯一或金額不符時，請到「銀行對帳」查看該批次的人工核對清單。</p>
            </div>
          </div>

          <div className="finance-filter-bar">
            <label>
              服務人員
              <select
                className="finance-select"
                value={selectedStaff ?? ''}
                onChange={(event) => { const value = Number(event.target.value); requestLeave(() => setSelectedStaff(value)); }}
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
              <table className="finance-table">
                <thead>
                  <tr>
                    <th>案件</th>
                    <th>應付</th>
                    <th>已付</th>
                    <th>餘額</th>
                    <th>應付日</th>
                    <th>付款狀態</th>
                  </tr>
                </thead>
                <tbody>
                  {payables.data.obligations.map((item) => (
                    <tr key={item.id} data-obligation-id={item.id}>
                      <td><strong>{item.caseNo}</strong></td>
                      <td>{item.amountDue}</td>
                      <td style={{ color: '#16a34a' }}>{item.netPaid}</td>
                      <td style={{ color: '#ea580c', fontWeight: 700 }}>{item.balance}</td>
                      <td>{item.dueDate}</td>
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
                  <select value={historicalStaffCase} onChange={(event) => { const value=event.target.value;requestLeave(()=>setHistoricalStaffCase(value)); }}>
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

      {activeTab==='case-accounting'&&<FinanceCaseList revision={reload} onCase={openCase} onNotice={(caseNo,stage)=>openCase(caseNo,stage)}/>}
      {activeTab==='government-list'&&<FinanceGovernmentSubsidyList revision={reload} onCase={openCase}/>}

      {activeTab === 'accounting-warnings' && <FinanceWarningWorkspace onCase={openCase} onBank={caseNo=>{setSelectedCase(caseNo);setCaseQuery(caseNo);openBank();}} />}
      {activeTab === 'finance-import' && (
        <section className="finance-workspace" data-surface-id="finance.finance-import.workflow">
          {/* 1. 緊湊型頂部工具列 */}
          <div className="finance-section-heading" style={{ borderBottom: '1px solid #f2e2dc', paddingBottom: '14px', marginBottom: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
              <h2 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span>🏦 銀行流水對帳</span>
              </h2>
              {batches.filter(b => b.batch_identity).length > 0 && (
                <label style={{ margin: 0, fontWeight: 600, fontSize: '0.84rem' }}>
                  <select
                    className="finance-select"
                    style={{ minHeight: '36px', padding: '6px 12px' }}
                    value={selectedBatchIdentity}
                    onChange={(e) => handleSelectBatch(e.target.value)}
                    aria-label="選擇匯入批次"
                  >
                    {batches.filter(b => b.batch_identity).map((b) => (
                      <option key={b.batch_identity!} value={b.batch_identity!}>
                        批次 #{b.batch_id} · {b.format_id === 'taishin' ? '台新銀行' : b.format_id === 'sinopac' ? '永豐銀行' : '歷史格式'} ({b.row_count} 筆)
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>
          </div>

          {/* 2. 緊湊一列式檔案上傳列 */}
          <div
            className="finance-inline-import"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: '12px',
              padding: '12px 16px',
              background: '#fffaf7',
              border: '1px dashed #fed9b8',
              borderRadius: '10px',
              marginBottom: '16px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
              <input
                type="file"
                accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                aria-label="選擇銀行交易明細工作簿"
                className="finance-input"
                style={{ padding: '6px 10px', fontSize: '0.82rem' }}
                disabled={importBusy || ingestion.kind === 'loading' || batchPreview.kind === 'loading' || applyJob.kind === 'loading' || batchOutcome.kind === 'loading' || (submittedFinanceCommand !== undefined && batchOutcome.kind !== 'ready')}
                onChange={(event) => {
                  controllers.current.get('batch-preview')?.abort();
                  controllers.current.get('source-review')?.abort();
                  controllers.current.get('batch-outcome')?.abort();

                  setFinanceWorkbook(event.target.files?.[0] ?? null);
                  setIngestion({ kind: 'idle' });
                  setBatchPreview({ kind: 'idle' });
                  setCorrectionRow(null);
                  setManuallyPostedRows(new Set());
                  setApplyJob({ kind: 'idle' });
                  setBatchOutcome({ kind: 'idle' });
                }}
              />
              <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.82rem', margin: 0 }}>
                正式銷帳原因（選填）
                <input
                  className="finance-input"
                  placeholder="輸入銷帳說明"
                  value={displayedApplyReason}
                  maxLength={500}
                  disabled={importBusy || ingestion.kind === 'loading' || batchPreview.kind === 'loading' || applyJob.kind === 'loading' || batchOutcome.kind === 'loading' || submittedFinanceCommand !== undefined}
                  onChange={event => setApplyReason(event.target.value)}
                  style={{ width: '200px', minHeight: '34px', padding: '6px 10px' }}
                />
              </label>
              <button
                className="finance-btn-primary"
                data-control-id="finance.finance-import.upload"
                disabled={importBusy || financeWorkbook === null || ingestion.kind === 'loading' || batchPreview.kind === 'loading' || applyJob.kind === 'loading' || batchOutcome.kind === 'loading' || submittedFinanceCommand !== undefined}
                onClick={() => void ingestWorkbook()}
                style={{ padding: '7px 14px' }}
              >
                {ingestion.kind === 'loading' || batchPreview.kind === 'loading' || applyJob.kind === 'loading' || batchOutcome.kind === 'loading' ? '匯入中…' : '匯入銀行交易明細'}
              </button>
            </div>
          </div>

          {ingestion.kind === 'error' && <StateMessage state={ingestion} empty="" />}
          {batchPreview.kind === 'error' && <StateMessage state={batchPreview} empty="" />}

          <FinancePostedBankTransactions onCase={openCase} revision={reload}/>
          {/* 3. 核心未銷帳明細工作台 (常駐呈現) */}
          <div style={{ marginTop: '10px' }}>
            {(confirmedImportReceipt || (batchPreview.kind === 'ready' && !importBusy && (!batchPreview.data.apply_allowed || batchPreview.data.counts.ready_dispatch === 0))) && (
              <div className="finance-meta" aria-label="匯入結果">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                  <span>本次已銷帳 {(confirmedImportReceipt?.reconciled_count ?? 0) + manuallyPostedRows.size} 筆｜已存在略過 {confirmedImportReceipt?.existing_count ?? (batchPreview.kind === 'ready' ? batchPreview.data.counts.existing : 0)} 筆</span>
                  {batchPreview.kind === 'ready' && !batchPreview.data.apply_allowed && (
                    <span style={{ color: '#c5221f', fontWeight: 700 }} role="alert">
                      （自動銷帳未執行：{financeImportBlockerMessage(batchPreview.data.blocking_codes)}。資料已匯入入帳，請查看未銷帳明細與原因）
                    </span>
                  )}
                </div>
              </div>
            )}

            <StateMessage state={sourceReview} empty="目前沒有未銷帳資料。" />

            {sourceReview.kind === 'ready' && (
              <div id="finance-import-review" className="finance-detail-block" data-surface-id="finance.finance-import.manual-review" style={{ marginTop: '12px' }}>
                <div className="finance-meta" style={{ background: '#ffffff', border: 'none', padding: '0 0 10px 0' }}>
                  <span style={{ fontWeight: 800, fontSize: '0.92rem', color: '#1e1b19' }}>
                    未銷帳明細 {sourceReview.data.items.length + sourceReview.data.sourceReviews.length} 筆
                  </span>
                  <button
                    className="finance-btn-secondary"
                    data-control-id="finance.finance-import.review-reload"
                    onClick={() => void loadSourceReview(sourceReview.data.batchIdentity)}
                    style={{ padding: '5px 12px', fontSize: '0.8rem' }}
                  >
                    重新查詢未銷帳明細
                  </button>
                </div>

                {sourceReview.data.items.length + sourceReview.data.sourceReviews.length === 0 ? (
                  <div className="finance-state">目前沒有未銷帳資料。</div>
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
                          <th>未銷帳原因</th>
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
                            <td>請核對來源資料</td>
                          </tr>
                        ))}
                        {sourceReview.data.items.map((row) => (
                          <tr key={row.row_id}>
                            <td><code>{row.source_sheet}#{row.source_row}</code></td>
                            <td>{row.transaction_date ?? '—'}</td>
                            <td>
                              <span className={['incoming', 'credit'].includes(row.direction) ? 'tag-incoming' : 'tag-outgoing'}>
                                {{ incoming: '存入', credit: '存入', outgoing: '支出', debit: '支出' }[row.direction] ?? '待確認'}
                              </span>
                            </td>
                            <td><strong>{row.amount_ntd}</strong></td>
                            <td>{{ receivable: '應收', payable: '應付', government_subsidy: '政府補助', subsidy_return: '補助退款', review: '待核對', legacy: '歷史格式' }[row.bank_type ?? 'legacy']}</td>
                            <td className="finance-review-reason">{financeImportReviewReason(row, batchPreview.kind === 'ready' ? batchPreview.data.rows.find(item => item.row_identity === row.row_identity) : undefined, postingStopped)}</td>
                            <td>
                              {row.disposition === 'blocked' || (batchPreview.kind === 'ready' && batchPreview.data.rows.find(item => item.row_identity === row.row_identity)?.disposition === 'blocked') ? (
                                <span>銷帳受阻</span>
                              ) : canCorrectFinanceImportRow(row, batchPreview.kind === 'ready' ? batchPreview.data.rows.find(item => item.row_identity === row.row_identity) : undefined) ? (
                                <button
                                  type="button"
                                  className={row.classification_type === 'client_refund' ? 'finance-btn-primary' : 'finance-btn-secondary'}
                                  style={{ padding: '4px 10px', fontSize: '0.78rem' }}
                                  onClick={() => requestLeave(() => setCorrectionRow(row))}
                                >
                                  {row.classification_type === 'staff_payout' ? '處理月嫂付款' : row.classification_type === 'client_refund' ? '處理客戶退款' : '指定正確訂單'}
                                </button>
                              ) : (
                                '—'
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {correctionRow && (
                  <Drawer isOpen onClose={() => setCorrectionRow(null)} closeDisabled={correctionBusy} closeLabel="關閉" ariaLabel="指定銀行入款的正確訂單" title={correctionRow.classification_type === 'staff_payout' ? '處理月嫂付款' : correctionRow.classification_type === 'client_refund' ? '處理客戶退款' : '指定正確訂單'}>
                    <div className="finance-scope-note">
                      <strong>{correctionRow.source_sheet}#{correctionRow.source_row}</strong>
                      <p>{correctionRow.transaction_date ?? '日期未提供'}｜{['incoming', 'credit'].includes(correctionRow.direction) ? '存入' : '支出'} NT$ {correctionRow.amount_ntd.toLocaleString()}</p>
                      <p><strong>未銷帳原因：</strong>{financeImportReviewReason(correctionRow, batchPreview.kind === 'ready' ? batchPreview.data.rows.find(item => item.row_identity === correctionRow.row_identity) : undefined, postingStopped)}</p>
                    </div>
                    <FinanceImportCorrectionForm
                      key={correctionRow.row_identity}
                      rowIdentity={correctionRow.row_identity}
                      sourceLabel={`${correctionRow.source_sheet} 第 ${correctionRow.source_row} 列`}
                      staff={staff}
                      initialKind={correctionRow.classification_type === 'client_refund' ? 'client_refund' : correctionRow.classification_type === 'staff_payout' ? 'staff_payout' : 'client_receipt'}
                      onBusyChange={setCorrectionBusy}
                      onPosted={() => {
                        setManuallyPostedRows(rows => new Set([...rows, correctionRow.row_identity]));
                        setReload(value => value + 1);
                        void loadSourceReview(sourceReview.data.batchIdentity);
                      }}
                    />
                  </Drawer>
                )}
              </div>
            )}

            {sourceReview.kind === 'error' && (
              <button
                className="finance-btn-secondary"
                style={{ marginTop: '10px' }}
                data-control-id="finance.finance-import.review-reload"
                onClick={() => void loadSourceReview(selectedBatchIdentity || (batchPreview.kind === 'ready' ? batchPreview.data.batch_identity : ''))}
              >
                重新查詢未銷帳明細
              </button>
            )}

            {applyJob.kind === 'error' && submittedFinanceCommand && batchPreview.kind === 'ready' && (
              <button type="button" className="finance-btn-primary" disabled={batchOutcome.kind === 'loading'} onClick={() => void applyImportedBatch(batchPreview.data)}>以原操作確認匯入結果</button>
            )}
          </div>

          {applyJob.kind === 'error' && <StateMessage state={applyJob} empty="" />}
          {batchOutcome.kind === 'error' && <StateMessage state={batchOutcome} empty="" />}
          {applyJob.kind === 'ready' && batchOutcome.kind === 'error' && (
            <button type="button" className="finance-btn-secondary" data-control-id="finance.finance-import.receipt" onClick={() => void observeApplyOutcome(applyJob.data.job_id, batchPreview.kind === 'ready' ? { batchIdentity: batchPreview.data.batch_identity, previewFingerprint: batchPreview.data.preview_fingerprint } : undefined)}>重新查詢匯入結果</button>
          )}
          {batchOutcome.kind === 'ready' && batchOutcome.data.status !== 'succeeded' && <p role="alert">未完成銷帳，請查看未銷帳明細與原因。</p>}

          {/* 成功對帳歷史明細 (置於底部) */}
          <div style={{ marginTop: '24px', paddingTop: '16px', borderTop: '1px solid #f2e2dc' }}>
            <FinanceStatementArchive />
          </div>
        </section>
      )}
      <details className="finance-related-tools"><summary>其他帳務作業</summary><nav className="finance-tab-bar" aria-label="帳務相關工具">{([['receipts','應收款'],['payments','應付款'],['staff-payables','人員付款'],['pending','待確認與預估'],['receipt-notices','入帳通知'],['accounting-warnings','逾期提醒']] as const).map(([id,label])=><button type="button" key={id} aria-current={activeTab===id?'page':undefined} onClick={()=>requestLeave(()=>setActiveTab(id))}>{label}</button>)}</nav></details>
      {caseDrawer&&<Drawer isOpen title={caseDrawer+(caseClientName?' · '+caseClientName:'')} ariaLabel={'案件帳務 · '+caseDrawer} closeLabel="關閉案件" size="xl" className="finance-accounting-drawer" onClose={()=>setCaseDrawer('')} footer={<button type="button" className="finance-btn-secondary" onClick={()=>requestLeave(()=>setCaseDrawer(''))}>關閉案件</button>}>
        <FinanceCaseAccounting key={caseDrawer} embedded initialCase={caseDrawer} initialNoticeStage={caseNotice} onIdentity={(caseNo,name)=>{if(caseNo===caseDrawer)setCaseClientName(name);}} onChanged={()=>setReload(value=>value+1)}/>
      </Drawer>}
    </div>
  );
};

export default FinancePage;

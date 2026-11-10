/**
 * File: FinancePage.tsx
 * Description: 呈現帳務四大工作區（案件帳務、銀行對帳、政府補助清單、每月帳務）並協調銀行對帳單匯入與自動核銷生命週期。
 */
import React, { useEffect, useRef, useState } from 'react';
import { ManagementPageHeader } from '../components/ManagementPageHeader';
import { useUnsavedDraft, useUnsavedNavigation } from '../components/UnsavedChanges';
import { useStaffIdentityLabels } from '../components/StaffIdentityProvider';
import { subscribeCaseAccountingChanges } from '../api/shared/case_accounting_changes';
import { Drawer } from '../components/Drawer';
import './FinancePage.css';
import { FinanceWorkbookSnapshot, financeImportMutationClient, type FinanceImportBatchOutcome, type FinanceImportBatchPreview, type FinanceImportJobAccepted, type FinanceWorkbookIngestionReceipt } from '../api/finance_import/finance_import_mutation_client';
import { FinanceImportQueryError } from '../api/finance_import/finance_import_query_errors';

import { FinanceCaseList } from '../components/FinanceCaseList';
import { FinanceGovernmentSubsidyList } from '../components/FinanceGovernmentSubsidyList';
import { FinanceMonthlyAccounting } from '../components/FinanceMonthlyAccounting';
import type { HistoricalPayableAuditItem } from '../api/accounts_payable/accounts_payable_query_schemas';
import { HistoricalPayableEditor } from '../components/HistoricalPayableReview';
import type { AccountingRange } from '../api/finance_import/monthly_accounting_client';
import type { FinanceBankTransaction } from '../api/finance_import/finance_import_query_schemas';
import { SubsidyPeriodWorkbench } from '../components/SubsidyPeriodWorkbench';
import { FinanceCaseAccounting } from '../components/FinanceCaseAccounting';
import { FinanceBankReconciliationWorkspace } from '../components/FinanceBankReconciliationWorkspace';

export type FinanceTab = 'case-accounting' | 'finance-import' | 'government-list' | 'monthly';
type LoadState<T> = { kind: 'idle' | 'loading' } | { kind: 'ready'; data: T } | { kind: 'empty' } | { kind: 'error'; message: string } | { kind: 'unavailable'; message: string };
type IngestionCommand = Parameters<typeof financeImportMutationClient.queryIngestionOutcome>[0];
const FINANCE_OUTCOME_POLL_LIMIT = 10;
const FINANCE_OUTCOME_POLL_DELAY_MS = 500;

function canApplyImportedBatch(preview: FinanceImportBatchPreview): boolean {
  return preview.apply_allowed && (preview.counts.ready_dispatch > 0 || preview.rows.some(
    row => row.disposition === 'business_pending' && (row.client_receipt_review != null || row.pending_reason != null),
  ));
}

function currentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

function normalizeFinanceTab(tab: string | null, overdue: boolean, hasCaseNo: boolean): FinanceTab {
  if (overdue) return 'case-accounting';
  if (!tab) return hasCaseNo ? 'case-accounting' : 'case-accounting';
  switch (tab) {
    case 'finance-import':
    case 'bank':
    case 'pending':
      return 'finance-import';
    case 'government-list':
    case 'subsidy-advance':
      return 'government-list';
    case 'monthly':
    case 'payment-destination':
    case 'payments':
    case 'staff-payables':
    case 'receipt-notices':
      return 'monthly';
    case 'case-accounting':
    case 'client-receipts':
    case 'receipts':
    case 'accounting-warnings':
    default:
      return 'case-accounting';
  }
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
  const message = typeof detail.message === 'string' && detail.message.trim() ? detail.message.trim() : '';
  if (message && message !== fallback) return message;
  return fallback;
}

export const FinancePage: React.FC = () => {
  const { requestLeave } = useUnsavedNavigation();
  useStaffIdentityLabels();
  const [entry] = useState(() => {
    const params = new URLSearchParams(window.location.hash.split('?')[1] ?? '');
    return {
      tab: params.get('tab'),
      overdue: params.get('view') === 'overdue',
      caseNo: (params.get('case_no') ?? '').slice(0, 50),
      fromWorkbench: params.get('from') === 'workbench',
      subTab: params.get('subtab') === 'all' ? ('all' as const) : ('ongoing' as const),
    };
  });
  const [activeTab, setActiveTab] = useState<FinanceTab>(() =>
    normalizeFinanceTab(entry.tab, entry.overdue, Boolean(entry.caseNo))
  );
  const [caseDrawer, setCaseDrawer] = useState(entry.caseNo);
  const [payableReview, setPayableReview] = useState<HistoricalPayableAuditItem | null>(null);
  const [bankReview, setBankReview] = useState<FinanceBankTransaction | null>(null);
  const [cancellationPosted, setCancellationPosted] = useState(false);
  const [bankReviewBusy, setBankReviewBusy] = useState(false);
  const [caseClientName, setCaseClientName] = useState('');
  const [caseNotice, setCaseNotice] = useState<'deposit' | 'first' | 'second' | undefined>();
  const [monthlyRange, setMonthlyRange] = useState<AccountingRange>(() => ({
    start_month: currentMonth(),
    end_month: currentMonth(),
    category: 'all',
  }));

  const openCase = (caseNo: string, noticeStage?: 'deposit' | 'first' | 'second') => {
    setBankReview(null);
    setPayableReview(null);
    setCancellationPosted(false);
    setCaseClientName('');
    setCaseNotice(noticeStage);
    setCaseDrawer(caseNo);
  };

  const openBankReview = (row: FinanceBankTransaction) => {
    if (row.status !== 'pending' || row.disposition === 'blocked') return;
    const targetCase = row.reconciliation_target?.case_no;
    if (!targetCase && (row.classification_type !== 'government_subsidy' || row.direction === 'unknown')) return;
    if (targetCase) openCase(targetCase);
    else setCaseDrawer('');
    setBankReview(row);
  };

  const closeCase = () => {
    setCaseDrawer('');
    setPayableReview(null);
    setBankReview(null);
    setCancellationPosted(false);
  };

  const bankReviewPosted = () => {
    if (bankReview?.reconciliation_target?.obligation_identities.some(id => id.startsWith('client-cancellation:'))) {
      setBankReview(null);
      setCancellationPosted(true);
    } else {
      closeCase();
    }
    setReload(value => value + 1);
    requestAnimationFrame(() => document.querySelector<HTMLElement>('[data-bank-reconciliation-focus]')?.focus({ preventScroll: true }));
  };

  const [financeWorkbook, setFinanceWorkbook] = useState<File | null>(null);
  const [ingestion, setIngestion] = useState<LoadState<FinanceWorkbookIngestionReceipt>>({ kind: 'idle' });
  const [batchPreview, setBatchPreview] = useState<LoadState<FinanceImportBatchPreview>>({ kind: 'idle' });
  const [unconfirmedIngestion, setUnconfirmedIngestion] = useState<IngestionCommand | null>(null);
  const [ingestionRecordMissing, setIngestionRecordMissing] = useState(false);
  const [applyReason, setApplyReason] = useState('');
  const [importBusy, setImportBusy] = useState(false);
  const [applyJob, setApplyJob] = useState<LoadState<FinanceImportJobAccepted>>({ kind: 'idle' });
  const [batchOutcome, setBatchOutcome] = useState<LoadState<FinanceImportBatchOutcome>>({ kind: 'idle' });
  const [reload, setReload] = useState(0);
  useEffect(() => subscribeCaseAccountingChanges(() => setReload(value => value + 1)), []);
  const controllers = useRef(new Map<string, AbortController>());
  const sequences = useRef(new Map<string, number>());
  const financeApplyCommandByPreview = useRef(new Map<string, { idempotencyKey: string; correlationId: string; reason: string }>());
  const submittedFinanceCommand = batchPreview.kind === 'ready'
    ? financeApplyCommandByPreview.current.get(batchPreview.data.preview_fingerprint)
    : undefined;
  const displayedApplyReason = submittedFinanceCommand?.reason ?? applyReason;
  const confirmedImportReceipt = batchOutcome.kind === 'ready' && batchOutcome.data.status === 'succeeded' ? batchOutcome.data.receipt : null;

  useEffect(() => () => controllers.current.forEach((controller) => controller.abort()), []);

  useEffect(() => {
    const onHashChange = () => {
      const hash = window.location.hash;
      if (!hash.startsWith('#finance')) return;
      const params = new URLSearchParams(hash.split('?')[1] ?? '');
      const tab = params.get('tab');
      const overdue = params.get('view') === 'overdue';
      const caseNo = (params.get('case_no') ?? '').slice(0, 50);
      setActiveTab(normalizeFinanceTab(tab, overdue, Boolean(caseNo)));
      if (caseNo) {
        setCaseDrawer(caseNo);
      }
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

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


  const ingestWorkbook = async (original?: IngestionCommand) => {
    if (importBusy || (unconfirmedIngestion && !original)) return;
    if (financeWorkbook === null) { setIngestion({ kind: 'error', message: '請先選擇 .xlsx 銀行交易明細工作簿。' }); return; }
    setImportBusy(true);
    setIngestion({ kind: 'loading' }); setBatchPreview({ kind: 'idle' }); setApplyJob({ kind: 'idle' }); setBatchOutcome({ kind: 'idle' });
    setIngestionRecordMissing(false);
    let command: IngestionCommand | null = null;
    try {
      const snapshot = await FinanceWorkbookSnapshot.fromFile(financeWorkbook);
      if (original && original.sourceDigest !== snapshot.sha256) {
        setIngestion({ kind: 'error', message: '檔案內容與原次匯入不同，請查詢原次結果。' });
        return;
      }
      command = original ?? {
        idempotencyKey: `ui-finance-ingest-${crypto.randomUUID()}`,
        correlationId: `ui-finance-ingest-${crypto.randomUUID()}`,
        sourceDigest: snapshot.sha256,
      };
      const receipt = await financeImportMutationClient.ingest(snapshot, command);
      setUnconfirmedIngestion(null);
      setIngestion({ kind: 'ready', data: receipt });
      await previewImportedBatch(receipt);
    } catch (error) {
      const status = error instanceof FinanceImportQueryError ? error.status : undefined;
      if (command && (status === undefined || status >= 500 || status === 408)) {
        setUnconfirmedIngestion(command);
        setIngestion({ kind: 'error', message: '本次匯入結果尚未確認，請查詢原次結果。' });
      } else {
        setReload(value => value + 1);
        setIngestion({ kind: 'error', message: financeErrorMessage(error, '銀行交易明細上傳失敗，請確認檔案。') });
      }
    } finally { setImportBusy(false); }
  };

  const lookupIngestion = async () => {
    if (!unconfirmedIngestion || importBusy) return;
    setImportBusy(true);
    setIngestionRecordMissing(false);
    try {
      const outcome = await financeImportMutationClient.queryIngestionOutcome(unconfirmedIngestion);
      if (outcome.status === 'committed' && outcome.receipt) {
        setUnconfirmedIngestion(null);
        setIngestion({ kind: 'ready', data: outcome.receipt });
        await previewImportedBatch(outcome.receipt);
      } else if (outcome.status === 'rolled_back') {
        setUnconfirmedIngestion(null);
        setIngestion({ kind: 'error', message: '已確認原次匯入失敗，流水未保存。' });
        setReload(value => value + 1);
      } else {
        setIngestionRecordMissing(true);
        setIngestion({ kind: 'error', message: '尚未查到原次匯入結果。可以稍後再查，或以原操作重送同一份檔案。' });
      }
    } catch (error) {
      setIngestion({ kind: 'error', message: financeErrorMessage(error, '暫時無法查詢原次匯入，請稍後再試。') });
    } finally { setImportBusy(false); }
  };

  const previewImportedBatch = async (ingested: FinanceWorkbookIngestionReceipt) => {
    const request = start('batch-preview');
    setBatchPreview({ kind: 'loading' }); setApplyJob({ kind: 'idle' }); setBatchOutcome({ kind: 'idle' });
    try {
      const preview = await financeImportMutationClient.preview(ingested.batch_identity, request.controller.signal);
      if (!current('batch-preview', request.sequence, request.controller)) return;
      setBatchPreview({ kind: 'ready', data: preview });
      if (canApplyImportedBatch(preview) && !preview.rows.some(row => row.subsidy_preflight != null)) {
        await applyImportedBatch(preview);
      } else {
        setReload(value => value + 1);
      }
    }
    catch (error) {
      if (current('batch-preview', request.sequence, request.controller)) {
        setBatchPreview({ kind: 'error', message: financeErrorMessage(error, '銀行交易檢查未完成，請重新按「匯入銀行交易明細」。') });
        setReload(value => value + 1);
      }
    }
  };

  const applyImportedBatch = async (checked: FinanceImportBatchPreview) => {
    if (!canApplyImportedBatch(checked)) return;
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
    } catch (error) {
      setApplyJob({ kind: 'error', message: financeErrorMessage(error, '匯入是否受理尚未確認，請按「以原操作確認匯入結果」。') });
      setReload(value => value + 1);
    }
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
          if (outcome.status === 'succeeded') {
            setApplyReason('');
          }
          setBatchOutcome({ kind: 'ready', data: outcome });
          setReload((value) => value + 1);
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, FINANCE_OUTCOME_POLL_DELAY_MS));
      }
      if (current('batch-outcome', request.sequence, request.controller)) {
        setBatchOutcome({ kind: 'error', message: '正式銷帳仍在處理中；可重新查詢結果，不需重複上傳。' });
        setReload((value) => value + 1);
      }
    } catch (error) {
      if (current('batch-outcome', request.sequence, request.controller)) {
        setBatchOutcome({ kind: 'error', message: financeErrorMessage(error, '正式匯入結果查詢失敗，請稍後重新查詢。') });
        setReload((value) => value + 1);
      }
    }
  };

  useUnsavedDraft(
    '銀行交易匯入',
    { '原因': applyReason },
    {
      baseline: { '原因': '' },
      enabled: activeTab === 'finance-import' && !caseDrawer && batchOutcome.kind !== 'ready',
      busy:
        unconfirmedIngestion !== null ||
        importBusy ||
        ingestion.kind === 'loading' ||
        batchPreview.kind === 'loading' ||
        applyJob.kind === 'loading' ||
        batchOutcome.kind === 'loading' ||
        (submittedFinanceCommand !== undefined && batchOutcome.kind !== 'ready'),
      discard: () => { setFinanceWorkbook(null); setBatchPreview({ kind: 'idle' }); setApplyReason(''); },
    }
  );

  return (
    <div data-surface-id="finance.page">
      <ManagementPageHeader
        className="finance-page-header"
        title="帳務工作台"
        description="四大核心工作區：案件帳務、銀行對帳、政府補助清單、每月帳務。"
      >
        {entry.fromWorkbench && entry.caseNo && (
          <a className="finance-case-return" href={`#order-workbench-v2?case=${encodeURIComponent(entry.caseNo)}`}>
            ← 返回案件處理
          </a>
        )}
      </ManagementPageHeader>

      <nav className="finance-tab-bar finance-primary-tabs" aria-label="帳務工作區">
        {([
          ['case-accounting', '案件帳務'],
          ['finance-import', '銀行對帳'],
          ['government-list', '政府補助清單'],
          ['monthly', '每月帳務'],
        ] as const).map(([id, label]) => (
          <button
            key={id}
            type="button"
            data-surface-id={`finance.tab.${id}`}
            className={activeTab === id ? 'active' : ''}
            aria-current={activeTab === id ? 'page' : undefined}
            onClick={() => requestLeave(() => setActiveTab(id))}
          >
            {label}
          </button>
        ))}
      </nav>

      {activeTab === 'case-accounting' && (
        <FinanceCaseList
          revision={reload}
          initialSubTab={entry.subTab}
          onCase={openCase}
          onNotice={(caseNo, stage) => openCase(caseNo, stage)}
        />
      )}

      {activeTab === 'finance-import' && (
        <FinanceBankReconciliationWorkspace
          onCase={openCase}
          revision={reload}
          ingestionNeedsLookup={unconfirmedIngestion !== null}
          onLookupIngestion={() => void lookupIngestion()}
          onResendIngestion={ingestionRecordMissing && unconfirmedIngestion && financeWorkbook
            ? () => void ingestWorkbook(unconfirmedIngestion)
            : undefined}
          financeWorkbook={financeWorkbook}
          onWorkbookChange={(file) => {
            controllers.current.get('batch-preview')?.abort();
            controllers.current.get('batch-outcome')?.abort();
            setFinanceWorkbook(file);
            setIngestion({ kind: 'idle' });
            setBatchPreview({ kind: 'idle' });
            setApplyJob({ kind: 'idle' });
            setBatchOutcome({ kind: 'idle' });
          }}
          applyReason={displayedApplyReason}
          onApplyReasonChange={setApplyReason}
          importBusy={importBusy}
          ingestion={ingestion}
          batchPreview={batchPreview}
          applyJob={applyJob}
          batchOutcome={batchOutcome}
          onIngest={() => void ingestWorkbook()}
          onApply={(preview) => void applyImportedBatch(preview)}
          onObserveApplyOutcome={(jobId, expected) => void observeApplyOutcome(jobId, expected)}
          onReconcile={openBankReview}
          confirmedImportReceipt={confirmedImportReceipt}
          submittedFinanceCommand={submittedFinanceCommand}
        />
      )}

      {activeTab === 'government-list' && (
        <FinanceGovernmentSubsidyList revision={reload} onCase={openCase} />
      )}

      {activeTab === 'monthly' && (
        <FinanceMonthlyAccounting
          revision={reload}
          initialRange={monthlyRange}
          onRangeChange={setMonthlyRange}
          onCase={openCase}
          onPayableReview={item => {
            openCase(item.case_no);
            setPayableReview(item);
          }}
        />
      )}

      {caseDrawer && (
        <Drawer
          isOpen
          title={caseDrawer + (caseClientName ? ' · ' + caseClientName : '')}
          ariaLabel={'案件帳務 · ' + caseDrawer}
          closeLabel="關閉案件"
          size="xl"
          className="finance-accounting-drawer"
          onClose={closeCase}
          closeDisabled={bankReviewBusy}
          footer={
            <button
              type="button"
              className="finance-btn-secondary"
              disabled={bankReviewBusy}
              onClick={() => requestLeave(closeCase)}
            >
              關閉案件
            </button>
          }
        >
          {payableReview && <HistoricalPayableEditor
            key={`${payableReview.case_no}:${payableReview.staff_id}:${payableReview.obligation_identity}`}
            item={payableReview} onSaved={() => setReload(value => value + 1)}
          />}
          {cancellationPosted ? <section aria-label="取消結算核銷結果">
            <p role="status">已記錄本次核銷，請查看本案帳務確認最新餘額。</p>
            <button type="button" onClick={() => setCancellationPosted(false)}>查看本案帳務</button>
          </section> : <FinanceCaseAccounting
            key={bankReview?.row_identity ?? (payableReview ? `${caseDrawer}:${reload}` : caseDrawer)}
            embedded
            initialCase={caseDrawer}
            initialNoticeStage={caseNotice}
            onPayableReview={payableReview ? undefined : setPayableReview}
            reviewObligation={payableReview && (payableReview.balance_ntd ?? 0) > 0 ? payableReview.obligation_identity ?? undefined : undefined}
            bankReconciliation={bankReview ? { row: bankReview, onPosted: bankReviewPosted, onBusyChange: setBankReviewBusy } : undefined}
            onIdentity={(caseNo, name) => {
              if (caseNo === caseDrawer) setCaseClientName(name);
            }}
            onChanged={() => setReload((value) => value + 1)}
          />}
        </Drawer>
      )}
      {bankReview?.classification_type === 'government_subsidy' && (
        <Drawer isOpen title="政府整期核對" closeLabel="關閉整期核對" size="wide"
          onClose={closeCase} closeDisabled={bankReviewBusy}>
          <p>台新 · {bankReview.transaction_date ?? '日期未提供'} · {bankReview.reference} · NT$ {bankReview.amount_ntd.toLocaleString()}</p>
          {bankReview.direction !== 'unknown' && (
            <SubsidyPeriodWorkbench key={bankReview.row_identity}
              bankSource={{ id: bankReview.row_id, direction: bankReview.direction, amountNtd: bankReview.amount_ntd }}
              onOpenCase={caseNo => requestLeave(() => openCase(caseNo))}
              onPosted={bankReviewPosted} onBusyChange={setBankReviewBusy} />
          )}
        </Drawer>
      )}
    </div>
  );
};

export default FinancePage;

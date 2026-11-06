import { ManagementPageHeader } from '../components/ManagementPageHeader';
import { useUnsavedDraft, useUnsavedNavigation } from '../components/UnsavedChanges';
import { useStaffIdentityDirectory, useStaffIdentityLabels } from '../components/StaffIdentityProvider';
/**
 * File: FinancePage.tsx
 * Description: 呈現 Finance 四大主工作區（案件帳務、銀行對帳、政府補助清單、每月帳務），收斂舊作業工具並維護受控銀行交易明細。
 */
import React, { useEffect, useRef, useState } from 'react';
import { Drawer } from '../components/Drawer';
import './FinancePage.css';
import { loadAllStaffDirectoryPages, staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { adaptStaffDirectoryPage, compareStaffUnionNumbers, staffDisplayLabel } from '../adapters/staff/staff_directory_adapter';
import { FinanceWorkbookSnapshot, financeImportMutationClient, type FinanceImportBatchOutcome, type FinanceImportBatchPreview, type FinanceImportJobAccepted, type FinanceWorkbookIngestionReceipt } from '../api/finance_import/finance_import_mutation_client';
import { financeImportQueryClient } from '../api/finance_import/finance_import_query_client';
import type { FinanceImportBatchSummary } from '../api/finance_import/finance_import_query_schemas';

import { FinanceCaseList } from '../components/FinanceCaseList';
import { FinanceGovernmentSubsidyList } from '../components/FinanceGovernmentSubsidyList';
import { FinanceMonthlyAccounting } from '../components/FinanceMonthlyAccounting';
import type { AccountingRange } from '../api/finance_import/monthly_accounting_client';
import { FinanceCaseAccounting } from '../components/FinanceCaseAccounting';
import { FinanceBankReconciliationWorkspace } from '../components/FinanceBankReconciliationWorkspace';

export type FinanceTab = 'case-accounting' | 'finance-import' | 'government-list' | 'monthly';
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
  const sharedStaffDirectory = useStaffIdentityDirectory();
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
  const [caseClientName, setCaseClientName] = useState('');
  const [caseNotice, setCaseNotice] = useState<'deposit' | 'first' | 'second' | undefined>();
  const [monthlyRange, setMonthlyRange] = useState<AccountingRange>(() => ({
    start_month: currentMonth(),
    end_month: currentMonth(),
    category: 'all',
  }));

  const openCase = (caseNo: string, noticeStage?: 'deposit' | 'first' | 'second') => {
    setCaseClientName('');
    setCaseNotice(noticeStage);
    setCaseDrawer(caseNo);
  };

  const [staff, setStaff] = useState<{ id: number; label: string }[]>([]);
  const [financeWorkbook, setFinanceWorkbook] = useState<File | null>(null);
  const [batches, setBatches] = useState<FinanceImportBatchSummary[]>([]);
  const [selectedBatchIdentity, setSelectedBatchIdentity] = useState<string>('');
  const [ingestion, setIngestion] = useState<LoadState<FinanceWorkbookIngestionReceipt>>({ kind: 'idle' });
  const [batchPreview, setBatchPreview] = useState<LoadState<FinanceImportBatchPreview>>({ kind: 'idle' });
  const [sourceReview, setSourceReview] = useState<LoadState<FinanceImportReviewSnapshot>>({ kind: 'idle' });
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

  useEffect(() => {
    if (activeTab !== 'finance-import') return;
    if (sharedStaffDirectory !== null) {
      if (staffReload.current !== reload) {
        staffReload.current = reload;
        sharedStaffDirectory.refresh();
        return;
      }
      if (sharedStaffDirectory.status === 'ready') {
        const people = [...sharedStaffDirectory.people.values()].sort(compareStaffUnionNumbers)
          .map(person => ({ id: person.id, label: staffDisplayLabel(person.unionNo, person.name ?? `服務人員摘要 #${person.id}`) }));
        setStaff(people);
      }
      return;
    }
    const request = start('staff');
    loadAllStaffDirectoryPages(
      staffDirectoryClient.queryPage.bind(staffDirectoryClient),
      { pageSize: 200 },
      { signal: request.controller.signal },
    )
    .then((page) => {
      if (!current('staff', request.sequence, request.controller)) return;
      const adapted = adaptStaffDirectoryPage(page).items.sort(compareStaffUnionNumbers).map((item) => ({ id: item.id, label: staffDisplayLabel(item.unionNo, item.displayName) }));
      setStaff(adapted);
    })
    .catch(() => {});
  }, [activeTab, reload, sharedStaffDirectory]);

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

  useUnsavedDraft(
    '銀行交易匯入',
    { '待匯入檔案': financeWorkbook?.name ?? '', '原因': applyReason },
    {
      baseline: { '待匯入檔案': '', '原因': '' },
      enabled: batchOutcome.kind !== 'ready' && !(ingestion.kind === 'ready' && batchPreview.kind === 'ready' && (!batchPreview.data.apply_allowed || batchPreview.data.counts.ready_dispatch <= 0)),
      busy: importBusy || applyJob.kind === 'loading' || batchOutcome.kind === 'loading' || (submittedFinanceCommand !== undefined && batchOutcome.kind !== 'ready'),
      save: ingestWorkbook,
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
          staff={staff}
          batches={batches}
          selectedBatchIdentity={selectedBatchIdentity}
          onSelectBatch={handleSelectBatch}
          sourceReview={sourceReview}
          onReloadSourceReview={loadSourceReview}
          financeWorkbook={financeWorkbook}
          onWorkbookChange={(file) => {
            controllers.current.get('batch-preview')?.abort();
            controllers.current.get('source-review')?.abort();
            controllers.current.get('batch-outcome')?.abort();
            setFinanceWorkbook(file);
            setIngestion({ kind: 'idle' });
            setBatchPreview({ kind: 'idle' });
            setManuallyPostedRows(new Set());
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
          onPostedManual={(rowIdentity) => {
            setManuallyPostedRows((rows) => new Set([...rows, rowIdentity]));
            setReload((value) => value + 1);
            if (sourceReview.kind === 'ready') void loadSourceReview(sourceReview.data.batchIdentity);
          }}
          postingStopped={postingStopped}
          manuallyPostedRows={manuallyPostedRows}
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
          onClose={() => setCaseDrawer('')}
          footer={
            <button
              type="button"
              className="finance-btn-secondary"
              onClick={() => requestLeave(() => setCaseDrawer(''))}
            >
              關閉案件
            </button>
          }
        >
          <FinanceCaseAccounting
            key={caseDrawer}
            embedded
            initialCase={caseDrawer}
            initialNoticeStage={caseNotice}
            onIdentity={(caseNo, name) => {
              if (caseNo === caseDrawer) setCaseClientName(name);
            }}
            onChanged={() => setReload((value) => value + 1)}
          />
        </Drawer>
      )}
    </div>
  );
};

export default FinancePage;

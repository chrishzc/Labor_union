/**
 * File: FinanceBankReconciliationWorkspace.tsx
 * Description: 銀行對帳工作台（WF-03/04），整合雙銀行匯入、待核對與已核銷總表、待核對統計與共用核對入口。
 */

import { useEffect, useRef, useState } from 'react';
import './FinanceBankReconciliationWorkspace.css';
import { Drawer } from './Drawer';
import { FinanceStatementArchive } from './FinanceStatementArchive';
import { financeMoney } from './FinanceReceiptsWorkspace';
import { bankReconciliationUnavailableReason, financeBankReviewPresentation, financeImportBlockerMessage, financeImportReviewReason } from '../adapters/finance/finance_import_query_adapter';
import type { FinanceBankTransaction, FinanceBankTransactionPage, FinanceImportHistoryPage, FinanceExcludedBankTransactionPage } from '../api/finance_import/finance_import_query_schemas';
import { financeImportMutationClient, type FinanceImportBatchOutcome, type FinanceImportBatchPreview, type FinanceImportJobAccepted, type FinanceWorkbookIngestionReceipt } from '../api/finance_import/finance_import_mutation_client';
import { financeImportQueryClient } from '../api/finance_import/finance_import_query_client';
import { formatTaipeiDateTime } from '../shared/taipeiTime';

type LoadState<T> = { kind: 'idle' | 'loading' } | { kind: 'ready'; data: T } | { kind: 'empty' } | { kind: 'error'; message: string } | { kind: 'unavailable'; message: string };
const purposeLabels: Record<string, string> = {
  client_receipt: '客戶入款', client_refund: '客戶退款', client_subsidy_return: '退客戶先墊補助', client_refund_return: '客戶退匯',
  staff_payout: '付月嫂', staff_salary: '付月嫂', staff_legacy_subsidy: '補助轉交月嫂',
  government_subsidy: '政府補助',
};

function bankPurposeLabel(row: FinanceBankTransaction): string {
  return row.bank === 'taishin' && ['staff_payout', 'staff_salary'].includes(row.classification_type)
    ? '補助轉交月嫂'
    : purposeLabels[row.classification_type] ?? '款項用途待確認';
}

const directionLabel = (direction: FinanceBankTransaction['direction']) =>
  direction === 'incoming' ? '入款' : direction === 'outgoing' ? '出款' : '方向待確認';

const bankNameMap: Record<string, string> = {
  sinopac: '永豐銀行',
  taishin: '台新銀行',
};

const bankShortNameMap: Record<string, string> = {
  sinopac: '永豐',
  taishin: '台新',
};

export function BankTransactionFacts({ row }: { row: FinanceBankTransaction }) {
  const memo = row.bank_memo ?? row.pairing_memo;
  return <section className="bank-fact-card" aria-label="銀行原始交易事實">
    <span className="eyebrow">銀行原始交易事實</span>
    <h3>{bankNameMap[row.bank]} · {directionLabel(row.direction)} {financeMoney(row.amount_ntd)}</h3>
    <p>{row.transaction_date ?? '日期待確認'} · 識別：{row.reference}</p>
    {row.counterparty_name && <p>交易對象 {row.counterparty_name}</p>}
    {memo && <p>{memo}</p>}
    <div className="bank-fact-grid">
      <div><span>款項用途</span><strong>{bankPurposeLabel(row)}</strong></div>
      <div><span>處理狀態</span>{row.status === 'posted'
        ? <span className="bank-chip-green">已核銷 · 唯讀查閱</span>
        : <span className="bank-chip-amber">{row.disposition === 'blocked' ? '銷帳受阻' : '待核對'}</span>}
      </div>
    </div>
  </section>;
}

export function BankTransactionReviewActions({ row, offerPairing, disabled, onBusyChange, onPaired, onExcluded }: {
  row: FinanceBankTransaction;
  offerPairing: boolean;
  disabled: boolean;
  onBusyChange: (busy: boolean) => void;
  onPaired: () => void;
  onExcluded: () => void;
}) {
  type Candidate = NonNullable<FinanceBankTransaction['pairing_candidates']>[number];
  const [reviewPurpose, setReviewPurpose] = useState(false);
  const [selected, setSelected] = useState<Candidate | null>(null);
  const [reason, setReason] = useState<string | null>(null);
  const [error, setError] = useState('');
  const active = useRef(false);
  const isSubsidyReturn = row.classification_type === 'client_subsidy_return';
  const target = row.reconciliation_target;
  if (isSubsidyReturn && (
    row.status !== 'pending' || row.disposition === 'blocked' || !target
    || target.staff_id !== null || target.obligation_identities.length === 0
  )) return null;

  const purposeReview = !isSubsidyReturn && row.disposition !== 'blocked' ? row.purpose_review : null;
  const candidates = reviewPurpose ? purposeReview?.candidates ?? [] : offerPairing && !isSubsidyReturn
    ? row.pairing_candidates ?? []
    : [];
  const run = async (action: () => Promise<number>, onDone: () => void, failure: string) => {
    if (disabled || active.current) return;
    active.current = true;
    onBusyChange(true);
    setError('');
    try {
      await action();
      setSelected(null);
      setReviewPurpose(false);
      onDone();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : failure);
    } finally {
      active.current = false;
      onBusyChange(false);
    }
  };

  return <>
    {!!purposeReview?.candidates.length && <button type="button" className="finance-btn-secondary" disabled={disabled}
      onClick={() => { setReviewPurpose(value => !value); setSelected(null); setError(''); }}>
      {reviewPurpose ? '返回核對交易' : '更正出款用途'}
    </button>}
    {!!candidates.length && <fieldset className="bank-fact-card" disabled={disabled}>
      <legend>{reviewPurpose ? '出款用途' : '候選案件'}</legend>
      {candidates.map(candidate => <p key={`${candidate.case_no}:${candidate.purpose}:${candidate.person_id}`}>
        <label>
          <input type="radio" name="bank-case-candidate" checked={selected === candidate} onChange={() => setSelected(candidate)} />
          {candidate.case_no} · {purposeLabels[candidate.purpose]}
          {candidate.purpose === 'staff_salary' && ` · ${candidate.person_name ?? `月嫂編號 ${candidate.person_id}`}`}
          {!reviewPurpose && <> · 預估補助入帳 {candidate.estimated_subsidy_payment_date ?? '—'}
            {candidate.purpose === 'staff_salary' && <> · 預估薪資入帳 {candidate.estimated_self_funded_staff_due_date ?? '—'}</>}
          </>}
        </label>
      </p>)}
      <button type="button" className="finance-btn-primary" disabled={!selected || disabled} onClick={() => {
        if (!selected) return;
        void run(() => reviewPurpose && purposeReview
          ? financeImportQueryClient.pairBankTransaction(row.row_id, selected, purposeReview.classification_version)
          : financeImportQueryClient.pairBankTransaction(row.row_id, selected), onPaired, '配對未確認，請重新查詢。');
      }}>{reviewPurpose ? '確認用途' : '確認配對'}</button>
    </fieldset>}
    {reason === null ? <button type="button" className="finance-btn-secondary" disabled={disabled}
      onClick={() => { setError(''); setReason(''); }}>移除誤匯入明細</button> : (
      <section className="bank-fact-card" aria-label="移除誤匯入明細">
        <label>移除原因<textarea maxLength={500} value={reason} disabled={disabled} onChange={event => setReason(event.target.value)} /></label>
        <button type="button" className="finance-btn-primary" disabled={disabled || !reason.trim()} onClick={() => void run(
          () => financeImportQueryClient.excludeBankTransaction(row.row_id, reason.trim()), onExcluded, '移除未確認，請重新查詢。',
        )}>確認移除</button>
        <button type="button" className="finance-btn-secondary" disabled={disabled} onClick={() => { setReason(null); setError(''); }}>取消移除</button>
      </section>
    )}
    {error && <p role="alert">{error}</p>}
  </>;
}

export function StaffSubsidyBankReview({ row, preview, job, outcome, submitted, busy, onPreview, onApply, onObserve }: {
  row: FinanceBankTransaction;
  preview: LoadState<FinanceImportBatchPreview>;
  job: LoadState<FinanceImportJobAccepted>;
  outcome: LoadState<FinanceImportBatchOutcome>;
  submitted: boolean;
  busy: boolean;
  onPreview: (selections?: Record<string, string>) => void;
  onApply: (preview: FinanceImportBatchPreview) => void;
  onObserve: (jobId: string, expected: { batchIdentity: string; previewFingerprint: string }) => void;
}) {
  if (preview.kind === 'idle' || preview.kind === 'loading') return <p role="status">正在查詢本筆月嫂補助預檢…</p>;
  if (preview.kind !== 'ready') return <div role="alert">
    <p>{preview.kind === 'error' ? preview.message : '查無本筆月嫂補助預檢。'}</p>
    <button type="button" className="finance-btn-secondary" disabled={busy} onClick={() => onPreview()}>重新查詢本筆預檢</button>
  </div>;

  const checked = preview.data;
  const item = checked.rows.find(candidate => candidate.row_identity === row.row_identity);
  if (!item) return <p role="alert">本次預檢未回傳原交易，請重新查詢原流水。</p>;
  const plan = item.subsidy_preflight;
  const canApply = checked.apply_allowed && checked.counts.ready_dispatch > 0 && item.disposition === 'create';
  const pending = job.kind === 'loading' || outcome.kind === 'loading' || (submitted && outcome.kind !== 'ready');
  return <section className="bank-fact-card" aria-label="補助處理預檢">
    <h4>本次補助處理預檢</h4>
    {(item.staff_subsidy_cases?.length ?? 0) > 1 && <fieldset disabled={busy || pending}>
      <legend>選擇同月補助案件</legend>
      {item.staff_subsidy_cases?.map(candidate => <button key={candidate.case_no} type="button"
        aria-pressed={item.selected_staff_subsidy_case === candidate.case_no}
        onClick={() => onPreview({ [row.row_identity]: candidate.case_no })}>
        {candidate.case_no} · {candidate.payable_due_date} · {financeMoney(candidate.payable_amount_ntd)}
      </button>)}
    </fieldset>}
    {plan && <>
      <p><strong>{plan.case_no} · 補助轉交月嫂</strong></p>
      <p>本案補助 {financeMoney(plan.subsidy_ntd)} · 銀行原實付 {financeMoney(plan.bank_cash_ntd)}</p>
      {plan.confirmation_only ? <p>服務尚未結束，本次只確認補助方案。</p> : <p>
        本次款項 {financeMoney(plan.payable_amount_ntd)} · 預計付款日 {plan.payable_due_date ?? '待確認'} · 手續費 {financeMoney(plan.transfer_fee_ntd)} · 預計核銷 {financeMoney(plan.settlement_ntd)} · 剩餘 {financeMoney(plan.remaining_ntd)}
      </p>}
      {plan.blocker && !plan.confirmation_only && <p role="alert">{/[\u3400-\u9fff]/.test(plan.blocker) ? plan.blocker
        : financeImportReviewReason({ ...row, recorded_pending_reason: null, dispatch_reason: null, review_reason: plan.blocker })}</p>}
    </>}
    {item.pending_reason && !plan?.blocker && <p>{financeImportReviewReason(row, item)}</p>}
    {!checked.apply_allowed && !!checked.blocking_codes.length && <p role="alert">{financeImportBlockerMessage(checked.blocking_codes)}</p>}
    {canApply && job.kind === 'idle' && outcome.kind === 'idle' && !submitted && <button type="button"
      className="finance-btn-primary" disabled={busy} onClick={() => onApply(checked)}>
      {plan?.confirmation_only ? '確認本案補助方案' : '確認核銷本筆交易'}
    </button>}
    {job.kind === 'error' && submitted && <button type="button" className="finance-btn-secondary" disabled={busy}
      onClick={() => onApply(checked)}>以原操作確認核銷結果</button>}
    {job.kind === 'ready' && outcome.kind === 'error' && <button type="button" className="finance-btn-secondary" disabled={busy}
      onClick={() => onObserve(job.data.job_id, { batchIdentity: checked.batch_identity, previewFingerprint: checked.preview_fingerprint })}>
      重新查詢核銷結果
    </button>}
    {job.kind === 'error' && <p role="alert">{job.message}</p>}
    {outcome.kind === 'error' && <p role="alert">{outcome.message}</p>}
    {outcome.kind === 'ready' && (outcome.data.status === 'succeeded' ? <p role="status">{outcome.data.receipt?.reconciled_count
      ? '本筆交易已核銷。' : '本次處理已完成，請查看案件帳務。'}</p> : <p role="alert">未完成核銷，請重新查詢原流水。</p>)}
    {(job.kind === 'loading' || outcome.kind === 'loading') && <p role="status">正在確認本筆核銷結果…</p>}
  </section>;
}

const historyStatus = {
  saved: '已保存', posting: '核銷處理中', posted: '核銷結果已確認', blocked: '自動核銷受阻',
  posting_failed: '流水已保存，核銷未完成', failed: '匯入失敗，流水未保存', legacy: '舊批次，結果未記錄',
};
const duplicateSkipReason = '交易指紋已存在，重複列已略過';

function FinanceImportHistory({ revision, onClose }: { revision: number; onClose: () => void }) {
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const [retry, setRetry] = useState(0);
  const [state, setState] = useState<LoadState<FinanceImportHistoryPage>>({ kind: 'loading' });
  const cursor = cursors.at(-1);
  useEffect(() => {
    const controller = new AbortController();
    setState({ kind: 'loading' });
    void financeImportQueryClient.listImportHistory(cursor, { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setState({ kind: 'ready', data });
    }).catch(() => {
      if (!controller.signal.aborted) setState({ kind: 'error', message: '暫時無法查詢匯入紀錄。' });
    });
    return () => controller.abort();
  }, [cursor, revision, retry]);
  const page = state.kind === 'ready' ? state.data : undefined;
  return (
    <Drawer isOpen onClose={onClose} closeLabel="關閉" ariaLabel="匯入紀錄" title="匯入紀錄" size="xl">
      <p>每次上傳各列一筆。待核對欄顯示當次記錄的筆數。</p>
      {state.kind === 'loading' && <p role="status">正在查詢匯入紀錄…</p>}
      {state.kind === 'error' && <div role="alert">{state.message} <button type="button" onClick={() => setRetry(value => value + 1)}>重新查詢匯入紀錄</button></div>}
      {page?.items.length === 0 && <p>目前沒有匯入紀錄。</p>}
      {!!page?.items.length && (
        <div className="finance-table-container">
          <table className="finance-table">
            <thead><tr><th>上傳時間</th><th>銀行／檔案</th><th>結果</th><th className="finance-num">新增流水</th><th className="finance-num">重複來源列</th><th className="finance-num">本次核銷</th><th className="finance-num">當時待核對</th></tr></thead>
            <tbody>{page.items.map(entry => (
              <tr key={entry.identity}>
                <td>{new Date(entry.started_at).toLocaleString('zh-TW', { timeZone: 'Asia/Taipei' })}</td>
                <td>{entry.bank ? bankShortNameMap[entry.bank] : '銀行無紀錄'}<br />{entry.source_file ?? '檔名無紀錄'}</td>
                <td>{historyStatus[entry.status]}{entry.source_warning_count ? <small> · 來源格式異常 {entry.source_warning_count} 筆</small> : null}</td>
                <td className="finance-num">{entry.new_count ?? '—'}</td>
                <td className="finance-num">
                  {entry.duplicate_count ?? '—'}
                  {!!entry.duplicate_count && <small className="bank-reconcile-sub">{duplicateSkipReason}</small>}
                </td>
                <td className="finance-num">{entry.reconciled_count ?? (entry.status === 'posting' ? '待確認' : '—')}</td>
                <td className="finance-num">{entry.pending_count ?? (entry.status === 'posting' ? '待確認' : '無紀錄')}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      {cursors.length > 1 && <button type="button" disabled={!page} onClick={() => setCursors(values => values.slice(0, -1))}>上一頁</button>}
      {page?.next_before != null && (
        <button type="button" onClick={() => setCursors(values => [...values, page.next_before!])}>下一頁</button>
      )}
    </Drawer>
  );
}

function FinanceExcludedTransactionsDrawer({ revision, onClose }: { revision: number; onClose: () => void }) {
  const [cursors, setCursors] = useState<(number | undefined)[]>([undefined]);
  const [retry, setRetry] = useState(0);
  const [state, setState] = useState<LoadState<FinanceExcludedBankTransactionPage>>({ kind: 'loading' });
  const beforeRowId = cursors.at(-1);

  useEffect(() => {
    const controller = new AbortController();
    setState({ kind: 'loading' });
    void financeImportQueryClient.listExcludedBankTransactions(
      { limit: 50, before_row_id: beforeRowId },
      { signal: controller.signal },
    ).then(data => {
      if (!controller.signal.aborted) setState({ kind: 'ready', data });
    }).catch(() => {
      if (!controller.signal.aborted) setState({ kind: 'error', message: '暫時無法查詢已移除流水紀錄。' });
    });
    return () => controller.abort();
  }, [beforeRowId, revision, retry]);

  const page = state.kind === 'ready' ? state.data : undefined;
  return (
    <Drawer isOpen onClose={onClose} closeLabel="關閉" ariaLabel="已移除流水紀錄" title="已移除流水紀錄" size="xl">
      <p>顯示已被系統管理員判定為誤匯入並排除之銀行流水與稽核紀錄。</p>
      {state.kind === 'loading' && <p role="status">正在查詢已移除流水紀錄…</p>}
      {state.kind === 'error' && (
        <div role="alert">
          {state.message} <button type="button" onClick={() => setRetry(value => value + 1)}>重新查詢已移除流水紀錄</button>
        </div>
      )}
      {page?.items.length === 0 && <p>目前沒有已移除的流水紀錄。</p>}
      {!!page?.items.length && (
        <div className="finance-table-container">
          <table className="finance-table">
            <thead>
              <tr>
                <th>移除時間</th>
                <th>移除人員</th>
                <th>移除原因</th>
                <th>交易日</th>
                <th>銀行</th>
                <th>方向</th>
                <th className="finance-num">金額</th>
                <th>摘要／備註</th>
                <th>原始來源</th>
              </tr>
            </thead>
            <tbody>
              {page.items.map(entry => (
                <tr key={entry.row_identity}>
                  <td>{entry.excluded_at ? new Date(entry.excluded_at).toLocaleString('zh-TW', { timeZone: 'Asia/Taipei' }) : '—'}</td>
                  <td>{entry.excluded_by || '系統'}</td>
                  <td style={{ maxWidth: '200px', wordBreak: 'break-word' }}>{entry.exclusion_reason}</td>
                  <td>{entry.transaction_date ?? '—'}</td>
                  <td>{bankShortNameMap[entry.bank]}</td>
                  <td>{entry.direction === 'incoming' ? '存入' : entry.direction === 'outgoing' ? '支出' : '未知'}</td>
                  <td className="finance-num">NT$ {entry.amount_ntd.toLocaleString()}</td>
                  <td>
                    {entry.counterparty_name && <div>對象：{entry.counterparty_name}</div>}
                    {entry.summary && <div>摘要：{entry.summary}</div>}
                    {entry.memo && <div>備註：{entry.memo}</div>}
                    {entry.raw_reference && <small className="bank-reconcile-sub">參考：{entry.raw_reference}</small>}
                  </td>
                  <td>
                    {entry.source_file ?? '檔名無紀錄'}
                    {entry.sheet_name ? <small className="bank-reconcile-sub">{entry.sheet_name}#{entry.source_row ?? '—'}</small> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {cursors.length > 1 && (
        <button type="button" disabled={!page} onClick={() => setCursors(values => values.slice(0, -1))}>上一頁</button>
      )}
      {page?.next_before_row_id != null && (
        <button type="button" onClick={() => setCursors(values => [...values, page.next_before_row_id!])}>下一頁</button>
      )}
    </Drawer>
  );
}

export interface FinanceBankReconciliationWorkspaceProps {
  onCase: (caseNo: string) => void;
  onCaseFromDetail?: (caseNo: string) => void;
  revision: number;
  ingestionNeedsLookup?: boolean;
  onLookupIngestion: () => void;
  onResendIngestion?: () => void;
  financeWorkbook: File | null;
  onWorkbookChange: (file: File | null) => void;
  applyReason?: string;
  onApplyReasonChange?: (reason: string) => void;
  importBusy: boolean;
  ingestion: LoadState<FinanceWorkbookIngestionReceipt>;
  batchPreview: LoadState<FinanceImportBatchPreview>;
  applyJob: LoadState<FinanceImportJobAccepted>;
  batchOutcome: LoadState<FinanceImportBatchOutcome>;
  onIngest: () => void;
  onApply: (preview: FinanceImportBatchPreview) => void;
  onObserveApplyOutcome: (jobId: string, expected?: { batchIdentity: string; previewFingerprint: string }) => void;
  onReconcile: (row: FinanceBankTransaction) => void;
  otherDrawerOpen?: boolean;
  reviewRowIdentity?: string | null;
  confirmedImportReceipt: { reconciled_count: number; existing_count: number } | null;
  submittedFinanceCommand?: unknown;
}

export function FinanceBankReconciliationWorkspace({
  onCase,
  onCaseFromDetail = onCase,
  revision,
  ingestionNeedsLookup = false,
  onLookupIngestion,
  onResendIngestion,
  financeWorkbook,
  onWorkbookChange,
  applyReason: _applyReason,
  onApplyReasonChange: _onApplyReasonChange,
  importBusy,
  ingestion,
  batchPreview,
  applyJob,
  batchOutcome,
  onIngest,
  onApply,
  onObserveApplyOutcome,
  onReconcile,
  otherDrawerOpen = false,
  reviewRowIdentity,
  confirmedImportReceipt,
  submittedFinanceCommand,
}: FinanceBankReconciliationWorkspaceProps) {
  const [dates, setDates] = useState({ start: '', end: '' });
  const [filterBank, setFilterBank] = useState<'all' | 'sinopac' | 'taishin'>('all');
  const [filterDir, setFilterDir] = useState<'all' | 'in' | 'out'>('all');
  const [filterStatus, setFilterStatus] = useState<'pending' | 'posted' | 'all'>('pending');
  const [filterSearch, setFilterSearch] = useState('');
  const [cursors, setCursors] = useState<(number | undefined)[]>([undefined]);
  const [retry, setRetry] = useState(0);
  const [rematch, setRematch] = useState<LoadState<string>>({ kind: 'idle' });

  async function reconcilePending() {
    setRematch({ kind: 'loading' });
    try {
      const result = await financeImportMutationClient.reconcilePending();
      setRematch({ kind: 'ready', data: `已查核 ${result.checked_count} 筆，核銷 ${result.reconciled_count} 筆，仍待核對 ${result.pending_count} 筆。` });
    } catch {
      setRematch({ kind: 'error', message: '無法確認批次核銷結果，請查核明細後再試。' });
    } finally {
      setCursors([undefined]);
      setRetry(value => value + 1);
    }
  }
  const [transactions, setTransactions] = useState<LoadState<FinanceBankTransactionPage>>({ kind: 'loading' });
  const [historyOpen, setHistoryOpen] = useState(false);
  const [excludedOpen, setExcludedOpen] = useState(false);
  const [showImportPanel, setShowImportPanel] = useState(false);
  const [targetBankFormat, setTargetBankFormat] = useState<string>('');
  const [viewedRow, setViewedRow] = useState<FinanceBankTransaction | null>(null);
  const [detailFetch, setDetailFetch] = useState<LoadState<null>>({ kind: 'idle' });
  const [detailRetry, setDetailRetry] = useState(0);
  const beforeRowId = cursors.at(-1);
  const viewedRowId = viewedRow?.row_id;

  useEffect(() => {
    if (!viewedRowId || otherDrawerOpen) return;
    const controller = new AbortController();
    setDetailFetch({ kind: 'loading' });
    void financeImportQueryClient.listBankTransactions({ transaction_status: 'all', row_id: viewedRowId },
      { signal: controller.signal }).then(data => {
      if (controller.signal.aborted) return;
      const fresh = data.items.find(row => row.row_id === viewedRowId);
      if (!fresh) {
        setDetailFetch({ kind: 'error', message: '查無原銀行流水的最新明細。' });
        return;
      }
      setViewedRow(fresh);
      setDetailFetch({ kind: 'ready', data: null });
    }).catch(() => {
      if (!controller.signal.aborted) setDetailFetch({ kind: 'error', message: '銀行交易明細暫時無法取得。' });
    });
    return () => controller.abort();
  }, [viewedRowId, otherDrawerOpen, revision, detailRetry]);

  useEffect(() => {
    if (dates.start && dates.end && dates.start > dates.end) {
      setTransactions({ kind: 'error', message: '交易起日不可晚於迄日。' });
      return;
    }
    const controller = new AbortController();
    setTransactions({ kind: 'loading' });
    void financeImportQueryClient.listBankTransactions({
      bank: filterBank === 'all' ? undefined : filterBank,
      direction: filterDir === 'all' ? undefined : filterDir === 'in' ? 'incoming' : 'outgoing',
      transaction_status: filterStatus,
      start_date: dates.start || undefined,
      end_date: dates.end || undefined,
      search: filterSearch.trim() || undefined,
      before_row_id: beforeRowId,
    }, { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setTransactions({ kind: 'ready', data });
    }).catch(() => {
      if (!controller.signal.aborted) setTransactions({ kind: 'error', message: '銀行交易暫時無法取得，請重新查詢。' });
    });
    return () => controller.abort();
  }, [dates.start, dates.end, filterBank, filterDir, filterStatus, filterSearch, beforeRowId, revision, retry]);

  const page = transactions.kind === 'ready' ? transactions.data : undefined;
  const pendingRows = page?.items.filter(row => row.status === 'pending') ?? [];
  const postedRows = page?.items.filter(row => row.status === 'posted') ?? [];
  const previewRows = new Map(batchPreview.kind === 'ready' ? batchPreview.data.rows.map(row => [row.row_identity, row]) : []);
  const postingStopped = batchPreview.kind === 'ready' && !batchPreview.data.apply_allowed
    ? 'preview_blocked'
    : batchOutcome.kind === 'ready' && (batchOutcome.data.status === 'failed' || batchOutcome.data.status === 'cancelled')
      ? 'apply_failed'
      : undefined;
  const viewedTransaction = otherDrawerOpen ? null : viewedRow;
  const detailTitle = viewedTransaction?.status === 'posted' ? '已核銷交易明細' : '待核對交易明細';
  const reviewBusy = importBusy || batchPreview.kind === 'loading' || applyJob.kind === 'loading'
    || batchOutcome.kind === 'loading' || (submittedFinanceCommand !== undefined && batchOutcome.kind !== 'ready');

  const fileInputRef = useRef<HTMLInputElement>(null);

  const triggerUpload = (bankId: 'sinopac' | 'taishin') => {
    setTargetBankFormat(bankId === 'sinopac' ? '永豐銀行' : '台新銀行');
    setShowImportPanel(true);
    fileInputRef.current?.click();
  };

  return (
    <div className="bank-reconcile-workspace" data-surface-id="finance.bank-reconciliation.workspace">
      {/* 1. 業務導引橫幅 Banner */}
      <section className="bank-reconcile-banner" aria-label="銀行對帳指引">
        <div className="bank-reconcile-banner-content">
          <span className="bank-reconcile-eyebrow">兩家銀行，一處核對</span>
          <h2>先辨識來源，再確認款項交給誰。</h2>
          <p>台新出款可能轉交月嫂，也可能退客戶。銀行名稱不能代替對象確認。</p>
        </div>
        <div className="bank-reconcile-actions">
          <button
            type="button"
            className="finance-btn-primary"
            disabled={ingestionNeedsLookup || importBusy}
            onClick={() => triggerUpload('sinopac')}
            aria-label="匯入永豐對帳單"
          >
            匯入永豐對帳單
          </button>
          <button
            type="button"
            className="finance-btn-primary"
            disabled={ingestionNeedsLookup || importBusy}
            onClick={() => triggerUpload('taishin')}
            aria-label="匯入台新對帳單"
          >
            匯入台新對帳單
          </button>
          <button type="button" className="finance-btn-secondary" onClick={() => setHistoryOpen(true)}>匯入紀錄</button>
          <button type="button" className="finance-btn-secondary" onClick={() => setExcludedOpen(true)}>已移除流水紀錄</button>
          <FinanceStatementArchive compact={true} />
          <button type="button" className="finance-btn-primary"
            disabled={importBusy || rematch.kind === 'loading'}
            onClick={() => void reconcilePending()}>
            {rematch.kind === 'loading' ? '重新配對中…' : '重新配對並核銷'}
          </button>
          {rematch.kind === 'ready' && <span role="status">{rematch.data}</span>}
          {rematch.kind === 'error' && <span role="alert">{rematch.message}</span>}
        </div>
      </section>

      {/* 2. 受控檔案上傳列 (點擊匯入或常駐支援) */}
      <div

        className="bank-reconcile-import-panel"
        style={{ display: showImportPanel || financeWorkbook || ingestionNeedsLookup ? 'flex' : 'none' }}
        data-surface-id="finance.finance-import.upload-panel"
      >
        <div className="bank-reconcile-import-row">
          <div className="bank-reconcile-import-fields">
            {targetBankFormat && (
              <span className="finance-status-pill" style={{ background: '#fff0e6', color: '#c2410c', borderColor: '#fed9b8' }}>
                格式：{targetBankFormat}
              </span>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              aria-label="選擇銀行交易明細工作簿"
              className="finance-input"
              style={{ padding: '6px 10px', fontSize: '0.82rem' }}
              disabled={
                ingestionNeedsLookup || importBusy ||
                ingestion.kind === 'loading' ||
                batchPreview.kind === 'loading' ||
                applyJob.kind === 'loading' ||
                batchOutcome.kind === 'loading' ||
                (submittedFinanceCommand !== undefined && batchOutcome.kind !== 'ready')
              }
              onChange={(event) => {
                onWorkbookChange(event.target.files?.[0] ?? null);
              }}
            />
            <button
              type="button"
              className="finance-btn-primary"
              data-control-id="finance.finance-import.upload"
              disabled={
                ingestionNeedsLookup || importBusy ||
                financeWorkbook === null ||
                ingestion.kind === 'loading' ||
                batchPreview.kind === 'loading' ||
                applyJob.kind === 'loading' ||
                batchOutcome.kind === 'loading' ||
                submittedFinanceCommand !== undefined
              }
              onClick={() => {
                if (fileInputRef.current) fileInputRef.current.value = '';
                onIngest();
              }}
              style={{ padding: '7px 14px' }}
            >
              {ingestion.kind === 'loading' ||
              batchPreview.kind === 'loading' ||
              applyJob.kind === 'loading' ||
              batchOutcome.kind === 'loading'
                ? '匯入中…'
                : '匯入銀行交易明細'}
            </button>
            <button
              type="button"
              className="bank-btn-ghost"
              disabled={ingestionNeedsLookup || importBusy}
              onClick={() => {
                setShowImportPanel(false);
                onWorkbookChange(null);
              }}
              style={{ fontSize: '0.8rem' }}
            >
              收起
            </button>
          </div>
        </div>

        {/* 上傳與審查即時結果 */}
        {ingestion.kind === 'error' && <p className="finance-state error" role="alert">{ingestion.message}</p>}
        {ingestionNeedsLookup && (
          <button type="button" className="finance-btn-secondary" disabled={importBusy} onClick={onLookupIngestion}>
            查詢原次匯入結果
          </button>
        )}
        {onResendIngestion && (
          <button type="button" className="finance-btn-secondary" disabled={importBusy} onClick={onResendIngestion}>
            以原操作重送同一檔案
          </button>
        )}
        {!reviewRowIdentity && <>
        {batchPreview.kind === 'error' && <p className="finance-state error" role="alert">{batchPreview.message}</p>}
        {batchOutcome.kind === 'error' && <p className="finance-state error" role="alert">{batchOutcome.message}</p>}
        {applyJob.kind === 'error' && Boolean(submittedFinanceCommand) && batchPreview.kind === 'ready' && (
          <button type="button" className="finance-btn-primary" disabled={batchOutcome.kind === 'loading'} onClick={() => onApply(batchPreview.data)}>
            以原操作確認匯入結果
          </button>
        )}
        {applyJob.kind === 'ready' && batchOutcome.kind === 'error' && (
          <button
            type="button"
            className="finance-btn-secondary"
            data-control-id="finance.finance-import.receipt"
            onClick={() =>
              onObserveApplyOutcome(
                applyJob.data.job_id,
                batchPreview.kind === 'ready'
                  ? { batchIdentity: batchPreview.data.batch_identity, previewFingerprint: batchPreview.data.preview_fingerprint }
                  : undefined
              )
            }
          >
            重新查詢匯入結果
          </button>
        )}
        {batchOutcome.kind === 'ready' && batchOutcome.data.status !== 'succeeded' && (
          <p role="alert" style={{ color: '#dc2626', fontWeight: 600, fontSize: '0.82rem', margin: '4px 0 0 0' }}>
            未完成銷帳，請查看未銷帳明細與原因。
          </p>
        )}
        {(confirmedImportReceipt ||
          (batchPreview.kind === 'ready' && !importBusy) ||
          (ingestion.kind === 'ready' && !importBusy)) && (
          <div className="finance-meta" style={{ marginTop: '10px' }}>
            <span>
              {submittedFinanceCommand !== undefined && batchOutcome.kind !== 'ready'
                ? '本次自動核銷結果待確認'
                : `本次自動核銷 ${confirmedImportReceipt?.reconciled_count ?? 0} 筆`}
              {ingestion.kind === 'ready' && <>｜新增流水 {ingestion.data.canonical_created_count} 筆｜重複來源列 {ingestion.data.duplicate_occurrence_count} 筆</>}
              {ingestion.kind === 'ready' && ingestion.data.duplicate_occurrence_count > 0 && <>（{duplicateSkipReason}）</>}
              {ingestion.kind === 'ready' && ingestion.data.source_warning_count > 0 && <>｜來源格式異常 {ingestion.data.source_warning_count} 筆</>}
            </span>
            {batchPreview.kind === 'ready' && !batchPreview.data.apply_allowed && (
              <span style={{ color: '#c5221f', fontWeight: 700 }} role="alert">
                （自動核銷受阻：{financeImportBlockerMessage(batchPreview.data.blocking_codes)}。流水已保存，請查看待核對明細）
              </span>
            )}
          </div>
        )}
        </>}
      </div>

      {page?.pending_count != null && (
        <div className="bank-reconcile-counts" aria-label="銀行對帳統計摘要">
          <span className="bank-reconcile-pill pill-pending">待核對 <strong>{page.pending_count}</strong> 筆</span>
        </div>
      )}
      <section className="bank-reconcile-panel" aria-label="銀行對帳總表">
        <div className="bank-reconcile-filters">
          <div className="bank-reconcile-filter-item">
            <label htmlFor="filter-bank">銀行</label>
            <select
              id="filter-bank"
              value={filterBank}
              onChange={(e) => { setCursors([undefined]); setFilterBank(e.target.value as typeof filterBank); }}
              aria-label="篩選銀行"
            >
              <option value="all">全部銀行</option>
              <option value="sinopac">永豐</option>
              <option value="taishin">台新</option>
            </select>
          </div>

          <div className="bank-reconcile-filter-item">
            <label htmlFor="filter-dir">方向</label>
            <select
              id="filter-dir"
              value={filterDir}
              onChange={(e) => { setCursors([undefined]); setFilterDir(e.target.value as typeof filterDir); }}
              aria-label="篩選方向"
            >
              <option value="all">全部方向</option>
              <option value="in">入款</option>
              <option value="out">出款</option>
            </select>
          </div>

          <div className="bank-reconcile-filter-item">
            <label htmlFor="filter-status">處理狀態</label>
            <select
              id="filter-status"
              value={filterStatus}
              onChange={(e) => { setCursors([undefined]); setFilterStatus(e.target.value as typeof filterStatus); }}
              aria-label="篩選處理狀態"
            >
              <option value="pending">待核對</option>
              <option value="posted">已核銷</option>
              <option value="all">全部狀態</option>
            </select>
          </div>

          <div className="bank-reconcile-filter-item">
            <label htmlFor="filter-start-date">起日</label>
            <input
              id="filter-start-date"
              type="date"
              value={dates.start}
              onChange={(e) => { setCursors([undefined]); setDates({ ...dates, start: e.target.value }); }}
              aria-label="交易起日"
            />
          </div>

          <div className="bank-reconcile-filter-item">
            <label htmlFor="filter-end-date">迄日</label>
            <input
              id="filter-end-date"
              type="date"
              value={dates.end}
              onChange={(e) => { setCursors([undefined]); setDates({ ...dates, end: e.target.value }); }}
              aria-label="交易迄日"
            />
          </div>

          <div className="bank-reconcile-filter-item bank-reconcile-search">
            <label htmlFor="filter-search-input">搜尋交易</label>
            <input
              id="filter-search-input"
              value={filterSearch}
              placeholder="案件、對象或來源識別"
              maxLength={120}
              onChange={(e) => { setCursors([undefined]); setFilterSearch(e.target.value); }}
              aria-label="搜尋交易" data-bank-reconciliation-focus
            />
          </div>
        </div>

        {/* 雙行主次排版表格 */}
        <div className="finance-table-container">
          <table className="finance-table">
            <thead>
              <tr>
                <th>日期／參考號</th>
                <th>銀行／方向</th>
                <th style={{ textAlign: 'right' }}>金額 (NT$)</th>
                <th>對象</th>
                <th>關聯案件</th>
                <th>款項用途</th>
                <th style={{ textAlign: 'center' }}>狀態</th>
                <th style={{ textAlign: 'right' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {/* 待核對交易列 */}
              {(filterStatus === 'pending' || filterStatus === 'all') &&
                pendingRows.map((row) => {
                  const review = financeBankReviewPresentation(row, previewRows.get(row.row_identity), postingStopped);
                  return (
                    <tr key={row.row_identity}>
                      <td>
                        <strong>{row.transaction_date ?? '日期待確認'}</strong>
                        <small className="bank-reconcile-sub">{row.reference}</small>
                      </td>
                      <td>
                        <strong>{bankShortNameMap[row.bank]}</strong>
                        <small className={row.direction === 'incoming' ? 'bank-direction-in' : 'bank-direction-out'}>
                          {directionLabel(row.direction)}
                        </small>
                      </td>
                      <td style={{ textAlign: 'right', fontWeight: 700, fontSize: '0.95rem' }}>
                        {financeMoney(row.amount_ntd)}
                      </td>
                      <td>
                        {row.counterparty_name || (row.classification_type === 'government_subsidy' ? '新竹市政府' : '對象待確認')}
                      </td>
                      <td>
                        {row.cases.length > 0 ? (
                          row.cases.map((caseNo: string) => (
                            <button
                              key={caseNo}
                              type="button"
                              className="finance-btn-link"
                              onClick={() => onCase(caseNo)}
                              style={{ marginRight: '6px', fontWeight: 700 }}
                            >
                              {caseNo}
                            </button>
                          ))
                        ) : row.classification_type === 'government_subsidy' ? (
                          <span className="bank-reconcile-sub" style={{ fontSize: '0.82rem' }}>整期核銷（待選期間）</span>
                        ) : (
                          <span className="bank-reconcile-sub" style={{ fontSize: '0.82rem' }}>未確認唯一案件</span>
                        )}
                      </td>
                      <td>
                        {bankPurposeLabel(row)}
                        <small className="bank-reconcile-sub">{review.reason}</small>
                        {review.nextStep !== review.reason && <small className="bank-reconcile-sub">{review.nextStep}</small>}
                      </td>
                      <td style={{ textAlign: 'center' }}>
                        <span className="bank-chip-amber">
                          {review.label}
                        </span>
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <button type="button" className="bank-btn-action" disabled={reviewBusy}
                          onClick={() => onReconcile(row)} aria-label={`核對交易 ${row.reference}`}>
                          核對交易
                        </button>
                        {!row.reconciliation_target && !row.staff_subsidy_batch_identity
                          && row.classification_type !== 'government_subsidy' && (
                          <small className="bank-reconcile-sub">{bankReconciliationUnavailableReason(row)}</small>
                        )}
                        <button
                          type="button"
                          className="bank-btn-action btn-view"
                          onClick={() => setViewedRow(row)}
                          aria-label={`查看交易 ${row.row_identity}`}
                        >
                          查看明細
                        </button>
                      </td>
                    </tr>
                  );
                })}

              {/* 已核銷銀行交易列 */}
              {(filterStatus === 'posted' || filterStatus === 'all') &&
                postedRows.map((row) => (
                  <tr key={row.row_identity}>
                    <td>
                      <strong>{row.transaction_date}</strong>
                      <small className="bank-reconcile-sub">{row.reference}</small>
                    </td>
                    <td>
                      <strong>{bankShortNameMap[row.bank ?? ''] ?? '來源待確認'}</strong>
                      <small className={row.direction === 'incoming' ? 'bank-direction-in' : 'bank-direction-out'}>
                        {directionLabel(row.direction)}
                      </small>
                    </td>
                    <td style={{ textAlign: 'right', fontWeight: 700, fontSize: '0.95rem' }}>
                      {financeMoney(row.amount_ntd)}
                    </td>
                    <td>{row.counterparty_name || (row.cases.length > 0 ? '已確認對象' : '對象待確認')}</td>
                    <td>
                      {row.cases.map((caseNo: string) => (
                        <button
                          key={caseNo}
                          type="button"
                          className="finance-btn-link"
                          onClick={() => onCase(caseNo)}
                          style={{ marginRight: '6px', fontWeight: 700 }}
                        >
                          {caseNo}
                        </button>
                      ))}
                      {row.cases.length > 1 && <small className="bank-reconcile-sub">整筆跨案來源</small>}
                    </td>
                    <td>
                      <span>{bankPurposeLabel(row)}</span>
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <span className="bank-chip-green">已核銷</span>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <button
                        type="button"
                        className="bank-btn-action btn-view"
                        onClick={() => setViewedRow(row)}
                        aria-label={`查看交易 ${row.row_identity}`}
                      >
                        查看明細
                      </button>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>

          {transactions.kind === 'loading' && <p role="status">正在查詢銀行交易…</p>}
          {transactions.kind === 'error' && (
            <div className="finance-state" role="alert">
              {transactions.message}
              <button type="button" onClick={() => setRetry(value => value + 1)}>重新查詢銀行交易</button>
            </div>
          )}
          {page?.items.length === 0 && <p className="finance-state">目前沒有符合條件的銀行交易資料。</p>}
        </div>
        <div className="bank-reconcile-footer-note">
          {cursors.length > 1 && <button type="button" disabled={!page} onClick={() => setCursors(values => values.slice(0, -1))}>上一頁</button>}
          {page?.next_before_row_id != null && <button type="button" onClick={() => setCursors(values => [...values, page.next_before_row_id!])}>下一頁</button>}
        </div>
      </section>

      {historyOpen && <FinanceImportHistory revision={revision} onClose={() => setHistoryOpen(false)} />}
      {excludedOpen && <FinanceExcludedTransactionsDrawer revision={revision} onClose={() => setExcludedOpen(false)} />}

      {viewedTransaction && (
        <Drawer
          isOpen
          onClose={() => setViewedRow(null)}
          closeLabel="返回"
          ariaLabel={detailTitle}
          title={detailTitle}
          footer={<>
            {viewedTransaction.status === 'pending' && (
              <button type="button" className="finance-btn-primary" disabled={reviewBusy}
                onClick={() => onReconcile(viewedTransaction)}>核對交易</button>
            )}
            <button type="button" className="finance-btn-secondary" onClick={() => setViewedRow(null)}>返回</button>
          </>}
        >
          <BankTransactionFacts row={viewedTransaction} />
          <section className="bank-fact-card" aria-label="核對紀錄">
            <h4>核對紀錄</h4>
            {(detailFetch.kind === 'idle' || detailFetch.kind === 'loading') && <p role="status">正在查詢本筆核對紀錄…</p>}
            {detailFetch.kind === 'error' && <div role="alert">
              <p>{detailFetch.message}</p>
              <button type="button" className="finance-btn-secondary" onClick={() => setDetailRetry(value => value + 1)}>重新查詢明細</button>
            </div>}
            {detailFetch.kind === 'ready' && (viewedTransaction.reconciliation_records?.length ? <ul>
              {viewedTransaction.reconciliation_records.map((record, index) => <li key={`${record.owning_domain}:${record.recorded_at}:${index}`}>
                {record.owning_domain === 'client_finance' ? '客戶款項核銷' : '月嫂款項核銷'} · {financeMoney(record.amount_ntd)} · {formatTaipeiDateTime(record.recorded_at, true)}
              </li>)}
            </ul> : <p>本筆沒有可查閱的核對紀錄。</p>)}
          </section>
          {viewedTransaction.status === 'pending' && (
            <section className="bank-fact-card" aria-label="未自動核銷原因">
              <h4>未自動核銷原因</h4>
              <p>{financeImportReviewReason(viewedTransaction, previewRows.get(viewedTransaction.row_identity), postingStopped)}</p>
              {viewedTransaction.dispatch_reason && <small>原因代碼 {viewedTransaction.dispatch_reason}</small>}
            </section>
          )}

          <div style={{ padding: '16px 0', borderTop: '1px solid #f2e2dc', marginTop: '16px' }}>
            <h4 style={{ margin: '0 0 10px 0', fontSize: '0.88rem', color: '#1e1b19' }}>關聯案件</h4>
            {viewedTransaction.cases.length === 0 ? (
              <p style={{ color: '#74593f', fontSize: '0.82rem' }}>無關聯特定案件。</p>
            ) : (
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                {viewedTransaction.cases.map((caseNo: string) => (
                  <button
                    key={caseNo}
                    type="button"
                    className="finance-btn-secondary"
                    onClick={() => onCaseFromDetail(caseNo)}
                  >
                    開啟案件 {caseNo}
                  </button>
                ))}
              </div>
            )}
            {viewedTransaction.status === 'posted' && (
              <p style={{ marginTop: '14px', fontSize: '0.78rem', color: '#9a8473', lineHeight: 1.6 }}>
                本筆為已核銷之正式銀行流水事實；逐筆來源只列一次，紀錄為唯讀查閱，不提供重複核銷。
              </p>
            )}
          </div>
        </Drawer>
      )}
    </div>
  );
}

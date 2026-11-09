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
import type { FinanceBankTransaction, FinanceBankTransactionPage, FinanceImportHistoryPage } from '../api/finance_import/finance_import_query_schemas';
import type { FinanceImportBatchOutcome, FinanceImportBatchPreview, FinanceImportJobAccepted, FinanceWorkbookIngestionReceipt } from '../api/finance_import/finance_import_mutation_client';
import { financeImportQueryClient } from '../api/finance_import/finance_import_query_client';

type LoadState<T> = { kind: 'idle' | 'loading' } | { kind: 'ready'; data: T } | { kind: 'empty' } | { kind: 'error'; message: string } | { kind: 'unavailable'; message: string };
const purposeLabels: Record<string, string> = {
  client_receipt: '客戶入款', client_refund: '客戶退款', client_subsidy_return: '退客戶先墊補助', client_refund_return: '客戶退匯',
  staff_payout: '付月嫂', staff_salary: '付月嫂', staff_legacy_subsidy: '補助轉交月嫂',
  government_subsidy: '政府補助',
};

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
            <thead><tr><th>上傳時間</th><th>銀行／檔案</th><th>結果</th><th>新增流水</th><th>重複來源列</th><th>本次核銷</th><th>當時待核對</th></tr></thead>
            <tbody>{page.items.map(entry => (
              <tr key={entry.identity}>
                <td>{new Date(entry.started_at).toLocaleString('zh-TW', { timeZone: 'Asia/Taipei' })}</td>
                <td>{entry.bank ? bankShortNameMap[entry.bank] : '銀行無紀錄'}<br />{entry.source_file ?? '檔名無紀錄'}</td>
                <td>{historyStatus[entry.status]}{entry.source_warning_count ? <small> · 來源格式異常 {entry.source_warning_count} 筆</small> : null}</td>
                <td>{entry.new_count ?? '—'}</td>
                <td>
                  {entry.duplicate_count ?? '—'}
                  {!!entry.duplicate_count && <small className="bank-reconcile-sub">{duplicateSkipReason}</small>}
                </td>
                <td>{entry.reconciled_count ?? (entry.status === 'posting' ? '待確認' : '—')}</td>
                <td>{entry.pending_count ?? (entry.status === 'posting' ? '待確認' : '無紀錄')}</td>
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

export interface FinanceBankReconciliationWorkspaceProps {
  onCase: (caseNo: string) => void;
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
  confirmedImportReceipt: { reconciled_count: number; existing_count: number } | null;
  submittedFinanceCommand?: unknown;
}

export function FinanceBankReconciliationWorkspace({
  onCase,
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
  const [transactions, setTransactions] = useState<LoadState<FinanceBankTransactionPage>>({ kind: 'loading' });
  const [historyOpen, setHistoryOpen] = useState(false);
  const [showImportPanel, setShowImportPanel] = useState(false);
  const [targetBankFormat, setTargetBankFormat] = useState<string>('');
  const [viewedRow, setViewedRow] = useState<FinanceBankTransaction | null>(null);
  const beforeRowId = cursors.at(-1);

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
  const viewedTransaction = viewedRow && (page?.items.find(row => row.row_id === viewedRow.row_id) ?? viewedRow);
  const detailTitle = viewedTransaction?.status === 'posted' ? '已核銷交易明細' : '待核對交易明細';

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
          <FinanceStatementArchive compact={true} />
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
              onClick={onIngest}
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
        {batchPreview.kind === 'error' && <p className="finance-state error" role="alert">{batchPreview.message}</p>}
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
                        {purposeLabels[row.classification_type] ?? '款項用途待確認'}
                        <small className="bank-reconcile-sub">{review.reason}</small>
                        <small className="bank-reconcile-sub">{review.nextStep}</small>
                      </td>
                      <td style={{ textAlign: 'center' }}>
                        <span className="bank-chip-amber">
                          {review.label}
                        </span>
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        {row.disposition === 'blocked' ? (
                          <span style={{ fontSize: '0.78rem', color: '#dc2626' }}>銷帳受阻</span>
                        ) : (row.reconciliation_target || (row.classification_type === 'government_subsidy' && row.direction !== 'unknown')) ? (
                          <button
                            type="button"
                            className="bank-btn-action"
                            onClick={() => onReconcile(row)}
                            aria-label={`核對交易 ${row.reference}`}
                          >
                            核對交易
                          </button>
                        ) : <span className="bank-reconcile-sub">{bankReconciliationUnavailableReason(row)}</span>}
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
                      <span>{purposeLabels[row.classification_type] ?? '用途已確認'}</span>
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

      {/* 7. WF-04 已核銷交易唯讀明細抽屜 */}
      {viewedTransaction && (
        <Drawer
          isOpen
          onClose={() => setViewedRow(null)}
          closeLabel="返回"
          ariaLabel={detailTitle}
          title={detailTitle}
          footer={
            <button type="button" className="finance-btn-secondary" onClick={() => setViewedRow(null)}>
              返回
            </button>
          }
        >
          <div className="bank-fact-card">
            <span className="eyebrow">銀行原始交易事實</span>
            <h3>
              {bankNameMap[viewedTransaction.bank ?? ''] ?? '銀行交易'} ·{' '}
              {directionLabel(viewedTransaction.direction)} {financeMoney(viewedTransaction.amount_ntd)}
            </h3>
            <p>
              {viewedTransaction.transaction_date ?? '日期待確認'} · 識別：{viewedTransaction.reference}
            </p>
            <div className="bank-fact-grid">
              <div>
                <span>款項用途</span>
                <strong>{purposeLabels[viewedTransaction.classification_type] ?? '款項用途待確認'}</strong>
              </div>
              <div>
                <span>處理狀態</span>
                {viewedTransaction.status === 'posted'
                  ? <span className="bank-chip-green">已核銷 · 唯讀查閱</span>
                  : <span className="bank-chip-amber">{viewedTransaction.disposition === 'blocked' ? '銷帳受阻' : '待核對'}</span>}
              </div>
            </div>
          </div>
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
                    onClick={() => {
                      setViewedRow(null);
                      onCase(caseNo);
                    }}
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

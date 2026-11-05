/**
 * File: FinanceBankReconciliationWorkspace.tsx
 * Description: 銀行對帳工作台（WF-03/04），整合雙銀行匯入、待核對與已核銷總表、KPI膠囊統計及逐筆核對抽屜。
 */

import { useEffect, useRef, useState } from 'react';
import './FinanceBankReconciliationWorkspace.css';
import { Drawer } from './Drawer';
import { FinanceImportCorrectionForm } from './FinanceImportCorrectionForm';
import { FinanceStatementArchive } from './FinanceStatementArchive';
import { monthlyAccountingClient, type MonthlyAccountingReport } from '../api/finance_import/monthly_accounting_client';
import { financeMoney } from './FinanceReceiptsWorkspace';
import { financeImportBlockerMessage, financeImportReviewReason, financeImportSkipsUnidentifiedOutgoing } from '../adapters/finance/finance_import_query_adapter';
import type { FinanceImportBatchSummary } from '../api/finance_import/finance_import_query_schemas';
import type { FinanceImportBatchOutcome, FinanceImportBatchPreview, FinanceImportJobAccepted, FinanceWorkbookIngestionReceipt } from '../api/finance_import/finance_import_mutation_client';
import type { financeImportQueryClient } from '../api/finance_import/finance_import_query_client';

type LoadState<T> = { kind: 'idle' | 'loading' } | { kind: 'ready'; data: T } | { kind: 'empty' } | { kind: 'error'; message: string } | { kind: 'unavailable'; message: string };
type FinanceImportReviewSnapshot = {
  batchIdentity: string;
  reviewCount: number;
  items: Awaited<ReturnType<typeof financeImportQueryClient.listReviewRows>>['items'];
  sourceReviews: Awaited<ReturnType<typeof financeImportQueryClient.listReviewRows>>['source_reviews'];
};

type ReviewRow = FinanceImportReviewSnapshot['items'][number];
type MonthlyBankFact = MonthlyAccountingReport['rows'][number]['bank_facts'][number];

const flowLabels: Record<string, string> = {
  C: '客戶入款',
  G: '政府入款',
  PS: '付月嫂',
  PT: '補助轉交月嫂',
  RS: '一般退客戶',
  RT: '退客戶先墊補助',
};

const bankTypeLabels: Record<string, string> = {
  receivable: '客戶收款 (待核對)',
  payable: '付月嫂款 (待核對)',
  government_subsidy: '政府入款 (待核對)',
  subsidy_return: '補助退款 (待核對)',
  review: '款項用途待確認',
  legacy: '待核對交易',
};

const bankNameMap: Record<string, string> = {
  sinopac: '永豐銀行',
  taishin: '台新銀行',
};

const bankShortNameMap: Record<string, string> = {
  sinopac: '永豐',
  taishin: '台新',
};

export interface FinanceBankReconciliationWorkspaceProps {
  onCase: (caseNo: string) => void;
  revision: number;
  staff: readonly { id: number; label: string }[];
  batches: FinanceImportBatchSummary[];
  selectedBatchIdentity: string;
  onSelectBatch: (identity: string) => void;
  sourceReview: LoadState<FinanceImportReviewSnapshot>;
  onReloadSourceReview: (batchIdentity: string) => void;
  financeWorkbook: File | null;
  onWorkbookChange: (file: File | null) => void;
  applyReason: string;
  onApplyReasonChange: (reason: string) => void;
  importBusy: boolean;
  ingestion: LoadState<FinanceWorkbookIngestionReceipt>;
  batchPreview: LoadState<FinanceImportBatchPreview>;
  applyJob: LoadState<FinanceImportJobAccepted>;
  batchOutcome: LoadState<FinanceImportBatchOutcome>;
  onIngest: () => void;
  onApply: (preview: FinanceImportBatchPreview) => void;
  onObserveApplyOutcome: (jobId: string, expected?: { batchIdentity: string; previewFingerprint: string }) => void;
  onPostedManual: (rowIdentity: string) => void;
  postingStopped?: boolean;
  manuallyPostedRows: ReadonlySet<string> | Set<string>;
  confirmedImportReceipt: { reconciled_count: number; existing_count: number } | null;
  submittedFinanceCommand?: unknown;
}

export function FinanceBankReconciliationWorkspace({
  onCase,
  revision,
  staff,
  batches,
  selectedBatchIdentity,
  onSelectBatch: _onSelectBatch,
  sourceReview,
  onReloadSourceReview: _onReloadSourceReview,
  financeWorkbook,
  onWorkbookChange,
  applyReason,
  onApplyReasonChange,
  importBusy,
  ingestion,
  batchPreview,
  applyJob,
  batchOutcome,
  onIngest,
  onApply,
  onObserveApplyOutcome,
  onPostedManual,
  postingStopped = false,
  manuallyPostedRows,
  confirmedImportReceipt,
  submittedFinanceCommand,
}: FinanceBankReconciliationWorkspaceProps) {
  // 1. 日期與篩選狀態
  const [dates, setDates] = useState(() => {
    const d = new Date();
    const m = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
    return {
      start: m + '-01',
      end: m + '-' + String(new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate()),
    };
  });
  const [filterBank, setFilterBank] = useState('all');
  const [filterDir, setFilterDir] = useState('all');
  const [filterStatus, setFilterStatus] = useState<'pending' | 'posted' | 'all'>('pending');
  const [filterSearch, setFilterSearch] = useState('');

  // 2. 匯入面板展開與匯入目標提示
  const [showImportPanel, setShowImportPanel] = useState(false);
  const [targetBankFormat, setTargetBankFormat] = useState<string>('');

  // 3. 已核銷銀行交易狀態
  const [postedState, setPostedState] = useState<{ data?: MonthlyAccountingReport; error?: string }>({});

  // 4. WF-04 抽屜狀態 (核對抽屜與已核銷查看抽屜)
  const [correctionRow, setCorrectionRow] = useState<ReviewRow | null>(null);
  const [viewedPostedRow, setViewedPostedRow] = useState<MonthlyBankFact | null>(null);
  const [correctionBusy, setCorrectionBusy] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setPostedState({});
    void monthlyAccountingClient
      .query(
        {
          start_month: dates.start.slice(0, 7),
          end_month: dates.end.slice(0, 7),
          category: 'all',
        },
        controller.signal
      )
      .then((data) => {
        if (!controller.signal.aborted) setPostedState({ data });
      })
      .catch(() => {
        if (!controller.signal.aborted) setPostedState({ error: '已核銷銀行交易暫時無法取得，請重新查詢。' });
      });
    return () => controller.abort();
  }, [dates, revision]);

  // 整理已核銷清單
  const postedRows: MonthlyBankFact[] =
    postedState.data?.rows
      .flatMap((row) => row.bank_facts)
      .filter((row) => {
        const dateMatch = row.occurred_on >= dates.start && row.occurred_on <= dates.end;
        const bankMatch = filterBank === 'all' || row.bank === filterBank;
        const dirMatch =
          filterDir === 'all' ||
          (filterDir === 'in' && row.direction === 'in') ||
          (filterDir === 'out' && row.direction === 'out');
        const searchMatch = !filterSearch.trim() || `${row.identity} ${row.cases.join(' ')}`.includes(filterSearch.trim());
        return dateMatch && bankMatch && dirMatch && searchMatch;
      }) ?? [];

  // 整理待核對清單 (來自 sourceReview)
  const reviewItems: ReviewRow[] = sourceReview.kind === 'ready' ? sourceReview.data.items : [];
  const selectedBatch = batches.find((b) => b.batch_identity === selectedBatchIdentity);
  const batchBankFormat = selectedBatch?.format_id; // 'taishin' | 'sinopac' | etc.

  const pendingRows = reviewItems.filter((row) => {
    if (manuallyPostedRows.has(row.row_identity)) return false;
    const itemDate = row.transaction_date ?? '';
    const dateMatch = !itemDate || (itemDate >= dates.start && itemDate <= dates.end);
    const bankMatch =
      filterBank === 'all' ||
      (filterBank === 'sinopac' && batchBankFormat === 'sinopac') ||
      (filterBank === 'taishin' && batchBankFormat === 'taishin');
    const isIncoming = ['incoming', 'credit'].includes(row.direction);
    const dirMatch =
      filterDir === 'all' ||
      (filterDir === 'in' && isIncoming) ||
      (filterDir === 'out' && !isIncoming);
    const searchMatch =
      !filterSearch.trim() ||
      `${row.source_sheet}#${row.source_row} ${row.amount_ntd}`.includes(filterSearch.trim());
    return dateMatch && bankMatch && dirMatch && searchMatch;
  });

  const pendingWithoutCase = pendingRows.filter(
    (row) => !row.available_actions.some((a) => a === 'preview_manual_correction')
  );

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
            onClick={() => triggerUpload('sinopac')}
            aria-label="匯入永豐對帳單"
          >
            匯入永豐對帳單
          </button>
          <button
            type="button"
            className="finance-btn-primary"
            onClick={() => triggerUpload('taishin')}
            aria-label="匯入台新對帳單"
          >
            匯入台新對帳單
          </button>
          <FinanceStatementArchive compact={true} />
        </div>
      </section>

      {/* 2. 受控檔案上傳列 (點擊匯入或常駐支援) */}
      <div
        className="bank-reconcile-import-panel"
        style={{ display: showImportPanel || financeWorkbook ? 'flex' : 'none' }}
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
                importBusy ||
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
            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.82rem', margin: 0, fontWeight: 600 }}>
              正式銷帳原因（選填）
              <input
                className="finance-input"
                placeholder="輸入銷帳說明"
                value={applyReason}
                maxLength={500}
                disabled={
                  importBusy ||
                  ingestion.kind === 'loading' ||
                  batchPreview.kind === 'loading' ||
                  applyJob.kind === 'loading' ||
                  batchOutcome.kind === 'loading' ||
                  submittedFinanceCommand !== undefined
                }
                onChange={(e) => onApplyReasonChange(e.target.value)}
                style={{ width: '200px', minHeight: '34px', padding: '6px 10px' }}
              />
            </label>
            <button
              type="button"
              className="finance-btn-primary"
              data-control-id="finance.finance-import.upload"
              disabled={
                importBusy ||
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
          (batchPreview.kind === 'ready' && !importBusy && (!batchPreview.data.apply_allowed || batchPreview.data.counts.ready_dispatch === 0))) && (
          <div className="finance-meta" style={{ marginTop: '10px' }}>
            <span>
              本次已銷帳 {(confirmedImportReceipt?.reconciled_count ?? 0) + manuallyPostedRows.size} 筆｜已存在略過{' '}
              {confirmedImportReceipt?.existing_count ?? (batchPreview.kind === 'ready' ? batchPreview.data.counts.existing : 0)} 筆
            </span>
            {batchPreview.kind === 'ready' && !batchPreview.data.apply_allowed && (
              <span style={{ color: '#c5221f', fontWeight: 700 }} role="alert">
                （自動銷帳未執行：{financeImportBlockerMessage(batchPreview.data.blocking_codes)}。資料已匯入入帳，請查看未銷帳明細與原因）
              </span>
            )}
          </div>
        )}
      </div>

      {/* 4. KPI 統計膠囊列 (Pill Tags) */}
      <div className="bank-reconcile-counts" aria-label="銀行對帳統計摘要">
        <span className="bank-reconcile-pill pill-pending">
          待核對 <strong id="kpi-pending-count">{pendingRows.length}</strong> 筆
        </span>
        <span className="bank-reconcile-pill pill-posted">
          已核銷 <strong>{postedRows.length}</strong> 筆
        </span>
        <span className="bank-reconcile-pill pill-warning">
          對象／案件待確認 <strong>{pendingWithoutCase.length}</strong> 筆
        </span>
      </div>

      {/* 5. 總表卡片面板 */}
      <section className="bank-reconcile-panel" aria-label="銀行對帳總表">
        {/* 篩選工具列 Filter Bar */}
        <div className="bank-reconcile-filters">
          <div className="bank-reconcile-filter-item">
            <label htmlFor="filter-bank">銀行</label>
            <select
              id="filter-bank"
              value={filterBank}
              onChange={(e) => setFilterBank(e.target.value)}
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
              onChange={(e) => setFilterDir(e.target.value)}
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
              onChange={(e) => setFilterStatus(e.target.value as 'pending' | 'posted' | 'all')}
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
              onChange={(e) => setDates({ ...dates, start: e.target.value })}
              aria-label="交易起日"
            />
          </div>

          <div className="bank-reconcile-filter-item">
            <label htmlFor="filter-end-date">迄日</label>
            <input
              id="filter-end-date"
              type="date"
              value={dates.end}
              onChange={(e) => setDates({ ...dates, end: e.target.value })}
              aria-label="交易迄日"
            />
          </div>

          <div className="bank-reconcile-filter-item bank-reconcile-search">
            <label htmlFor="filter-search-input">搜尋交易</label>
            <input
              id="filter-search-input"
              value={filterSearch}
              placeholder="案件、對象或來源識別"
              onChange={(e) => setFilterSearch(e.target.value)}
              aria-label="搜尋交易"
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
                  const isIncoming = ['incoming', 'credit'].includes(row.direction);
                  const bankLabel = batchBankFormat === 'taishin' ? '台新' : batchBankFormat === 'sinopac' ? '永豐' : '待確認';
                  return (
                    <tr key={row.row_identity}>
                      <td>
                        <strong>{row.transaction_date ?? '日期待確認'}</strong>
                        <small className="bank-reconcile-sub">{row.source_sheet}#{row.source_row}</small>
                      </td>
                      <td>
                        <strong>{bankLabel}</strong>
                        <small className={isIncoming ? 'bank-direction-in' : 'bank-direction-out'}>
                          {isIncoming ? '入款' : '出款'}
                        </small>
                      </td>
                      <td style={{ textAlign: 'right', fontWeight: 700, fontSize: '0.95rem' }}>
                        {financeMoney(row.amount_ntd)}
                      </td>
                      <td>{row.classification_type === 'staff_payout' ? '月嫂（待指定）' : row.classification_type === 'client_refund' ? '客戶（待退款）' : '對象待確認'}</td>
                      <td>
                        <span style={{ color: '#74593f', fontSize: '0.8rem' }}>待指派案件</span>
                      </td>
                      <td>
                        <span>{bankTypeLabels[row.bank_type ?? 'review']}</span>
                        <small className="bank-reconcile-sub">{financeImportReviewReason(row, undefined, postingStopped)}</small>
                      </td>
                      <td style={{ textAlign: 'center' }}>
                        <span className="bank-chip-amber">待核對</span>
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        {row.disposition === 'blocked' ? (
                          <span style={{ fontSize: '0.78rem', color: '#dc2626' }}>銷帳受阻</span>
                        ) : !financeImportSkipsUnidentifiedOutgoing(row) ? (
                          <button
                            type="button"
                            className="bank-btn-action"
                            onClick={() => setCorrectionRow(row)}
                            aria-label={`核對交易 ${row.source_sheet}#${row.source_row}`}
                          >
                            核對交易
                          </button>
                        ) : (
                          <span style={{ fontSize: '0.78rem', color: '#9a8473' }}>略過出款</span>
                        )}
                      </td>
                    </tr>
                  );
                })}

              {/* 已核銷銀行交易列 */}
              {(filterStatus === 'posted' || filterStatus === 'all') &&
                postedRows.map((row) => (
                  <tr key={row.identity}>
                    <td>
                      <strong>{row.occurred_on}</strong>
                      <small className="bank-reconcile-sub">{row.identity}</small>
                    </td>
                    <td>
                      <strong>{bankShortNameMap[row.bank ?? ''] ?? '來源待確認'}</strong>
                      <small className={row.direction === 'in' ? 'bank-direction-in' : 'bank-direction-out'}>
                        {row.direction === 'in' ? '入款' : '出款'}
                      </small>
                    </td>
                    <td style={{ textAlign: 'right', fontWeight: 700, fontSize: '0.95rem' }}>
                      {financeMoney(row.amount_ntd)}
                    </td>
                    <td>{row.cases.length > 0 ? '已確認對象' : '對象待確認'}</td>
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
                      <span>{row.cash_flow ? flowLabels[row.cash_flow] : '用途已確認'}</span>
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <span className="bank-chip-green">已核銷</span>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <button
                        type="button"
                        className="bank-btn-action btn-view"
                        onClick={() => setViewedPostedRow(row)}
                        aria-label={`查看交易 ${row.identity}`}
                      >
                        查看明細
                      </button>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>

          {/* 空狀態顯示 */}
          {((filterStatus === 'pending' && pendingRows.length === 0) ||
            (filterStatus === 'posted' && postedRows.length === 0) ||
            (filterStatus === 'all' && pendingRows.length === 0 && postedRows.length === 0)) && (
            <div className="finance-state" style={{ padding: '36px 20px' }}>
              目前沒有符合條件的銀行交易資料。
            </div>
          )}
        </div>

        {/* 底註說明 */}
        <div className="bank-reconcile-footer-note">
          <span>政府整批款保留整筆來源與期間關聯；缺正式分配時，不把整額複製到每個案件。</span>
          <span>
            篩選顯示：待核對 {pendingRows.length} 筆 · 已核銷 {postedRows.length} 筆
          </span>
        </div>
      </section>

      {/* 6. WF-04 逐筆核對抽屜 (待核對交易核實) */}
      {correctionRow && (
        <Drawer
          isOpen
          onClose={() => setCorrectionRow(null)}
          closeDisabled={correctionBusy}
          closeLabel="關閉"
          ariaLabel="核對銀行交易"
          title="WF-04 · 逐筆核對抽屜"
          size="xl"
        >
          {/* 原始交易事實卡片 */}
          <div className="bank-fact-card">
            <span className="eyebrow">銀行原始交易事實</span>
            <h3>
              {batchBankFormat === 'taishin' ? '台新銀行' : batchBankFormat === 'sinopac' ? '永豐銀行' : '銀行交易'} ·{' '}
              {['incoming', 'credit'].includes(correctionRow.direction) ? '入款' : '出款'}{' '}
              {correctionRow.amount_ntd.toLocaleString()} 元
            </h3>
            <p>
              {correctionRow.transaction_date ?? '日期未提供'} · {correctionRow.source_sheet}#{correctionRow.source_row}
            </p>
            <div className="bank-fact-grid">
              <div>
                <span>未銷帳原因</span>
                <strong>{financeImportReviewReason(correctionRow, undefined, postingStopped)}</strong>
              </div>
              <div>
                <span>處理狀態</span>
                <span className="bank-chip-amber">待核銷 (未入帳)</span>
              </div>
            </div>
          </div>

          {/* 核銷表單 (接入原有的完整業務防護表單) */}
          <FinanceImportCorrectionForm
            key={correctionRow.row_identity}
            rowIdentity={correctionRow.row_identity}
            sourceLabel={`${correctionRow.source_sheet} 第 ${correctionRow.source_row} 列`}
            staff={staff}
            initialKind={
              correctionRow.classification_type === 'client_refund'
                ? 'client_refund'
                : correctionRow.classification_type === 'staff_payout'
                ? 'staff_payout'
                : 'client_receipt'
            }
            onBusyChange={setCorrectionBusy}
            onPosted={() => {
              onPostedManual(correctionRow.row_identity);
              setCorrectionRow(null);
            }}
          />
        </Drawer>
      )}

      {/* 7. WF-04 已核銷交易唯讀明細抽屜 */}
      {viewedPostedRow && (
        <Drawer
          isOpen
          onClose={() => setViewedPostedRow(null)}
          closeLabel="返回"
          ariaLabel="已核銷交易明細"
          title="已核銷交易明細"
          footer={
            <button type="button" className="finance-btn-secondary" onClick={() => setViewedPostedRow(null)}>
              返回
            </button>
          }
        >
          <div className="bank-fact-card">
            <span className="eyebrow">銀行原始交易事實</span>
            <h3>
              {bankNameMap[viewedPostedRow.bank ?? ''] ?? '銀行交易'} ·{' '}
              {viewedPostedRow.direction === 'in' ? '入款' : '出款'} {financeMoney(viewedPostedRow.amount_ntd)}
            </h3>
            <p>
              {viewedPostedRow.occurred_on} · 識別：{viewedPostedRow.identity}
            </p>
            <div className="bank-fact-grid">
              <div>
                <span>款項用途</span>
                <strong>{viewedPostedRow.cash_flow ? flowLabels[viewedPostedRow.cash_flow] : '已確認'}</strong>
              </div>
              <div>
                <span>處理狀態</span>
                <span className="bank-chip-green">已核銷 · 唯讀查閱</span>
              </div>
            </div>
          </div>

          <div style={{ padding: '16px 0', borderTop: '1px solid #f2e2dc', marginTop: '16px' }}>
            <h4 style={{ margin: '0 0 10px 0', fontSize: '0.88rem', color: '#1e1b19' }}>關聯案件</h4>
            {viewedPostedRow.cases.length === 0 ? (
              <p style={{ color: '#74593f', fontSize: '0.82rem' }}>無關聯特定案件。</p>
            ) : (
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                {viewedPostedRow.cases.map((caseNo: string) => (
                  <button
                    key={caseNo}
                    type="button"
                    className="finance-btn-secondary"
                    onClick={() => {
                      setViewedPostedRow(null);
                      onCase(caseNo);
                    }}
                  >
                    開啟案件 {caseNo}
                  </button>
                ))}
              </div>
            )}
            <p style={{ marginTop: '14px', fontSize: '0.78rem', color: '#9a8473', lineHeight: 1.6 }}>
              本筆為已核銷之正式銀行流水事實；逐筆來源只列一次，紀錄為唯讀查閱，不提供重複核銷。
            </p>
          </div>
        </Drawer>
      )}
    </div>
  );
}

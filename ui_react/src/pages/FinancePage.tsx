/**
 * File: FinancePage.tsx
 * Description: 呈現Finance查詢與受控銀行流水 Upload、Preview、durable Apply、terminal receipt 工作區。
 */
import React, { useEffect, useRef, useState } from 'react';
import './FinancePage.css';
import { loadAllOrderSummaries, ordersQueryClient } from '../api/orders/order_query_client';
import { adaptOrderSummaryPage } from '../adapters/orders/order_summary_adapter';
import { loadAllStaffDirectoryPages, staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { adaptStaffDirectoryPage } from '../adapters/staff/staff_directory_adapter';
import { clientReceiptQueryClient } from '../api/client_finance/client_receipt_query_client';
import { adaptClientReceiptQuery } from '../adapters/finance/client_receipt_query_adapter';
import { staffPayablesQueryClient } from '../api/staff_payables/staff_payables_query_client';
import { adaptStaffPayablesQuery } from '../adapters/finance/staff_payables_query_adapter';
import { accountsPayableQueryClient } from '../api/accounts_payable/accounts_payable_query_client';
import { adaptAccountsPayablePreview } from '../adapters/finance/accounts_payable_query_adapter';
import { financeImportBlockerMessage } from '../adapters/finance/finance_import_query_adapter';
import { FinanceWorkbookSnapshot, financeImportMutationClient, type FinanceImportBatchOutcome, type FinanceImportBatchPreview, type FinanceImportJobAccepted, type FinanceWorkbookIngestionReceipt } from '../api/finance_import/finance_import_mutation_client';

type FinanceTab = 'client-receipts' | 'staff-payables' | 'accounts-payable' | 'finance-import';
type LoadState<T> = { kind: 'idle' | 'loading' } | { kind: 'ready'; data: T } | { kind: 'empty' } | { kind: 'error'; message: string } | { kind: 'unavailable'; message: string };
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
  const [activeTab, setActiveTab] = useState<FinanceTab>('client-receipts');
  const [cases, setCases] = useState<{ id: string; label: string }[]>([]);
  const [selectedCase, setSelectedCase] = useState('');
  const [caseQuery, setCaseQuery] = useState('');
  const [receipt, setReceipt] = useState<LoadState<ReturnType<typeof adaptClientReceiptQuery>>>({ kind: 'idle' });
  const [staff, setStaff] = useState<{ id: number; label: string }[]>([]);
  const [selectedStaff, setSelectedStaff] = useState<number | null>(null);
  const [payables, setPayables] = useState<LoadState<ReturnType<typeof adaptStaffPayablesQuery>>>({ kind: 'idle' });
  const [targetMonth, setTargetMonth] = useState(currentMonth);
  const [accountsPayable, setAccountsPayable] = useState<LoadState<ReturnType<typeof adaptAccountsPayablePreview>>>({ kind: 'idle' });
  const [financeWorkbook, setFinanceWorkbook] = useState<File | null>(null);
  const [ingestion, setIngestion] = useState<LoadState<FinanceWorkbookIngestionReceipt>>({ kind: 'idle' });
  const [batchPreview, setBatchPreview] = useState<LoadState<FinanceImportBatchPreview>>({ kind: 'idle' });
  const [applyReason, setApplyReason] = useState('已核對銀行流水預覽，確認匯入');
  const [applyConfirmed, setApplyConfirmed] = useState(false);
  const [applyJob, setApplyJob] = useState<LoadState<FinanceImportJobAccepted>>({ kind: 'idle' });
  const [batchOutcome, setBatchOutcome] = useState<LoadState<FinanceImportBatchOutcome>>({ kind: 'idle' });
  const [reload, setReload] = useState(0);
  const controllers = useRef(new Map<string, AbortController>());
  const sequences = useRef(new Map<string, number>());
  const financeApplyCorrelationByPreview = useRef(new Map<string, string>());

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
        const adapted = adaptOrderSummaryPage(page).items.map((item) => ({ id: item.id, label: `${item.id}｜${item.clientName}` }));
        setCases(adapted);
        setSelectedCase((value) => adapted.some((item) => item.id === value) ? value : adapted[0]?.id ?? '');
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
    if (activeTab !== 'staff-payables') return;
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
    if (activeTab !== 'accounts-payable') return;
    return schedule('accounts-payable', (request) => {
      setAccountsPayable({ kind: 'loading' });
      void accountsPayableQueryClient.query(targetMonth, { signal: request.controller.signal })
        .then((data) => { if (current('accounts-payable', request.sequence, request.controller)) setAccountsPayable(data.rows.length ? { kind: 'ready', data: adaptAccountsPayablePreview(data) } : { kind: 'empty' }); })
        .catch((error: unknown) => { if (current('accounts-payable', request.sequence, request.controller)) setAccountsPayable({ kind: 'error', message: financeErrorMessage(error, '應付帳款查詢失敗，請重新整理。') }); });
    });
  }, [activeTab, targetMonth, reload]);

  const ingestWorkbook = async () => {
    if (financeWorkbook === null) { setIngestion({ kind: 'error', message: '請先選擇 .xlsx 銀行流水工作簿。' }); return; }
    setIngestion({ kind: 'loading' }); setBatchPreview({ kind: 'idle' }); setApplyConfirmed(false); setApplyJob({ kind: 'idle' }); setBatchOutcome({ kind: 'idle' });
    try {
      const snapshot = await FinanceWorkbookSnapshot.fromFile(financeWorkbook);
      const receipt = await financeImportMutationClient.ingest(snapshot, { idempotencyKey: `ui-finance-ingest-${snapshot.sha256}`, correlationId: `ui-finance-ingest-${crypto.randomUUID()}` });
      setIngestion({ kind: 'ready', data: receipt });
    } catch (error) { setIngestion({ kind: 'error', message: financeErrorMessage(error, '銀行流水上傳失敗，請重新選擇檔案。') }); }
  };
  const previewImportedBatch = async () => {
    if (ingestion.kind !== 'ready') return;
    setBatchPreview({ kind: 'loading' }); setApplyConfirmed(false); setApplyJob({ kind: 'idle' }); setBatchOutcome({ kind: 'idle' });
    try { setBatchPreview({ kind: 'ready', data: await financeImportMutationClient.preview(ingestion.data.batch_identity) }); }
    catch (error) { setBatchPreview({ kind: 'error', message: financeErrorMessage(error, '匯入預覽未完成，請重新執行預覽。') }); }
  };
  const applyImportedBatch = async () => {
    if (batchPreview.kind !== 'ready' || !applyConfirmed) return;
    setApplyJob({ kind: 'loading' }); setBatchOutcome({ kind: 'idle' });
    try {
      const previewFingerprint = batchPreview.data.preview_fingerprint;
      const correlationId = financeApplyCorrelationByPreview.current.get(previewFingerprint)
        ?? `ui-finance-apply-${crypto.randomUUID()}`;
      financeApplyCorrelationByPreview.current.set(previewFingerprint, correlationId);
      const accepted = await financeImportMutationClient.apply(batchPreview.data, applyReason, { idempotencyKey: `ui-finance-apply-${previewFingerprint}`, correlationId });
      setApplyJob({ kind: 'ready', data: accepted });
      await observeApplyOutcome(accepted.job_id);
    } catch (error) { setApplyJob({ kind: 'error', message: financeErrorMessage(error, '正式匯入未受理，請重新預覽後再試。') }); }
  };
  const observeApplyOutcome = async (jobId: string) => {
    const request = start('batch-outcome');
    setBatchOutcome({ kind: 'loading' });
    try {
      for (let attempt = 0; attempt < FINANCE_OUTCOME_POLL_LIMIT; attempt += 1) {
        const outcome = await financeImportMutationClient.queryBatchOutcome(jobId, request.controller.signal);
        if (!current('batch-outcome', request.sequence, request.controller)) return;
        if (outcome.status === 'succeeded' || outcome.status === 'failed' || outcome.status === 'cancelled') {
          setBatchOutcome({ kind: 'ready', data: outcome });
          setReload((value) => value + 1);
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
          <p className="page-subtitle">客戶收款、月嫂應付款、遮罩後的應付帳款與三步銀行流水匯入。</p>
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
          ['finance-import', '銀行流水匯入'],
        ] as const).map(([id, label]) => (
          <button
            key={id}
            data-surface-id={`finance.tab.${id}`}
            className={activeTab === id ? 'active' : ''}
            onClick={() => setActiveTab(id)}
          >
            {label}
          </button>
        ))}
      </nav>

      <div className="finance-toolbar">
        <span>{activeTab === 'finance-import' ? '上傳檔案 → 預覽 → 匯入完成' : '查詢結果以目前選取頁籤為準'}</span>
        {activeTab !== 'finance-import' && (
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
              <p>正常收款由銀行流水匯入自動核銷；不唯一或金額不符時由異常審核處理。</p>
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
            </>
          )}
        </section>
      )}

      {activeTab === 'staff-payables' && (
        <section className="finance-workspace">
          <div className="finance-section-heading">
            <div>
              <h2>月嫂應付款與付款事件</h2>
              <p>正常付款由銀行流水匯入自動核銷；不唯一或金額不符時由異常審核處理。</p>
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
            </>
          )}
        </section>
      )}

      {activeTab === 'accounts-payable' && (
        <section className="finance-workspace">
          <div className="finance-section-heading">
            <div>
              <h2>應付帳款預覽</h2>
              <p>畫面只顯示遮罩後資料，不會顯示完整銀行帳號與身分證。</p>
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
            <span className="finance-status-pill" style={{ marginLeft: 'auto' }}>
              🛡️ 去敏保護啟用
            </span>
          </div>

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
                <span className="finance-badge finance-badge-paid">敏感資料已遮罩</span>
              </div>

              <table className="finance-table">
                <thead>
                  <tr>
                    <th>日期</th>
                    <th>類型</th>
                    <th>受款人</th>
                    <th>銀行帳號（遮罩）</th>
                    <th>身分資料（遮罩）</th>
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
                  setFinanceWorkbook(event.target.files?.[0] ?? null);
                  setIngestion({ kind: 'idle' });
                  setBatchPreview({ kind: 'idle' });
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
                    <span className="finance-kpi-value orange">{batchPreview.data.counts.manual_review}</span>
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
                  可自動入帳 {batchPreview.data.counts.ready_dispatch}｜已存在 {batchPreview.data.counts.existing}｜待人工確認 {batchPreview.data.counts.manual_review}｜待業務配對 {batchPreview.data.counts.business_pending}｜阻擋 {batchPreview.data.counts.blocked}。
                  {batchPreview.data.apply_allowed && batchPreview.data.counts.ready_dispatch > 0
                    ? '可進入匯入確認。'
                    : batchPreview.data.apply_allowed
                      ? '目前沒有可自動入帳的筆數；請先從帳務異常處理完成配對。'
                    : `目前不可匯入：${financeImportBlockerMessage(batchPreview.data.blocking_codes)}`}
                </div>

                {batchPreview.data.apply_allowed && batchPreview.data.counts.ready_dispatch > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '12px' }}>
                    <label style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '0.84rem', fontWeight: 700 }}>
                      正式入帳原因
                      <input
                        className="finance-input"
                        value={applyReason}
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
                      disabled={!applyConfirmed || !applyReason.trim() || applyJob.kind === 'loading' || batchOutcome.kind === 'loading'}
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
                    onClick={() => void observeApplyOutcome(applyJob.data.job_id)}
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
                    : '未完成正式入帳；請重新預覽，或至帳務異常處理查看業務原因。'}
                </span>
                {batchOutcome.data.receipt && batchOutcome.data.receipt.pending_count > 0 && (
                  <a href="#anomalies" className="finance-btn-secondary">前往異常中心</a>
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

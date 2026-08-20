/**
 * File: FinancePage.tsx
 * Description: 以四組真實GET呈現Finance唯讀工作區，所有付款與匯出操作保持停用。
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import './FinancePage.css';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { adaptOrderSummaryPage } from '../adapters/orders/order_summary_adapter';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { adaptStaffDirectoryPage } from '../adapters/staff/staff_directory_adapter';
import { clientReceiptQueryClient } from '../api/client_finance/client_receipt_query_client';
import { adaptClientReceiptQuery } from '../adapters/finance/client_receipt_query_adapter';
import { staffPayablesQueryClient } from '../api/staff_payables/staff_payables_query_client';
import { adaptStaffPayablesQuery } from '../adapters/finance/staff_payables_query_adapter';
import { accountsPayableQueryClient } from '../api/accounts_payable/accounts_payable_query_client';
import { adaptAccountsPayablePreview } from '../adapters/finance/accounts_payable_query_adapter';
import { financeImportQueryClient } from '../api/finance_import/finance_import_query_client';
import { adaptFinanceImportBatch, adaptFinanceImportManifest } from '../adapters/finance/finance_import_query_adapter';

type FinanceTab = 'client-receipts' | 'staff-payables' | 'accounts-payable' | 'finance-import';
type LoadState<T> = { kind: 'idle' | 'loading' } | { kind: 'ready'; data: T } | { kind: 'empty' } | { kind: 'error'; message: string };

function currentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

function StateMessage<T>({ state, empty }: { state: LoadState<T>; empty: string }) {
  if (state.kind === 'loading') return <div className="finance-state" role="status">正在載入真實資料…</div>;
  if (state.kind === 'empty') return <div className="finance-state">{empty}</div>;
  if (state.kind === 'error') return <div className="finance-state error" role="alert">{state.message}</div>;
  return null;
}

export const FinancePage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<FinanceTab>('client-receipts');
  const [cases, setCases] = useState<{ id: string; label: string }[]>([]);
  const [selectedCase, setSelectedCase] = useState('');
  const [receipt, setReceipt] = useState<LoadState<ReturnType<typeof adaptClientReceiptQuery>>>({ kind: 'idle' });
  const [staff, setStaff] = useState<{ id: number; label: string }[]>([]);
  const [selectedStaff, setSelectedStaff] = useState<number | null>(null);
  const [payables, setPayables] = useState<LoadState<ReturnType<typeof adaptStaffPayablesQuery>>>({ kind: 'idle' });
  const [targetMonth, setTargetMonth] = useState(currentMonth);
  const [accountsPayable, setAccountsPayable] = useState<LoadState<ReturnType<typeof adaptAccountsPayablePreview>>>({ kind: 'idle' });
  const [batches, setBatches] = useState<LoadState<ReturnType<typeof adaptFinanceImportBatch>[]>>({ kind: 'idle' });
  const [selectedBatch, setSelectedBatch] = useState('');
  const [manifest, setManifest] = useState<LoadState<ReturnType<typeof adaptFinanceImportManifest>>>({ kind: 'idle' });
  const [reload, setReload] = useState(0);
  const controllers = useRef(new Map<string, AbortController>());
  const sequences = useRef(new Map<string, number>());

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
    if (activeTab !== 'client-receipts') return;
    const request = start('cases');
    void ordersQueryClient.getOrderSummaries({ page_size: 20 }, { signal: request.controller.signal })
      .then((page) => {
        if (!current('cases', request.sequence, request.controller)) return;
        const adapted = adaptOrderSummaryPage(page).items.map((item) => ({ id: item.id, label: `${item.id}｜${item.clientName}` }));
        setCases(adapted);
        setSelectedCase((value) => adapted.some((item) => item.id === value) ? value : adapted[0]?.id ?? '');
        if (adapted.length === 0) setReceipt({ kind: 'empty' });
      })
      .catch((error: unknown) => {
        if (current('cases', request.sequence, request.controller)) setReceipt({ kind: 'error', message: error instanceof Error ? error.message : '案件摘要載入失敗' });
      });
  }, [activeTab, reload]);

  useEffect(() => {
    if (activeTab !== 'client-receipts' || !selectedCase) return;
    const request = start('receipt');
    setReceipt({ kind: 'loading' });
    void clientReceiptQueryClient.query(selectedCase, { signal: request.controller.signal })
      .then((data) => { if (current('receipt', request.sequence, request.controller)) setReceipt({ kind: 'ready', data: adaptClientReceiptQuery(data) }); })
      .catch((error: unknown) => { if (current('receipt', request.sequence, request.controller)) setReceipt({ kind: 'error', message: error instanceof Error ? error.message : '客戶收款查詢失敗' }); });
  }, [activeTab, selectedCase, reload]);

  useEffect(() => {
    if (activeTab !== 'staff-payables') return;
    const request = start('staff');
    setPayables({ kind: 'loading' });
    void staffDirectoryClient.queryPage({ pageSize: 20 }, { signal: request.controller.signal })
      .then((page) => {
        if (!current('staff', request.sequence, request.controller)) return;
        const adapted = adaptStaffDirectoryPage(page).items.map((item) => ({ id: item.id, label: item.displayName }));
        setStaff(adapted);
        setSelectedStaff((value) => value !== null && adapted.some((item) => item.id === value) ? value : adapted[0]?.id ?? null);
        if (adapted.length === 0) setPayables({ kind: 'empty' });
      })
      .catch((error: unknown) => { if (current('staff', request.sequence, request.controller)) setPayables({ kind: 'error', message: error instanceof Error ? error.message : '服務人員摘要載入失敗' }); });
  }, [activeTab, reload]);

  useEffect(() => {
    if (activeTab !== 'staff-payables' || selectedStaff === null) return;
    const request = start('payables');
    setPayables({ kind: 'loading' });
    void staffPayablesQueryClient.query(selectedStaff, { signal: request.controller.signal })
      .then((data) => { if (current('payables', request.sequence, request.controller)) setPayables({ kind: 'ready', data: adaptStaffPayablesQuery(data) }); })
      .catch((error: unknown) => { if (current('payables', request.sequence, request.controller)) setPayables({ kind: 'error', message: error instanceof Error ? error.message : '月嫂應付款查詢失敗' }); });
  }, [activeTab, selectedStaff, reload]);

  useEffect(() => {
    if (activeTab !== 'accounts-payable') return;
    const request = start('accounts-payable');
    setAccountsPayable({ kind: 'loading' });
    void accountsPayableQueryClient.query(targetMonth, { signal: request.controller.signal })
      .then((data) => { if (current('accounts-payable', request.sequence, request.controller)) setAccountsPayable(data.rows.length ? { kind: 'ready', data: adaptAccountsPayablePreview(data) } : { kind: 'empty' }); })
      .catch((error: unknown) => { if (current('accounts-payable', request.sequence, request.controller)) setAccountsPayable({ kind: 'error', message: error instanceof Error ? error.message : '應付帳款查詢失敗' }); });
  }, [activeTab, targetMonth, reload]);

  useEffect(() => {
    if (activeTab !== 'finance-import') return;
    const request = start('batches');
    setBatches({ kind: 'loading' });
    void financeImportQueryClient.listBatches({ limit: 50 }, { signal: request.controller.signal })
      .then((items) => {
        if (!current('batches', request.sequence, request.controller)) return;
        const adapted = items.map(adaptFinanceImportBatch);
        setBatches(adapted.length ? { kind: 'ready', data: adapted } : { kind: 'empty' });
        setSelectedBatch((value) => adapted.some((item) => item.identity === value) ? value : adapted.find((item) => item.identity)?.identity ?? '');
      })
      .catch((error: unknown) => { if (current('batches', request.sequence, request.controller)) setBatches({ kind: 'error', message: error instanceof Error ? error.message : 'Finance Import批次載入失敗' }); });
  }, [activeTab, reload]);

  useEffect(() => {
    if (activeTab !== 'finance-import' || !selectedBatch) return;
    const request = start('manifest');
    setManifest({ kind: 'loading' });
    void financeImportQueryClient.getManifest(selectedBatch, { signal: request.controller.signal })
      .then((data) => { if (current('manifest', request.sequence, request.controller)) setManifest({ kind: 'ready', data: adaptFinanceImportManifest(data) }); })
      .catch((error: unknown) => { if (current('manifest', request.sequence, request.controller)) setManifest({ kind: 'error', message: error instanceof Error ? error.message : 'Manifest載入失敗' }); });
  }, [activeTab, selectedBatch, reload]);

  const disabledActions = useMemo(() => [
    ['finance.refund.approve', '核准退款'],
    ['finance.subsidy.advance', '補助代墊'],
    ['finance.accounts-payable.export-xlsx', '匯出XLSX'],
  ] as const, []);

  return <div data-surface-id="finance.page">
    <header className="page-header-banner finance-page-header"><div><h1 className="page-title">💰 財務查詢與對帳工作台</h1><p className="page-subtitle">客戶收款、月嫂應付款、masked應付帳款與Finance Import真實唯讀資料。</p></div><div className="finance-header-actions">{disabledActions.map(([id, label]) => <button key={id} data-control-id={id} disabled>{label}（未開放）</button>)}</div></header>
    <nav className="finance-tab-bar" aria-label="財務查詢工作區">
      {([['client-receipts','客戶收款'],['staff-payables','月嫂應付款'],['accounts-payable','應付帳款'],['finance-import','Finance Import']] as const).map(([id,label]) => <button key={id} data-surface-id={`finance.tab.${id}`} className={activeTab===id?'active':''} onClick={() => setActiveTab(id)}>{label}</button>)}
    </nav>
    <div className="finance-toolbar"><span>Active tab only｜0 polling｜GET only</span><button onClick={() => setReload((value) => value + 1)}>重新載入</button></div>

    {activeTab === 'client-receipts' && <section className="finance-workspace"><div className="finance-section-heading"><div><h2>客戶收款根事實</h2><p>bank facts與obligations分開顯示；不由前端推導settled。</p></div><label>案件<select value={selectedCase} onChange={(event) => setSelectedCase(event.target.value)}>{cases.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label></div><StateMessage state={receipt} empty="目前沒有可顯示的收款根事實。" />{receipt.kind==='ready' && <><div className="finance-meta">案件 {receipt.data.caseNo}｜Account version {receipt.data.accountVersion}</div><table className="finance-table"><thead><tr><th>義務</th><th>階段</th><th>應收</th><th>到期日</th><th>狀態</th><th>操作</th></tr></thead><tbody>{receipt.data.obligations.map((item) => <tr key={item.id}><td>{item.id}</td><td>{item.stage}</td><td>{item.amountDue}</td><td>{item.dueDate}</td><td>{item.settlementStatus}</td><td><button data-control-id="finance.client-receipt.settle" disabled>核銷（未開放）</button></td></tr>)}</tbody></table><h3>已載入銀行根事實</h3><table className="finance-table"><tbody>{receipt.data.bankFacts.map((item) => <tr key={item.id}><td>#{item.id}</td><td>{item.transactionDate}</td><td>{item.amount}</td><td>{item.fingerprint}</td></tr>)}</tbody></table></>}</section>}

    {activeTab === 'staff-payables' && <section className="finance-workspace"><div className="finance-section-heading"><div><h2>月嫂應付款與付款事件</h2><p>payout_status只顯示server值；balance不推導paid。</p></div><label>服務人員<select value={selectedStaff ?? ''} onChange={(event) => setSelectedStaff(Number(event.target.value))}>{staff.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label><button data-control-id="finance.staff-payable.adjustment" disabled>新增調整（未開放）</button></div><StateMessage state={payables} empty="目前沒有可顯示的應付款。" />{payables.kind==='ready' && <><div className="finance-meta">Staff #{payables.data.staffId}｜Version {payables.data.version}</div><table className="finance-table"><thead><tr><th>義務</th><th>案件</th><th>應付</th><th>已付</th><th>餘額</th><th>Server status</th><th>操作</th></tr></thead><tbody>{payables.data.obligations.map((item) => <tr key={item.id}><td>{item.id}</td><td>{item.caseNo}</td><td>{item.amountDue}</td><td>{item.netPaid}</td><td>{item.balance}</td><td>{item.payoutStatus}</td><td><button data-control-id="finance.staff-payable.mark-paid" disabled>標記已付（未開放）</button></td></tr>)}</tbody></table><h3>付款事件</h3><table className="finance-table"><tbody>{payables.data.events.map((item) => <tr key={item.id}><td>#{item.id}</td><td>{item.type}</td><td>{item.amount}</td><td>{item.occurredOn}</td><td>{item.reference}</td></tr>)}</tbody></table></>}</section>}

    {activeTab === 'accounts-payable' && <section className="finance-workspace"><div className="finance-section-heading"><div><h2>Masked Accounts Payable Preview</h2><p>完整銀行帳號與身分證不進DOM；XLSX不在本page-slice。</p></div><label>月份<input type="month" value={targetMonth} onChange={(event) => setTargetMonth(event.target.value)} /></label><button data-control-id="finance.accounts-payable.export-xlsx" disabled>匯出XLSX（未開放）</button></div><StateMessage state={accountsPayable} empty="本月沒有應付帳款。" />{accountsPayable.kind==='ready' && <><div className="finance-meta">付款日 {accountsPayable.data.targetPaymentDate}｜{accountsPayable.data.rowCount}筆｜{accountsPayable.data.totalAmount}</div><table className="finance-table"><thead><tr><th>日期</th><th>類型</th><th>受款人</th><th>Masked銀行帳號</th><th>Masked身分</th><th>金額</th><th>案件</th></tr></thead><tbody>{accountsPayable.data.rows.map((row) => <tr key={row.id}><td>{row.paymentDate}</td><td>{row.paymentType}</td><td>{row.recipientName}</td><td>{row.bankDisplay}</td><td>{row.identityDisplay}</td><td>{row.amount}</td><td>{row.caseNumbers.join('、') || '—'}</td></tr>)}</tbody></table></>}</section>}

    {activeTab === 'finance-import' && <section className="finance-workspace"><div className="finance-section-heading"><div><h2>Finance Import批次</h2><p>只顯示server labels；不把status或available_actions映射成Apply成功。</p></div><button data-control-id="finance.finance-import.upload" disabled>上傳（未開放）</button><button data-control-id="finance.finance-import.preview" disabled>Preview（未開放）</button><button data-control-id="finance.finance-import.apply" disabled>Apply（未開放）</button><button data-control-id="finance.finance-import.reprocess" disabled>Reprocess（未開放）</button></div><StateMessage state={batches} empty="目前沒有Finance Import批次。" />{batches.kind==='ready' && <div className="finance-split"><div><label>已載入批次<select value={selectedBatch} onChange={(event) => setSelectedBatch(event.target.value)}>{batches.data.filter((item) => item.identity).map((item) => <option key={item.id} value={item.identity ?? ''}>{item.identity}｜{item.status}</option>)}</select></label><table className="finance-table"><tbody>{batches.data.map((item) => <tr key={item.id}><td>#{item.id}</td><td>{item.identity ?? '無public identity'}</td><td>{item.formatId}</td><td>{item.rowCount}</td><td>{item.status}</td></tr>)}</tbody></table></div><aside><StateMessage state={manifest} empty="請選擇具identity的批次。" />{manifest.kind==='ready' && <dl className="finance-manifest"><dt>Batch</dt><dd>{manifest.data.identity}</dd><dt>Sheet</dt><dd>{manifest.data.sheetName}</dd><dt>Status</dt><dd>{manifest.data.status}</dd><dt>Version</dt><dd>{manifest.data.version}</dd><dt>Digest</dt><dd>{manifest.data.digest}</dd><dt>Source/Canonical</dt><dd>{manifest.data.sourceRows} / {manifest.data.canonicalRows}</dd><dt>Review/Occurrence</dt><dd>{manifest.data.reviewCount} / {manifest.data.occurrenceCount}</dd></dl>}</aside></div>}</section>}
  </div>;
};

export default FinancePage;

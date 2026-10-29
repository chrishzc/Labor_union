import { useEffect, useRef, useState } from 'react';
import { financeAccountingClient, type AccountingItem, type AccountingWarning, type CaseAccounting } from '../api/finance_import/finance_accounting_client';
import { financeMoney } from './FinanceReceiptsWorkspace';
import './FinanceCaseAccounting.css';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { useUnsavedChanges } from './UnsavedChanges';

const labels = { over_received: '客戶超收', over_paid: '付款超付', under_paid: '付款差額超過 100 元' };
const money = (value: number | null) => value === null ? '尚無款項' : financeMoney(value);
function difference(item: AccountingItem) {
  const value = item.expected_ntd - item.actual_ntd;
  return value === 0 ? '金額相符' : `${value > 0 ? (item.direction === 'payable' ? '少付' : '少收') : (item.direction === 'payable' ? '超付' : '超收')} ${financeMoney(Math.abs(value))}`;
}

export function AccountingWarningList({ data, onChange }: { data: CaseAccounting; onChange: (data: CaseAccounting) => void }) {
  const [showDismissed, setShowDismissed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useUnsavedChanges('帳務警示解除', [], { busy });
  async function dismiss(row: AccountingWarning) {
    setBusy(true); setError('');
    try { onChange(await financeAccountingClient.dismiss(data.case_no, row)); }
    catch { setError('解除失敗或款項已變更，請重新整理後確認。'); }
    finally { setBusy(false); }
  }
  return <section className="case-accounting-card" aria-label="共用帳務警示">
    <div className="finance-section-heading"><h3>帳務警示 · 待檢查 {data.pending_warning_count}</h3><label><input type="checkbox" checked={showDismissed} onChange={event => setShowDismissed(event.target.checked)} /> 顯示已解除</label></div>
    {error && <p role="alert">{error}</p>}
    {data.warnings.filter(row => showDismissed || !row.dismissed).map(row => <div className="case-accounting-warning" key={`${row.item_identity}:${row.kind}:${row.difference_ntd}`}>
      <div><strong>{labels[row.kind]}</strong><p>{[...data.client_items, ...data.staff_items].find(item => item.identity === row.item_identity)?.label} · {[...data.client_items, ...data.staff_items].find(item => item.identity === row.item_identity)?.party} · 應收／應付 {money(row.expected_ntd)}，實收／實付 {money(row.actual_ntd)}；差額 {money(row.difference_ntd)}</p></div>
      {row.dismissed ? <span>已解除 · {row.dismissed_by} · {row.dismissed_at}</span> : <button className="finance-btn-secondary" disabled={busy} type="button" onClick={() => void dismiss(row)}>解除警示</button>}
    </div>)}
    {!data.warnings.some(row => showDismissed || !row.dismissed) && <p className="finance-state">目前沒有{showDismissed ? '' : '待檢查'}帳務警示。</p>}
  </section>;
}

export function FinanceCaseAccounting({ initialCase = '' }: { initialCase?: string }) {
  const [input, setInput] = useState(initialCase);
  const [selected, setSelected] = useState(initialCase);
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<{ caseNo: string; data?: CaseAccounting; error?: string }>({ caseNo: initialCase });
  const [detailItem, setDetailItem] = useState('');
  const [matches, setMatches] = useState<{ case_no: string; client_name: string }[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [listQuery, setListQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState('');
  const searchRequest = useRef<AbortController | null>(null);
  useEffect(() => () => searchRequest.current?.abort(), []);
  function openCase(caseNo: string) { searchRequest.current?.abort(); setSearching(false); setSearchError(''); setInput(caseNo); setState({ caseNo }); setSelected(caseNo); setDetailItem(''); setRevision(value => value + 1); }
  async function loadCases(value: string, after?: string) {
    searchRequest.current?.abort(); setSearchError('');
    const controller = new AbortController(); searchRequest.current = controller;
    setSearching(true);
    if (!after) { setMatches([]); setNextCursor(null); setListQuery(value); }
    try {
      const page = await ordersQueryClient.getOrderSummaries({ query_text: value, page_size: 50, ...(after ? { after_case_no: after } : {}) }, { signal: controller.signal });
      if (!controller.signal.aborted) {
        setMatches(previous => after ? [...new Map([...previous, ...page.items].map(row => [row.case_no, row])).values()] : page.items);
        setNextCursor(page.next_cursor);
      }
    }
    catch { if (!controller.signal.aborted) setSearchError('案件搜尋失敗，請稍後再試。'); }
    finally { if (!controller.signal.aborted) setSearching(false); }
  }
  useEffect(() => { void loadCases(''); }, []);
  async function search() {
    const value = input.trim();
    if (/^(?:[0-9]{9}|A[0-9]{6})$/.test(value)) { openCase(value); return; }
    setSelected(''); setDetailItem('');
    await loadCases(value);
  }
  useEffect(() => {
    const controller = new AbortController();
    if (selected) {
      void financeAccountingClient.query(selected, controller.signal).then(data => { if (!controller.signal.aborted) setState({ caseNo: selected, data }); }).catch(() => { if (!controller.signal.aborted) setState({ caseNo: selected, error: '找不到案件或帳務資料暫時無法取得，請確認案件編號後重試。' }); });
    }
    return () => controller.abort();
  }, [selected, revision]);
  const data = state.caseNo === selected && !state.error ? state.data : undefined;
  const rows = (items: AccountingItem[]) => <div className="finance-table-container"><table className="finance-table"><thead><tr><th>項目／對象</th><th>到期日</th><th>應收／應付</th><th>實收／實付</th><th>差額</th><th>檢查結果</th><th>明細</th></tr></thead><tbody>{items.map(item => <tr key={item.identity}><td><strong>{item.label}</strong><div>{item.party}</div></td><td>{item.due_date ?? '未設定'}</td><td>{money(item.expected_ntd)}</td><td>{money(item.actual_ntd)}</td><td>{money(item.expected_ntd - item.actual_ntd)}</td><td>{difference(item)}{item.direction === 'payable' && item.has_payment && item.expected_ntd > item.actual_ntd && item.expected_ntd - item.actual_ntd <= 100 && <div>100 元內 · 手續費參考，請人工檢查</div>}</td><td><button type="button" className="finance-btn-secondary" onClick={() => setDetailItem(item.identity)}>明細</button></td></tr>)}</tbody></table>{!items.length && <p className="finance-state">本案尚無此類正式款項。</p>}</div>;
  return <section aria-label="案件帳務" className="case-accounting">
    <h2>案件帳務</h2><p>集中查看單一案件的應收、應付與實際收付款差額。</p>
    <form className="case-accounting-card case-accounting-search" onSubmit={event => { event.preventDefault(); void search(); }}>
      <div className="case-accounting-field"><label htmlFor="accounting-case-select">選擇案件</label><select id="accounting-case-select" value={selected} onChange={event => { if (event.target.value) openCase(event.target.value); }}>
        <option value="">請選擇案件</option>
        {selected && !matches.some(row => row.case_no === selected) && <option value={selected}>{selected}</option>}
        {matches.map(row => <option key={row.case_no} value={row.case_no}>{row.case_no}｜{row.client_name}</option>)}
      </select></div>
      <div className="case-accounting-field"><label htmlFor="accounting-case">案件編號</label><input id="accounting-case" placeholder="輸入完整／部分案件編號或客戶姓名" value={input} maxLength={50} onChange={event => setInput(event.target.value)} /></div><button className="finance-btn-primary">查看案件</button>
      {nextCursor && <button type="button" className="finance-btn-secondary" disabled={searching} onClick={() => void loadCases(listQuery, nextCursor)}>載入更多案件</button>}
    </form>
    {searching && <p role="status">正在搜尋案件…</p>}{searchError && <p role="alert">{searchError}</p>}
    {!searching && !searchError && <p className="finance-state">{matches.length ? '可直接下拉選擇案件，或輸入編號／姓名搜尋；同名客戶請核對案件編號。' : '沒有符合的案件，可輸入完整編號直接查詢，或重新搜尋。'}{nextCursor && ' 尚有更多案件，可繼續載入或縮小搜尋。'}</p>}
    {!selected ? <p className="finance-state">請選擇或搜尋案件。</p> : state.caseNo === selected && state.error ? <p role="alert">{state.error}</p> : !data ? <p role="status">正在載入案件帳務…</p> : <>
      <h3>{data.client_name} · 案件 {data.case_no}</h3>
      <div className="case-accounting-summary">
        <article><span>案件應收</span><strong>{money(data.receivable_ntd)}</strong><small>客戶收款 · 實收 {money(data.received_ntd)}</small></article>
        <article><span>案件應付</span><strong>{money(data.payable_ntd)}</strong><small>客戶退款＋月嫂付款 · 實付 {money(data.paid_ntd)}</small></article>
        <article><span>應付與實付差額</span><strong>{money(data.payable_ntd === null || data.paid_ntd === null ? null : data.payable_ntd - data.paid_ntd)}</strong><small>差額僅供人工檢查</small></article>
        <article><span>帳務警示</span><strong>{data.pending_warning_count}</strong><small>待檢查</small></article>
      </div>
      <section className="case-accounting-card"><h3>案件應收 · 客戶收款</h3>{rows(data.client_items.filter(item => item.direction === 'receivable'))}</section>
      <section className="case-accounting-card"><h3>案件應付 · 客戶退款＋月嫂付款</h3><p>差額＝應付－實付，僅作手續費參考；少付超過 100 元或超付時顯示帳務警示。</p>{rows([...data.client_items.filter(item => item.direction === 'payable'), ...data.staff_items.filter(item => item.summary_included !== false)])}
        {data.staff_items.filter(item => item.summary_included === false).map(item => <div key={item.identity} className="finance-scope-note"><strong>{item.label} · {item.party}</strong><p>來源應付 {money(item.expected_ntd)}，實付 {money(item.actual_ntd)}；{difference(item)}。此付款來源不重複計入案件應付；跨案部分維持各案的正式分配。</p>{(item.unallocated_surplus_ntd ?? 0) > 0 && <p>本案實付另含超付款 {money(item.unallocated_surplus_ntd ?? 0)}。</p>}</div>)}
      </section>
      {detailItem && <section className="case-accounting-card" aria-label="收付款明細"><div className="finance-section-heading"><h3>收付款明細</h3><button type="button" onClick={() => setDetailItem('')}>關閉明細</button></div><div className="finance-table-container"><table className="finance-table"><thead><tr><th>日期</th><th>銀行</th><th>種類</th><th>本項分配金額</th></tr></thead><tbody>{data.transactions.filter(row => row.item_identity === detailItem).map(row => <tr key={row.identity}><td>{row.occurred_on}</td><td>{{ sinopac: '永豐', taishin: '台新', legacy: '歷史格式' }[row.bank ?? ''] ?? '非銀行來源'}</td><td>{{ receipt: '收款', refund: '退款', payout: '付款', return: '退匯', reversal: '沖正' }[row.kind] ?? row.kind}</td><td>{money(row.amount_ntd)}</td></tr>)}</tbody></table>{!data.transactions.some(row => row.item_identity === detailItem) && <p className="finance-state">本項尚無銀行收付款分配紀錄。</p>}</div></section>}
      <AccountingWarningList key={data.case_no} data={data} onChange={value => setState(previous => previous.caseNo === value.case_no ? { caseNo: value.case_no, data: value } : previous)} />
    </>}
  </section>;
}

export function FinanceAccountingWarnings({ onCase }: { onCase: (caseNo: string) => void }) {
  const [data, setData] = useState<CaseAccounting[] | null>(null);
  const [error, setError] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => { const controller = new AbortController(); setData(null); setError(false); void financeAccountingClient.warnings(controller.signal).then(value => { if (!controller.signal.aborted) setData(value); }).catch(() => { if (!controller.signal.aborted) setError(true); }); return () => controller.abort(); }, [revision]);
  return <section><h2>共用帳務警示</h2>{error ? <p role="alert">帳務警示暫時無法取得，請重新整理。</p> : !data ? <p role="status">正在載入帳務警示…</p> : !data.length ? <p className="finance-state">目前沒有帳務警示。</p> : data.map(row => <div key={row.case_no}><button className="finance-btn-secondary" type="button" onClick={() => onCase(row.case_no)}>{row.case_no} · {row.client_name} · 查看案件</button><AccountingWarningList data={row} onChange={() => setRevision(value => value + 1)} /></div>)}</section>;
}

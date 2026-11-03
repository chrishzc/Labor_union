import { Fragment, useEffect, useRef, useState } from 'react';
import { financeAccountingClient, type AccountingItem, type AccountingWarning, type CaseAccounting } from '../api/finance_import/finance_accounting_client';
import { financeMoney } from './FinanceReceiptsWorkspace';
import './FinanceCaseAccounting.css';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { HistoricalAccountingMarkerPanel } from './HistoricalAccountingMarkerPanel';
import { ClientReceiptReconciliationPanel } from './ClientReceiptReconciliationPanel';
import { AccountingDifferencePanel } from './AccountingDifferencePanel';
import { useUnsavedChanges, useUnsavedNavigation } from './UnsavedChanges';
import { ApiHttpError } from '../api/shared/typed_errors';

const labels = { over_received: '客戶超收', over_paid: '付款超付', under_paid: '付款差額超過 100 元' };
const money = (value: number | null) => value === null ? '尚無款項' : financeMoney(value);
function difference(item: AccountingItem) {
  if (!item.has_payment) return item.direction === 'payable' ? '待付款' : '待收款';
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

export function FinanceCaseAccounting({ initialCase = '', onBank, onSubsidy, onLegacy }: { initialCase?: string; onBank?: () => void; onSubsidy?: (caseNo: string) => void; onLegacy?: (caseNo: string) => void }) {
  const {requestLeave} = useUnsavedNavigation();
  const [input, setInput] = useState(initialCase);
  const [selected, setSelected] = useState(initialCase);
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<{ caseNo: string; data?: CaseAccounting; error?: string }>({ caseNo: initialCase });
  const [detailItem, setDetailItem] = useState('');
  const [view, setView] = useState<'detail'|'historical'>('detail');
  const [matches, setMatches] = useState<{ case_no: string; client_name: string }[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [listQuery, setListQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState('');
  const searchRequest = useRef<AbortController | null>(null);
  useEffect(() => () => searchRequest.current?.abort(), []);
  function openCase(caseNo: string) { requestLeave(()=>{searchRequest.current?.abort(); setSearching(false); setSearchError(''); setInput(caseNo); setState({ caseNo }); setSelected(caseNo); setView('detail'); setDetailItem(''); setRevision(value => value + 1);}); }
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
  useEffect(() => { let active=true; queueMicrotask(()=>{if(active)void loadCases('');}); return()=>{active=false;}; }, []);
  async function search() {
    const value = input.trim();
    if (/^(?:[0-9]{9}|A[0-9]{6})$/.test(value)) { openCase(value); return; }
    requestLeave(()=>{setSelected(''); setDetailItem(''); void loadCases(value);});
  }
  useEffect(() => {
    const controller = new AbortController();
    if (selected) {
      queueMicrotask(()=>{if(controller.signal.aborted)return;void financeAccountingClient.query(selected, controller.signal).then(data => { if (!controller.signal.aborted) setState({ caseNo: selected, data }); }).catch(error => { if (!controller.signal.aborted) setState({ caseNo: selected, error: error instanceof ApiHttpError && error.status === 404 ? '找不到此案件，請確認案件編號。' : error instanceof ApiHttpError && error.status === 401 ? '登入已失效，請重新登入後查詢。' : error instanceof ApiHttpError && error.status === 403 ? '目前沒有查閱帳務的權限。' : '帳務資料暫時無法取得，請稍後重新查詢。' }); });});
    }
    return () => controller.abort();
  }, [selected, revision]);
  const data = state.caseNo === selected && !state.error ? state.data : undefined;
  const allItems = data ? [...data.client_items, ...data.staff_items].filter(item => item.summary_included !== false) : [];
  const kindLabels: Record<string,string> = { receipt:'收款', refund:'退款', payout:'付款', subsidy_return:'補助退款', subsidy_advance:'工會代墊', subsidy_return_reversal:'補助退款沖正', return:'既有返款紀錄', reversal:'沖正' };
  const unified = () => <div className="finance-table-container"><table className="finance-table case-accounting-unified"><thead><tr><th>款項／對象</th><th>方向</th><th>到期日</th><th>應收／應付</th><th>已核銷收／付</th><th>其他處理</th><th>待收／待付</th><th>目前狀態</th><th>明細</th></tr></thead><tbody>{allItems.map(item => <Fragment key={item.identity}><tr data-obligation-id={item.identity}><td><strong>{item.label}</strong><small>{item.party}</small></td><td>{item.direction==='receivable'?'收':'付'}</td><td>{item.due_date??'待確認'}</td><td>{money(item.expected_ntd)}</td><td>{money(item.actual_ntd)}</td><td>{money(item.noncash_ntd??0)}</td><td>{money(item.remaining_ntd??null)}</td><td>{data?.historical_marker?'案件已人工核銷':item.settled?'已結清':difference(item)}</td><td><button type="button" className="finance-btn-secondary" aria-expanded={detailItem===item.identity} onClick={()=>setDetailItem(detailItem===item.identity?'':item.identity)}>{detailItem===item.identity?'收合':'展開'}明細</button></td></tr>{detailItem===item.identity&&<tr><td colSpan={9}><section className="case-accounting-allocation" aria-label="收付款明細"><h4>{item.label} · 收付款分配紀錄</h4><div className="finance-table-container"><table className="finance-table"><thead><tr><th>日期</th><th>銀行</th><th>種類</th><th>本項分配金額</th></tr></thead><tbody>{data?.transactions.filter(row=>row.item_identity===item.identity).map(row=><tr key={row.identity}><td>{row.occurred_on}</td><td>{{sinopac:'永豐',taishin:'台新',legacy:'歷史格式'}[row.bank??'']??'非銀行來源'}</td><td>{kindLabels[row.kind]??row.kind}</td><td>{money(row.amount_ntd)}</td></tr>)}</tbody></table></div>{!data?.transactions.some(row=>row.item_identity===item.identity)&&<p>本項尚無銀行收付款分配紀錄。</p>}</section></td></tr>}</Fragment>)}</tbody></table></div>;
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
      {data.historical_marker&&<p className="finance-scope-note">案件帳務已人工核銷；原差額保留，整案金額不計入統計，不表示訂單或服務已完成。</p>}
      <div className="case-accounting-summary case-accounting-totals">
        <article><span>{data.historical_marker?'原始未收餘額':'目前待收'}</span><strong>{money(data.remaining_in_ntd??null)}</strong><small>應收 {money(data.receivable_ntd)} · 已核銷收款 {money(data.received_ntd)}</small></article>
        <article><span>{data.historical_marker?'原始未付餘額':'目前待付'}</span><strong>{money(data.remaining_out_ntd??null)}</strong><small>應付 {money(data.payable_ntd)} · 已核銷付款 {money(data.paid_ntd)}</small></article>
      </div>
      <div className="finance-tab-bar" role="tablist" aria-label="案件帳務功能">{(['detail','historical'] as const).map((id,index)=><button key={id} type="button" role="tab" id={'accounting-view-'+id} aria-controls="case-accounting-output" aria-selected={view===id} tabIndex={view===id?0:-1} onClick={()=>requestLeave(()=>setView(id))} onKeyDown={event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const next=event.key==='Home'?'detail':event.key==='End'?'historical':index?'detail':'historical';requestLeave(()=>{setView(next);document.getElementById('accounting-view-'+next)?.focus();});}}>{id==='detail'?'帳務明細':'歷史人工核銷'}</button>)}</div>
      <div id="case-accounting-output" role="tabpanel" aria-labelledby={'accounting-view-'+view}>{view==='historical'?<HistoricalAccountingMarkerPanel key={data.case_no} data={data} onMarked={marker=>setState(previous=>previous.data?{...previous,data:{...previous.data,historical_marker:marker}}:previous)}/>:<>
        <section className="case-accounting-card"><h3>本案帳務明細</h3><p>全期款項，不受收付款頁的月份篩選影響；應收、應付與實際收付合併查閱。</p>{unified()}
          {data.staff_items.filter(item=>item.summary_included===false).map(item=><p className="finance-scope-note" key={item.identity}>{item.label} · {item.party} · 來源實付 {money(item.actual_ntd)}；跨案來源不重複計入本案應付。</p>)}
        </section>
        {!data.historical_marker&&<ClientReceiptReconciliationPanel key={data.case_no} caseNo={data.case_no} refreshVersion={revision} onChanged={()=>setRevision(value=>value+1)}/>}
        {!data.historical_marker&&<AccountingDifferencePanel key={'difference:'+data.case_no} caseNo={data.case_no} refreshVersion={revision} onChanged={()=>setRevision(value=>value+1)}/>}
        <section className="case-accounting-card"><h3>本案關聯銀行收付款</h3><p>銀行各筆來源獨立保留；同一銀行款只列一次，跨案件款項的全額不當作本案分配金額。</p><div className="finance-table-container"><table className="finance-table"><thead><tr><th>日期</th><th>來源</th><th>關聯案件</th><th>實際入款</th><th>實際出款</th></tr></thead><tbody>{data.bank_facts?.map(bank=><tr key={bank.identity}><td>{bank.occurred_on}</td><td>{bank.identity}</td><td>{bank.cases.join('、')}</td><td>{bank.direction==='in'?money(bank.amount_ntd):'—'}</td><td>{bank.direction==='out'?money(bank.amount_ntd):'—'}</td></tr>)}</tbody></table>{!data.bank_facts?.length&&<p>尚無已正式核銷的銀行來源。</p>}</div>{onBank&&<button type="button" className="finance-btn-secondary" onClick={onBank}>前往銀行對帳核對收付款</button>}</section>
        {onSubsidy&&<section className="case-accounting-card"><h3>政府補助與工會代墊</h3><p>查閱本案補助、退款及整期歸屬；政府整筆入款不拆成本案實收。</p><button type="button" className="finance-btn-secondary" onClick={()=>onSubsidy(data.case_no)}>查看補助與整期帳務</button></section>}
      </>}</div>
      <details><summary>金額警示與既有檢查紀錄</summary><AccountingWarningList key={data.case_no} data={data} onChange={value => setState(previous => previous.caseNo === value.case_no ? { caseNo: value.case_no, data: value } : previous)} /></details>
      {onLegacy && <details><summary>歷史收付款與既有查證工具</summary><p>查閱原有款項歷程、歷史收付款確認及歷史案件完成工具。</p><button type="button" className="finance-btn-secondary" onClick={() => onLegacy(data.case_no)}>開啟本案既有帳務工具</button></details>}
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

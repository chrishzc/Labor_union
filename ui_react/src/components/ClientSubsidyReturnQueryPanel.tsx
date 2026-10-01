/** Case-based subsidy refund presentation, without creating finance facts. */
import { useEffect, useState } from 'react';
import { clientSubsidyReturnQueryClient, type ClientSubsidyReturnQuery } from '../api/client_finance/client_subsidy_return_query_client';
import { ApiHttpError } from '../api/shared/typed_errors';

type QueryState = { kind: 'loading' } | { kind: 'ready'; data: ClientSubsidyReturnQuery } | { kind: 'error'; message: string };
type Props = { targetMonth: string; onMonthChange: (month: string) => void; onOpenPayables: () => void; initialCaseNo?: string };
const formatMoney = (amount: number) => `NT$ ${amount.toLocaleString('zh-TW')}`;
function errorMessage(error: unknown): string {
  if (error instanceof ApiHttpError) {
    if (error.status === 401) return '請先登入後再查詢補助退款。';
    if (error.status === 403) return '目前帳號沒有查詢這項客戶帳務的權限。';
  }
  return '補助退款資料暫時無法取得，請重新查詢。';
}

export function ClientSubsidyReturnQueryPanel({ targetMonth, onMonthChange, onOpenPayables, initialCaseNo = '' }: Props) {
  const [result, setResult] = useState<QueryState>({ kind: 'loading' });
  const [reload, setReload] = useState(0);
  const [draft, setDraft] = useState(initialCaseNo);
  const [search, setSearch] = useState('');
  const [caseNo, setCaseNo] = useState(initialCaseNo);
  const [monthOnly, setMonthOnly] = useState(false);
  const [afterCaseNo, setAfterCaseNo] = useState<string | undefined>();
  const selectedMonth = monthOnly ? targetMonth : undefined;

  useEffect(() => {
    const controller = new AbortController();
    setResult({ kind: 'loading' });
    void clientSubsidyReturnQueryClient.query({ search: search || undefined, caseNo: caseNo || undefined,
      targetMonth: selectedMonth, afterCaseNo, signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setResult({ kind: 'ready', data }); })
      .catch(error => { if (!controller.signal.aborted) setResult({ kind: 'error', message: errorMessage(error) }); });
    return () => controller.abort();
  }, [search, caseNo, selectedMonth, afterCaseNo, reload]);

  const rows = result.kind === 'ready' ? result.data.rows : [];
  const query = () => { setSearch(draft.trim()); setCaseNo(''); setAfterCaseNo(undefined); setReload(value => value + 1); };
  const reset = () => { setDraft(''); setSearch(''); setCaseNo(''); setMonthOnly(false); setAfterCaseNo(undefined); setReload(value => value + 1); };

  return <section className="finance-workspace subsidy-refund-panel" aria-labelledby="subsidy-refund-heading">
    <div className="finance-section-heading">
      <div><h2 id="subsidy-refund-heading">客戶補助退款</h2><p>查看各案件應退補助金額與應退款日期，補助款一次全額退清。</p></div>
      <button type="button" className="finance-btn-primary" onClick={onOpenPayables}>前往應付帳款</button>
    </div>
    <p className="subsidy-refund-note">列出有補助資格、需由客戶先付款的案件；取消案件、全補助且客戶不需付款的案件與已完成補助退款的案件不列入。</p>
    <form className="subsidy-refund-case-form" onSubmit={event => { event.preventDefault(); query(); }}>
      <label>客戶姓名或案件編號<input className="finance-input" value={draft} onChange={event => setDraft(event.target.value)} maxLength={100} placeholder="輸入姓名或案件編號" /></label>
      <button className="finance-btn-primary" type="submit">查詢</button>
      <button type="button" className="finance-reload-btn" onClick={reset}>查看全部應退案件</button>
    </form>
    <div className="subsidy-refund-period">
      <label className="subsidy-refund-month-toggle"><input type="checkbox" checked={monthOnly} onChange={event => { setMonthOnly(event.target.checked); setAfterCaseNo(undefined); }} />依應退款月份篩選</label>
      {monthOnly && <label>應退款月份<input className="finance-input" type="month" value={targetMonth} onChange={event => { if (event.target.value) { onMonthChange(event.target.value); setAfterCaseNo(undefined); } }} /></label>}
      <button type="button" className="finance-reload-btn" disabled={result.kind === 'loading'} onClick={() => setReload(value => value + 1)}>重新查詢</button>
    </div>
    {result.kind === 'loading' && <div className="finance-state" role="status">正在查詢補助退款案件…</div>}
    {result.kind === 'error' && <div className="finance-state error" role="alert">{result.message}</div>}
    {result.kind === 'ready' && <>
      <div className="finance-kpi-grid" role="group" aria-label="補助退款案件摘要">
        <div className="finance-kpi-item"><span className="finance-kpi-label">本頁應退補助金額（含預估）</span><strong className="finance-kpi-value">{formatMoney(rows.reduce((total, row) => total + (row.amount_ntd ?? 0), 0))}</strong>{rows.some(row => row.amount_ntd === null) && <span>部分案件金額待確認，未計入合計。</span>}</div>
        <div className="finance-kpi-item"><span className="finance-kpi-label">本頁案件數</span><strong className="finance-kpi-value">{rows.length} 筆</strong></div>
      </div>
      {rows.length === 0 ? <div className="finance-state">沒有符合條件的補助退款案件。可清除搜尋或月份篩選，查看全部應退案件。</div> : <div className="finance-table-container"><table className="finance-table">
        <caption className="subsidy-refund-caption">應退補助案件；預估金額依目前服務條件，結案後依實際服務與正式退款資料確認。</caption>
        <thead><tr><th scope="col">客戶</th><th scope="col">案件</th><th scope="col">訂單狀態</th><th scope="col">應退補助金額</th><th scope="col">應退款日期</th></tr></thead>
        <tbody>{rows.map(row => <tr key={row.case_no}>
          <td><strong>{row.client_name}</strong></td><td>{row.case_no}</td><td>{row.order_status}</td>
          <td className="subsidy-refund-money">{row.amount_ntd === null ? '待確認' : formatMoney(row.amount_ntd)}{row.is_estimate && row.amount_ntd !== null && <span className="subsidy-refund-estimate">預估</span>}</td>
          <td>{row.due_date ?? (['訂單完成', '歷史訂單－服務完成', '歷史訂單－帳務完成'].includes(row.order_status) ? '待確認' : '待結案')}</td>
        </tr>)}</tbody>
      </table></div>}
      <p className="subsidy-refund-note">正式出款須核對客戶付款與退款資料，再到應付帳款處理。未確定退款日期的案件不會出現在月份篩選結果。</p>
      <div className="subsidy-refund-pagination">
        {afterCaseNo && <button type="button" className="finance-reload-btn" onClick={() => setAfterCaseNo(undefined)}>返回第一頁</button>}
        {result.data.next_cursor && <button type="button" className="finance-reload-btn" onClick={() => setAfterCaseNo(result.data.next_cursor ?? undefined)}>下一頁</button>}
      </div>
    </>}
  </section>;
}

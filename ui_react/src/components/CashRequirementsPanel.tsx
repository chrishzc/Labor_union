import { useStaffIdentityLabels } from './StaffIdentityProvider';
/** Cash planning presentation; does not create, settle, or export payment instructions. */
import { useEffect, useState } from 'react';
import { cashRequirementsQueryClient, type CashRequirementRow } from '../api/accounts_payable/cash_requirements_query_client';

const TYPES = { staff_payable: '月嫂應付款', client_refund: '客戶一般退款', client_subsidy_return: '客戶補助退款' };
const SOURCES = { staff_obligation: '月嫂應付帳務', historical_payroll: '歷史服務資料試算', missing_payroll: '排班案件・帳務待確認', client_refund: '客戶退款單', subsidy_estimate: '排班服務量與客戶付款條款' };
const money = (amount: number | null) => amount === null ? '待確認' : `NT$ ${amount.toLocaleString('zh-TW')}`;
type State = { kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'ready'; rows: CashRequirementRow[] };

export function CashRequirementsPanel({ revision = 0 }: { revision?: number }) {
  const staffIdentity = useStaffIdentityLabels();
  const [state, setState] = useState<State>({ kind: 'loading' });
  const [queryRevision, setQueryRevision] = useState(0);
  const [month, setMonth] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    setState({ kind: 'loading' });
    void cashRequirementsQueryClient.queryAll(controller.signal)
      .then(rows => { if (!controller.signal.aborted) setState({ kind: 'ready', rows }); })
      .catch(error => { if (!controller.signal.aborted) setState({ kind: 'error', message: error?.status === 401 ? '請先登入後重新查詢。' : '預估資金需求暫時無法取得，請重新查詢。' }); });
    return () => controller.abort();
  }, [revision, queryRevision]);
  const rows = state.kind === 'ready' ? state.rows : [];
  const datedRows = rows.filter(row => row.payment_date !== null && (!month || row.payment_date.slice(0, 7) === month));
  const undatedRows = rows.filter(row => row.payment_date === null);
  const months = [...new Set(datedRows.map(row => row.payment_date!.slice(0, 7)))].sort();
  const totalKnown = [...datedRows, ...undatedRows].reduce((sum, row) => sum + (row.unpaid_amount_ntd ?? 0), 0);
  const renderRows = (items: CashRequirementRow[]) => <div className="finance-table-container" tabIndex={0}><table className="finance-table cash-requirements-table">
    <thead><tr><th>案件</th><th>受款人</th><th>款項類型</th><th>金額性質</th><th>來源金額</th><th>未付款金額</th><th>付款日期</th><th>資料來源</th><th>待確認原因</th></tr></thead>
    <tbody>{items.map(row => <tr key={row.row_id}>
      <td>{row.case_no}</td><td>{row.payment_type === 'staff_payable' ? staffIdentity.label(row.staff_id, row.recipient_name) : row.recipient_name ?? '待確認受款人'}</td><td>{TYPES[row.payment_type]}</td>
      <td>{row.certainty === 'estimated' ? '預估' : '已確定'}</td>
      <td>{money(row.source_amount_ntd)}</td><td>{money(row.unpaid_amount_ntd)}</td>
      <td>{row.payment_date === null ? '待確認' : `${row.date_is_estimate ? '預估付款日' : '已確定付款日'} ${row.payment_date}`}</td>
      <td>{SOURCES[row.source]}</td><td>{row.pending_reasons.join('；') || '—'}</td>
    </tr>)}</tbody>
  </table></div>;
  return <section role="tabpanel" id="cash-requirements-panel" aria-labelledby="cash-requirements-tab">
    <div className="finance-section-heading"><div><h2>預估資金需求</h2>
      <p>從已建立排班的案件查看未付款與預估客戶補助退款，供安排資金。預估金額與日期可能更新；此表不作為付款指示。</p></div></div>
    <div className="finance-filter-bar"><label>付款月份<select className="finance-select" value={month} onChange={event => setMonth(event.target.value)}>
      <option value="">全部月份</option>{[...new Set(rows.flatMap(row => row.payment_date ? [row.payment_date.slice(0, 7)] : []))].sort().map(value => <option key={value} value={value}>{value}</option>)}
    </select></label><button type="button" className="finance-btn-primary" onClick={() => setQueryRevision(value => value + 1)}>重新查詢預估</button></div>
    {state.kind === 'loading' && <p role="status">正在載入預估資金需求…</p>}
    {state.kind === 'error' && <p role="alert">{state.message}</p>}
    {state.kind === 'ready' && <>
      <div className="finance-kpi-grid"><div className="finance-kpi-item" style={{ gridColumn: '1 / -1' }}><span className="finance-kpi-label">已知金額小計</span><strong className="finance-kpi-value">{money(totalKnown)}</strong></div></div>
      <p>已知金額小計包含下方日期待確認的已知金額；缺金額的項目未計入，不代表完整資金總額。</p>
      {rows.length === 0 && <p className="finance-state">目前沒有已排班案件的未付款或預估退款項目。</p>}
      {rows.length > 0 && datedRows.length === 0 && <p>所選月份沒有付款日期已知的項目。</p>}
      {months.map(value => <section key={value} aria-label={`${value} 資金需求`}><h3>{value} · 已知金額小計 {money(datedRows.filter(row => row.payment_date!.startsWith(value)).reduce((sum, row) => sum + (row.unpaid_amount_ntd ?? 0), 0))}</h3>{renderRows(datedRows.filter(row => row.payment_date!.startsWith(value)))}</section>)}
      {undatedRows.length > 0 && <section aria-label="付款日期待確認項目"><h3>付款日期待確認</h3><p>這些項目保留顯示，不歸入所選月份。</p>{renderRows(undatedRows)}</section>}
    </>}
  </section>;
}

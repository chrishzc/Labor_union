/** One unpaid list; estimates never enter the confirmed payable subtotal. */
import { useEffect, useRef, useState } from 'react';
import { cashRequirementsQueryClient, type CashRequirementRow } from '../api/accounts_payable/cash_requirements_query_client';
import { accountsPayableExportClient } from '../api/accounts_payable/accounts_payable_export_client';
import { financeMoney } from './FinanceReceiptsWorkspace';

const types = { staff_payable: '月嫂薪資', client_refund: '客戶退款', client_subsidy_return: '補助退款' };
const awaitsServiceEnd = (row: CashRequirementRow) => row.certainty === 'estimated' && row.pending_reasons.includes('服務尚未完成');
type Props = { revision: number; targetMonth: string; onMonthChange: (value: string) => void; onOpenStaff: (staffId?: number) => void; onOpenCase: (caseNo: string) => void; onOpenSubsidy: (caseNo: string) => void; onOpenBank: () => void };
export function FinancePaymentsWorkspace({ revision, targetMonth, onMonthChange, onOpenStaff, onOpenCase, onOpenSubsidy, onOpenBank }: Props) {
  const [rows, setRows] = useState<CashRequirementRow[]>([]);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [type, setType] = useState('all');
  const [status, setStatus] = useState('all');
  const [search, setSearch] = useState('');
  const [month, setMonth] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [download, setDownload] = useState('');
  const [downloading, setDownloading] = useState(false);
  const downloadController = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController(); setState('loading');
    queueMicrotask(() => {
      if (controller.signal.aborted) return;
      void cashRequirementsQueryClient.queryAll(controller.signal).then(data => { if (!controller.signal.aborted) { setRows(data); setState('ready'); } })
        .catch(() => { if (!controller.signal.aborted) setState('error'); });
    });
    return () => controller.abort();
  }, [revision, refresh]);
  useEffect(() => () => downloadController.current?.abort(), []);
  useEffect(() => { downloadController.current?.abort(); setDownloading(false); setDownload(''); }, [targetMonth]);
  const filtered = rows.filter(row => (type === 'all' || row.payment_type === type)
    && (status === 'all' || (status === 'service_pending' ? awaitsServiceEnd(row) : row.certainty === 'confirmed'))
    && (!month || !row.payment_date || row.payment_date.startsWith(month))
    && `${row.case_no} ${row.recipient_name ?? ''}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()));
  const total = (certainty: CashRequirementRow['certainty']) => filtered.filter(row => row.certainty === certainty).reduce((sum, row) => sum + (row.unpaid_amount_ntd ?? 0), 0);
  const exportXlsx = async () => {
    downloadController.current?.abort(); const controller = new AbortController(); downloadController.current = controller;
    setDownloading(true); setDownload('');
    try {
      const artifact = await accountsPayableExportClient.download(targetMonth, controller.signal);
      if (controller.signal.aborted) return;
      const url = URL.createObjectURL(artifact.blob); const link = document.createElement('a');
      link.href = url; link.download = artifact.filename; document.body.appendChild(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000); setDownload(`已送出下載：${artifact.filename}`);
    } catch { if (!controller.signal.aborted) setDownload('下載失敗，請確認登入與付款資料後再試。'); }
    finally { if (!controller.signal.aborted) setDownloading(false); }
  };
  return <section className="finance-workspace finance-collection" aria-label="付款清單">
    <div className="finance-section-heading"><div><h2>付款</h2><p>月嫂薪資、客戶退款與補助退款，一份清單安排付款。</p></div><div className="finance-row-actions"><button type="button" onClick={() => onOpenStaff()}>人員與歷史付款</button><button type="button" onClick={() => setRefresh(value => value + 1)}>重新整理</button></div></div>
    <div className="finance-filter-bar">
      <label>款項類型<select className="finance-select" value={type} onChange={event => setType(event.target.value)}><option value="all">全部類型</option>{Object.entries(types).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label>付款狀態<select className="finance-select" value={status} onChange={event => setStatus(event.target.value)}><option value="all">全部</option><option value="confirmed">確認待付</option><option value="service_pending">待確認服務結束</option></select></label>
      <label>付款月份<input className="finance-input" type="month" value={month} onChange={event => setMonth(event.target.value)} /></label>
      <label className="finance-search">搜尋<input className="finance-input" value={search} maxLength={100} placeholder="受款人或案件編號" onChange={event => setSearch(event.target.value)} /></label>
      {month && <button type="button" className="finance-reload-btn" onClick={() => setMonth('')}>全部月份</button>}
    </div>
    {state === 'loading' ? <p className="finance-state" role="status">正在查詢付款資料…</p> : state === 'error' ? <p className="finance-state error" role="alert">付款資料暫時無法取得，請重新整理。</p> : <>
      <div className="finance-inline-summary" aria-label="付款摘要"><span>{filtered.length} 筆</span><span>確認待付 <strong>{financeMoney(total('confirmed'))}</strong></span><span>預估 <strong>{financeMoney(total('estimated'))}</strong></span>{filtered.some(row => row.unpaid_amount_ntd === null) && <span>部分金額待確認，未計入合計</span>}</div>
      <div className="finance-table-container"><table className="finance-table"><thead><tr><th>受款人／案件</th><th>款項類型</th><th>待付金額</th><th>付款日期</th><th>狀態</th><th>操作</th></tr></thead><tbody>{filtered.map(row => <tr key={row.row_id}>
        <td><strong>{row.recipient_name ?? '待確認受款人'}</strong><small className="finance-secondary">{row.case_no}</small></td><td>{types[row.payment_type]}</td><td>{financeMoney(row.unpaid_amount_ntd)}</td><td>{row.payment_date ?? '待確認'}{row.date_is_estimate && <small className="finance-secondary">預估日期</small>}</td>
        <td><span className={`finance-badge ${row.certainty === 'estimated' ? 'finance-badge-stage' : 'finance-badge-unpaid'}`}>{row.certainty === 'confirmed' ? '確認待付' : awaitsServiceEnd(row) ? '待確認服務結束' : '待確認'}</span></td>
        <td className="finance-row-actions">{row.payment_type === 'client_subsidy_return' ? <button type="button" onClick={() => onOpenSubsidy(row.case_no)}>案件補助明細</button> : row.payment_type === 'staff_payable' ? row.staff_id ? <button type="button" onClick={() => onOpenStaff(row.staff_id!)}>人員付款明細</button> : <button type="button" onClick={() => onOpenStaff()}>選擇人員明細</button> : <button type="button" onClick={() => onOpenCase(row.case_no)}>案件付款紀錄</button>}</td>
      </tr>)}</tbody></table></div>
      {!filtered.length && <p className="finance-state">沒有符合條件的未付款項或預估款項。</p>}
      {month && <p className="subsidy-refund-note">付款日期尚未確認的項目仍列出，供後續核對。</p>}
    </>}
    <div className="finance-export-bar"><label>會計清冊月份<input type="month" className="finance-input" value={targetMonth} onChange={event => { if (event.target.value) onMonthChange(event.target.value); }} /></label><button type="button" className="finance-btn-primary" data-control-id="finance.accounts-payable.export-xlsx" disabled={downloading} onClick={() => void exportXlsx()}>{downloading ? '正在準備下載…' : '下載應付帳款 Excel'}</button><p>依既有付款條件匯出正式清冊；預估、待確認款項及畫面篩選不會改變匯出條件。</p></div>
    {download && <p role="status">{download}</p>}
    <div className="finance-footer-note">已付與沖正紀錄可在案件、人員明細查閱。<button type="button" onClick={onOpenBank}>前往銀行對帳</button></div>
  </section>;
}

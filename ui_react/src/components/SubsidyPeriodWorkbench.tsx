/** One month/quarter/year selector, one bank receipt, one reconciliation. */
import { useEffect, useRef, useState } from 'react';
import { subsidyPeriodClient, type SubsidyBankRow, type SubsidyPeriod, type SubsidyPeriodView } from '../api/government_subsidy/period_reconciliation_client';
import { ApiHttpError } from '../api/shared/typed_errors';

const money = (value:number|null) => value === null ? '待確認' : `NT$ ${value.toLocaleString('zh-TW')}`;
export function SubsidyPeriodWorkbench({revision=0,onOpenCase}:{revision?:number;onOpenCase:(caseNo:string)=>void}) {
  const [period,setPeriod] = useState<SubsidyPeriod>({unit:'quarter',year:new Date().getFullYear(),index:Math.floor(new Date().getMonth()/3)+1});
  const [yearText,setYearText] = useState(String(new Date().getFullYear()));
  const [view,setView] = useState<SubsidyPeriodView|null>(null);
  const [banks,setBanks] = useState<SubsidyBankRow[]>([]);
  const [bank,setBank] = useState('');
  const [error,setError] = useState('');
  const [message,setMessage] = useState('');
  const [busy,setBusy] = useState(false);
  const [refresh,setRefresh] = useState(0);
  const command = useRef<{scope:string;key:string}|null>(null);
  useEffect(() => {
    const controller = new AbortController();
    setView(null);setError('');setBank('');
    void Promise.all([subsidyPeriodClient.query(period,controller.signal),subsidyPeriodClient.bankRows(controller.signal)])
      .then(([result,rows]) => {if (!controller.signal.aborted) {setView(result);setBanks(rows);}})
      .catch(() => {if (!controller.signal.aborted) setError('補助資料暫時無法取得，請重新整理。');});
    return () => controller.abort();
  },[period,revision,refresh]);
  const selected = banks.find(row => String(row.id)===bank);
  const validYear=/^\d{4}$/.test(yearText)&&Number(yearText)>=1912&&Number(yearText)<=9998;
  const exact = validYear && !!view && selected?.amount_ntd===view.total_ntd && view.can_reconcile;
  const apply = async (reversalId?:number) => {
    if (!view || !selected || busy) return;
    const scope=JSON.stringify([view.period,view.version,selected.id,reversalId]);
    if (command.current?.scope!==scope) command.current={scope,key:crypto.randomUUID()};
    setBusy(true);setError('');setMessage('');
    try {
      if (reversalId) await subsidyPeriodClient.reverse(reversalId,selected.id,command.current.key);
      else await subsidyPeriodClient.reconcile(view,selected.id,command.current.key);
      command.current=null;
      setMessage(reversalId?'整期沖正已記錄，原核銷紀錄保留。':'整期入款已核銷，代墊回收已同步記錄。');
      setRefresh(value=>value+1);
    } catch (caught) {
      setError(caught instanceof ApiHttpError ? caught.message : '尚未確認儲存結果，請用相同選擇重試。');
    } finally {setBusy(false);}
  };
  return <section aria-label="政府補助整期核銷" className="subsidy-period-workbench">
    <h3>政府補助整期核銷</h3><p>依服務結束月份彙總；申請與核准在系統外辦理。</p>
    <div className="finance-filter-bar"><label>彙總單位<select className="finance-select" disabled={busy} value={period.unit} onChange={event=>{setMessage('');setPeriod({...period,unit:event.target.value as SubsidyPeriod['unit'],index:1});}}><option value="month">月</option><option value="quarter">季</option><option value="year">年</option></select></label>
      <label>年度<input className="finance-input" type="number" min="1912" max="9998" disabled={busy} value={yearText} onChange={event=>{const value=event.target.value;setYearText(value);const year=Number(value);if(/^\d{4}$/.test(value)&&year>=1912&&year<=9998)setPeriod({...period,year});}} onBlur={()=>{if(!validYear)setYearText(String(period.year));}} /></label>
      {period.unit!=='year'&&<label>{period.unit==='month'?'月份':'季度'}<select className="finance-select" disabled={busy} value={period.index} onChange={event=>setPeriod({...period,index:Number(event.target.value)})}>{Array.from({length:period.unit==='month'?12:4},(_,i)=><option key={i+1} value={i+1}>{i+1}</option>)}</select></label>}
      <button type="button" className="finance-reload-btn" disabled={busy} onClick={()=>setRefresh(value=>value+1)}>重新整理補助</button></div>
    {error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
    {!view&&!error&&<p role="status">正在查詢整期補助…</p>}
    {view&&<><p><strong>{view.label}</strong>・{view.lines.length} 件・本期補助總額 <strong>{money(view.total_ntd)}</strong></p>
      {view.coverage.map(coverage=><p key={coverage.receipt_id}>本期已由「{coverage.label}」核銷涵蓋。原整筆入款 {money(coverage.amount_ntd)}；已回收代墊 {money(coverage.recovered_advance_ntd)}。{selected&&selected.amount_ntd===-coverage.amount_ntd&&<button type="button" disabled={busy} onClick={()=>void apply(coverage.receipt_id)}>依整筆退回款沖正</button>}</p>)}
      {!!view.changed_cases.length&&<p role="alert">已核銷後案件資料有變更：{view.changed_cases.join('、')}。原核銷明細保留，請核對。</p>}
      {!!view.blocked_cases.length&&!view.coverage.length&&<p role="alert">案件已由其他期間核銷，無法再次核銷：{view.blocked_cases.join('、')}。</p>}
      <div className="finance-table-container"><table className="finance-table"><thead><tr><th>案件</th><th>服務結束／歸屬月份</th><th>補助金額</th></tr></thead><tbody>{view.lines.map(line=><tr key={line.case_no}><td className="finance-row-actions"><button type="button" disabled={busy} onClick={()=>onOpenCase(line.case_no)}>{line.case_no}</button></td><td>{line.service_end_date}</td><td>{money(line.amount_ntd)}{line.unavailable_reason&&<small> {line.unavailable_reason==='scheduling_effective_generation_invalid'?'排班資料待確認':'計算資料待確認'}</small>}</td></tr>)}</tbody></table></div>
      {!view.lines.length&&<p>本期沒有補助案件。</p>}
      <div className="subsidy-period-bank-actions"><label>政府銀行款項<select className="finance-select" disabled={busy} value={bank} onChange={event=>setBank(event.target.value)}><option value="">選擇已匯入的整筆款項</option>{banks.map(row=><option key={row.id} value={row.id}>{row.paid_on}・{money(row.amount_ntd)}・流水 #{row.id}</option>)}</select></label>
      <button type="button" className="finance-btn-primary" disabled={busy||!exact} onClick={()=>void apply()}>{busy?'處理中…':'核銷本期入款'}</button></div>
      {selected&&selected.amount_ntd>0&&view.total_ntd!==null&&selected.amount_ntd!==view.total_ntd&&<p role="alert">銀行金額與所選期間總額不一致，不能核銷。</p>}
      <p className="subsidy-refund-note">已涵蓋的月、季、年禁止重複核銷；整筆款項不拆成逐案或逐月入款。</p>
    </>}
  </section>;
}

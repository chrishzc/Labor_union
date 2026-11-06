import { useEffect, useState } from 'react';
import { monthlyAccountingClient, type AccountingRange, type ReceivableAccountingList } from '../api/finance_import/monthly_accounting_client';
import { financeMoney } from './FinanceReceiptsWorkspace';
export type ReceivableFilters={month:string|null;category:AccountingRange['category'];status:'all'|'open'|'settled'|'received';search:string};
const currentMonth=()=>{const now=new Date();return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}`;};

export function FinanceReceivableItems({revision=0,undatedOnly=false,initialFilters,onFiltersChange,onCase,onSubsidy}:{revision?:number;undatedOnly?:boolean;initialFilters?:ReceivableFilters;onFiltersChange?:(filters:ReceivableFilters)=>void;onCase:(caseNo:string)=>void;onSubsidy?:(caseNo:string)=>void}){
  const [filters,setFilters]=useState<ReceivableFilters>(()=>initialFilters??{month:undatedOnly?null:currentMonth(),category:'subsidy',status:'all',search:''});
  const [draftMonth,setDraftMonth]=useState(filters.month??'');
  const [data,setData]=useState<ReceivableAccountingList>();
  const [error,setError]=useState('');
  const [refresh,setRefresh]=useState(0);
  useEffect(()=>{
    const controller=new AbortController();setData(undefined);setError('');
    queueMicrotask(()=>{if(controller.signal.aborted)return;
    void monthlyAccountingClient.receivables(undatedOnly?null:filters.month,filters.category,undatedOnly,controller.signal).then(value=>{if(!controller.signal.aborted)setData(value);}).catch(()=>{if(!controller.signal.aborted)setError('應收款項暫時無法取得，請重新查詢。');});
    });
    return()=>controller.abort();
  },[revision,refresh,filters.month,filters.category,undatedOnly]);
  function change(next:ReceivableFilters){setFilters(next);onFiltersChange?.(next);}
  const rows=data?.items.filter(item=>(filters.status==='all'||(filters.status==='open'?item.remaining_ntd>0:filters.status==='received'?item.actual_ntd>0:item.remaining_ntd===0))&&`${item.case_no} ${item.client_name} ${item.party} ${item.label}`.toLocaleLowerCase().includes(filters.search.trim().toLocaleLowerCase()));
  return <section className="finance-collection" aria-label={undatedOnly?'未定到期日應收款':'到期月份應收款'}>
    {undatedOnly&&<h2>未定到期日的應收款</h2>}
    <form className="finance-filter-bar finance-receivable-filters" onSubmit={event=>{event.preventDefault();change({...filters,month:draftMonth||null});setRefresh(value=>value+1);}}>
      {!undatedOnly&&<label>到期月份<input className="finance-input" type="month" value={draftMonth} onChange={event=>setDraftMonth(event.target.value)}/></label>}
      <label>案件類別<select className="finance-select" value={filters.category} onChange={event=>change({...filters,category:event.target.value as ReceivableFilters['category']})}><option value="subsidy">補助案件</option><option value="non_citizen">非市民案件</option><option value="all">全部案件</option></select></label>
      <label>核銷狀態<select className="finance-select" value={filters.status} onChange={event=>change({...filters,status:event.target.value as ReceivableFilters['status']})}><option value="all">全部狀態</option><option value="open">仍待收</option><option value="received">已收款（含部分）</option><option value="settled">已結清</option></select></label>
      <label className="finance-search">搜尋案件或對象<input className="finance-input" value={filters.search} onChange={event=>change({...filters,search:event.target.value})} maxLength={100} placeholder="案件編號、客戶或款項"/></label>
      <button type="submit" className="finance-btn-primary">查詢</button>
      {!undatedOnly&&<button type="button" className="finance-btn-link" onClick={()=>{setDraftMonth('');change({...filters,month:null});}}>查看全部月份</button>}
    </form>
    {error?<p role="alert">{error}</p>:!rows?<p role="status">正在查詢應收款項…</p>:<>
      <div className="finance-inline-summary"><span>{rows.length} 筆 · {undatedOnly?'到期日待確認':filters.month??'全部月份'}</span><span>目前待收 <strong>{financeMoney(rows.reduce((sum,item)=>sum+BigInt(item.remaining_ntd),0n))}</strong></span></div>
      <div className="finance-table-container"><table className="finance-table finance-receivables-table"><thead><tr><th>案件／對象</th><th>款項</th><th>到期日</th><th>應收</th><th>已收</th><th>其他處理</th><th>待收</th><th>狀態</th><th>案件明細</th></tr></thead><tbody>{rows.map(item=><tr key={`${item.case_no}:${item.identity}`}><td><strong>{item.case_no}</strong><small className="finance-secondary">{item.client_name}</small></td><td>{item.label}</td><td>{item.due_date??'待確認'}</td><td>{financeMoney(item.expected_ntd)}</td><td>{financeMoney(item.actual_ntd)}</td><td>{financeMoney(item.noncash_ntd)}</td><td>{financeMoney(item.remaining_ntd)}</td><td>{item.remaining_ntd===0?(item.noncash_ntd>0?'已結清（其他處理）':item.actual_ntd>item.expected_ntd?'已收，另有多付款':'已核銷'):item.actual_ntd>0?'部分已收':'待收款'}</td><td><button type="button" className="finance-btn-link" onClick={()=>onCase(item.case_no)}>查看案件</button>{onSubsidy&&<button type="button" className="finance-btn-link" onClick={()=>onSubsidy(item.case_no)}>案件補助明細</button>}</td></tr>)}</tbody></table></div>
      {!rows.length&&<p className="finance-state">沒有符合條件的應收款項。</p>}
      {!undatedOnly&&data&&data.undated_count>0&&<p className="finance-scope-note">另有 {data.undated_count} 筆未定到期日的應收款，請至「待確認與預估」查看。</p>}
    </>}
  </section>;
}

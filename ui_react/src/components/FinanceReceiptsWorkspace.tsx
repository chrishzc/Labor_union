import { useUnsavedNavigation } from './UnsavedChanges';
/** Customer receipts and whole-period government receipts use their owning queries. */
import { useEffect, useState } from 'react';
import { clientFinanceHistoryClient, type ClientFinanceSummary } from '../api/client_finance/client_finance_history_client';
import { loadAllOrderSummaries, ordersQueryClient } from '../api/orders/order_query_client';
import { SubsidyPeriodWorkbench } from './SubsidyPeriodWorkbench';
import { caseCategoriesClient, type FinanceCaseCategory, type FinanceCaseFilter } from '../api/client_finance/case_categories_client';
export const financeMoney = (value: number | null) => value === null ? '待確認' : `NT$ ${value.toLocaleString('zh-TW')}`;
const receiptLabels = { pending: '待確認', unpaid: '待收款', partially_received: '部分收款', received: '已收款', settled: '已結清' };
type ClientRow = Omit<ClientFinanceSummary, 'open_receivable_amount_ntd'> & { name: string; open_receivable_amount_ntd: number | null };
type Props = { revision: number; initialSource?: 'client' | 'government'; initialRecovery?: boolean; onOpenCase: (caseNo: string) => void; onOpenSubsidy: (caseNo: string) => void };
export function FinanceReceiptsWorkspace({revision,initialSource='client',onOpenCase,onOpenSubsidy}:Props) {
  const {requestLeave}=useUnsavedNavigation();
  const [source,setSource]=useState(initialSource);
  const [status,setStatus]=useState('all');
  const [search,setSearch]=useState('');
  const [clients,setClients]=useState<ClientRow[]>([]);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  const [refresh,setRefresh]=useState(0);
  const [caseCategory,setCaseCategory]=useState<FinanceCaseFilter>('subsidy');
  const [categories,setCategories]=useState(new Map<string,FinanceCaseCategory>());
  useEffect(()=>{
    if(source!=='client')return;
    const controller=new AbortController();setLoading(true);setError('');
    queueMicrotask(() => {
    if (controller.signal.aborted) return;
    void Promise.all([clientFinanceHistoryClient.queryAll(controller.signal),caseCategoriesClient.query(controller.signal),
      loadAllOrderSummaries(ordersQueryClient.getOrderSummaries.bind(ordersQueryClient),{page_size:200},{signal:controller.signal})])
      .then(([facts,caseCategories,orders])=>{
        const names=new Map(orders.items.map(row=>[row.case_no,row.client_name]));
        const byCase=new Map<string,ClientRow>(facts.map(row=>[row.case_no,{...row,name:names.get(row.case_no)??'客戶資料待確認'}]));
        for(const row of orders.items)if(!byCase.has(row.case_no))byCase.set(row.case_no,{case_no:row.case_no,name:row.client_name,account_version:'0',open_receivable_amount_ntd:null,open_payable_amount_ntd:0,obligation_count:0,ledger_entry_count:0,receipt_entry_count:0,receipt_status:'pending'});
        if([...byCase.keys()].some(caseNo=>!caseCategories.has(caseNo))) throw new Error('case_category_missing');
        if(!controller.signal.aborted){setClients([...byCase.values()]);setCategories(caseCategories);}
      }).catch(()=>{if(!controller.signal.aborted)setError('收款資料暫時無法取得，請重新整理。');})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    });
    return()=>controller.abort();
  },[source,revision,refresh]);
  const clientRows=clients.filter(row=>(caseCategory==='all'||categories.get(row.case_no)===caseCategory)&&`${row.case_no} ${row.name}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())&&(status==='all'||(status==='unpaid'?row.open_receivable_amount_ntd!==null&&row.open_receivable_amount_ntd>0:['received','partially_received'].includes(row.receipt_status))));
  return <section className="finance-workspace finance-collection" aria-label="收款清單">
    <div className="finance-section-heading"><div><h2>收款</h2><p>客戶收款與政府整期補助。</p></div><button type="button" className="finance-reload-btn" onClick={()=>setRefresh(value=>value+1)}>重新整理</button></div>
    <div className="finance-filter-bar"><label>收款來源<select className="finance-select" value={source} onChange={event=>{const value=event.target.value as typeof source;requestLeave(()=>{setSource(value);setStatus('all');});}}><option value="client">客戶收款</option><option value="government">政府補助／代墊回收</option></select></label>
    {source==='client'&&<><label>案件類別<select aria-label="案件類別" className="finance-select" value={caseCategory} onChange={event=>setCaseCategory(event.target.value as FinanceCaseFilter)}><option value="subsidy">補助案件</option><option value="non_citizen">非市民案件</option><option value="all">全部案件</option></select></label><label>狀態<select className="finance-select" value={status} onChange={event=>setStatus(event.target.value)}><option value="all">全部</option><option value="unpaid">待收款</option><option value="history">已收款</option></select></label><label>搜尋<input className="finance-input" value={search} maxLength={100} onChange={event=>setSearch(event.target.value)} placeholder="姓名或案件編號" /></label></>}
    </div>
    {source==='government'?<SubsidyPeriodWorkbench revision={revision+refresh} onOpenCase={onOpenSubsidy}/>:loading?<p role="status">正在查詢收款資料…</p>:error?<p role="alert">{error}</p>:<>
      <div className="finance-inline-summary"><span>{clientRows.length} 件</span><span>目前待收合計 <strong>{financeMoney(clientRows.reduce((sum, row) => sum + (row.open_receivable_amount_ntd ?? 0), 0))}</strong></span>{clientRows.some(row => row.open_receivable_amount_ntd === null) && <span>計算資料待確認的案件未計入合計</span>}</div>
      <div className="finance-table-container"><table className="finance-table"><thead><tr><th>客戶／案件</th><th>目前應收</th><th>收款狀態</th><th>歷史入帳</th><th>操作</th></tr></thead><tbody>{clientRows.map(row => <tr key={row.case_no}><td><strong>{row.name}</strong><small className="finance-secondary">{row.case_no}</small></td><td>{financeMoney(row.open_receivable_amount_ntd)}</td><td>{receiptLabels[row.receipt_status]}</td><td>{row.ledger_entry_count ? '可查看歷史紀錄' : '尚無入帳紀錄'}</td><td className="finance-row-actions"><button type="button" onClick={() => onOpenCase(row.case_no)}>收款明細</button><button type="button" onClick={() => onOpenSubsidy(row.case_no)}>案件補助明細</button></td></tr>)}</tbody></table></div>
      {!clientRows.length && <p className="finance-state">沒有符合條件的客戶收款。</p>}
    </>}
  </section>;
}

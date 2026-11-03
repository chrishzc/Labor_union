import { useState } from 'react';
import { useUnsavedNavigation } from './UnsavedChanges';
import { PaymentOverdueReminderWorkbench } from './PaymentOverdueReminderWorkbench';
import { SubsidyPeriodWorkbench } from './SubsidyPeriodWorkbench';
import { FinanceReceivableItems, type ReceivableFilters } from './FinanceReceivableItems';
export const financeMoney = (value: number | null) => value === null ? '待確認' : `NT$ ${value.toLocaleString('zh-TW')}`;
type Props = { revision: number; initialView?: 'all' | 'overdue'; onOpenBank?: (caseNo: string) => void; initialSource?: 'client' | 'government'; initialRecovery?: boolean; initialFilters?:ReceivableFilters; onFiltersChange?:(filters:ReceivableFilters)=>void; onOpenCase: (caseNo: string) => void; onOpenSubsidy: (caseNo: string) => void };
export function FinanceReceiptsWorkspace({revision,initialSource='client',initialView='all',initialFilters,onFiltersChange,onOpenBank,onOpenCase,onOpenSubsidy}:Props) {
  const {requestLeave}=useUnsavedNavigation();
  const [view,setView]=useState(initialView);
  const [source,setSource]=useState(initialSource);
  const [refresh,setRefresh]=useState(0);
  return <section className="finance-workspace finance-collection" aria-label="收款清單">
    <div className="finance-section-heading"><div><h2>應收款</h2><p>依到期月份查看跨案件款項；單案完整資料由案件帳務查閱。</p></div><button type="button" className="finance-reload-btn" onClick={()=>setRefresh(value=>value+1)}>重新整理</button></div>
    {view==='overdue'?<><button type="button" className="finance-btn-link" onClick={()=>setView('all')}>返回應收款</button><PaymentOverdueReminderWorkbench key={revision+refresh} onOpenBank={onOpenBank}/></>:<>
      <div className="finance-filter-bar"><label>收款來源<select className="finance-select" value={source} onChange={event=>{const value=event.target.value as typeof source;requestLeave(()=>setSource(value));}}><option value="client">客戶收款</option><option value="government">政府補助／代墊回收</option></select></label></div>
      {source==='government'?<SubsidyPeriodWorkbench revision={revision+refresh} onOpenCase={onOpenSubsidy}/>:<FinanceReceivableItems revision={revision+refresh} initialFilters={initialFilters} onFiltersChange={onFiltersChange} onCase={onOpenCase} onSubsidy={onOpenSubsidy}/>}
    </>}
  </section>;
}

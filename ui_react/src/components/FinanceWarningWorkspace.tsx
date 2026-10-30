import { useState } from 'react';
import { FinanceAccountingWarnings } from './FinanceCaseAccounting';
import { PaymentReminderSchedulePanel } from './PaymentReminderSchedulePanel';
import { LineNotificationWorkbench } from './LineNotificationWorkbench';
import { useUnsavedNavigation } from './UnsavedChanges';

type View='warnings'|'reminder-schedule'|'reminder-content';
const views=[['warnings','待處理警示'],['reminder-schedule','提醒排程'],['reminder-content','提醒內容']] as const;
function params(){return new URLSearchParams(window.location.hash.split('?')[1]??'');}

export function FinanceWarningWorkspace({onCase}:{onCase:(caseNo:string)=>void}){
  const {requestLeave}=useUnsavedNavigation();
  const [view,setView]=useState<View>(()=>{const value=params().get('view');return value==='reminder-schedule'||value==='reminder-content'?value:'warnings';});
  const [message,setMessage]=useState<string|null>(()=>params().get('message')??'deposit-reminder');
  const [search,setSearch]=useState('');
  function navigate(next:View,focus=false){requestLeave(()=>{setView(next);const query=params();query.set('tab','accounting-warnings');query.set('view',next);window.history.replaceState(null,'','#finance?'+query.toString());if(focus)document.getElementById('finance-warning-tab-'+next)?.focus();});}
  return <section data-surface-id="finance.accounting-warnings"><nav className="finance-warning-tabs" role="tablist" aria-label="帳務警示功能">
    {views.map(([id,label],index)=><button key={id} type="button" role="tab" tabIndex={view===id?0:-1} aria-selected={view===id} aria-controls={'finance-warning-'+id} id={'finance-warning-tab-'+id} onClick={()=>navigate(id)} onKeyDown={event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const target=event.key==='Home'?0:event.key==='End'?views.length-1:(index+(event.key==='ArrowRight'?1:views.length-1))%views.length;navigate(views[target][0],true);}}>{label}</button>)}
  </nav>{views.map(([id])=><div key={id} id={'finance-warning-'+id} role="tabpanel" hidden={view!==id} aria-labelledby={'finance-warning-tab-'+id}>
    {view===id&&<>
    {view==='warnings'&&<FinanceAccountingWarnings onCase={onCase}/>}
    {view==='reminder-schedule'&&<PaymentReminderSchedulePanel/>}
    {view==='reminder-content'&&<LineNotificationWorkbench scope="payment-reminders" search={search} enabled="all" onSearchChange={setSearch} onEnabledChange={()=>{}} selectedEntryId={message} onSelectedEntryChange={id=>{setMessage(id);const query=params();if(id)query.set('message',id);else query.delete('message');window.history.replaceState(null,'','#finance?'+query.toString());}}/>}
    </>}
  </div>)}</section>;
}

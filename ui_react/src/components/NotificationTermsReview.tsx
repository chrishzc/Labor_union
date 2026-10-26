/** Reuse the existing adjustment Query/Preview/Apply and recontact commands. */
import { useEffect, useRef, useState } from 'react';
import { z } from 'zod';
import { OrderTermsQuerySchema, type OrderTermsQuery } from '../api/orders/order_terms_mutation_client';
import { transport } from '../api/shared/transport';
import { notificationOptions, notificationFailure, type NotificationItem } from '../api/line_notifications/notification_tasks_client';
import { useUnsavedDraft } from './UnsavedChanges';

const operationSchema=z.object({order_terms:OrderTermsQuerySchema,terms_change_completed:z.boolean(),recontact_allowed:z.boolean(),
  candidates:z.array(z.object({candidate_id:z.number().int(),staff_name:z.string(),recontact_queued:z.boolean()}).strict())});
const recontactSchema=z.array(z.object({candidate_id:z.number().int(),staff_name:z.string(),text:z.string(),preview_fingerprint:z.string()}).strict());
type Information=NonNullable<NotificationItem['information']>;
type Terms=OrderTermsQuery['terms'];
export function AdjustmentReview({information:info,onCommitted}:{information:Information;onCommitted:()=>Promise<void>}) {
  const [view,setView]=useState<z.infer<typeof operationSchema>|null>(null);const [terms,setTerms]=useState<Terms|null>(null);
  const [open,setOpen]=useState(false);const [selected,setSelected]=useState<number[]>([]);const [busy,setBusy]=useState(false);const [message,setMessage]=useState('');
  const locked=useRef(false);const intent=useRef<{signature:string;key:string}|null>(null);
  const path=`/api/v1/line/notification-task-actions/adjustments/${info.pool_id}`;
  const context={case_no:info.case_no,customer_answer_event_id:info.customer_answer_event_id!};
  const read=async(signal?:AbortSignal)=>{
    const raw=await transport.get<{data:unknown}>(path,{...notificationOptions(signal),params:context});
    const data=operationSchema.parse(raw.data);if(signal?.aborted)return;
    setView(data);setTerms(data.order_terms.terms);return data;
  };
  useEffect(()=>{
    if(!open || !info.customer_answer_event_id)return;const abort=new AbortController();setBusy(true);setMessage('');
    void read(abort.signal).catch(e=>{if(!abort.signal.aborted)setMessage(notificationFailure(e));}).finally(()=>{if(!abort.signal.aborted)setBusy(false);});return()=>abort.abort();
  },[open,info.customer_answer_event_id]);
  useUnsavedDraft('審核客戶更新後條件',{'條件':terms},{enabled:open && !!terms && JSON.stringify(terms)!==JSON.stringify(view?.order_terms.terms),busy});
  const approve=async()=>{
    if(!view || !terms || locked.current)return;locked.current=true;setBusy(true);setMessage('');
    const signature=JSON.stringify([terms,view.order_terms.order_version]);if(intent.current?.signature!==signature)intent.current={signature,key:crypto.randomUUID()};
    try {
      const payload={...context,proposed_terms:terms};
      await transport.post(path+'/preview',payload,notificationOptions());
      const raw=await transport.post<{data:unknown}>(path+'/approve',{...payload,expected_order_version:view.order_terms.order_version,idempotency_key:intent.current.key},notificationOptions());
      z.object({status:z.enum(['approved','idempotent_replay']),approval_event_id:z.number().int().positive()}).parse(raw.data);
      intent.current=null;setMessage('審核通過，案件已更新為新的條件。請選擇月嫂重新詢問。');await read();await onCommitted();
    }catch(e){setMessage(notificationFailure(e));}finally{locked.current=false;setBusy(false);}
  };
  const recontact=async()=>{
    if(locked.current || !selected.length)return;locked.current=true;setBusy(true);setMessage('');
    try {
      const raw=await transport.post<{data:unknown}>(path+'/recontact/preview',{...context,candidate_ids:selected},notificationOptions());
      const previews=recontactSchema.parse(raw.data);
      await transport.post(path+'/recontact/apply',{...context,items:previews.map(p=>({candidate_id:p.candidate_id,preview_fingerprint:p.preview_fingerprint}))},notificationOptions());
      setMessage('已建立重新詢問工作，尚未證明送達。');setSelected([]);await read();await onCommitted();
    }catch(e){setMessage(notificationFailure(e));}finally{locked.current=false;setBusy(false);}
  };
  const set=<K extends keyof Terms>(key:K,value:Terms[K])=>setTerms(old=>old?{...old,[key]:value}:old);
  return <section aria-label="客戶新條件審核"><button className="np-button" disabled={!info.customer_answer_event_id || busy} onClick={()=>setOpen(true)}>{info.review_completed?'選擇月嫂重新詢問':'審核客戶新條件'}</button>
    {!info.customer_answer_event_id && <p>等待客戶回答更新後的條件。</p>}
    {open && view && terms && <><p>客戶回答的是更新後條件，審核通過即更新案件。</p>
      <fieldset disabled={busy || view.terms_change_completed} className="notification-terms-fields"><legend>新的案件條件</legend>
        <label>預計開始日<input type="date" value={terms.planned_start_date} onChange={e=>set('planned_start_date',e.target.value)} /></label>
        <label>服務天數<input type="number" min={1} value={terms.service_days} onChange={e=>set('service_days',Number(e.target.value))} /></label>
        <label>每日時數<input type="number" min={0.5} max={24} step={0.5} value={terms.service_hours_per_day} onChange={e=>set('service_hours_per_day',Number(e.target.value))} /></label>
        <label>下廚需求<select value={terms.requires_cooking===null?'unknown':String(terms.requires_cooking)} onChange={e=>set('requires_cooking',e.target.value==='unknown'?null:e.target.value==='true')}><option value="unknown">尚未確定</option><option value="true">需要</option><option value="false">不需要</option></select></label>
        <label>樓層加給總額<input type="number" min={0} value={terms.floor_fee_ntd} onChange={e=>set('floor_fee_ntd',Number(e.target.value))} /></label>
        <label>開始時間<input type="time" value={terms.service_time.start_time?.slice(0,5)??''} onChange={e=>set('service_time',{...terms.service_time,start_time:e.target.value?e.target.value+':00':null})} /></label>
        <label>結束時間<input type="time" value={terms.service_time.end_time?.slice(0,5)??''} onChange={e=>set('service_time',{...terms.service_time,end_time:e.target.value?e.target.value+':00':null})} /></label>
        <label>結束日<select value={terms.service_time.end_day_offset??0} onChange={e=>set('service_time',{...terms.service_time,end_day_offset:Number(e.target.value)})}><option value={0}>當日</option><option value={1}>次日</option></select></label>
      </fieldset>
      {!view.terms_change_completed && <button className="np-button primary" disabled={busy} onClick={()=>void approve()}>審核通過並更新案件條件</button>}
      {view.recontact_allowed && <fieldset disabled={busy}><legend>選擇月嫂重新詢問</legend>{view.candidates.map(candidate=><label key={candidate.candidate_id}><input type="checkbox" disabled={candidate.recontact_queued} checked={selected.includes(candidate.candidate_id)} onChange={e=>setSelected(old=>e.target.checked?[...old,candidate.candidate_id]:old.filter(id=>id!==candidate.candidate_id))} />{candidate.staff_name}{candidate.recontact_queued?'（已建立寄送工作）':''}</label>)}
        <button className="np-button primary" disabled={busy || !selected.length} onClick={()=>void recontact()}>重新詢問選定月嫂</button></fieldset>}
    </>}{message && <p role="status">{message}</p>}</section>;
}

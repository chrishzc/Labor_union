import { useEffect, useRef, useState } from 'react';
import { z } from 'zod';
import { notificationOptions, notificationFailure } from '../api/line_notifications/notification_tasks_client';
import { transport } from '../api/shared/transport';
import { useUnsavedDraft } from './UnsavedChanges';
import './TaskOperation.css';
import { LineDeliveryTaskActions } from './LineDeliveryTaskActions';
const failureDetailSchema=z.object({case_no:z.string(),notification_reason:z.enum(['recipient_unavailable','template_or_schedule_invalid']),
  related_task_ids:z.array(z.number().int().positive()),
  sources:z.array(z.object({source_event_id:z.number().int().positive(),event_code:z.string(),can_replay:z.boolean(),unavailable_reason:z.string().nullable()}).strict())}).strict();

export function LineNotificationFailureActions({issueKey,onCommitted}:{issueKey:string;onCommitted:()=>Promise<void>}) {
  const [detail,setDetail]=useState<z.infer<typeof failureDetailSchema>|null>(null);
  const [error,setError]=useState('');const [busy,setBusy]=useState(false);const [revision,setRevision]=useState(0);
  const intents=useRef<Record<number,string>>({});const locked=useRef(false);const current=useRef(true);
  useEffect(()=>{current.current=true;const abort=new AbortController();setDetail(null);setError('');
    void Promise.resolve().then(()=>transport.get<{data:unknown}>(`/api/v1/line/notification-task-actions/notification-failures/${issueKey}/query`,notificationOptions(abort.signal)))
      .then(raw=>{if(!abort.signal.aborted)setDetail(failureDetailSchema.parse(raw.data));})
      .catch(e=>{if(!abort.signal.aborted)setError(notificationFailure(e));});
    return()=>{current.current=false;abort.abort();};},[issueKey,revision]);
  useUnsavedDraft('通知補送',{}, {busy});
  const replay=async(id:number)=>{
    if(locked.current)return;locked.current=true;setBusy(true);setError('');
    const storageKey=`notification-replay:${issueKey}:${id}`;
    intents.current[id]??=sessionStorage.getItem(storageKey) ?? crypto.randomUUID();sessionStorage.setItem(storageKey,intents.current[id]);
    try {await transport.post(`/api/v1/line/notification-rules/sources/${id}/manual-replay`,{
      reason:'',idempotency_key:intents.current[id],correlation_id:intents.current[id]},notificationOptions());
      sessionStorage.removeItem(storageKey);delete intents.current[id];
      if(!current.current)return;
      await onCommitted();if(current.current)setRevision(v=>v+1);
    }catch(e){if(current.current)setError(notificationFailure(e));}finally{locked.current=false;if(current.current)setBusy(false);}
  };
  return <section aria-label="通知建立異常處理"><h3>核對原通知</h3>
    <p>設定補齊後仍需核對原通知。補送只建立寄送工作，尚不代表送達。</p>
    {error && <p role="alert">{error}</p>}{!detail && !error && <p role="status">正在核對通知…</p>}
    <a className="np-button" href={`#line-management?tab=order_groups&group_q=${encodeURIComponent(detail?.case_no ?? '')}`}>本案案件群組設定</a>
    <a className="np-button" href="#line-management?tab=binding">LINE 身分綁定</a>
    <a className="np-button" href="#line-management?tab=push_queue">通知內容與規則設定</a>
    <button type="button" className="np-button" disabled={busy} onClick={()=>setRevision(v=>v+1)}>重新核對通知</button>
    {detail?.sources.map(source=><div key={source.source_event_id}><p>原通知 #{source.source_event_id}</p>
      {source.unavailable_reason && <p>{source.unavailable_reason}</p>}
      <button type="button" className="np-button primary" disabled={busy || !source.can_replay} onClick={()=>void replay(source.source_event_id)}>補送原通知 #{source.source_event_id}</button>
    </div>)}
    {detail?.related_task_ids.map(id=><LineDeliveryTaskActions key={id} id={id} onCommitted={async()=>{await onCommitted();if(current.current)setRevision(v=>v+1);}} />)}
  </section>;
}

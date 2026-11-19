import { useEffect, useRef, useState } from 'react';
import { z } from 'zod';
import { notificationOptions, notificationFailure } from '../api/line_notifications/notification_tasks_client';
import { transport } from '../api/shared/transport';
import { useUnsavedDraft } from './UnsavedChanges';
import './TaskOperation.css';
import { NotificationHandlingSchema } from '../api/line_delivery/line_delivery_query_schemas';
import { LineDeliveryTaskActions } from './LineDeliveryTaskActions';
const failureDetailSchema=z.object({handling:NotificationHandlingSchema,case_no:z.string(),notification_reason:z.enum(['recipient_unavailable','template_or_schedule_invalid']),
  related_task_ids:z.array(z.number().int().positive()),
  sources:z.array(z.object({source_event_id:z.number().int().positive(),event_code:z.string(),can_replay:z.boolean(),unavailable_reason:z.string().nullable()}).strict())}).strict();

const closePreviewSchema=z.strictObject({
  issue_key:z.string(),case_no:z.string(),notification_reason:z.string(),
  owner_snapshot_token:z.string(),preview_fingerprint:z.string(),
  source_event_ids:z.array(z.number().int().positive()),
  tasks:z.array(z.strictObject({task_id:z.number().int().positive(),status:z.string()})),
});

export function LineNotificationFailureActions({issueKey,onCommitted,showRelatedTasks=true}:{issueKey:string;onCommitted:()=>Promise<void>;showRelatedTasks?:boolean}) {
  const [detail,setDetail]=useState<z.infer<typeof failureDetailSchema>|null>(null);
  const [error,setError]=useState('');const [busy,setBusy]=useState(false);const [revision,setRevision]=useState(0);
  const [preview,setPreview]=useState<z.infer<typeof closePreviewSchema>|null>(null),[reason,setReason]=useState('');
  const closeIntent=useRef<{key:string;reason:string;preview:z.infer<typeof closePreviewSchema>}|null>(null);
  const [recoveryError,setRecoveryError]=useState('');
  const closeStorageKey=`line-notification-close:${issueKey}`;
  const intents=useRef<Record<number,string>>({});const locked=useRef(false);const current=useRef(true);
  useEffect(()=>{
    try {
      const raw=sessionStorage.getItem(closeStorageKey);
      if(raw){
        const saved=z.strictObject({key:z.string().uuid(),reason:z.string().min(1),preview:closePreviewSchema}).parse(JSON.parse(raw));
        if(saved.preview.issue_key!==issueKey)throw new Error('scope mismatch');
        closeIntent.current=saved;setPreview(saved.preview);setReason(saved.reason);
      }
    }catch{setRecoveryError('前次結清紀錄無法核對，請先確認原操作結果。');}
  },[closeStorageKey,issueKey]);
  useEffect(()=>{current.current=true;const abort=new AbortController();setDetail(null);setError('');
    void Promise.resolve().then(()=>transport.get<{data:unknown}>(`/api/v1/line/notification-task-actions/notification-failures/${issueKey}/query`,notificationOptions(abort.signal)))
      .then(raw=>{if(!abort.signal.aborted)setDetail(failureDetailSchema.parse(raw.data));})
      .catch(e=>{if(!abort.signal.aborted)setError(notificationFailure(e));});
    return()=>{current.current=false;abort.abort();};},[issueKey,revision]);
  useUnsavedDraft('通知補送與結清',{reason}, {busy});
  const close=async(confirm:boolean)=>{
    if(locked.current || recoveryError || (!detail?.handling.allowed_actions.includes('close') && !(confirm && closeIntent.current)))return;
    if(confirm && !reason.trim()){setError('請填寫結清原因。');return;}
    locked.current=true;setBusy(true);setError('');
    try {
      const path=`/api/v1/line/notification-rules/failures/${issueKey}/skip`;
      if(!confirm){
        const response=await transport.post<{data:unknown}>(path+'/preview',{},notificationOptions());
        const value=closePreviewSchema.parse(response.data);
        if(value.issue_key!==issueKey)throw new Error('結清範圍與原通知不符，請重新核對。');
        setPreview(value);
      }else if(preview){
        closeIntent.current??={key:crypto.randomUUID(),reason:reason.trim(),preview};
        const command=closeIntent.current;
        sessionStorage.setItem(closeStorageKey,JSON.stringify(command));
        const response=await transport.post<{data:unknown}>(path+'/apply',{
          owner_snapshot_token:command.preview.owner_snapshot_token,
          preview_fingerprint:command.preview.preview_fingerprint,
          reason:command.reason,idempotency_key:command.key,
        },notificationOptions());
        const receipt=z.strictObject({issue_key:z.string(),replayed:z.boolean()}).parse(response.data);
        if(receipt.issue_key!==issueKey)throw new Error('結清收據與原通知不符。');
        sessionStorage.removeItem(closeStorageKey);
        closeIntent.current=null;setPreview(null);setReason('');
        await onCommitted();if(current.current)setRevision(value=>value+1);
      }
    }catch(error){if(current.current)setError('尚未確認結清，請重新核對原通知；重送會沿用原操作識別。'+notificationFailure(error));}
    finally{locked.current=false;if(current.current)setBusy(false);}
  };
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
    {recoveryError && <p role="alert">{recoveryError}</p>}
    <a className="np-button" href={`#line-management?tab=order_groups&group_q=${encodeURIComponent(detail?.case_no ?? '')}`}>本案案件群組設定</a>
    <a className="np-button" href="#line-management?tab=binding">LINE 身分綁定</a>
    <a className="np-button" href="#line-management?tab=push_queue">通知內容與規則設定</a>
    <button type="button" className="np-button" disabled={busy} onClick={()=>setRevision(v=>v+1)}>重新核對通知</button>
    {detail?.handling.blocked_reason && <p role="status">{detail.handling.blocked_reason}</p>}
    {detail?.handling.allowed_actions.includes('close') && <button className="np-button" disabled={busy || !!recoveryError || closeIntent.current!==null} onClick={()=>void close(false)}>不再寄送／結清</button>}
    {preview && <div aria-label="原通知結清範圍">
      <p>案件 {preview.case_no}，原通知 {preview.notification_reason}。停止以下範圍的後續寄送，保留通知與寄送歷史。</p>
      <p>來源事件：{preview.source_event_ids.join('、') || '無'}</p>
      {preview.tasks.map(task=><p key={task.task_id}>寄送工作 #{task.task_id}：{task.status}</p>)}
      <label>結清原因<input value={reason} disabled={busy || closeIntent.current!==null} onChange={event=>setReason(event.target.value)} /></label>
      <button className="np-button" disabled={busy || !!recoveryError || !reason.trim()} onClick={()=>void close(true)}>確認結清原通知</button>
    </div>}
    {detail?.sources.map(source=><div key={source.source_event_id}><p>原通知 #{source.source_event_id}</p>
      {source.unavailable_reason && <p>{source.unavailable_reason}</p>}
      <button type="button" className="np-button primary" disabled={busy || !detail.handling.allowed_actions.includes('replay') || !source.can_replay} onClick={()=>void replay(source.source_event_id)}>補送原通知 #{source.source_event_id}</button>
    </div>)}
    {showRelatedTasks && detail?.related_task_ids.map(id=><LineDeliveryTaskActions key={id} id={id} onCommitted={async()=>{await onCommitted();if(current.current)setRevision(v=>v+1);}} />)}
  </section>;
}

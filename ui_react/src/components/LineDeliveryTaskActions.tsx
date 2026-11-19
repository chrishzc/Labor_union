import { useEffect, useRef, useState } from 'react';
import { notificationOptions, notificationFailure } from '../api/line_notifications/notification_tasks_client';
import { transport } from '../api/shared/transport';
import { useUnsavedDraft } from './UnsavedChanges';
import './TaskOperation.css';
import { lineDeliveryQueryClient } from '../api/line_delivery/line_delivery_query_client';
import type { LineDeliveryDetail } from '../api/line_delivery/line_delivery_query_schemas';
import { LineNotificationFailureActions } from './LineNotificationFailureActions';
import { z } from 'zod';

export function LineDeliveryTaskActions({id,onCommitted}:{id:number;onCommitted:()=>Promise<void>}) {
  const [view,setView]=useState<LineDeliveryDetail|null>(null);
  const [error,setError]=useState(''),[busy,setBusy]=useState(false),[reason,setReason]=useState('');
  const [review,setReview]=useState(false),[revision,setRevision]=useState(0);
  const intent=useRef<{action:'retry'|'cancel';key:string;reason:string}|null>(null);
  const locked=useRef(false);
  const [recoveryError,setRecoveryError]=useState('');
  const storageKey=`line-delivery-close:${id}`;
  useEffect(()=>{
    try {
      const raw=sessionStorage.getItem(storageKey);
      if(raw){
        const saved=z.strictObject({task_id:z.number().int().positive(),action:z.literal('cancel'),key:z.string().uuid(),reason:z.string().min(1)}).parse(JSON.parse(raw));
        if(saved.task_id!==id)throw new Error('scope mismatch');
        intent.current={action:saved.action,key:saved.key,reason:saved.reason};setReason(saved.reason);setReview(true);
      }
    }catch{setRecoveryError('前次結清紀錄無法核對，請先確認原操作結果。');}
  },[id,storageKey]);
  useEffect(()=>{
    const abort=new AbortController();setView(null);setError('');
    void lineDeliveryQueryClient.detail(id,{signal:abort.signal})
      .then(value=>{if(!abort.signal.aborted)setView(value);})
      .catch(error=>{if(!abort.signal.aborted)setError(notificationFailure(error));});
    return()=>abort.abort();
  },[id,revision]);
  useUnsavedDraft('寄送工作',{reason},{busy});
  const control=async(action:'retry'|'cancel')=>{
    if(locked.current || recoveryError || !(view?.handling.allowed_actions.includes(action) || (action==='cancel' && (view?.handling.allowed_actions.includes('close') || intent.current?.action==='cancel'))))return;
    if(action==='cancel' && !reason.trim()){setError('請填寫結清原因。');return;}
    if(intent.current && intent.current.action!==action){setError('前次操作結果尚未確認，請重新核對原操作。');return;}
    locked.current=true;setBusy(true);setError('');
    intent.current??={action,key:crypto.randomUUID(),reason:reason.trim()};
    try {
      if(action==='cancel')sessionStorage.setItem(storageKey,JSON.stringify({...intent.current,task_id:id}));
      await transport.post(`/api/v1/line/tasks/${id}/${action}`,{
        reason:intent.current.reason,idempotency_key:intent.current.key,correlation_id:intent.current.key,
      },notificationOptions());
      if(action==='cancel')sessionStorage.removeItem(storageKey);
      intent.current=null;setReview(false);setReason('');
      setView(await lineDeliveryQueryClient.detail(id));await onCommitted();
    }catch(error){setError('尚未確認操作完成，請重新核對；重送會沿用原操作識別。'+notificationFailure(error));}
    finally{locked.current=false;setBusy(false);}
  };
  const handling=view?.handling;
  return <section aria-label="寄送工作處理"><h3>寄送工作 #{id}</h3>
    {error && <p role="alert">{error}</p>}
    {recoveryError && <p role="alert">{recoveryError}</p>}
    {intent.current?.action==='cancel' && <button className="np-button" disabled={busy || !!recoveryError} onClick={()=>void control('cancel')}>核對前次結清結果</button>}
    <button className="np-button" disabled={busy} onClick={()=>setRevision(value=>value+1)}>重新核對寄送工作</button>
    {view && handling && <>
      <p>已嘗試 {view.task.completed_attempts}／{view.task.max_attempts} 次</p>
      <p>排程時間：{view.task.scheduled_at}</p>
      {handling.blocked_reason && <p role="status">{handling.blocked_reason}</p>}
      {handling.allowed_actions.includes('retry') && view.task.next_retry_at && <p>下次重試：{view.task.next_retry_at}</p>}
      {handling.allowed_actions.includes('retry') && <button className="np-button primary" disabled={busy} onClick={()=>void control('retry')}>重試寄送工作</button>}
      {handling.target_kind==='notification_failure'
        ? <LineNotificationFailureActions issueKey={handling.target_identity} showRelatedTasks={false} onCommitted={async()=>{setRevision(value=>value+1);await onCommitted();}} />
        : handling.allowed_actions.some(action=>action==='cancel'||action==='close') && <>
          <button className="np-button" disabled={busy || !!recoveryError} onClick={()=>setReview(true)}>不再寄送／結清</button>
          {review && <div aria-label="結清範圍">
            <p>僅結清寄送工作 #{id}，來源 {view.task.source_type}，目前狀態 {view.task.status}。停止該工作的後續寄送，保留寄送歷史。</p>
            <label>結清原因<input value={reason} disabled={busy || intent.current!==null} onChange={event=>setReason(event.target.value)} /></label>
            <button className="np-button" disabled={busy || !reason.trim()} onClick={()=>void control('cancel')}>確認結清寄送工作</button>
          </div>}
        </>}
    </>}
  </section>;
}

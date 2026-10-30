import { useEffect, useRef, useState } from 'react';
import { notificationOptions, notificationFailure } from '../api/line_notifications/notification_tasks_client';
import { transport } from '../api/shared/transport';
import { useUnsavedDraft } from './UnsavedChanges';
import './TaskOperation.css';
import { lineDeliveryQueryClient } from '../api/line_delivery/line_delivery_query_client';
import type { LineDeliveryDetail } from '../api/line_delivery/line_delivery_query_schemas';
export function LineDeliveryTaskActions({id,onCommitted}:{id:number;onCommitted:()=>Promise<void>}) {
  const [view,setView]=useState<LineDeliveryDetail|null>(null);const [error,setError]=useState('');const [busy,setBusy]=useState(false);
  const intent=useRef<{action:string;key:string}|null>(null);const locked=useRef(false);
  useEffect(()=>{const abort=new AbortController();void lineDeliveryQueryClient.detail(id,{signal:abort.signal}).then(v=>{if(!abort.signal.aborted)setView(v);})
    .catch(e=>{if(!abort.signal.aborted)setError(notificationFailure(e));});return()=>abort.abort();},[id]);
  useUnsavedDraft('寄送工作',{}, {busy});
  const control=async(action:'retry'|'cancel')=>{
    if(locked.current)return;locked.current=true;setBusy(true);setError('');
    if(intent.current?.action!==action)intent.current={action,key:crypto.randomUUID()};
    try {
      await transport.post(`/api/v1/line/tasks/${id}/${action}`,{reason:'',idempotency_key:intent.current.key,correlation_id:intent.current.key},notificationOptions());
      intent.current=null;setView(await lineDeliveryQueryClient.detail(id));await onCommitted();
    }catch(e){setError(notificationFailure(e));}finally{locked.current=false;setBusy(false);}
  };
  return <section aria-label="寄送工作處理"><h3>寄送工作 #{id}</h3>{error && <p role="alert">{error}</p>}{view && <><p>已嘗試 {view.task.completed_attempts}／{view.task.max_attempts} 次</p>
    <p>排程時間：{view.task.scheduled_at}</p>{view.task.next_retry_at && <p>下次重試：{view.task.next_retry_at}</p>}
    <div className="notification-preview-actions">{['failed','retryable_failed'].includes(view.task.status) && <button className="np-button primary" disabled={busy} onClick={()=>void control('retry')}>重試寄送工作</button>}
      {['pending','retryable_failed'].includes(view.task.status) && <button className="np-button" disabled={busy} onClick={()=>void control('cancel')}>取消寄送工作</button>}</div><p>重試僅接續原寄送工作，不重做核銷或案件作業。</p></>}</section>;
}

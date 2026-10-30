import { useEffect, useRef, useState } from 'react';
import { z } from 'zod';
import { notificationOptions, notificationFailure } from '../api/line_notifications/notification_tasks_client';
import { transport } from '../api/shared/transport';
import { useUnsavedDraft } from './UnsavedChanges';
import './TaskOperation.css';
export const profileSchema=z.object({request_id:z.number(),client_id:z.number(),status:z.string(),request_version:z.number(),profile_version:z.number(),
  before:z.record(z.string(),z.string()),requested:z.record(z.string(),z.string()),reason:z.string()}).strict();
const profileLabels:Record<string,string>={name:'姓名',gender:'性別',phone:'電話',email:'電子郵件',city:'縣市',address:'地址',residence_type:'居住型態',delivery_type:'生產方式',baby_info:'寶寶資訊',notes:'備註',due_month:'預計日期',reject_reason:'不適合原因',service_type:'服務方式'};
export function ClientProfileRequestReview({id,onCommitted}:{id:number;onCommitted:()=>Promise<void>}) {
  const [view,setView]=useState<z.infer<typeof profileSchema>|null>(null);
  const [reason,setReason]=useState('');const [busy,setBusy]=useState(false);const [message,setMessage]=useState('');
  const [revision,setRevision]=useState(0),[loading,setLoading]=useState(true);
  const intent=useRef<{signature:string;key:string;fingerprint?:string}|null>(null);
  const locked=useRef(false);
  useEffect(()=>{const abort=new AbortController();setLoading(true);setMessage('');void transport.get<{data:unknown}>(`/api/v1/client-profile/requests/${id}`,notificationOptions(abort.signal))
    .then(raw=>{if(!abort.signal.aborted){const data=profileSchema.parse(raw.data);if(data.request_id!==id)throw new Error('申請編號不一致');setView(data);}})
    .catch(e=>{if(!abort.signal.aborted){setView(null);setMessage(notificationFailure(e));}}).finally(()=>{if(!abort.signal.aborted)setLoading(false);});return()=>abort.abort();},[id,revision]);
  useUnsavedDraft('客戶資料異動審核',{'原因':reason},{busy:busy||loading});
  const decide=async(approve:boolean)=>{
    if(!view || loading || view.status!=='pending' || locked.current)return;locked.current=true;setBusy(true);setMessage('');
    const signature=JSON.stringify([approve,reason,view.request_version]);
    if(intent.current?.signature!==signature)intent.current={signature,key:crypto.randomUUID()};
    const operation=intent.current;
    try {
      const base=`/api/v1/client-profile/requests/${id}`;
      const previewBody=approve?{expected_request_version:view.request_version}:{expected_request_version:view.request_version,reason:reason.trim()};
      if(!operation.fingerprint) {
        const raw=await transport.post<{data:unknown}>(base+(approve?'/approve/preview':'/reject/preview'),previewBody,notificationOptions());
        operation.fingerprint=z.object({preview_fingerprint:z.string(),apply_ready:z.literal(true)}).parse(raw.data).preview_fingerprint;
      }
      await transport.post(base+(approve?'/approve/apply':'/reject'),{...previewBody,...(approve?{expected_profile_version:view.profile_version}:{}),
        reason:reason.trim(),preview_fingerprint:operation.fingerprint,idempotency_key:operation.key,correlation_id:operation.key},notificationOptions());
      setReason('');setMessage(approve?'客戶資料已核准套用。':'資料異動已退回。');setView(null);await onCommitted().catch(()=>setMessage('資料異動已處理，待辦暫時無法更新，請重新整理。'));
    }catch(e){setMessage(notificationFailure(e));}finally{locked.current=false;setBusy(false);}
  };
  return <section aria-label="客戶資料異動審核"><h3>資料異動申請 #{id}</h3>{!view && !message && <p role="status">正在讀取指定申請…</p>}{view && <>{view.status!=='pending' && <p role="status">此申請已不在待審核狀態，不能重複處理。</p>}<dl>{Object.entries(view.requested).map(([key,value])=><div key={key}><dt>{profileLabels[key] ?? '其他資料'}</dt><dd>{view.before[key] || '未填'} → {value}</dd></div>)}</dl>
    <label>處理原因（選填）<textarea value={reason} disabled={busy} onChange={e=>setReason(e.target.value)} /></label>
    <div className="notification-preview-actions"><button className="np-button primary" disabled={busy || loading || view.status!=='pending'} onClick={()=>void decide(true)}>核准資料異動</button><button className="np-button" disabled={busy || loading || view.status!=='pending'} onClick={()=>void decide(false)}>退回資料異動</button></div></>}
    {message && <p role="status">{message}</p>}<button className="np-button" disabled={busy||loading} onClick={()=>setRevision(value=>value+1)}>重新讀取這筆申請</button></section>;
}

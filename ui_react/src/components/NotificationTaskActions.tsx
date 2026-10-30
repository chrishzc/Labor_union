/** Thin presenters reusing the original owner commands and workspaces. */
import { useEffect, useRef, useState } from 'react';
import { z } from 'zod';
import { notificationOptions, notificationFailure, type NotificationItem } from '../api/line_notifications/notification_tasks_client';
import { transport } from '../api/shared/transport';
import { customerServiceClient } from '../api/customer_service/customer_service_client';
import { adaptCustomerServiceDetail, type CustomerServiceDetailModel } from '../adapters/customer_service/customer_service_adapter';
import { LineCustomerServiceActions } from './LineCustomerServiceActions';
import { RegistrationApplications } from './RegistrationApplications';
import { ServiceStartSubstituteWorkbench } from './ServiceStartSubstituteWorkbench';
import { lineDeliveryQueryClient } from '../api/line_delivery/line_delivery_query_client';
import type { LineDeliveryDetail } from '../api/line_delivery/line_delivery_query_schemas';
import { useUnsavedDraft } from './UnsavedChanges';

export function notificationHref(item:NotificationItem):string | null {
  const caseNo = encodeURIComponent(item.case_no ?? '');
  switch(item.source) {
    case 'identity': return `#line-management?tab=binding&identity=reviews&review=${item.reference_id}`;
    case 'runtime': return '/line-mobile-admin?target=staff_review';
    case 'followup': return `#order-workbench-v2?case=${caseNo}&work=matching`;
    case 'recommendation': return item.reference_id ? null : `#order-workbench-v2?case=${caseNo}&work=${item.tag==='待簽約'?'contracts':'recommendation'}`;
    default: return null;
  }
}

export function NotificationTaskActions({item,onCommitted,sourceReadError}:{item:NotificationItem;onCommitted:()=>Promise<void>;sourceReadError?:string}) {
  if(item.source==='customer_binding' || item.source==='staff_binding') return <BindingReminder item={item} />;
  if(item.source==='registration') return <RegistrationApplications initialId={item.reference_id ?? undefined} onEditStateChange={()=>{}} onCommitted={onCommitted} />;
  if(item.source==='profile') return <ProfileReview id={item.reference_id!} onCommitted={onCommitted} />;
  if(item.source==='information') return <InformationActions item={item} onCommitted={onCommitted} sourceReadError={sourceReadError} />;
  if(item.source==='service_start') return <ServiceStartSubstituteWorkbench caseNo={item.case_no ?? undefined} onCompleted={onCommitted} />;
  if(item.source==='customer_service' || (item.source==='recommendation' && item.reference_id)) return <TicketActions id={item.reference_id!} onCommitted={onCommitted} />;
  if(item.source==='delivery') return <DeliveryActions id={item.reference_id!} onCommitted={onCommitted} />;
  if(item.source==='notification_failure') return <NotificationFailureActions item={item} onCommitted={onCommitted} />;
  if(item.source==='group') return <section aria-label="案件建群方式"><h3>建立與綁定案件群組</h3><pre style={{whiteSpace:'pre-wrap',font:'inherit'}}>{item.message}</pre><a className="np-button" href={`#line-management?tab=order_groups&group_q=${encodeURIComponent(item.case_no!)}`}>查看本案群組設定</a></section>;
  return null;
}

const failureDetailSchema=z.object({case_no:z.string(),notification_reason:z.enum(['recipient_unavailable','template_or_schedule_invalid']),
  related_task_ids:z.array(z.number().int().positive()),
  sources:z.array(z.object({source_event_id:z.number().int().positive(),event_code:z.string(),can_replay:z.boolean(),unavailable_reason:z.string().nullable()}).strict())}).strict();

function NotificationFailureActions({item,onCommitted}:{item:NotificationItem;onCommitted:()=>Promise<void>}) {
  const [detail,setDetail]=useState<z.infer<typeof failureDetailSchema>|null>(null);
  const [error,setError]=useState('');const [busy,setBusy]=useState(false);const [revision,setRevision]=useState(0);
  const intents=useRef<Record<number,string>>({});const locked=useRef(false);const current=useRef(true);
  useEffect(()=>{current.current=true;const abort=new AbortController();setDetail(null);setError('');
    void Promise.resolve().then(()=>transport.get<{data:unknown}>(`/api/v1/line/notification-task-actions/notification-failures/${item.failure!.issue_key}/query`,notificationOptions(abort.signal)))
      .then(raw=>{if(!abort.signal.aborted)setDetail(failureDetailSchema.parse(raw.data));})
      .catch(e=>{if(!abort.signal.aborted)setError(notificationFailure(e));});
    return()=>{current.current=false;abort.abort();};},[item.failure?.issue_key,revision]);
  useUnsavedDraft('通知補送',{}, {busy});
  const replay=async(id:number)=>{
    if(locked.current)return;locked.current=true;setBusy(true);setError('');
    const storageKey=`notification-replay:${item.failure!.issue_key}:${id}`;
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
    <a className="np-button" href={`#line-management?tab=order_groups&group_q=${encodeURIComponent(item.case_no ?? '')}`}>本案案件群組設定</a>
    <a className="np-button" href="#line-management?tab=binding">LINE 身分綁定</a>
    <a className="np-button" href="#line-management?tab=push_queue">通知內容與規則設定</a>
    <button type="button" className="np-button" disabled={busy} onClick={()=>setRevision(v=>v+1)}>重新核對通知</button>
    {detail?.sources.map(source=><div key={source.source_event_id}><p>原通知 #{source.source_event_id}</p>
      {source.unavailable_reason && <p>{source.unavailable_reason}</p>}
      <button type="button" className="np-button primary" disabled={busy || !source.can_replay} onClick={()=>void replay(source.source_event_id)}>補送原通知 #{source.source_event_id}</button>
    </div>)}
    {detail?.related_task_ids.map(id=><DeliveryActions key={id} id={id} onCommitted={async()=>{await onCommitted();if(current.current)setRevision(v=>v+1);}} />)}
  </section>;
}

function BindingReminder({item}:{item:NotificationItem}) {
  const [notice,setNotice]=useState('');
  const phone=(item.recipient ?? '').replace(/[\s-]/g,'');
  return <section aria-label="人工綁定提醒方式"><h3>聯絡 {item.person}</h3>
    {/^0\d{8,9}$/.test(phone)?<a className="np-button" href={`tel:${phone}`}>電話聯絡 {item.recipient}</a>:<p>尚無可用電話，請先核對聯絡資料。</p>}
    <button type="button" className="np-button" onClick={()=>void navigator.clipboard.writeText(item.message ?? '').then(()=>setNotice('已複製，請由您透過既有聯絡方式轉達。')).catch(()=>setNotice('無法複製，請直接選取上方提醒內容。'))}>複製綁定提醒</button>
    <a className="np-button" href={`#line-management?tab=binding&binding_role=${item.source==='customer_binding'?'customer':'staff'}&binding_q=${encodeURIComponent(item.person)}`}>查看綁定狀態</a>
    {item.case_no && <a className="np-button" href={`#clients?case=${encodeURIComponent(item.case_no)}`}>查看本案資料</a>}
    <p>聯絡後仍保留此事項；完成綁定{item.source==='customer_binding'?'、案件取消或完工':'、月嫂停用或退役'}後，重新查詢即移除。</p>
    {notice && <p role="status">{notice}</p>}
  </section>;
}

function TicketActions({id,onCommitted}:{id:number;onCommitted:()=>Promise<void>}) {
  const [detail,setDetail]=useState<CustomerServiceDetailModel|null>(null);
  const [error,setError]=useState('');
  useEffect(()=>{const abort=new AbortController();void customerServiceClient.getTicketDetail(id,{signal:abort.signal})
    .then(value=>{if(!abort.signal.aborted)setDetail(adaptCustomerServiceDetail(value));})
    .catch(e=>{if(!abort.signal.aborted)setError(notificationFailure(e));});return()=>abort.abort();},[id]);
  return <section aria-label="客服案件處理">{error && <p role="alert">{error}</p>}{!detail && !error && <p role="status">讀取客服案件…</p>}
    {detail && <><h3>客服案件 #{id}</h3><ul>{detail.events.filter(event=>event.messageText).map(event=><li key={event.id}>{event.messageText}</li>)}</ul>
      <LineCustomerServiceActions detail={detail} onCommitted={value=>{setDetail(value);void onCommitted().catch(()=>setError('客服案件已處理，待辦暫時無法更新，請重新整理。'));}} /></>}</section>;
}

const profileSchema=z.object({request_id:z.number(),client_id:z.number(),status:z.string(),request_version:z.number(),profile_version:z.number(),
  before:z.record(z.string(),z.string()),requested:z.record(z.string(),z.string()),reason:z.string()}).strict();
const profileLabels:Record<string,string>={name:'姓名',gender:'性別',phone:'電話',email:'電子郵件',city:'縣市',address:'地址',residence_type:'居住型態',delivery_type:'生產方式',baby_info:'寶寶資訊',notes:'備註',due_month:'預計日期',reject_reason:'不適合原因',service_type:'服務方式'};
function ProfileReview({id,onCommitted}:{id:number;onCommitted:()=>Promise<void>}) {
  const [view,setView]=useState<z.infer<typeof profileSchema>|null>(null);
  const [reason,setReason]=useState('');const [busy,setBusy]=useState(false);const [message,setMessage]=useState('');
  const intent=useRef<{signature:string;key:string;fingerprint?:string}|null>(null);
  const locked=useRef(false);
  useEffect(()=>{const abort=new AbortController();void transport.get<{data:unknown}>(`/api/v1/client-profile/requests/${id}`,notificationOptions(abort.signal))
    .then(raw=>{if(!abort.signal.aborted)setView(profileSchema.parse(raw.data));}).catch(e=>{if(!abort.signal.aborted)setMessage(notificationFailure(e));});return()=>abort.abort();},[id]);
  useUnsavedDraft('客戶資料異動審核',{'原因':reason},{busy});
  const decide=async(approve:boolean)=>{
    if(!view || locked.current)return;locked.current=true;setBusy(true);setMessage('');
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
  return <section aria-label="客戶資料異動審核"><h3>核對資料異動</h3>{view && <><dl>{Object.entries(view.requested).map(([key,value])=><div key={key}><dt>{profileLabels[key] ?? '其他資料'}</dt><dd>{view.before[key] || '未填'} → {value}</dd></div>)}</dl>
    <label>處理原因（選填）<textarea value={reason} disabled={busy} onChange={e=>setReason(e.target.value)} /></label>
    <div className="notification-preview-actions"><button className="np-button primary" disabled={busy || view.status!=='pending'} onClick={()=>void decide(true)}>核准資料異動</button><button className="np-button" disabled={busy || view.status!=='pending'} onClick={()=>void decide(false)}>退回資料異動</button></div></>}
    {message && <p role="status">{message}</p>}<a href="#line-management?tab=binding">前往 LINE 身分綁定</a></section>;
}

function InformationActions({item,onCommitted,sourceReadError}:{item:NotificationItem;onCommitted:()=>Promise<void>;sourceReadError?:string}) {
  const info=item.information!;
  const [text,setText]=useState('');const [busy,setBusy]=useState(false);const [message,setMessage]=useState('');
  const intent=useRef<{signature:string;key:string}|null>(null);const locked=useRef(false);
  useUnsavedDraft('月嫂確認與條件協調',{'發送文案':text},{busy});
  const waitingCustomer=!!info.customer_message && !(info.request_kind==='condition_adjustment' && info.customer_answer!==null);
  const customerBlocker=sourceReadError?'目前無法核對這筆需求，暫時不能發送。請重新核對後再試。':!info.customer_available?'這位客戶尚未綁定 LINE，目前無法發送訊息。請先聯絡客戶完成綁定，再按「重新核對」。':waitingCustomer?'已詢問客戶，請等待客戶回答後再接續處理。':null;
  const recheck=async()=>{setBusy(true);setMessage('');try{await onCommitted();}catch(e){setMessage(notificationFailure(e));}finally{setBusy(false);}};
  const send=async(recipient:'customer'|'caregiver')=>{
    if(locked.current || !text.trim() || info.review_completed || sourceReadError || (recipient==='customer' && customerBlocker))return;locked.current=true;setBusy(true);setMessage('');
    const signature=JSON.stringify([recipient,text.trim()]);
    if(intent.current?.signature!==signature)intent.current={signature,key:crypto.randomUUID()};
    try {
      const raw=await transport.post<{data:unknown}>(`/api/v1/line/notification-task-actions/information/${info.question_id}/send`,{
        recipient,message_text:text.trim(),idempotency_key:intent.current.key},notificationOptions());
      z.object({status:z.enum(['queued','idempotent_replay']),event_id:z.number().int().positive()}).strict().parse(raw.data);
      setText('');setMessage('已建立寄送工作，尚未證明送達。');intent.current=null;await onCommitted().catch(()=>setMessage('已建立寄送工作，待辦暫時無法更新，請重新整理。'));
    }catch(e){setMessage(notificationFailure(e));}finally{locked.current=false;setBusy(false);}
  };
  return <section aria-label="月嫂確認與條件協調"><h3>人員輸入發送文案</h3>{info.customer_message && <p>已詢問客戶：{info.customer_message}</p>}
    {info.customer_answer!==null && <p>客戶回答{info.request_kind==='condition_adjustment'?'的更新後條件':''}：{info.customer_answer || '未填文字'}</p>}
    <label>發送文案<textarea rows={4} maxLength={1000} value={text} disabled={busy || info.review_completed} onChange={e=>setText(e.target.value)} /></label>
    {info.review_completed?<p role="note">這筆需求已完成審核，無需再次發送；請接續下方重新詢問月嫂的步驟。</p>:!text.trim() && <p role="note">請先輸入要發送的文案，再選擇收件人。</p>}
    <div className="notification-preview-actions">{info.request_kind==='information_question' && <button className="np-button primary" disabled={busy || !text.trim() || info.review_completed || !!sourceReadError} onClick={()=>void send('caregiver')}>發送給月嫂</button>}
      <button className="np-button" aria-describedby={customerBlocker?'information-customer-blocker':undefined} disabled={busy || !text.trim() || info.review_completed || !!customerBlocker} onClick={()=>void send('customer')}>發送給客戶</button></div>
    {customerBlocker && <div className="notification-preview-blocker" role="note" id="information-customer-blocker"><p>{customerBlocker}</p>
      {!info.customer_available && <><a className="np-button" href="#line-management?tab=binding&binding_role=customer">查看客戶綁定方式與狀態</a><p>請客戶加入工會官方帳號，點選身分綁定並依畫面填寫姓名與電話。</p></>}
      {sourceReadError && <p>{sourceReadError}</p>}</div>}
    <button className="np-button" disabled={busy} onClick={()=>void recheck()}>重新核對</button>
    {info.request_kind==='condition_adjustment' && <AdjustmentReview information={info} onCommitted={onCommitted} />}
    {message && <p role="status">{message}</p>}</section>;
}

function DeliveryActions({id,onCommitted}:{id:number;onCommitted:()=>Promise<void>}) {
  const [view,setView]=useState<LineDeliveryDetail|null>(null);const [error,setError]=useState('');const [busy,setBusy]=useState(false);
  const intent=useRef<{action:string;key:string}|null>(null);const locked=useRef(false);
  useEffect(()=>{const abort=new AbortController();void lineDeliveryQueryClient.detail(id,{signal:abort.signal}).then(v=>{if(!abort.signal.aborted)setView(v);})
    .catch(e=>{if(!abort.signal.aborted)setError(notificationFailure(e));});return()=>abort.abort();},[id]);
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

// The approval panel uses the existing matching adjustment writer (see client).
import { AdjustmentReview } from './NotificationTermsReview';

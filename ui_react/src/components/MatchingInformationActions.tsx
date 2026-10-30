import { useRef, useState } from 'react';
import { z } from 'zod';
import { notificationOptions, notificationFailure, type NotificationItem } from '../api/line_notifications/notification_tasks_client';
import { transport } from '../api/shared/transport';
import { useUnsavedDraft } from './UnsavedChanges';
import './TaskOperation.css';
import { AdjustmentReview } from './NotificationTermsReview';
export function MatchingInformationActions({information:info,onCommitted,sourceReadError}:{information:NonNullable<NotificationItem['information']>;onCommitted:()=>Promise<void>;sourceReadError?:string}) {
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

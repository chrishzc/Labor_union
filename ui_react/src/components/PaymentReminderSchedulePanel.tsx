import { useEffect, useRef, useState } from 'react';
import { CalendarDays, Clock3, MessageCircle, Bell, Info } from 'lucide-react';
import { ApiHttpError } from '../api/shared/typed_errors';
import { PaymentReminderScheduleSchema,paymentReminderScheduleClient,type PaymentReminderSchedule,type PaymentReminderSettings,type PaymentReminderScheduleClient } from '../api/line_order_groups/payment_reminder_schedule_client';
import { useUnsavedDraft, useUnsavedNavigation } from './UnsavedChanges';
import './PaymentReminderSchedulePanel.css';

type Stage='deposit'|'first'|'second';
const names={deposit:'訂金',first:'第一期',second:'第二期'};
const copyError=(error:unknown,saving=false)=>error instanceof ApiHttpError&&error.status===409
  ?'排程已由其他人更新，已保留你的修改，請重新讀取後確認。'
  :error instanceof ApiHttpError&&error.status===403?'目前帳號沒有維護提醒排程的權限。'
  :saving?'儲存結果尚未確認，已保留原操作；重試會沿用相同操作識別。':'提醒排程暫時無法取得，請重新載入。';

function minutes(value:string){const [hour,minute]=value.split(':').map(Number);return hour*60+minute;}
function day(value:string){const [year,month,date]=value.split('-').map(Number);return Date.UTC(year,month-1,date);}
function stamp(value:number){return new Intl.DateTimeFormat('zh-TW',{timeZone:'UTC',month:'2-digit',day:'2-digit',weekday:'short',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(value));}

/** Display-only sample arithmetic. The server independently owns eligibility. */
export function paymentReminderPreview(dueDate:string,sentDate:string,sentTime:string,overdueTime:string){
  const original=day(sentDate)+minutes(sentTime)*60_000;
  const earliest=Math.max(day(dueDate)+86_400_000,original+86_400_000);
  let next=Math.floor(earliest/86_400_000)*86_400_000+minutes(overdueTime)*60_000;
  if(next<earliest)next+=86_400_000;
  return {original,earliest,next};
}

export function PaymentReminderSchedulePanel({client=paymentReminderScheduleClient}:{client?:PaymentReminderScheduleClient}){
  const {requestLeave}=useUnsavedNavigation();
  const [current,setCurrent]=useState<PaymentReminderSettings|null>(null);
  const [draft,setDraft]=useState<PaymentReminderSchedule|null>(null);
  const [error,setError]=useState('');const [notice,setNotice]=useState('');
  const [loading,setLoading]=useState(true);const [busy,setBusy]=useState(false);const [reload,setReload]=useState(0);
  const operation=useRef<string|null>(null);const sending=useRef(false);
  const [stage,setStage]=useState<Stage>('first');const [dueDate,setDueDate]=useState('2026-11-05');const [sentDate,setSentDate]=useState('2026-11-05');
  const [sentTime,setSentTime]=useState('14:30');const [reply,setReply]=useState('none');
  useEffect(()=>{const controller=new AbortController();setLoading(true);setError('');
    void client.get(controller.signal).then(value=>{if(!controller.signal.aborted){setCurrent(value);setDraft({...value.schedule});operation.current=null;}})
      .catch(error=>{if(!controller.signal.aborted)setError(copyError(error));}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();},[client,reload]);
  const valid=draft!==null&&PaymentReminderScheduleSchema.safeParse(draft).success;
  const dirty=current!==null&&draft!==null&&JSON.stringify(current.schedule)!==JSON.stringify(draft);
  async function save(){
    if(!draft||!current||!valid||sending.current)return;
    sending.current=true;setBusy(true);setError('');setNotice('');operation.current??=crypto.randomUUID();
    try{const result=await client.save({schedule:{...draft},expected_revision:current.revision,idempotency_key:operation.current});
      setCurrent(result);setDraft({...result.schedule});operation.current=null;setNotice('提醒排程已儲存，新建的提醒會套用這組時間。');
    }catch(error){setError(copyError(error,true));}finally{sending.current=false;setBusy(false);}
  }
  const guard=useUnsavedDraft('繳款提醒排程',draft??{}, {baseline:current?.schedule??null,enabled:!!draft,busy,save,discard:()=>{if(current)setDraft({...current.schedule});operation.current=null;}});
  function change<K extends keyof PaymentReminderSchedule>(field:K,value:PaymentReminderSchedule[K]){setDraft(previous=>previous?{...previous,[field]:value}:null);operation.current=null;setNotice('');}
  if(loading)return <p role="status">正在讀取提醒排程…</p>;
  if(!draft||!current)return <div><p role="alert">{error}</p><button type="button" className="finance-btn-secondary" onClick={()=>setReload(value=>value+1)}>重新載入提醒排程</button></div>;
  const sampleTime=stage==='deposit'&&draft.deposit_mode==='immediate'?sentTime:draft[`${stage}_time`];
  const preview=valid&&dueDate&&sentDate&&/^\d{2}:\d{2}$/.test(sampleTime)?paymentReminderPreview(dueDate,sentDate,sampleTime,draft.overdue_time):null;
  const replied=reply==='message'||reply==='button',settled=reply==='settled';
  return <section className="payment-reminder-settings" ref={guard} aria-labelledby="reminder-schedule-heading">
    <header className="reminder-settings-heading"><div><h2 id="reminder-schedule-heading">繳款提醒排程</h2><p>安排各期提醒與逾期補寄；所有繳款提醒均寄客戶私訊。</p></div><span><MessageCircle size={15}/>客戶私人聊天室 · 台北時間</span></header>
    {error&&<p role="alert" className="reminder-error">{error}</p>}{notice&&<p role="status" className="reminder-saved">{notice}</p>}
    <div className="reminder-settings-grid"><div>
      <section className="reminder-settings-card"><header><Clock3 size={20}/><div><h3>首次繳費提醒</h3><p>每期符合條件後，自動私訊客戶一次</p></div><small>UTC+8</small></header>
        <div className="reminder-time-rows">
          <div className="reminder-time-row"><strong>訂金</strong><div><p>雙方簽約完成，且繳費資料齊全</p><label className="reminder-field"><span className="sr-only">訂金提醒時機</span><select aria-label="訂金提醒時機" value={draft.deposit_mode} disabled={busy} onChange={event=>change('deposit_mode',event.target.value as 'immediate'|'daily')}><option value="immediate">資格齊備後立即寄送</option><option value="daily">齊備後的下一個固定時間</option></select></label></div><label className="reminder-field"><span>寄送時間</span><input aria-label="訂金寄送時間" type="time" value={draft.deposit_time} disabled={busy||draft.deposit_mode==='immediate'} onChange={event=>change('deposit_time',event.target.value)} required/></label></div>
          <div className="reminder-time-row"><strong>第一期</strong><div><p>正式服務開始當天</p><small>已結清時，僅保留服務開始問候。</small></div><label className="reminder-field"><span>寄送時間</span><input aria-label="第一期寄送時間" type="time" value={draft.first_time} disabled={busy} onChange={event=>change('first_time',event.target.value)} required/></label></div>
          <div className="reminder-time-row"><strong>第二期</strong><div><p>正式到期當天，且該期仍有餘額</p><small>不需第二期、金額為零或已結清則不寄。</small></div><label className="reminder-field"><span>寄送時間</span><input aria-label="第二期寄送時間" type="time" value={draft.second_time} disabled={busy} onChange={event=>change('second_time',event.target.value)} required/></label></div>
        </div><footer>未綁定客戶 LINE 或繳費資料不足時，保留人員待辦。</footer>
      </section>
      <section className="reminder-settings-card"><header><Bell size={20}/><div><h3>逾期自動補寄</h3><p>訂金、第一期、第二期各自判斷</p></div><small>每期最多補寄一次</small></header>
        <div className="reminder-overdue-body"><div className="reminder-overdue-time"><div><label htmlFor="payment-overdue-time">每日補寄檢查時間</label><p>條件齊備後，在下一個設定時間寄送。</p></div><input id="payment-overdue-time" aria-label="逾期補寄檢查時間" type="time" value={draft.overdue_time} disabled={busy} onChange={event=>change('overdue_time',event.target.value)} required/></div>
        <ul><li>雙方簽約完成，正式到期隔天起，該期仍有未核銷餘額。</li><li>距原繳費提醒成功送出已滿 <b>24 小時</b>。</li><li>客戶尚未回覆，且本期尚未自動補寄；不循環催款。</li></ul>
        <div className="reminder-reply-rule"><MessageCircle size={18}/><p>任何客戶私訊或按鈕回覆 → 停止自動補寄<small>改由人員手動提醒；未核銷款項仍保留待辦。</small></p></div></div>
      </section>
    </div><aside className="reminder-settings-card" aria-labelledby="reminder-preview-title"><header><CalendarDays size={20}/><div><h3 id="reminder-preview-title">寄送時間試算</h3><p>使用示範日期，不建立寄送工作</p></div></header>
      <div className="reminder-preview-body"><div className="reminder-preview-inputs">
        <label className="reminder-field"><span>款項期別</span><select value={stage} onChange={event=>setStage(event.target.value as Stage)} aria-label="試算款項期別">{Object.entries(names).map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label>
        <label className="reminder-field"><span>正式到期日</span><input aria-label="試算正式到期日" type="date" value={dueDate} onChange={event=>setDueDate(event.target.value)}/></label>
        <label className="reminder-field"><span>原提醒送出日</span><input aria-label="試算原提醒送出日" type="date" value={sentDate} onChange={event=>setSentDate(event.target.value)}/></label>
        <label className="reminder-field"><span>原提醒送出時間</span><input aria-label="試算原提醒送出時間" type="time" value={sampleTime} disabled={stage!=='deposit'||draft.deposit_mode!=='immediate'} onChange={event=>setSentTime(event.target.value)}/></label>
      </div><label className="reminder-field reminder-status-select"><span>模擬客戶狀態</span><select aria-label="模擬客戶狀態" value={reply} onChange={event=>setReply(event.target.value)}><option value="none">尚未回覆・尚未核銷</option><option value="message">已傳送私訊・尚未核銷</option><option value="button">已按鈕回覆・尚未核銷</option><option value="settled">已正式核銷結清</option></select></label>
        <div className="reminder-timeline" aria-live="polite">{preview&&Number.isFinite(preview.next)?<><div><span>原繳費提醒</span><strong>{stamp(preview.original)}</strong><small>寄送至客戶私人聊天室</small></div><div><span>補寄最早門檻</span><strong>{stamp(preview.earliest)}</strong><small>到期隔天起，且距原提醒滿 24 小時</small></div><div className={replied||settled?'reminder-timeline-stop':'reminder-timeline-next'}><span>{replied?'已停止自動補寄':settled?'提醒已結束':'預計自動補寄'}</span><strong>{replied?'改由人員手動提醒':settled?'已結清，不再催繳':stamp(preview.next)}</strong><small>{replied?'未核銷款項保留待辦':settled?'依正式核銷結果移除該期待辦':'在設定時段補寄，最多一次'}</small></div></>:<p>請補齊有效日期與時間。</p>}</div>
        <p className="reminder-preview-note"><Info size={16}/>回覆不等於入帳；款項依正式核銷結清。</p>
      </div></aside></div>
    <footer className="reminder-settings-actions"><p>儲存後套用於新建提醒；已提交的工作保留原快照。</p><div><button type="button" className="finance-btn-secondary" disabled={busy} onClick={()=>requestLeave(()=>setReload(value=>value+1))}>重新讀取</button><button type="button" className="finance-btn-secondary" disabled={busy||!dirty} onClick={()=>{setDraft({...current.schedule});operation.current=null;setError('');}}>還原已儲存設定</button><button type="button" className="finance-btn-primary" disabled={busy||!valid||!dirty} onClick={()=>void save()}>{busy?'儲存中…':'儲存提醒排程'}</button></div></footer>
    {!valid&&<p role="alert">請填寫完整且有效的提醒時間。</p>}
  </section>;
}

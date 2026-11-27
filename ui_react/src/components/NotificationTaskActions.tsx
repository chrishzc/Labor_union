/** Notification links and guidance for work performed outside this system. */
import { useRef, useState } from 'react';
import { hcmResubmissionClient, type HcmReviewSkipPreview } from '../api/case_import/hcm_resubmission_client';
import { importFieldIssueHref } from '../api/case_import/import_field_issues';
import { notificationTasksClient, notificationFailure, type NotificationItem } from '../api/line_notifications/notification_tasks_client';
export function notificationHref(item:NotificationItem):string | null {
  const caseNo = encodeURIComponent(item.case_no ?? '');
  switch(item.source) {
    case 'registration': return `#clients?tab=applications&registration=${item.reference_id}`;
    case 'staff_profile': return `#staff?profile_request=${item.reference_id}`;
    case 'import_fields': return item.case_no ? importFieldIssueHref(item.case_no, item.import_field_issues?.[0]) : null;
    case 'service_start': return `#scheduling?tab=coordination&case_no=${caseNo}&request=${item.reference_id}`;
    case 'delivery': return `#line-management?tab=delivery&task=${item.reference_id}`;
    case 'payment_receipt': return '#finance?'+new URLSearchParams({tab:'accounting-warnings',case_no:item.case_no??'',
      ...(item.receipt?{receipt_stage:item.receipt.payment_stage,settlement_identity:item.receipt.settlement_identity}:{})});
    case 'notification_failure': return `#line-management?tab=delivery&view=failures&issue=${encodeURIComponent(item.failure!.issue_key)}`;
    case 'identity': return `#line-management?tab=binding&identity=reviews&review=${item.reference_id}`;
    case 'runtime': return '/line-mobile-admin?target=staff_review';
    case 'followup': return `#order-workbench-v2?case=${caseNo}&work=matching`;
    case 'recommendation': return `#order-workbench-v2?case=${caseNo}&work=${item.tag==='待簽約'?'contracts':'recommendation'}`;
    default: return null;
  }
}

export function NotificationTaskActions({item,onCommitted}:{item:NotificationItem;onCommitted:()=>Promise<void>;sourceReadError?:string}) {
  if(item.source==='customer_binding' || item.source==='staff_binding') return <BindingReminder key={item.id} item={item} onCommitted={onCommitted} />;
  if(item.source==='group') return <section aria-label="案件建群方式"><h3>建立與綁定案件群組</h3><pre style={{whiteSpace:'pre-wrap',font:'inherit'}}>{item.message}</pre><a className="np-button" href={`#line-management?tab=order_groups&group_q=${encodeURIComponent(item.case_no!)}`}>查看本案群組設定</a></section>;
  return null;
}

export function OptionalImportFieldSkip({ caseNo, reviewIdentity, sourceField, onCommitted }: {
  caseNo: string; reviewIdentity: string; sourceField: string; onCommitted: () => Promise<void>;
}) {
  const [intent, setIntent] = useState<{ preview: HcmReviewSkipPreview; key: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [saved, setSaved] = useState(false);
  const locked = useRef(false);
  const run = async () => {
    if (locked.current || saved) return;
    locked.current = true;
    setBusy(true);
    setNotice('');
    try {
      if (!intent) {
        const preview = await hcmResubmissionClient.previewFieldSkip(reviewIdentity, sourceField, true);
        if (preview.case_no !== caseNo) throw new Error('案件已變更，請先重新整理。');
        setIntent({ preview, key: crypto.randomUUID() });
      } else {
        await hcmResubmissionClient.applyFieldSkip(intent.preview, intent.key, true);
        setSaved(true);
        setNotice('已記錄略過這一欄，正在更新待辦。');
        await onCommitted();
      }
    } catch (error) {
      setNotice(notificationFailure(error));
    } finally {
      locked.current = false;
      setBusy(false);
    }
  };
  return <div>
    {intent && !saved && <p>這一欄可以不補。確認後只略過這一欄，不會改動原資料。</p>}
    <button type="button" className="np-button" disabled={busy || saved} onClick={() => void run()}>
      {busy ? '處理中…' : saved ? '已記錄略過' : intent ? '確認略過此欄' : '略過此欄'}
    </button>
    {notice && <p role="status">{notice}</p>}
  </div>;
}

function BindingReminder({item,onCommitted}:{item:NotificationItem;onCommitted:()=>Promise<void>}) {
  const [notice,setNotice]=useState('');
  const [busy,setBusy]=useState(false);
  const command=useRef<{key:string;reason:string}|null>(null);
  const locked=useRef(false);
  const dismiss=async()=>{
    if(locked.current)return;
    locked.current=true;setBusy(true);
    command.current ??= {key:crypto.randomUUID(),reason:'使用者移除提醒'};
    try {await notificationTasksClient.dismissCustomerBinding(item,command.current.reason,command.current.key);setNotice('本案綁定提醒已移除。');await onCommitted();}
    catch(error){setNotice(notificationFailure(error));}
    finally{locked.current=false;setBusy(false);}
  };
  const phone=(item.recipient ?? '').replace(/[\s-]/g,'');
  return <section aria-label="人工綁定提醒方式"><h3>聯絡 {item.person}</h3>
    {/^0\d{8,9}$/.test(phone)?<a className="np-button" href={`tel:${phone}`}>電話聯絡 {item.recipient}</a>:<p>尚無可用電話，請先核對聯絡資料。</p>}
    <button type="button" className="np-button" onClick={()=>void navigator.clipboard.writeText(item.message ?? '').then(()=>setNotice('已複製，請由您透過既有聯絡方式轉達。')).catch(()=>setNotice('無法複製，請直接選取上方提醒內容。'))}>複製綁定提醒</button>
    <a className="np-button" href={`#line-management?tab=binding&binding_role=${item.source==='customer_binding'?'customer':'staff'}&binding_q=${encodeURIComponent(item.person)}`}>查看綁定狀態</a>
    {item.case_no && <a className="np-button" href={`#clients?case=${encodeURIComponent(item.case_no)}`}>查看本案資料</a>}
    <p>完成綁定{item.source==='customer_binding'?'、案件取消或完工':'、月嫂停用或退役'}後，重新整理即移除。</p>
    {item.source==='customer_binding' && item.reference_id && item.case_no && <button type="button" className="np-button" disabled={busy} onClick={()=>void dismiss()}>{busy?'處理中…':'移除提醒'}</button>}
    {notice && <p role="status">{notice}</p>}
  </section>;
}

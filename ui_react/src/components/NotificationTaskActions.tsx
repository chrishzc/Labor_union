/** Notification links and guidance for work performed outside this system. */
import { useState } from 'react';
import type { NotificationItem } from '../api/line_notifications/notification_tasks_client';
export function notificationHref(item:NotificationItem):string | null {
  const caseNo = encodeURIComponent(item.case_no ?? '');
  switch(item.source) {
    case 'registration': return `#clients?tab=applications&registration=${item.reference_id}`;
    case 'profile': return `#clients?tab=profile-requests&request=${item.reference_id}`;
    case 'information': return `#order-workbench-v2?case=${caseNo}&work=matching&question=${item.reference_id}`;
    case 'service_start': return `#scheduling?tab=coordination&case_no=${caseNo}&request=${item.reference_id}`;
    case 'delivery': return `#line-management?tab=delivery&task=${item.reference_id}`;
    case 'notification_failure': return `#line-management?tab=delivery&view=failures&issue=${encodeURIComponent(item.failure!.issue_key)}`;
    case 'identity': return `#line-management?tab=binding&identity=reviews&review=${item.reference_id}`;
    case 'runtime': return '/line-mobile-admin?target=staff_review';
    case 'followup': return `#order-workbench-v2?case=${caseNo}&work=matching`;
    case 'customer_service': return `#line-management?tab=tickets&ticket_q=${item.reference_id ?? ''}`;
    case 'recommendation': return item.reference_id ? `#line-management?tab=tickets&ticket_q=${item.reference_id}` : `#order-workbench-v2?case=${caseNo}&work=${item.tag==='待簽約'?'contracts':'recommendation'}`;
    default: return null;
  }
}

export function NotificationTaskActions({item}:{item:NotificationItem;onCommitted:()=>Promise<void>;sourceReadError?:string}) {
  if(item.source==='customer_binding' || item.source==='staff_binding') return <BindingReminder item={item} />;
  if(item.source==='group') return <section aria-label="案件建群方式"><h3>建立與綁定案件群組</h3><pre style={{whiteSpace:'pre-wrap',font:'inherit'}}>{item.message}</pre><a className="np-button" href={`#line-management?tab=order_groups&group_q=${encodeURIComponent(item.case_no!)}`}>查看本案群組設定</a></section>;
  return null;
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

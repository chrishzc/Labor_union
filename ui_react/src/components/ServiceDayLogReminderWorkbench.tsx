/** Union decides whether a missing-log reminder should be sent to the case group. */
import { useEffect, useRef, useState } from 'react';
import { serviceDayLogReminderClient, type ServiceDayLogReminderClient,
  type ServiceDayLogReminderPage, type ServiceDayLogReminder } from '../api/line_order_groups/service_day_log_reminder_client';

export function ServiceDayLogReminderWorkbench({client=serviceDayLogReminderClient}: {client?:ServiceDayLogReminderClient}) {
  const [page,setPage]=useState(1);
  const [reload,setReload]=useState(0);
  const [data,setData]=useState<ServiceDayLogReminderPage|null>(null);
  const [loading,setLoading]=useState(false);
  const [pending,setPending]=useState<string|null>(null);
  const [queued,setQueued]=useState<Record<string,boolean>>({});
  const [error,setError]=useState('');
  const [message,setMessage]=useState('');
  const keys=useRef(new Map<string,string>());
  useEffect(()=>{
    let active=true;
    setLoading(true);setError('');setData(null);
    client.list(page).then(value=>{if(active)setData(value);})
      .catch(()=>{if(active)setError('日誌提醒讀取失敗，請重新整理。');})
      .finally(()=>{if(active)setLoading(false);});
    return ()=>{active=false;};
  },[client,page,reload]);
  function identity(item:ServiceDayLogReminder) {return `${item.case_no}:${item.staff_id}:${item.missing_from}:${item.missing_through}`;}
  async function send(item:ServiceDayLogReminder) {
    if(pending)return;
    const id=identity(item);
    if(!keys.current.has(id))keys.current.set(id,crypto.randomUUID());
    setPending(id);setError('');setMessage('');
    try {
      const result=await client.send(item,keys.current.get(id)!);
      setQueued(value=>({...value,[id]:true}));
      setMessage(result.status==='cancelled' ? '提醒工作已取消，請重新整理缺漏紀錄。' : '已建立案件群組提醒寄送工作。');
    } catch(error) {
      setError(error instanceof Error ? error.message : '提醒建立失敗，請稍後以原操作重試。');
    } finally {setPending(null);}
  }
  return <section className="line-table-container" aria-labelledby="log-reminder-title">
    <div className="line-section-heading"><div><h2 id="log-reminder-title">服務日誌提醒</h2>
      <p>連續超過 3 日未填才列出，由工會決定是否提醒案件群組。</p></div>
      <button type="button" className="line-secondary-btn" disabled={loading||!!pending} onClick={()=>setReload(value=>value+1)}>重新整理日誌提醒</button></div>
    {error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
    {loading?<p role="status">正在讀取日誌提醒…</p>:data&&<>
      {data.items.length===0?<p>目前沒有連續超過 3 日未填的服務日誌。</p>:<div className="line-table-scroll"><table className="line-data-table">
        <thead><tr><th scope="col">案件群組</th><th scope="col">連續缺漏</th><th scope="col">操作</th></tr></thead>
        <tbody>{data.items.map(item=><tr key={identity(item)}><td>{item.group_label}</td><td>連續 {item.consecutive_days} 日</td>
          <td><button type="button" className="line-primary-btn" disabled={!item.can_send||!!pending||queued[identity(item)]}
            onClick={()=>void send(item)}>{queued[identity(item)]?'已建立寄送工作':pending===identity(item)?'建立中…':'發送提醒'}</button>
            {!item.can_send&&<span>尚無可用案件群組</span>}</td></tr>)}</tbody></table></div>}
      {data.total>data.page_size&&<nav aria-label="日誌提醒分頁"><button type="button" disabled={page<=1||!!pending} onClick={()=>setPage(value=>value-1)}>上一頁</button>
        <span>第 {page} 頁</span><button type="button" disabled={page*data.page_size>=data.total||!!pending} onClick={()=>setPage(value=>value+1)}>下一頁</button></nav>}
    </>}
  </section>;
}

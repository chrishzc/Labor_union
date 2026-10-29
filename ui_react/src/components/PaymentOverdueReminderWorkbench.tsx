/** Union-only overdue tasks; opening or refreshing never queues a message. */
import { useEffect,useRef,useState } from 'react';
import { ApiHttpError } from '../api/shared/typed_errors';
import { paymentOverdueReminderClient,type PaymentOverdueReminderClient,type PaymentOverdueTodo,type PaymentOverduePage } from '../api/line_order_groups/payment_overdue_reminder_client';
import './PaymentOverdueReminderWorkbench.css';

const names={deposit:'訂金',first:'第一期款',second:'第二期款'};
const statuses:Record<string,string>={pending:'待寄送',processing:'寄送中',sent:'已寄送',retryable_failed:'等待重試',failed:'寄送失敗',cancelled:'已取消'};
const inQueue=new Set(['pending','processing','retryable_failed']);
const identity=(item:PaymentOverdueTodo)=>JSON.stringify(item.payment);

export function PaymentOverdueReminderWorkbench({client=paymentOverdueReminderClient,onOpenBank}:{client?:PaymentOverdueReminderClient;onOpenBank?:(caseNo:string)=>void}) {
  const [data,setData]=useState<PaymentOverduePage|null>(null);
  const [page,setPage]=useState(1);
  const [reload,setReload]=useState(0);
  const [loading,setLoading]=useState(true);
  const [pending,setPending]=useState<string|null>(null);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const keys=useRef(new Map<string,string>());
  const busy=useRef(false);
  useEffect(()=>{
    const controller=new AbortController();setLoading(true);setData(null);setError('');
    void client.list(page,controller.signal).then(value=>{if(!controller.signal.aborted)setData(value);})
      .catch(()=>{if(!controller.signal.aborted)setError('繳款逾期待辦暫時無法取得，請重新整理。');})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return ()=>controller.abort();
  },[client,page,reload]);
  async function send(item:PaymentOverdueTodo) {
    if(busy.current)return;
    busy.current=true;const id=identity(item);setPending(id);setError('');setNotice('');
    const key=keys.current.get(id)??crypto.randomUUID();keys.current.set(id,key);
    try {
      await client.send(item,key);keys.current.delete(id);
      setNotice(`${item.payment.case_no} ${names[item.payment.payment_stage]}提醒已建立寄送工作；待辦會保留至核銷清償。`);
      setData(null);setReload(value=>value+1);
    } catch(caught) {
      if(caught instanceof ApiHttpError&&caught.status===409) {
        keys.current.delete(id);setData(null);setReload(value=>value+1);
        setNotice('款項或收件對象已變更，已重新查詢待辦，請確認最新資料。');
      } else if(caught instanceof ApiHttpError&&caught.status===403) {
        setError('目前帳號沒有發送提醒的權限。');
      } else {
        setError('寄送工作結果尚未確認；再次點擊「確認原操作結果」會沿用原操作，不重複建立。');
      }
    } finally {busy.current=false;setPending(null);}
  }
  return <section className="line-table-container payment-overdue-workbench" aria-labelledby="payment-overdue-title">
    <div className="line-section-heading"><div><h2 id="payment-overdue-title">逾期提醒</h2>
      <p>僅列雙方簽約完成且各期到期日已過、仍有未核銷餘額的款項。訂金提醒客戶私訊；第一、二期提醒案件群組。</p></div>
      <button className="line-secondary-btn" type="button" disabled={loading||!!pending} onClick={()=>setReload(value=>value+1)}>重新整理逾期待辦</button></div>
    {error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
    {loading?<p role="status">正在查詢各期繳款逾期待辦…</p>:data&&<>
      <p>共 {data.total} 筆；是否發送由工會逐次決定。</p>
      {!data.items.length?<p>目前沒有符合提醒資格的逾期款。</p>:<div className="line-table-scroll"><table className="line-data-table">
        <thead><tr><th scope="col">案件／期別</th><th scope="col">到期日</th><th scope="col">未核銷餘額</th><th scope="col">提醒對象</th><th scope="col">上次提醒</th><th scope="col">操作</th></tr></thead>
        <tbody>{data.items.map(item=><tr key={item.payment.obligation_identity}>
          <td>{item.payment.case_no}<br/>{names[item.payment.payment_stage]}</td><td>{item.payment.due_date}<br/>逾期 {item.overdue_days} 天</td>
          <td>NT$ {item.payment.remaining_amount_ntd.toLocaleString('zh-TW')}</td><td>{item.recipient_label}</td>
          <td>{item.last_reminder?<>{new Date(item.last_reminder.requested_at).toLocaleString('zh-TW',{timeZone:'Asia/Taipei'})}<br/>{statuses[item.last_reminder.status]??'結果待確認'}</>:'尚未提醒'}</td>
          <td><button type="button" className="line-primary-btn" disabled={!item.can_send||!!pending||!!item.last_reminder&&inQueue.has(item.last_reminder.status)} onClick={()=>void send(item)}>
            {pending===identity(item)?'建立中…':item.last_reminder&&inQueue.has(item.last_reminder.status)?'已建立寄送工作':keys.current.has(identity(item))?'確認原操作結果':'發送提醒'}</button>
            {item.unavailable_reason&&<p>{item.unavailable_reason}</p>}
            <p><a href={`#finance?tab=finance-import&case_no=${encodeURIComponent(item.payment.case_no)}`} onClick={event=>{if(onOpenBank){event.preventDefault();onOpenBank(item.payment.case_no);}}}>核對銀行入款</a></p></td>
        </tr>)}</tbody></table></div>}
      {data.total>data.page_size&&<nav aria-label="繳款逾期待辦分頁"><button type="button" disabled={page===1||!!pending} onClick={()=>setPage(value=>value-1)}>上一頁</button>
        <span>第 {page} 頁</span><button type="button" disabled={page*data.page_size>=data.total||!!pending} onClick={()=>setPage(value=>value+1)}>下一頁</button></nav>}
    </>}
  </section>;
}

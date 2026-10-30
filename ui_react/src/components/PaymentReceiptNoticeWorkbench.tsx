/** Committed receipt todos require a human click; queries never send. */
import { useEffect,useRef,useState } from 'react';
import { createPortal } from 'react-dom';
import { paymentReceiptClient,type PaymentReceiptClient,type PaymentReceiptPage,type PaymentReceiptTodo } from '../api/line_order_groups/payment_receipt_notification_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import './PaymentReceiptNoticeWorkbench.css';
const identity=(item:PaymentReceiptTodo)=>item.payment.payment_stage+':'+item.payment.settlement_identity;
const labels={deposit:'訂金',second:'第二期款'};
export function PaymentReceiptNoticeWorkbench({revision,expanded=false,client=paymentReceiptClient}:{revision:number;expanded?:boolean;client?:PaymentReceiptClient}){
  const [data,setData]=useState<PaymentReceiptPage|null>(null);const [page,setPage]=useState(1);const [reload,setReload]=useState(0);
  const [error,setError]=useState('');const [notice,setNotice]=useState('');const [busy,setBusy]=useState(false);
  const [opened,setOpened]=useState(false);const dialog=useRef<HTMLDialogElement>(null);const seen=useRef(new Set<string>());const sending=useRef(false);
  useEffect(()=>{const timer=window.setInterval(()=>setReload(value=>value+1),30000);return()=>window.clearInterval(timer);},[]);
  useEffect(()=>{const abort=new AbortController();void client.list(page,abort.signal).then(value=>{
    if(abort.signal.aborted)return;setData(value);setError('');
    if(value.items.some(item=>!seen.current.has(identity(item)))){value.items.forEach(item=>seen.current.add(identity(item)));setOpened(true);}
  }).catch(()=>{if(!abort.signal.aborted)setError('入帳通知待辦暫時無法取得，請重新整理。');});return()=>abort.abort();},[client,revision,page,reload]);
  useEffect(()=>{const node=dialog.current;if(!node)return;if(opened&&!node.open)node.showModal();if(!opened&&node.open)node.close();},[opened]);
  async function send(item:PaymentReceiptTodo){
    if(sending.current)return;sending.current=true;setBusy(true);setError('');setNotice('');
    try{await client.send(item);setNotice(`${item.payment.case_no} ${labels[item.payment.payment_stage]}入帳通知已建立人工寄送工作，尚未證明送達。`);setReload(value=>value+1);}
    catch(caught){if(caught instanceof ApiHttpError&&caught.status===409){setData(null);setReload(value=>value+1);setError('帳款或寄送狀態已變更，請核對最新待辦。');}
      else if(caught instanceof ApiHttpError&&caught.status===403)setError('目前帳號沒有發送入帳通知的權限。');
      else setError('寄送結果尚未確認；再次點擊會確認同一筆操作，不重複建立。');}
    finally{sending.current=false;setBusy(false);}
  }
  const contents=<><p>帳款已正式核銷，請核對案件與金額後手動發送客戶私訊。稍後處理仍會保留待辦。</p>
    {error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
    {data&&<><p>共 {data.total} 筆待確認。</p><div className="receipt-notice-scroll"><table className="finance-table"><thead><tr><th>案件／期別</th><th>入帳金額</th><th>操作</th></tr></thead><tbody>{data.items.map(item=><tr key={identity(item)}><td>{item.payment.case_no}<br/>{labels[item.payment.payment_stage]}</td><td>NT$ {item.payment.amount_ntd.toLocaleString('zh-TW')}</td><td><button type="button" disabled={busy||!item.can_send} onClick={()=>void send(item)}>發送入帳通知</button>{item.unavailable_reason&&<p>{item.unavailable_reason}</p>}</td></tr>)}</tbody></table></div>{!data.items.length&&<p>目前沒有待發送的入帳通知。</p>}
      {data.total>data.page_size&&<nav aria-label="入帳通知分頁"><button type="button" disabled={busy||page===1} onClick={()=>setPage(value=>value-1)}>上一頁</button><span>第 {page} 頁</span><button type="button" disabled={busy||page*data.page_size>=data.total} onClick={()=>setPage(value=>value+1)}>下一頁</button></nav>}</>}
    <button type="button" disabled={busy} onClick={()=>setReload(value=>value+1)}>重新整理入帳待辦</button></>;
  return <section className="receipt-notice-workspace" aria-label="入帳通知待辦">
    {expanded?<><h2>入帳通知待辦</h2>{!opened&&contents}</>:<><button type="button" onClick={()=>setOpened(true)}>入帳通知待辦{data?`（${data.total}）`:''}</button>{error&&!opened&&<p role="alert">{error}</p>}</>}
    {createPortal(<dialog ref={dialog} className="receipt-notice-dialog" aria-labelledby="receipt-notice-title" onCancel={event=>{event.preventDefault();if(!busy)setOpened(false);}}><h2 id="receipt-notice-title">帳款已入帳，請確認是否通知客戶</h2>{opened&&contents}<button type="button" disabled={busy} onClick={()=>setOpened(false)}>稍後處理，保留待辦</button></dialog>,document.body)}
  </section>;
}

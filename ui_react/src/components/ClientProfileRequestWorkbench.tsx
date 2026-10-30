import { useCallback, useEffect, useState } from 'react';
import { z } from 'zod';
import { ClientProfileRequestReview, profileSchema } from './ClientProfileRequestReview';
import { transport } from '../api/shared/transport';
import { notificationOptions, notificationFailure } from '../api/line_notifications/notification_tasks_client';
import { useUnsavedNavigation } from './UnsavedChanges';
import './TaskOperation.css';

const pageSchema=z.object({items:z.array(profileSchema),total:z.number(),page:z.number(),page_size:z.number()});
export function ClientProfileRequestWorkbench({requestId}:{requestId?:string}) {
  const initial=Number(requestId);
  const invalid=!!requestId && (!Number.isSafeInteger(initial) || initial<=0);
  const [selected,setSelected]=useState<number|null>(requestId && !invalid?initial:null);
  const [page,setPage]=useState(1),[reload,setReload]=useState(0);
  const [result,setResult]=useState<z.infer<typeof pageSchema>|null>(null);
  const [error,setError]=useState('');
  const {requestLeave}=useUnsavedNavigation();
  const refresh=useCallback(async()=>{setReload(value=>value+1);},[]);
  useEffect(()=>{const abort=new AbortController();setResult(null);setError('');
    void transport.get<{data:unknown}>('/api/v1/client-profile/requests',{...notificationOptions(abort.signal),params:{status:'pending',page,page_size:25}})
      .then(raw=>{if(!abort.signal.aborted)setResult(pageSchema.parse(raw.data));})
      .catch(e=>{if(!abort.signal.aborted)setError(notificationFailure(e));});return()=>abort.abort();
  },[page,reload]);
  return <section className="task-operation-workspace" aria-label="客戶資料異動作業">
    <header><h2>客戶資料異動審核</h2><button className="np-button" onClick={()=>requestLeave(()=>{void refresh();})}>重新查詢</button></header>
    {invalid?<p role="alert">申請編號無效，請從通知事項重新開啟。</p>:<>
      {error && <p role="alert">{error}</p>}{!result && !error && <p role="status">正在查詢資料異動…</p>}
      {result && <><p>{result.total} 筆待審核申請</p><div className="task-operation-selector">{result.items.map(item=><button className="np-button" key={item.request_id} aria-pressed={selected===item.request_id} onClick={()=>requestLeave(()=>{setSelected(item.request_id);const params=new URLSearchParams(window.location.hash.split('?')[1]);params.set('request',String(item.request_id));window.history.replaceState(null,'',`#clients?${params}`);})}>申請 #{item.request_id} · 客戶 #{item.client_id}</button>)}</div>
        {result.total>25 && <nav aria-label="資料異動申請分頁"><button disabled={page===1} onClick={()=>setPage(value=>value-1)}>上一頁</button><span>第 {page} 頁</span><button disabled={page*25>=result.total} onClick={()=>setPage(value=>value+1)}>下一頁</button></nav>}</>}
      {selected!==null?<div className="notification-task-operation"><ClientProfileRequestReview key={selected} id={selected} onCommitted={refresh}/></div>:<p>選擇一筆申請查看異動前後內容。</p>}
    </>}
  </section>;
}

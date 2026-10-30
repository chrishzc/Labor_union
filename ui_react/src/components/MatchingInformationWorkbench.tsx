import { useCallback, useEffect, useState } from 'react';
import { z } from 'zod';
import { MatchingInformationActions } from './MatchingInformationActions';
import { informationSchema, notificationFailure, notificationOptions } from '../api/line_notifications/notification_tasks_client';
import { transport } from '../api/shared/transport';
import { ApiHttpError } from '../api/shared/typed_errors';
import { useUnsavedNavigation } from './UnsavedChanges';
import './TaskOperation.css';
const pageSchema=z.object({items:z.array(informationSchema),total:z.number(),page:z.number(),page_size:z.number()});
export function MatchingInformationWorkbench({caseNo,questionId}:{caseNo:string;questionId?:string}) {
  const invalid=!!questionId && (!Number.isSafeInteger(Number(questionId)) || Number(questionId)<=0);
  const [selected,setSelected]=useState<number|null>(questionId && !invalid?Number(questionId):null);
  const [page,setPage]=useState(1),[revision,setRevision]=useState(0);
  const [result,setResult]=useState<z.infer<typeof pageSchema>|null>(null);
  const [detail,setDetail]=useState<z.infer<typeof informationSchema>|null>(null);
  const [error,setError]=useState(''),[detailError,setDetailError]=useState(''),[checking,setChecking]=useState(false);
  const {requestLeave}=useUnsavedNavigation();
  const refresh=useCallback(async()=>{setRevision(value=>value+1);},[]);
  const path='/api/v1/line/notification-task-actions/information';
  useEffect(()=>{const abort=new AbortController();setResult(null);setError('');
    if(invalid)return;
    void transport.get<{data:unknown}>(path,{...notificationOptions(abort.signal),params:{case_no:caseNo,page}})
      .then(raw=>{if(!abort.signal.aborted)setResult(pageSchema.parse(raw.data));})
      .catch(e=>{if(!abort.signal.aborted)setError(notificationFailure(e));});return()=>abort.abort();
  },[caseNo,page,revision,invalid]);
  useEffect(()=>{if(selected===null)return;const abort=new AbortController();setChecking(true);setDetailError('');
    void transport.get<{data:unknown}>(`${path}/${selected}/query`,{...notificationOptions(abort.signal),params:{case_no:caseNo}})
      .then(raw=>{if(abort.signal.aborted)return;const value=informationSchema.parse(raw.data);if(value.question_id!==selected || value.case_no!==caseNo)throw new Error('需求回應與目前案件不一致');setDetail(value);})
      .catch(e=>{if(!abort.signal.aborted){if(e instanceof ApiHttpError && e.status===404)setDetail(null);setDetailError(notificationFailure(e));}})
      .finally(()=>{if(!abort.signal.aborted)setChecking(false);});return()=>abort.abort();
  },[caseNo,selected,revision]);
  return <section className="task-operation-workspace" aria-label="確認資訊與調整條件作業">
    <header><h3>確認資訊與調整條件</h3><button className="np-button" onClick={()=>void refresh()}>重新查詢問題</button></header>
    {invalid?<p role="alert">問題編號無效，請從通知事項重新開啟。</p>:<>
      {error && <p role="alert">{error}</p>}{!result && !error && <p role="status">正在查詢本案問題…</p>}
      {result && <><p>本案 {result.total} 筆待處理問題</p><div className="task-operation-selector">{result.items.map(item=><button className="np-button" key={item.question_id} aria-pressed={selected===item.question_id} onClick={()=>requestLeave(()=>{setSelected(item.question_id);const params=new URLSearchParams(window.location.hash.split('?')[1]);params.set('question',String(item.question_id));window.history.replaceState(null,'',`#order-workbench-v2?${params}`);})}>問題 #{item.question_id} · {item.staff_name}</button>)}</div>
        {result.total>25 && <nav aria-label="案件問題分頁"><button disabled={page===1} onClick={()=>setPage(value=>value-1)}>上一頁</button><span>第 {page} 頁</span><button disabled={page*25>=result.total} onClick={()=>setPage(value=>value+1)}>下一頁</button></nav>}</>}
      {checking && <p role="status">正在核對指定問題…</p>}{detailError && <p role="alert">{detailError}</p>}
      {detail && detail.question_id===selected && <div className="notification-task-operation"><h4>問題 #{detail.question_id} · {detail.staff_name}</h4><dl>{detail.issues.map((issue,index)=><div key={index}><dt>{issue.label}</dt><dd>{issue.detail}</dd></div>)}</dl><MatchingInformationActions key={detail.question_id} information={detail} sourceReadError={checking?'正在核對目前問題，請稍候。':detailError || undefined} onCommitted={refresh}/></div>}
    </>}
  </section>;
}

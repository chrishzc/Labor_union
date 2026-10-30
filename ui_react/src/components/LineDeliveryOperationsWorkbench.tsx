import { useCallback, useEffect, useState } from 'react';
import { LineDeliveryTaskWorkbench } from './LineDeliveryTaskWorkbench';
import { LineDeliveryTaskActions } from './LineDeliveryTaskActions';
import { LineNotificationFailureActions } from './LineNotificationFailureActions';
import { notificationTasksClient, notificationFailure, type NotificationPage } from '../api/line_notifications/notification_tasks_client';
import { useUnsavedNavigation } from './UnsavedChanges';
import './TaskOperation.css';

export function LineDeliveryOperationsWorkbench() {
  const initial=new URLSearchParams(window.location.hash.split('?')[1]);
  const [failures,setFailures]=useState(initial.get('view')==='failures');
  const [task,setTask]=useState(initial.get('task') ?? '');
  const [issue,setIssue]=useState(initial.get('issue') ?? '');
  const [cursor,setCursor]=useState<number|string>(0),[revision,setRevision]=useState(0);
  const [result,setResult]=useState<NotificationPage|null>(null),[error,setError]=useState('');
  const {requestLeave}=useUnsavedNavigation();
  const refresh=useCallback(async()=>{setRevision(value=>value+1);},[]);
  const navigate=(nextFailures:boolean,nextTask='',nextIssue='')=>requestLeave(()=>{
    setFailures(nextFailures);setTask(nextTask);setIssue(nextIssue);setCursor(0);
    const params=new URLSearchParams(window.location.hash.split('?')[1]);
    params.set('tab','delivery');params.delete('task');params.delete('issue');params.delete('view');
    if(nextFailures)params.set('view','failures');if(nextTask)params.set('task',nextTask);if(nextIssue)params.set('issue',nextIssue);
    window.history.replaceState(null,'',`#line-management?${params}`);
  });
  useEffect(()=>{if(!failures)return;const abort=new AbortController();setResult(null);setError('');
    void notificationTasksClient.list('notification_failure',cursor,abort.signal)
      .then(value=>{if(!abort.signal.aborted)setResult(value);}).catch(e=>{if(!abort.signal.aborted)setError(notificationFailure(e));});return()=>abort.abort();
  },[failures,cursor,revision]);
  const invalidTask=!!task && (!Number.isSafeInteger(Number(task)) || Number(task)<=0);
  const invalidIssue=!!issue && !/^ci_[0-9a-f]{64}$/.test(issue);
  return <section className="task-operation-workspace" aria-label="LINE 寄送與異常作業">
    <header><h2>寄送與異常</h2><nav className="task-operation-selector" aria-label="寄送與異常分類"><button className="np-button" aria-pressed={!failures} onClick={()=>navigate(false)}>寄送工作</button><button className="np-button" aria-pressed={failures} onClick={()=>navigate(true)}>通知建立異常</button></nav></header>
    {failures?<>
      {invalidIssue?<p role="alert">異常編號無效，請從通知事項重新開啟。</p>:issue && <div className="notification-task-operation"><LineNotificationFailureActions key={issue} issueKey={issue} onCommitted={refresh}/></div>}
      {error && <p role="alert">{error}</p>}{!result && !error && <p role="status">正在查詢通知建立異常…</p>}
      {result && <><div className="task-operation-selector">{result.items.map(item=><button className="np-button" key={item.id} aria-pressed={issue===item.failure?.issue_key} onClick={()=>navigate(true,'',item.failure!.issue_key)}>{item.case_no} · {item.summary}</button>)}</div>
        {!result.items.length && <p>此頁沒有通知建立異常。</p>}{result.next_cursor!==null && <button className="np-button" onClick={()=>setCursor(result.next_cursor!)}>載入下一頁異常</button>}{cursor!==0 && <button className="np-button" onClick={()=>setCursor(0)}>回第一頁</button>}</>}
    </>:<>
      {invalidTask?<p role="alert">寄送工作編號無效，請從通知事項重新開啟。</p>:task && <div className="notification-task-operation"><LineDeliveryTaskActions key={task} id={Number(task)} onCommitted={refresh}/></div>}
      <LineDeliveryTaskWorkbench reloadToken={revision} onOpenTask={id=>navigate(false,String(id))}/>
    </>}
  </section>;
}

import { useCallback, useEffect, useState } from 'react';
import { ApiHttpError } from '../api/shared/typed_errors';
import { serviceStartClient, type ServiceStartView, type StartCommand, type HandoverContext, type HandoverInquiry } from '../api/scheduling/service_start_client';
import './ServiceStartSubstituteWorkbench.css';

interface Props {caseNo?:string;onCompleted?:()=>Promise<void>}
interface Pending {id:number;action:'inquire'|'invite'|'dates'|'defer';body:StartCommand}
const storageKey=(id:number)=>`service-start-command:${id}`;
const willingness={pending:'等待月嫂回覆',willing:'願意代班',unwilling:'無法代班'};
const invitationLabels:Record<string,string>={pending:'待寄送',processing:'寄送中',sent:'已寄送',failed:'寄送失敗',cancelled:'已取消'};

export function ServiceHandoverWorkbench({caseNo,assignmentId}:{caseNo:string;assignmentId?:number}) {
  const [context,setContext]=useState<HandoverContext|null>(null);
  const [options,setOptions]=useState<{staff_id:number;name:string}[]>([]);
  const [keyword,setKeyword]=useState('');
  const [staff,setStaff]=useState('');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const key=`service-handover-command:${caseNo}:${assignmentId??''}`;
  const [pending,setPending]=useState<HandoverInquiry|null>(()=>{try{return JSON.parse(sessionStorage.getItem(key)??'null') as HandoverInquiry|null;}catch{return null;}});
  const refresh=useCallback(async()=>{setBusy(true);setError('');try {
    const [result,staffOptions]=await Promise.all([serviceStartClient.handoverContext(caseNo,assignmentId),serviceStartClient.options()]);
    setContext(result);setOptions(staffOptions.items);
  }catch(e){setError(e instanceof Error?e.message:'換人資料載入失敗。');}finally{setBusy(false);}},[caseNo,assignmentId]);
  useEffect(()=>{void refresh();},[refresh]);
  const send=async(body:HandoverInquiry)=>{setBusy(true);setError('');setPending(body);sessionStorage.setItem(key,JSON.stringify(body));
    try {const request=await serviceStartClient.inquireHandover(body);setContext(current=>current?{...current,request}:current);
      setPending(null);sessionStorage.removeItem(key);
    }catch(e){setError(e instanceof Error?e.message:'尚無法確認詢問結果。');
      if(e instanceof ApiHttpError && e.status>=400 && e.status<500){setPending(null);sessionStorage.removeItem(key);}
    }finally{setBusy(false);}};
  const search=async()=>{setBusy(true);setError('');try{setOptions((await serviceStartClient.options(keyword)).items);}catch(e){setError(e instanceof Error?e.message:'人選查詢失敗。');}finally{setBusy(false);}};
  return <section className="service-start-workbench" aria-label="服務中換人作業">
    <header><h2>案件 {caseNo}</h2><button type="button" disabled={busy} onClick={()=>void refresh()}>重新查詢換人資料</button></header>
    {busy && <p role="status">正在處理…</p>}{error && <p role="alert">{error}</p>}
    {pending && <p>這筆詢問結果尚未確認。<button type="button" disabled={busy} onClick={()=>void send(pending)}>確認原操作結果</button></p>}
    {context && !context.request && <article className="service-start-card"><h3>原月嫂：{context.staff_name}</h3>
      <p>原區段剩餘 {context.service_dates.length} 個服務日：{context.service_dates.join('、')}</p>
      <p>詢問接任意願 → 邀請加入原案件群組 → 工會填交接日 → 更新剩餘排班與帳務。</p>
      <fieldset disabled={busy || pending!==null}><legend>選擇接任月嫂</legend>
        <label>月嫂姓名<input aria-label="搜尋月嫂姓名" maxLength={50} value={keyword} onChange={e=>setKeyword(e.target.value)}/></label>
        <button type="button" onClick={()=>void search()}>搜尋代班月嫂</button>
        <label>接任月嫂<select aria-label="接任月嫂" value={staff} onChange={e=>setStaff(e.target.value)}><option value="">請選擇月嫂</option>
          {options.filter(option=>option.staff_id!==context.staff_id).map(option=><option key={option.staff_id} value={option.staff_id}>{option.name}</option>)}</select></label>
        <button type="button" disabled={!staff} onClick={()=>void send({case_no:caseNo,assignment_id:context.assignment_id,staff_id:Number(staff),
          expected_order_version:context.order_version,expected_scheduling_version:context.scheduling_version,idempotency_key:crypto.randomUUID()})}>詢問該月嫂意願</button>
      </fieldset></article>}
    {context?.request && !pending && <SubstituteCard key={context.request.request_id} initial={context.request} options={options}/>}
  </section>;
}

export function ServiceStartSubstituteWorkbench({caseNo,onCompleted}:Props) {
  const [page,setPage]=useState(1);
  const [total,setTotal]=useState(0);
  const [items,setItems]=useState<ServiceStartView[]>([]);
  const [error,setError]=useState('');
  const [loading,setLoading]=useState(false);
  const [options,setOptions]=useState<{staff_id:number;name:string}[]>([]);
  const refresh=useCallback(async()=>{
    setLoading(true);setError('');
    try {const result=await serviceStartClient.todos(page,caseNo);
      const recovered:ServiceStartView[]=[];
      for(let i=0;i<sessionStorage.length;i++) {
        const key=sessionStorage.key(i);
        if(!key?.startsWith('service-start-command:')) continue;
        const id=Number(key.split(':')[1]);
        if(!Number.isSafeInteger(id) || result.items.some(item=>item.request_id===id)) continue;
        const item=await serviceStartClient.detail(id);
        if(!caseNo || item.case_no===caseNo) recovered.push(item);
      }
      setItems([...result.items,...recovered]);setTotal(result.total);
      if(result.items.length===0 && page>1 && result.total>0) setPage(Math.max(1,Math.ceil(result.total/25)));
      const staff=await serviceStartClient.options();setOptions(staff.items);
    } catch(e) {setError(e instanceof Error?e.message:'代班待辦載入失敗。');}
    finally {setLoading(false);}
  },[page,caseNo]);
  useEffect(()=>{void refresh();},[refresh]);
  return <section className="service-start-workbench" aria-label="服務開始、請假與代班待辦">
    <header><h2>服務開始、請假與代班待辦</h2><span>{total} 件待處理</span><button type="button" disabled={loading} onClick={()=>void refresh()}>重新查詢代班待辦</button></header>
    {error && <p role="alert">{error}</p>}
    {loading && <p role="status">正在查詢…</p>}
    {!loading && !error && items.length===0 && <p>目前沒有需要工會處理的排程衝突或代班。</p>}
    {items.map(item=><SubstituteCard key={item.request_id} initial={item} options={options} onCompleted={async()=>{setTotal((await serviceStartClient.todos(page,caseNo)).total);await onCompleted?.();}}/>)}
    {total>25 && <nav aria-label="代班待辦分頁"><button type="button" disabled={page===1 || loading} onClick={()=>setPage(p=>p-1)}>上一頁</button><span>{page} / {Math.ceil(total/25)}</span><button type="button" disabled={page*25>=total || loading} onClick={()=>setPage(p=>p+1)}>下一頁</button></nav>}
  </section>;
}

function SubstituteCard({initial,options,onCompleted}:{initial:ServiceStartView;options:{staff_id:number;name:string}[];onCompleted?:()=>Promise<void>}) {
  const [item,setItem]=useState(initial);
  useEffect(()=>setItem(initial),[initial]);
  const [staffId,setStaffId]=useState('');
  const [keyword,setKeyword]=useState('');
  const [found,setFound]=useState<typeof options|null>(null);
  const search=async()=>{setBusy(true);setError('');try{setFound((await serviceStartClient.options(keyword)).items);}catch(e){setError(e instanceof Error?e.message:'人選查詢失敗。');}finally{setBusy(false);}};
  const [start,setStart]=useState(initial.workflow_kind==='leave'?initial.leave_dates[0]?.original_date??'':initial.workflow_kind==='handover'?initial.requested_start_date??initial.proposed_start_date??'':initial.proposed_start_date??initial.requested_start_date??'');
  const [end,setEnd]=useState(initial.workflow_kind==='leave'?initial.leave_dates.at(-1)?.original_date??'':'');
  const [dateChanges,setDateChanges]=useState<Record<string,string>>(()=>Object.fromEntries((initial.leave_dates??[]).map(d=>[d.original_date,d.new_date??d.original_date])));
  const [pending,setPending]=useState<Pending|null>(()=>{
    try {const value=sessionStorage.getItem(storageKey(initial.request_id));return value?JSON.parse(value) as Pending:null;} catch {return null;}
  });
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [choosing,setChoosing]=useState(false);
  const [recordDefer,setRecordDefer]=useState(Boolean(initial.conflict_message));
  const command=async(saved:Pending)=>{
    setBusy(true);setError('');setNotice('');
    setPending(saved);sessionStorage.setItem(storageKey(item.request_id),JSON.stringify(saved));
    try {const result=await serviceStartClient.command(saved.id,saved.action,saved.body);
      setItem(result);setPending(null);sessionStorage.removeItem(storageKey(item.request_id));setChoosing(false);
      setNotice(result.status==='applied'?(result.result?.group_record_queued?'服務日期與排班已更新，日期表已交付寄送。':'正式排班已更新；本案尚缺服務群組，請先完成群組設定。'):saved.action==='invite'?'群組邀請已排入寄送，請等待月嫂加入。':saved.action==='inquire'?'代班意願詢問已排入寄送。':'仍需處理代班，請核對日期與檔期。');
      if(result.status==='applied') await onCompleted?.();
    } catch(e) {setError(e instanceof Error?e.message:'尚無法確認處理結果。');
      if(e instanceof ApiHttpError && e.status>=400 && e.status<500) {setPending(null);sessionStorage.removeItem(storageKey(item.request_id));}
    } finally {setBusy(false);}
  };
  const run=(action:Pending['action'],fields:Partial<StartCommand>={})=>void command({id:item.request_id,action,body:{expected_version:item.version,idempotency_key:crypto.randomUUID(),...fields}});
  const refresh=async()=>{setBusy(true);setError('');setNotice('');try {setItem(await serviceStartClient.detail(item.request_id));}catch(e){setError(e instanceof Error?e.message:'無法查詢最新結果。');}finally{setBusy(false);}};
  const frozen=busy || pending!==null || item.status==='applied';
  const leave=item.workflow_kind==='leave';
  const handover=item.workflow_kind==='handover';
  const handoverDates=(item.handover_dates??[]).filter(day=>day>=start);
  const changes=(item.leave_dates??[]).map(d=>({original_date:d.original_date,new_date:dateChanges[d.original_date]??''}));
  const datesValid=changes.length>0 && changes.every(d=>d.new_date) && new Set(changes.map(d=>d.new_date)).size===changes.length;
  const dateInputs=()=>changes.map(d=><label key={d.original_date}>原服務日 {d.original_date} → 實際服務日<input type="date" aria-label={`${d.original_date} 實際服務日`} value={d.new_date} onChange={e=>setDateChanges({...dateChanges,[d.original_date]:e.target.value})}/></label>);
  return <article className="service-start-card"><h3>案件 {item.case_no}</h3>
    <p>原月嫂：{item.staff_name} · {handover?'服務中換人':leave?'請假協調結果':'客戶希望開始日：'+(item.requested_start_date??'尚待工會確認')}</p>
    {leave && <p>原服務日：{item.leave_dates.map(d=>d.original_date).join('、')}</p>}
    {handover && <p>原區段剩餘服務日：{item.handover_dates.join('、')}</p>}
    {item.conflict_message && <p role="status">{item.conflict_message}</p>}
    {item.status==='applied'?<><strong>正式排班已完成</strong><p>開始日：{item.result?.actual_start_date} · 第一期款期限：{item.result?.first_payment_due_date}</p>
      {item.result?.assignments.map((assignment,index)=><p key={index}>{assignment.staff_name}：{assignment.service_dates.join('、')}</p>)}</>:<>
      {leave && !recordDefer && <button type="button" disabled={frozen} onClick={()=>setRecordDefer(true)}>記錄原月嫂順延日期</button>}
      {leave && recordDefer && <fieldset disabled={frozen}><legend>記錄雙方重新談妥的順延日期</legend>{dateInputs()}
        <button type="button" disabled={!datesValid || changes.some(d=>d.new_date<=d.original_date)} onClick={()=>run('defer',{dates:changes})}>儲存順延日期並更新排班</button></fieldset>}
      <p>選定代班月嫂：{item.selected_staff_name??'尚未選定'} · {item.willingness?willingness[item.willingness]:'請先選人並詢問意願'}</p>
      {item.proposed_start_date && <p>需替代區段：{item.proposed_start_date} ～ {item.proposed_end_date}</p>}
      {(!item.selected_staff_id || item.willingness==='unwilling' || choosing) && <fieldset disabled={frozen}>
        <legend>替代區段與代班人選</legend>
        <label>月嫂姓名<input aria-label="搜尋月嫂姓名" value={keyword} maxLength={50} onChange={e=>setKeyword(e.target.value)}/></label>
        <button type="button" onClick={()=>void search()}>搜尋代班月嫂</button>
        <label>代班月嫂<select aria-label="代班月嫂" value={staffId} onChange={e=>setStaffId(e.target.value)}><option value="">請選擇月嫂</option>{(found??options).filter(o=>o.staff_id!==item.staff_id).map(o=><option key={o.staff_id} value={o.staff_id}>{o.name}</option>)}</select></label>
        {!handover && <><label>需替代開始日<input type="date" value={start} readOnly={leave} onChange={e=>setStart(e.target.value)}/></label>
        <label>需替代結束日<input type="date" value={end} readOnly={leave} onChange={e=>setEnd(e.target.value)}/></label></>}
        <button type="button" disabled={!staffId || (!handover && (!start || !end || end<start))} onClick={()=>run('inquire',{staff_id:Number(staffId),start_date:handover?item.handover_dates[0]:start,end_date:handover?item.handover_dates.at(-1):end})}>詢問該月嫂意願</button>
      </fieldset>}
      {item.selected_staff_id && (handover || item.willingness!=='willing') && !choosing && <button type="button" disabled={frozen} onClick={()=>setChoosing(true)}>改問其他月嫂</button>}
      <p>邀請：{item.invitation_status?(invitationLabels[item.invitation_status]??'待查核'):'尚未寄送'} · 加入狀態：{item.joined?'已加入原案件群組':'待加入'}</p>
      {item.willingness==='willing' && !item.joined && <button type="button" disabled={frozen || ['pending','processing','sent'].includes(item.invitation_status??'')} onClick={()=>run('invite')}>寄送本案群組邀請連結</button>}
      <button type="button" disabled={busy} onClick={()=>void refresh()}>重新查詢加入狀態</button>
      {item.willingness==='willing' && item.joined && !choosing && <fieldset disabled={frozen}><legend>{handover?'記錄雙方已協調的交接日':'人員填寫實際服務日期'}</legend>
        {leave?dateInputs():<label>{handover?'交接日':'實際服務開始日'}<input type="date" value={start} onChange={e=>setStart(e.target.value)}/></label>}
        {handover && <><p>交接日起接任 {handoverDates.length} 個服務日：{handoverDates.join('、')}</p><p>儲存後更新剩餘排班與帳務，已服務日期及已付款紀錄保留，日期表交付原案件群組。</p></>}
        <button type="button" disabled={leave?!datesValid:!start || (handover && handoverDates.length===0)} onClick={()=>run('dates',leave?{start_date:changes[0].new_date,date_changes:changes}:{start_date:start})}>{handover?'儲存交接日並更新排班與帳務':'儲存並更新排班'}</button>
      </fieldset>}
    </>}
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {pending && <p>這筆操作結果尚未確認。<button type="button" disabled={busy} onClick={()=>void command(pending)}>確認原操作結果</button></p>}
  </article>;
}

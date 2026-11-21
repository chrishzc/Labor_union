import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiHttpError } from '../api/shared/typed_errors';
import { serviceStartClient, type ServiceStartView, type StartCommand, type HandoverContext, type HandoverInquiry } from '../api/scheduling/service_start_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import './ServiceStartSubstituteWorkbench.css';

interface Pending {id:number;action:'inquire'|'invite'|'dates';body:StartCommand;observeOnly?:boolean}
const storageKey=(id:number)=>`service-start-command:${id}`;
const willingness={pending:'等待月嫂回覆',willing:'願意代班',unwilling:'無法代班'};
const invitationLabels:Record<string,string>={pending:'待寄送',processing:'寄送中',sent:'已寄送',failed:'寄送失敗',cancelled:'已取消'};

async function verifyCompletedAssignment(result:ServiceStartView, initial:ServiceStartView, signal:AbortSignal) {
  const receipt=result.result;
  if(result.request_id!==initial.request_id || result.case_no!==initial.case_no || result.staff_id!==initial.staff_id
    || result.workflow_kind!==initial.workflow_kind || result.status!=='applied' || !receipt || receipt.assignments.length===0
    || (initial.selected_staff_id!==null && result.selected_staff_id!==initial.selected_staff_id)
    || (result.selected_staff_id!==null && !receipt.assignments.some(row=>row.staff_id===result.selected_staff_id))) {
    throw new Error('尚未確認最新排班結果。');
  }
  const plan=await ordersQueryClient.getAssignmentPlan(initial.case_no,{signal});
  const grouped=(rows:readonly {staff_id:number;dates:readonly string[]}[])=>{
    const byStaff=new Map<number,string[]>();
    for(const row of rows) byStaff.set(row.staff_id,[...(byStaff.get(row.staff_id)??[]),...row.dates]);
    return JSON.stringify([...byStaff].sort(([a],[b])=>a-b).map(([id,days])=>[id,days.sort()]));
  };
  if(plan.case_no!==initial.case_no || plan.order_version<receipt.order_version
    || grouped(plan.assignments.map(row=>({staff_id:row.staff_id,dates:row.official_service_dates})))
      !==grouped(receipt.assignments.map(row=>({staff_id:row.staff_id,dates:row.service_dates})))) {
    throw new Error('尚未確認最新排班結果。');
  }
}

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

export function ServiceStartSubstituteWorkbench({ initial }: { initial: ServiceStartView }) {
  const [options, setOptions] = useState<{ staff_id: number; name: string }[]>([]);
  useEffect(() => {
    let current = true;
    if (initial.status !== 'applied') {
      void serviceStartClient.options().then(result => {
        if (current) setOptions(result.items);
      }).catch(() => undefined);
    }
    return () => { current = false; };
  }, [initial]);
  return <section className="service-start-workbench" aria-label="服務中換人">
    <SubstituteCard key={initial.request_id} initial={initial} options={options} />
  </section>;
}

function SubstituteCard({initial,options}:{initial:ServiceStartView;options:{staff_id:number;name:string}[]}) {
  const [item,setItem]=useState(initial);
  const [observed,setObserved]=useState(false);
  const mounted=useRef(true);
  const inFlight=useRef(false);
  const observation=useRef<AbortController|null>(null);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;observation.current?.abort();};},[]);
  const [staffId,setStaffId]=useState('');
  const [keyword,setKeyword]=useState('');
  const [found,setFound]=useState<typeof options|null>(null);
  const search=async()=>{setBusy(true);setError('');try{setFound((await serviceStartClient.options(keyword)).items);}catch(e){setError(e instanceof Error?e.message:'人選查詢失敗。');}finally{setBusy(false);}};
  const [start,setStart]=useState(initial.requested_start_date??initial.proposed_start_date??'');
  const [pending,setPending]=useState<Pending|null>(()=>{
    try {const value=sessionStorage.getItem(storageKey(initial.request_id));return value?JSON.parse(value) as Pending:null;} catch {return null;}
  });
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [choosing,setChoosing]=useState(false);
  const savePending=(value:Pending|null)=>{
    if(mounted.current) setPending(value);
    if(value) sessionStorage.setItem(storageKey(initial.request_id),JSON.stringify(value));
    else sessionStorage.removeItem(storageKey(initial.request_id));
  };
  useEffect(()=>{
    setItem(initial);setObserved(false);
    if(initial.status!=='applied') return;
    if(pending && !pending.observeOnly) savePending({...pending,observeOnly:true});
    const controller=new AbortController();
    void verifyCompletedAssignment(initial,initial,controller.signal).then(()=>{
      if(!controller.signal.aborted){setObserved(true);setError('');}
    }).catch(()=>{if(!controller.signal.aborted) setError('尚未確認最新排班結果。');});
    return()=>controller.abort();
  },[initial]);
  const command=async(saved:Pending)=>{
    if(inFlight.current) return;
    inFlight.current=true;
    setBusy(true);setError('');setNotice('');
    let current=saved;
    savePending(current);
    try {const result=saved.observeOnly?await serviceStartClient.detail(saved.id):await serviceStartClient.command(saved.id,saved.action,saved.body);
      if(result.status==='applied') {current={...saved,observeOnly:true};savePending(current);}
      if(!mounted.current) return;
      if(result.request_id!==initial.request_id || result.case_no!==initial.case_no || result.staff_id!==initial.staff_id
        || result.workflow_kind!==initial.workflow_kind || (saved.observeOnly && result.status!=='applied')) {
        throw new Error('尚未確認最新排班結果。');
      }
      if(result.status==='applied') {
        const controller=new AbortController();observation.current=controller;
        await verifyCompletedAssignment(result,initial,controller.signal);
        if(controller.signal.aborted || !mounted.current) return;
        if(controller.signal.aborted || !mounted.current) return;
        setObserved(true);
      }
      setItem(result);savePending(null);setChoosing(false);
      setNotice(result.status==='applied'?(result.result?.group_record_queued?'服務日期與排班已更新，日期表已交付寄送。':'正式排班已更新；本案尚缺服務群組，請先完成群組設定。'):saved.action==='invite'?'群組邀請已排入寄送，請等待月嫂加入。':saved.action==='inquire'?'代班意願詢問已排入寄送。':'仍需處理代班，請核對日期與檔期。');
    } catch(e) {if(mounted.current) setError(current.observeOnly?'尚未確認最新排班結果。':e instanceof Error?e.message:'尚無法確認處理結果。');
      if(!current.observeOnly && e instanceof ApiHttpError && e.status>=400 && e.status<500) savePending(null);
    } finally {inFlight.current=false;if(mounted.current) setBusy(false);}
  };
  const run=(action:Pending['action'],fields:Partial<StartCommand>={})=>void command({id:item.request_id,action,body:{expected_version:item.version,idempotency_key:crypto.randomUUID(),...fields}});
  const refresh=async()=>{
    if(pending?.observeOnly){await command(pending);return;}
    if(inFlight.current) return;
    inFlight.current=true;setBusy(true);setError('');setNotice('');
    let completed=false;
    try {
      const result=await serviceStartClient.detail(initial.request_id);
      completed=result.status==='applied';
      if(completed && pending) savePending({...pending,observeOnly:true});
      if(result.request_id!==initial.request_id || result.case_no!==initial.case_no || result.staff_id!==initial.staff_id
        || result.workflow_kind!==initial.workflow_kind) throw new Error('回讀的服務安排與目前案件不一致。');
      if(result.status==='applied') {
        const controller=new AbortController();observation.current=controller;
        await verifyCompletedAssignment(result,initial,controller.signal);
        if(controller.signal.aborted || !mounted.current) return;
        if(controller.signal.aborted || !mounted.current) return;
        setObserved(true);
        savePending(null);
      }
      if(mounted.current) setItem(result);
    }catch(e){if(mounted.current) setError(completed?'尚未確認最新排班結果。':e instanceof Error?e.message:'無法查詢最新結果。');}
    finally{inFlight.current=false;if(mounted.current) setBusy(false);}
  };
  const frozen=busy || pending!==null || item.status==='applied';
  const handoverDates=(item.handover_dates??[]).filter(day=>day>=start);
  return <article className="service-start-card"><h3>案件 {item.case_no}</h3>
    <p>原月嫂：{item.staff_name} · 服務中換人</p>
    <p>原區段剩餘服務日：{item.handover_dates.join('、')}</p>
    {item.conflict_message && <p role="status">{item.conflict_message}</p>}
    {item.status==='applied'?(observed?<><strong>正式排班已完成</strong><p>開始日：{item.result?.actual_start_date} · 第一期款期限：{item.result?.first_payment_due_date}</p>
      {item.result?.assignments.map((assignment,index)=><p key={index}>{assignment.staff_name}：{assignment.service_dates.join('、')}</p>)}</>:<p>排班已處理，尚未確認最新結果。{!pending && <button type="button" disabled={busy} onClick={()=>void refresh()}>查詢排班結果</button>}</p>):<>
      <p>選定代班月嫂：{item.selected_staff_name??'尚未選定'} · {item.willingness?willingness[item.willingness]:'請先選人並詢問意願'}</p>
      {item.proposed_start_date && <p>需替代區段：{item.proposed_start_date} ～ {item.proposed_end_date}</p>}
      {(!item.selected_staff_id || item.willingness==='unwilling' || choosing) && <fieldset disabled={frozen}>
        <legend>替代區段與代班人選</legend>
        <label>月嫂姓名<input aria-label="搜尋月嫂姓名" value={keyword} maxLength={50} onChange={e=>setKeyword(e.target.value)}/></label>
        <button type="button" onClick={()=>void search()}>搜尋代班月嫂</button>
        <label>代班月嫂<select aria-label="代班月嫂" value={staffId} onChange={e=>setStaffId(e.target.value)}><option value="">請選擇月嫂</option>{(found??options).filter(o=>o.staff_id!==item.staff_id).map(o=><option key={o.staff_id} value={o.staff_id}>{o.name}</option>)}</select></label>
        <button type="button" disabled={!staffId || item.handover_dates.length === 0} onClick={()=>run('inquire',{staff_id:Number(staffId),start_date:item.handover_dates[0],end_date:item.handover_dates.at(-1)})}>詢問該月嫂意願</button>
      </fieldset>}
      {item.selected_staff_id && !choosing && <button type="button" disabled={frozen} onClick={()=>setChoosing(true)}>改問其他月嫂</button>}
      <p>邀請：{item.invitation_status?(invitationLabels[item.invitation_status]??'待查核'):'尚未寄送'} · 加入狀態：{item.joined?'已加入原案件群組':'待加入'}</p>
      {item.willingness==='willing' && !item.joined && <button type="button" disabled={frozen || ['pending','processing','sent'].includes(item.invitation_status??'')} onClick={()=>run('invite')}>寄送本案群組邀請連結</button>}
      <button type="button" disabled={busy} onClick={()=>void refresh()}>重新查詢加入狀態</button>
      {item.willingness==='willing' && item.joined && !choosing && <fieldset disabled={frozen}><legend>記錄雙方已協調的交接日</legend>
        <label>交接日<input type="date" value={start} onChange={e=>setStart(e.target.value)}/></label>
        <p>交接日起接任 {handoverDates.length} 個服務日：{handoverDates.join('、')}</p><p>儲存後更新剩餘排班與帳務，已服務日期及已付款紀錄保留，日期表交付原案件群組。</p>
        <button type="button" disabled={!start || handoverDates.length===0} onClick={()=>run('dates',{start_date:start})}>儲存交接日並更新排班與帳務</button>
      </fieldset>}
    </>}
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {pending && <p>這筆操作結果尚未確認。<button type="button" disabled={busy} onClick={()=>void command(pending)}>{pending.observeOnly?'查詢排班結果':'確認原操作結果'}</button></p>}
  </article>;
}

/** Ongoing collection list; owner queries supply stages and accounting amounts. */
import {useEffect,useRef,useState} from 'react';
import {loadAllOrderSummaries,ordersQueryClient} from '../api/orders/order_query_client';
import type {OrderSummaryItem} from '../api/orders/order_query_schemas';
import {loadAllCoreStageTimelines} from '../api/orders/load_all_core_stage_timelines';
import type {OrderCoreStageTimeline} from '../api/orders/order_core_stage_projection_schemas';
import {financeAccountingClient,type CaseAccounting} from '../api/finance_import/finance_accounting_client';
import {financeMoney} from './FinanceReceiptsWorkspace';
import {paymentOverdueReminderClient,type CasePaymentReminder} from '../api/line_order_groups/payment_overdue_reminder_client';
import {lastNotification,notificationTime,notificationStatus} from './FinanceCaseNotice';

type Row={order:OrderSummaryItem;accounting?:CaseAccounting;notices?:CasePaymentReminder[]};
type Stage='deposit'|'first'|'second'|'scheme';
const stageLabels={deposit:'訂金',first:'第一期',second:'第二期',scheme:'設定補助退款方案'};
const money=(value:number|null|undefined)=>value==null?'待確認':financeMoney(value);
function taipeiDate(){return new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Taipei',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());}
function hasEnteredDeposit(timeline:OrderCoreStageTimeline){return (timeline.current_core_stage_ordinal??0)>=8||(timeline.historical_current_owner_stage_ordinal??0)>=8||timeline.core_stages[7]?.status==='completed';}
function dateStatus(row:Row,today:string){const progress=row.accounting?.collection_progress;if(!progress||!progress.sources_complete)return '來源待確認';if(progress.stage==='scheme')return '待確認';if(!progress.due_date)return '日期待確認';return progress.due_date>today?'未到期':progress.due_date===today?'今日到期':'逾期';}
export function FinanceCaseList({onCase,onNotice,revision=0}:{onCase:(caseNo:string)=>void;onNotice?:(caseNo:string,stage:CasePaymentReminder['payment_stage'])=>void;revision?:number}){
 const[input,setInput]=useState(''),[query,setQuery]=useState(''),[pageIndex,setPageIndex]=useState(0);
 const[rows,setRows]=useState<Row[]>([]),[loading,setLoading]=useState(true),[error,setError]=useState('');
 const[stage,setStage]=useState('all'),[timing,setTiming]=useState('all'),[request,setRequest]=useState(0),[unknownScope,setUnknownScope]=useState(0);
 const scopeRef=useRef('');const today=taipeiDate();
 useEffect(()=>{
  if(scopeRef.current!==query){scopeRef.current=query;setRows([]);}
  const controller=new AbortController();setLoading(true);setError('');setUnknownScope(0);
  void Promise.all([
   loadAllOrderSummaries((params,options)=>ordersQueryClient.getOrderSummaries(params,options),{page_size:100,...(query?{query_text:query}:{})},{signal:controller.signal}),
   loadAllCoreStageTimelines({lifecycle_scope:'all',page_size:200},{signal:controller.signal})
  ]).then(async([page,timelines])=>{
   if(controller.signal.aborted)return;
   const byCase=new Map(timelines.items.map(item=>[item.case_no,item]));
   const eligible=page.items.filter(order=>{const timeline=byCase.get(order.case_no);return timeline&&hasEnteredDeposit(timeline);});
   setUnknownScope(page.items.filter(order=>!byCase.has(order.case_no)).length);
   const collected:Row[]=new Array(eligible.length);let index=0;
   await Promise.all(Array.from({length:Math.min(4,eligible.length)},async()=>{
    while(index<eligible.length&&!controller.signal.aborted){const current=index++,order=eligible[current];
     try{const [accounting,notices]=await Promise.allSettled([financeAccountingClient.query(order.case_no,controller.signal),paymentOverdueReminderClient.case(order.case_no,controller.signal)]);collected[current]={order,accounting:accounting.status==='fulfilled'?accounting.value:undefined,notices:notices.status==='fulfilled'?notices.value:undefined};}
     catch{collected[current]={order};}
    }
   }));
   if(!controller.signal.aborted)setRows(collected);
  }).catch(()=>{if(!controller.signal.aborted)setError('進行中案件或營運階段暫時無法取得，請重新查詢。');}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
  return()=>controller.abort();
 },[query,revision,request]);
 const matched=rows.filter(row=>!row.accounting?.ongoing_completed&&(stage==='all'||row.accounting?.collection_progress?.stage===stage)&&(timing==='all'||(timing==='future'?dateStatus(row,today)==='未到期':dateStatus(row,today)!=='未到期')));
 const pageCount=Math.max(1,Math.ceil(matched.length/20)),currentPage=Math.min(pageIndex,pageCount-1),shown=matched.slice(currentPage*20,(currentPage+1)*20);
 return <section className="case-accounting finance-ongoing-list" aria-label="進行中案件清單">
  <form className="case-accounting-card case-accounting-search finance-ongoing-toolbar" onSubmit={event=>{event.preventDefault();setPageIndex(0);setQuery(input.trim());setRequest(value=>value+1);}}>
   <label>搜尋案件或對象<input data-ongoing-focus value={input} onChange={event=>setInput(event.target.value)} placeholder="案件編號、客戶或月嫂" maxLength={50}/></label>
   <label>目前階段<select aria-label="目前階段" value={stage} onChange={event=>{setStage(event.target.value);setPageIndex(0);}}><option value="all">全部階段</option>{Object.entries(stageLabels).map(([key,label],index)=><option key={key} value={key}>{index+1}. {label}</option>)}</select></label>
   <label>時效篩選<select aria-label="時效篩選" value={timing} onChange={event=>{setTiming(event.target.value);setPageIndex(0);}}><option value="all">全部狀態</option><option value="action">目前待處理／待確認</option><option value="future">款項未到期</option></select></label>
   <button className="finance-btn-primary" disabled={loading}>查詢案件</button><div className="finance-ongoing-count" aria-busy={loading}><strong>{loading?'—':matched.length}</strong> 案<small>查核日 {today}（台灣時間）</small></div>
  </form>
  {loading&&<p role="status">正在讀取進行中案件與正式帳務…</p>}{error&&<p role="alert">{error}</p>}{!loading&&unknownScope>0&&<p role="status">有 {unknownScope} 案的營運階段來源待確認，暫未列入本清單。</p>}
  {!error&&<div className="finance-table-container" aria-busy={loading} tabIndex={0} role="region" aria-label="進行中案件六欄，可左右捲動"><table className="finance-table finance-ongoing-table"><thead><tr><th>案件／客戶</th><th>實際開始／結束日</th><th>相關月嫂</th><th>案件總額 T</th><th>應操作／目前狀態</th><th>操作</th></tr></thead><tbody>{shown.map(row=>{const{order,accounting:a}=row,progress=a?.collection_progress,current=progress?.stage,state=dateStatus(row,today),notice=row.notices?.find(item=>item.payment_stage===current),last=lastNotification(notice);return <tr key={order.case_no} data-accounting-case={order.case_no}>
   <td><button className="finance-btn-link" onClick={()=>onCase(order.case_no)}>{order.case_no}</button><small>{order.client_name}</small></td><td><span>實際開始 {order.actual_start_date??'待確認'}</span><small>實際結束 {order.actual_end_date??'待確認'}</small></td><td>{order.staff_display_label??order.staff_name??'待確認'}</td><td>{money(a?.staff_receivable_ntd)}</td>
   <td><div className="finance-ongoing-item"><strong>{!progress?'帳務來源待確認':!progress.sources_complete?stageLabels[progress.stage]+'來源待確認':current==='scheme'?'設定補助退款方案':'待收'+stageLabels[current as Stage]}</strong><span className={'finance-ongoing-status '+(state==='未到期'?'future':state==='逾期'?'overdue':'')}>{current==='scheme'?'未設定':state}</span>{progress?.sources_complete&&current!=='scheme'&&<><span>待收 {money(progress.remaining_ntd)}</span><small>{progress.due_date?'原到期日 '+progress.due_date:'到期日待確認'}</small>{(progress.received_ntd??0)>0&&<small>部分已收 {money(progress.received_ntd)}</small>}<small>{last?'已發送 '+notificationTime(last):notice?'尚無成功通知紀錄':'通知紀錄待確認'}{notice&&notificationStatus(notice)?' · '+notificationStatus(notice):''}</small></>}</div></td>
   <td><div className="finance-ongoing-actions"><button className="finance-btn-secondary" onClick={()=>onCase(order.case_no)}>查看案件</button><button className="finance-btn-primary" disabled={!onNotice||!notice?.can_send||!progress?.sources_complete||current==='scheme'} title={current==='scheme'?'客戶各期款已齊':notice?.unavailable_reason??'查看目前期款通知'} onClick={()=>{if(current&&current!=='scheme')onNotice?.(order.case_no,current);}}>發出提醒</button></div></td>
  </tr>})}</tbody></table>{!loading&&!shown.length&&<p className="finance-state">目前沒有符合條件的進行中案件。</p>}</div>}
  <div className="finance-row-actions"><button type="button" className="finance-btn-secondary" disabled={loading||currentPage===0} onClick={()=>setPageIndex(currentPage-1)}>上一頁</button><span>搜尋範圍共 {matched.length} 案；第 {currentPage+1}／{pageCount} 頁，每頁20案；篩選使用完整搜尋結果</span><button type="button" className="finance-btn-secondary" disabled={loading||currentPage>=pageCount-1} onClick={()=>setPageIndex(currentPage+1)}>下一頁</button></div>
 </section>;
}

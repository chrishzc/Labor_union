import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import {financeAccountingClient,type CaseAccounting,type AccountingWarning} from '../api/finance_import/finance_accounting_client';
import {paymentOverdueReminderClient,type CasePaymentReminder} from '../api/line_order_groups/payment_overdue_reminder_client';
import {ordersQueryClient} from '../api/orders/order_query_client';
import type {OrderDetail} from '../api/orders/order_query_schemas';
import {financeMoney} from './FinanceReceiptsWorkspace';
import {useUnsavedChanges,useUnsavedNavigation} from './UnsavedChanges';
import {ApiHttpError} from '../api/shared/typed_errors';
import {FinanceSubsidyPlanForm,subsidyPlanLabels,subsidyPlanTargets} from './FinanceSubsidyPlanForm';
import {FinanceCaseNotice,lastNotification,notificationTime,notificationStatus} from './FinanceCaseNotice';
import './FinanceCaseAccounting.css';
import './FinanceCompactCase.css';
const labels={over_received:'客戶超收',over_paid:'付款超付',under_paid:'付款差額超過 100 元'};
const money=(value:number|null|undefined)=>value==null?'待確認':financeMoney(value);
type Stage='deposit'|'first'|'second';
const stageNames:Record<Stage,string>={deposit:'訂金',first:'第一期',second:'第二期'};
const stages:Stage[]=['deposit','first','second'];
export function AccountingWarningList({ data, onChange }: { data: CaseAccounting; onChange: (data: CaseAccounting) => void }) {
  const [showDismissed, setShowDismissed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useUnsavedChanges('帳務警示解除', [], { busy });
  async function dismiss(row: AccountingWarning) {
    setBusy(true); setError('');
    try { onChange(await financeAccountingClient.dismiss(data.case_no, row)); }
    catch { setError('解除失敗或款項已變更，請重新整理後確認。'); }
    finally { setBusy(false); }
  }
  return <section className="case-accounting-card" aria-label="共用帳務警示">
    <div className="finance-section-heading"><h3>帳務警示 · 待檢查 {data.pending_warning_count}</h3><label><input type="checkbox" checked={showDismissed} onChange={event => setShowDismissed(event.target.checked)} /> 顯示已解除</label></div>
    {error && <p role="alert">{error}</p>}
    {data.warnings.filter(row => showDismissed || !row.dismissed).map(row => <div className="case-accounting-warning" key={`${row.item_identity}:${row.kind}:${row.difference_ntd}`}>
      <div><strong>{labels[row.kind]}</strong><p>{[...data.client_items, ...data.staff_items].find(item => item.identity === row.item_identity)?.label} · {[...data.client_items, ...data.staff_items].find(item => item.identity === row.item_identity)?.party} · 應收／應付 {money(row.expected_ntd)}，實收／實付 {money(row.actual_ntd)}；差額 {money(row.difference_ntd)}</p></div>
      {row.dismissed ? <span>已解除 · {row.dismissed_by} · {row.dismissed_at}</span> : <button className="finance-btn-secondary" disabled={busy} type="button" onClick={() => void dismiss(row)}>解除警示</button>}
    </div>)}
    {!data.warnings.some(row => showDismissed || !row.dismissed) && <p className="finance-state">目前沒有{showDismissed ? '' : '待檢查'}帳務警示。</p>}
  </section>;
}

export function FinanceCaseAccounting({initialCase='',embedded=false,onChanged,initialNoticeStage,onIdentity}: {initialCase?:string;embedded?:boolean;onChanged?:()=>void;initialNoticeStage?:Stage;onIdentity?:(caseNo:string,name:string)=>void;onBank?:()=>void;onSubsidy?:(caseNo:string)=>void;onLegacy?:(caseNo:string)=>void}){
 const {requestLeave}=useUnsavedNavigation();
 const[state,setState]=useState<{caseNo:string;data?:CaseAccounting;order?:OrderDetail;notices?:CasePaymentReminder[];error?:string;noticeError?:boolean;loading?:boolean}>({caseNo:initialCase,loading:true});
 const[revision,setRevision]=useState(0),[view,setView]=useState<Stage|'plan'|null>(initialNoticeStage??null);
 const section=useRef<HTMLElement>(null),returnScroll=useRef(0),returnFocus=useRef<HTMLElement|null>(null);
 useEffect(()=>{const controller=new AbortController();setState(old=>old.caseNo===initialCase?{...old,loading:true,error:undefined}:{caseNo:initialCase,loading:true});if(!initialCase)return()=>controller.abort();void Promise.allSettled([financeAccountingClient.query(initialCase,controller.signal),ordersQueryClient.getOrderDetail(initialCase,{signal:controller.signal}),paymentOverdueReminderClient.case(initialCase,controller.signal)]).then(([accounting,order,notices])=>{if(controller.signal.aborted)return;if(accounting.status==='rejected'){const status=accounting.reason instanceof ApiHttpError?accounting.reason.status:0;setState({caseNo:initialCase,error:status===404?'找不到此案件，請確認案件編號。':status===401?'登入已失效，請重新登入後查詢。':status===403?'目前沒有查閱帳務的權限。':'帳務資料暫時無法取得，請稍後重新查詢。'});return;}setState({caseNo:initialCase,data:accounting.value,order:order.status==='fulfilled'?order.value:undefined,notices:notices.status==='fulfilled'?notices.value:undefined,noticeError:notices.status==='rejected',loading:false});});return()=>controller.abort();},[initialCase,revision]);
 useLayoutEffect(()=>{if(view!==null){section.current?.querySelector<HTMLElement>('.finance-case-subview h3')?.focus();return;}if(view===null&&returnFocus.current){const body=section.current?.closest('.drawer-body');if(body)body.scrollTop=returnScroll.current;const trigger=returnFocus.current;const target=trigger.isConnected?trigger:section.current?.querySelector('summary');target?.focus({preventScroll:true});returnFocus.current=null;}},[view,!!state.data]);
 useEffect(()=>{if(state.caseNo===initialCase&&state.data)onIdentity?.(initialCase,state.data.client_name);},[initialCase,state.caseNo,state.data,onIdentity]);
 function refresh(){setRevision(v=>v+1);onChanged?.();}
 function open(next:Stage|'plan'){returnFocus.current=document.activeElement instanceof HTMLElement?document.activeElement:null;returnScroll.current=section.current?.closest('.drawer-body')?.scrollTop??0;requestLeave(()=>setView(next));}
 function back(){requestLeave(()=>setView(null));}
 const data=state.caseNo===initialCase?state.data:undefined;
 const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Taipei',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
 if(!initialCase)return <p>請從案件清單選擇案件。</p>;
 const selected=data?.subsidy_plan?.events.at(-1)?.scheme;
 const staff=data?[...new Set(data.staff_items.filter(row=>row.direction==='payable').map(row=>row.party))].join('、'):'';
 return <section ref={section} className="case-accounting finance-compact-case" aria-label="案件帳務內容">
 {!embedded&&data&&<h2>{data.case_no} · {data.client_name}</h2>}{state.error&&<p role="alert">{state.error}</p>}{state.loading&&<p role="status">正在讀取案件資料…</p>}{state.error&&<button onClick={()=>setRevision(v=>v+1)}>重新讀取案件</button>}
 {data&&<><div hidden={view!==null}>
 <dl className="finance-compact-facts" aria-label="案件精簡摘要"><div><dt>相關月嫂</dt><dd>{staff||state.order?.staff_name||'待確認'}</dd></div><div><dt>實際開始</dt><dd>{state.order?.actual_start_date??'待確認'}</dd></div><div><dt>實際結束</dt><dd>{state.order?.actual_end_date??'待確認'}</dd></div><div><dt>案件總額 T</dt><dd>{money(data.staff_receivable_ntd)}</dd></div></dl>
 <details className="finance-case-block" open><summary>01　客戶繳款</summary><div className="finance-case-block-body"><div className="finance-table-container" tabIndex={0} role="region" aria-label="各期繳款與通知，可左右捲動"><table className="finance-table finance-case-periods"><thead><tr><th>期款</th><th>原到期日</th><th>應繳</th><th>已收／待收</th><th>入帳資訊</th><th>通知時間</th><th>通知</th></tr></thead><tbody>{stages.map(stage=>{
 const sources=data.client_items.filter(row=>row.direction==='receivable'&&row.payment_stage===stage),item=sources.length===1?sources[0]:undefined;
 const exempt=data.customer_fully_received===true&&data.customer_amount_ntd===0;
 const expected=item?.expected_ntd??(exempt?0:null),actual=item?.actual_ntd??(exempt?0:null),remaining=item?.remaining_ntd??(exempt?0:null);
 const notice=state.notices?.find(row=>row.payment_stage===stage),last=lastNotification(notice);
 const receipts=item?data.transactions.filter(row=>row.item_identity===item.identity&&row.kind==='receipt'&&row.amount_ntd>0).slice().sort((a,b)=>b.occurred_on.localeCompare(a.occurred_on)):[];
 return <tr key={stage} data-payment-stage={stage} className={data.collection_progress?.stage===stage?'is-current':''}><td><strong>{stageNames[stage]}</strong>{stage==='deposit'&&<small>含樓層／其他費用</small>}</td><td>{expected===0?'不需繳納':item?.due_date??'日期待確認'}{remaining!=null&&remaining>0&&item?.due_date&&<small>{item.due_date>today?'未到期':item.due_date===today?'今日到期':'逾期'}</small>}</td><td>{money(expected)}</td><td><span>已收 {money(actual)}</span>{remaining===0?<small className="finance-paid">{expected===0?'免繳':'已繳齊'}</small>:<small>待收 {money(remaining)}</small>}</td><td>{receipts.length?<><span>{receipts[0].occurred_on} · {receipts[0].bank==='sinopac'?'永豐':receipts[0].bank==='taishin'?'台新':receipts[0].bank==='legacy'?'歷史來源':'原來源'}</span>{receipts.length>1&&<details><summary>{receipts.length} 筆入帳</summary>{receipts.map(row=><p key={row.identity}>{row.occurred_on} · {money(row.amount_ntd)}</p>)}</details>}</>:<span>{item||exempt?'尚無已核銷入帳':'來源待確認'}</span>}</td><td>{last?notificationTime(last):notice?(notice.history.length?'尚無成功通知':'尚未通知'):'待確認'}{notice&&notificationStatus(notice)&&<small>{notificationStatus(notice)}</small>}</td><td><button type="button" className="finance-btn-primary finance-case-notice-button" aria-label={'通知'+stageNames[stage]} disabled={remaining==null||remaining<=0||!notice?.can_send||!!state.loading} title={remaining===0?(expected===0?'本期免繳':'本期已繳齊'):notice?.unavailable_reason??(notice?'查看本期通知內容與紀錄':'通知來源待確認')} onClick={()=>open(stage)}>通知</button></td></tr>;
 })}</tbody></table></div>{state.noticeError&&<p role="status">通知資料暫時無法取得，時間保留待確認。<button className="finance-btn-link" onClick={()=>setRevision(v=>v+1)}>重新讀取通知</button></p>}</div></details>
 <details className="finance-case-block" open><summary>02　補助退款方案</summary><div className="finance-case-block-body"><div className="finance-compact-plan"><div><small>本案補助 {money(data.subsidy_ntd)}</small><strong>{selected?subsidyPlanLabels[selected]:'尚未設定'}</strong><p>{selected?subsidyPlanTargets[selected]:'由人員設定補助款歸屬，不從歷史金流自動代選。'}</p></div><button type="button" className="finance-btn-primary" disabled={!data.subsidy_plan||!!state.loading} onClick={()=>open('plan')}>{selected?'修改補助退款方案':'設定補助退款方案'}</button></div><p>可提前設定，不改各期應繳。案件結束後再處理補助與應付清單。</p>{selected&&<p role="status">{data.ongoing_completed?'客戶款已齊且方案已保存，已移出進行中案件。':'方案已保存，客戶款未齊時仍保留在進行中案件。'}</p>}</div></details>
 </div>{view==='plan'&&data.subsidy_plan&&<FinanceSubsidyPlanForm key={initialCase} caseNo={initialCase} source={data.subsidy_plan} onBack={back} onSaved={()=>{setView(null);refresh();}}/>}{view&&view!=='plan'&&(state.notices?.find(row=>row.payment_stage===view)?<FinanceCaseNotice key={initialCase+view} item={state.notices.find(row=>row.payment_stage===view)!} onBack={back} onChanged={refresh}/>:<div><p>本期通知來源待確認。</p><button onClick={back}>返回案件</button></div>)}</>}
 </section>;
}
export function FinanceAccountingWarnings({ onCase }: { onCase: (caseNo: string) => void }) {
  const [data, setData] = useState<CaseAccounting[] | null>(null);
  const [error, setError] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => { const controller = new AbortController(); setData(null); setError(false); void financeAccountingClient.warnings(controller.signal).then(value => { if (!controller.signal.aborted) setData(value); }).catch(() => { if (!controller.signal.aborted) setError(true); }); return () => controller.abort(); }, [revision]);
  return <section><h2>共用帳務警示</h2>{error ? <p role="alert">帳務警示暫時無法取得，請重新整理。</p> : !data ? <p role="status">正在載入帳務警示…</p> : !data.length ? <p className="finance-state">目前沒有帳務警示。</p> : data.map(row => <div key={row.case_no}><button className="finance-btn-secondary" type="button" onClick={() => onCase(row.case_no)}>{row.case_no} · {row.client_name} · 查看案件</button><AccountingWarningList data={row} onChange={() => setRevision(value => value + 1)} /></div>)}</section>;
}

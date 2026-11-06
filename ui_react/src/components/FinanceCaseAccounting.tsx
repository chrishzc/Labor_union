/**
 * File: FinanceCaseAccounting.tsx
 * Description: 案件帳務精簡抽屜與警示清單，提供各期核銷、補助方案、銀行對帳虛擬帳號與退款帳戶核對。
 */
import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import {financeAccountingClient,type CaseAccounting,type AccountingWarning} from '../api/finance_import/finance_accounting_client';
import {paymentOverdueReminderClient,type CasePaymentReminder} from '../api/line_order_groups/payment_overdue_reminder_client';
import {ordersQueryClient} from '../api/orders/order_query_client';
import type {OrderDetail} from '../api/orders/order_query_schemas';
import {clientRegistryClient} from '../api/client_registry/client_registry_client';
import type {ClientRegistryDetail} from '../api/client_registry/client_registry_schemas';
import {caseVirtualAccountClient,type CaseVirtualAccountView} from '../api/client_finance/case_virtual_account_client';
import {financeMoney} from './FinanceReceiptsWorkspace';
import {useUnsavedChanges,useUnsavedNavigation} from './UnsavedChanges';
import {ApiHttpError} from '../api/shared/typed_errors';
import {FinanceSubsidyPlanForm,subsidyPlanLabels,subsidyPlanTargets} from './FinanceSubsidyPlanForm';
import {FinanceCaseNotice,lastNotification,notificationTime,notificationStatus} from './FinanceCaseNotice';
import {ClientReceiptReconciliationPanel} from './ClientReceiptReconciliationPanel';
import {clientReceiptQueryClient} from '../api/client_finance/client_receipt_query_client';
import type {ClientReceiptQuery} from '../api/client_finance/client_receipt_query_schemas';
import {CaseDifferenceResolutionWorkbench} from './CaseDifferenceResolutionWorkbench';
import {differenceResolutionClient,type ClientDifferenceView} from '../api/client_finance/difference_resolution_client';
import './FinanceCaseAccounting.css';
import './FinanceCompactCase.css';

const TAIWAN_BANKS: Record<string, string> = {
  '004': '臺灣銀行', '005': '土地銀行', '006': '合作金庫', '007': '第一銀行', '008': '華南銀行', '009': '彰化銀行',
  '011': '上海商銀', '012': '台北富邦', '013': '國泰世華', '016': '高雄銀行', '017': '兆豐銀行', '050': '臺灣企銀',
  '052': '渣打銀行', '053': '台中銀行', '054': '京城銀行', '102': '華泰銀行', '103': '新光銀行', '108': '陽信銀行',
  '147': '三信商銀', '700': '中華郵政', '803': '聯邦銀行', '805': '遠東銀行', '806': '元大銀行', '807': '永豐銀行',
  '808': '玉山銀行', '809': '凱基銀行', '810': '星展銀行', '812': '台新銀行', '816': '安泰銀行', '822': '中國信託',
};

export function formatBankDisplay(code: string | null | undefined): string {
  if (!code) return '';
  const trimmed = code.trim();
  if (trimmed.length < 3) return trimmed;
  const head = trimmed.slice(0, 3);
  const branch = trimmed.length > 3 ? trimmed.slice(3) : '';
  const bankName = TAIWAN_BANKS[head];
  if (!bankName) return branch ? `${head}（分行 ${branch}）` : head;
  return branch ? `${head} ${bankName}（分行 ${branch}）` : `${head} ${bankName}`;
}

export function isSameMonth(dateA?: string | null, dateB?: string | null): boolean {
  if (!dateA || !dateB) return false;
  return dateA.slice(0, 7) === dateB.slice(0, 7);
}

export function buildDefaultVirtualAccount(caseNo: string): string | null {
  if (!caseNo) return null;
  const match = caseNo.match(/^A?(\d{3})(\d{3,6})$/);
  if (!match) return null;
  const prefix = '99781699';
  const year = match[1];
  const rawSeq = parseInt(match[2], 10);
  if (isNaN(rawSeq)) return null;
  const accountSeq = caseNo.startsWith('A') ? rawSeq + 500 : rawSeq;
  if (accountSeq < 1 || accountSeq > 999) return null;
  return `${prefix}${year}${String(accountSeq).padStart(3, '0')}`;
}

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
 const[state,setState]=useState<{caseNo:string;data?:CaseAccounting;order?:OrderDetail;notices?:CasePaymentReminder[];registry?:ClientRegistryDetail;accountView?:CaseVirtualAccountView;receiptFacts?:ClientReceiptQuery;diffClient?:ClientDifferenceView;error?:string;noticeError?:boolean;loading?:boolean}>({caseNo:initialCase,loading:true});
 const[revision,setRevision]=useState(0),[view,setView]=useState<Stage|'plan'|null>(initialNoticeStage??null);
 const[activeDiffStage,setActiveDiffStage]=useState<Stage|null>(null);
 const[copied,setCopied]=useState(false);
 const section=useRef<HTMLElement>(null),returnScroll=useRef(0),returnFocus=useRef<HTMLElement|null>(null);
 useEffect(()=>{const controller=new AbortController();setState(old=>old.caseNo===initialCase?{...old,loading:true,error:undefined}:{caseNo:initialCase,loading:true});if(!initialCase)return()=>controller.abort();void Promise.allSettled([financeAccountingClient.query(initialCase,controller.signal),ordersQueryClient.getOrderDetail(initialCase,{signal:controller.signal}),paymentOverdueReminderClient.case(initialCase,controller.signal),clientRegistryClient.query(initialCase,controller.signal),caseVirtualAccountClient.query(initialCase,controller.signal),clientReceiptQueryClient.query(initialCase,{signal:controller.signal}),differenceResolutionClient.client(initialCase,controller.signal)]).then(([accounting,order,notices,registry,accountView,receiptFacts,diffClient])=>{if(controller.signal.aborted)return;if(accounting.status==='rejected'){const status=accounting.reason instanceof ApiHttpError?accounting.reason.status:0;setState({caseNo:initialCase,error:status===404?'找不到此案件，請確認案件編號。':status===401?'登入已失效，請重新登入後查詢。':status===403?'目前沒有查閱帳務的權限。':'帳務資料暫時無法取得，請稍後重新查詢。'});return;}setState({caseNo:initialCase,data:accounting.value,order:order.status==='fulfilled'?order.value:undefined,notices:notices.status==='fulfilled'?notices.value:undefined,registry:registry.status==='fulfilled'?registry.value:undefined,accountView:accountView.status==='fulfilled'?accountView.value:undefined,receiptFacts:receiptFacts.status==='fulfilled'?receiptFacts.value:undefined,diffClient:diffClient.status==='fulfilled'?diffClient.value:undefined,noticeError:notices.status==='rejected',loading:false});});return()=>controller.abort();},[initialCase,revision]);
 useLayoutEffect(()=>{if(view!==null){section.current?.querySelector<HTMLElement>('.finance-case-subview h3')?.focus();return;}if(view===null&&returnFocus.current){const body=section.current?.closest('.drawer-body');if(body)body.scrollTop=returnScroll.current;const trigger=returnFocus.current;const target=trigger.isConnected?trigger:section.current?.querySelector('summary');target?.focus({preventScroll:true});returnFocus.current=null;}},[view,!!state.data]);
 useEffect(()=>{if(state.caseNo===initialCase&&state.data)onIdentity?.(initialCase,state.data.client_name);},[initialCase,state.caseNo,state.data,onIdentity]);
 function refresh(){setRevision(v=>v+1);onChanged?.();}
 function open(next:Stage|'plan'){returnFocus.current=document.activeElement instanceof HTMLElement?document.activeElement:null;returnScroll.current=section.current?.closest('.drawer-body')?.scrollTop??0;requestLeave(()=>setView(next));}
 function back(){requestLeave(()=>setView(null));}
 function copyVirtual(val:string){if(!val)return;if(typeof navigator!=='undefined'&&navigator.clipboard){void navigator.clipboard.writeText(val).then(()=>{setCopied(true);setTimeout(()=>setCopied(false),2000);});}}
 const data=state.caseNo===initialCase?state.data:undefined;
 const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Taipei',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
 if(!initialCase)return <p>請從案件清單選擇案件。</p>;
 const selected=data?.subsidy_plan?.events.at(-1)?.scheme;
 const staff=data?[...new Set(data.staff_items.filter(row=>row.direction==='payable').map(row=>row.party))].join('、'):'';
 const staffItems=data?.staff_items.filter(row=>row.direction==='payable')??[];
 const staffTransactions=data?.transactions.filter(row=>row.kind==='payout'||staffItems.some(s=>s.identity===row.item_identity))??[];
 const staffPayableTotal=staffItems.reduce((sum,item)=>sum+item.expected_ntd,0);
 const staffPaidTotal=staffItems.reduce((sum,item)=>sum+item.actual_ntd,0);
 const staffRemainingTotal=staffItems.reduce((sum,item)=>sum+(item.remaining_ntd??Math.max(0,item.expected_ntd-item.actual_ntd)),0);

 const refundClientItems=data?.client_items.filter(row=>row.direction==='payable')??[];
 const refundTransactions=data?.transactions.filter(row=>row.kind==='refund'||refundClientItems.some(r=>r.identity===row.item_identity))??[];
 const refundRemainingTotal=refundClientItems.reduce((sum,item)=>sum+(item.remaining_ntd??Math.max(0,item.expected_ntd-item.actual_ntd)),0);

 const subsidyTotal=data?.subsidy_ntd??0;
 const govBankFacts=data?.bank_facts?.filter(b=>b.cash_flow==='G')??[];
 const govReceivedNtd=data?.cash_by_flow?.G??govBankFacts.reduce((s,b)=>s+b.amount_ntd,0);

 const virtualAccount=state.accountView?.imported_virtual_accounts?.[0]??state.registry?.finance?.values?.virtual_account??state.accountView?.built_in_virtual_account??buildDefaultVirtualAccount(initialCase);
 const isImportedVirtual=(state.accountView?.imported_virtual_accounts?.length??0)>0;
 const hasMultipleImported=(state.accountView?.imported_virtual_accounts?.length??0)>1;
 const refundBankCode=state.registry?.beclass?.values?.refund_bank_code??null;
 const refundAccountNo=state.registry?.beclass?.values?.refund_account_no??null;
 const refundAccountStatus=state.registry?.beclass?.values?.refund_account_status??null;
 const refundName=state.registry?.beclass?.values?.name??state.registry?.client?.values?.name??data?.client_name??'';
 const contactPhone=state.registry?.beclass?.values?.phone??state.registry?.client?.values?.phone??null;

 return <section ref={section} className="case-accounting finance-compact-case" aria-label="案件帳務內容">
 {!embedded&&data&&<h2>{data.case_no} · {data.client_name}</h2>}{state.error&&<p role="alert">{state.error}</p>}{state.loading&&<p role="status">正在讀取案件資料…</p>}{state.error&&<button onClick={()=>setRevision(v=>v+1)}>重新讀取案件</button>}
 {data&&<><div hidden={view!==null}>
 <dl className="finance-compact-facts" aria-label="案件精簡摘要"><div><dt>相關月嫂</dt><dd>{staff||state.order?.staff_name||'待確認'}</dd></div><div><dt>實際開始</dt><dd>{state.order?.actual_start_date??'待確認'}</dd></div><div><dt>實際結束</dt><dd>{state.order?.actual_end_date??'待確認'}</dd></div><div><dt>案件總額 T</dt><dd>{money(data.staff_receivable_ntd)}</dd></div></dl>
 <section className="finance-reconciliation-card" aria-label="銀行對帳與帳戶資訊">
   <div className="finance-reconciliation-header">
     <div className="finance-reconciliation-title">
       <h4>銀行對帳與帳戶核對資訊</h4>
       <span className="finance-reconciliation-hint">核對永豐銷帳編號與台新退款／出款流水</span>
     </div>
     {contactPhone && <span className="finance-reconciliation-phone">聯絡電話：{contactPhone}</span>}
   </div>
   <dl className="finance-reconciliation-grid">
     <div className="finance-reconciliation-item">
       <dt>永豐專屬虛擬帳號</dt>
       <dd>
         {virtualAccount ? (
           <div className="finance-account-mono-group">
             <strong className="finance-mono-text" data-testid="virtual-account-display">{virtualAccount}</strong>
             <button type="button" className="finance-copy-chip" onClick={()=>copyVirtual(virtualAccount)} aria-label="複製虛擬帳號">{copied ? '已複製' : '複製'}</button>
             {isImportedVirtual && <span className="finance-tag-imported" title="人工匯入指定之虛擬帳號">匯入</span>}
             {hasMultipleImported && <span className="finance-tag-warn" title="名冊存在多筆匯入虛擬帳號，請確認">多筆衝突</span>}
           </div>
         ) : (
           <span className="finance-missing-text" data-testid="virtual-account-missing">尚未設定 / 無虛擬帳號</span>
         )}
       </dd>
     </div>
     <div className="finance-reconciliation-item">
       <dt>退款銀行與分行</dt>
       <dd>
         {refundBankCode ? (
           <span className="finance-bank-text" data-testid="refund-bank-display">{formatBankDisplay(refundBankCode)}</span>
         ) : (
           <span className="finance-missing-text" data-testid="refund-bank-missing">待補齊 / 未填寫銀行代碼</span>
         )}
       </dd>
     </div>
     <div className="finance-reconciliation-item">
       <dt>退款帳號</dt>
       <dd>
         {refundAccountNo ? (
           <strong className="finance-mono-text" data-testid="refund-account-display">{refundAccountNo}</strong>
         ) : (
           <span className="finance-missing-text" data-testid="refund-account-missing">待補齊 / 未填寫帳號</span>
         )}
       </dd>
     </div>
     <div className="finance-reconciliation-item">
       <dt>退款戶名／登錄狀態</dt>
       <dd>
         <div className="finance-status-group">
           <span>{refundName || '待確認'}</span>
           {refundAccountStatus === 'complete' ? (
             <span className="finance-badge-complete">已登錄完整</span>
           ) : (refundBankCode || refundAccountNo) ? (
             <span className="finance-badge-partial">資料未齊全</span>
           ) : (
             <span className="finance-badge-incomplete">未填寫</span>
           )}
         </div>
       </dd>
     </div>
   </dl>
   <div className="finance-reconciliation-footer">
     <small>提示：若銀行對帳單未配對成功，請核對「永豐入帳銷帳編號」是否為此 14 碼虛擬帳號；出款／退款核對客戶上述「退款帳號末四碼」與「戶名」。缺少帳號時請至客戶名冊補齊。</small>
   </div>
 </section>
 <details className="finance-case-block" open><summary>01　客戶繳款</summary><div className="finance-case-block-body"><div className="finance-table-container" tabIndex={0} role="region" aria-label="各期繳款與通知，可左右捲動"><table className="finance-table finance-case-periods"><thead><tr><th>期款</th><th>原到期日</th><th>應繳</th><th>已收／待收</th><th>入帳資訊</th><th>通知時間</th><th>通知</th></tr></thead><tbody>{stages.map(stage=>{
 const sources=data.client_items.filter(row=>row.direction==='receivable'&&row.payment_stage===stage),item=sources.length===1?sources[0]:undefined;
 const exempt=data.customer_fully_received===true&&data.customer_amount_ntd===0;
 const expected=item?.expected_ntd??(exempt?0:null),actual=item?.actual_ntd??(exempt?0:null),remaining=item?.remaining_ntd??(exempt?0:null);
 const notice=state.notices?.find(row=>row.payment_stage===stage),last=lastNotification(notice);
 const receipts=item?data.transactions.filter(row=>row.item_identity===item.identity&&row.kind==='receipt'&&row.amount_ntd>0).slice().sort((a,b)=>b.occurred_on.localeCompare(a.occurred_on)):[];
 const monthPending=item?.due_date&&remaining!=null&&remaining>0?state.receiptFacts?.bank_facts.filter(b=>isSameMonth(b.transaction_date,item.due_date))??[]:[];
 const pendingSum=monthPending.reduce((sum,r)=>sum+r.amount_ntd,0);
  const diff=pendingSum-(expected??0);
  const hasDiff=(remaining!=null&&remaining>0&&((actual??0)>0||monthPending.length>0))||monthPending.length>0;
  return <tr key={stage} data-payment-stage={stage} className={data.collection_progress?.stage===stage?'is-current':''}><td><strong>{stageNames[stage]}</strong>{stage==='deposit'&&<small>含樓層／其他費用</small>}</td><td>{expected===0?'不需繳納':item?.due_date??'日期待確認'}{remaining!=null&&remaining>0&&item?.due_date&&<small>{item.due_date>today?'未到期':item.due_date===today?'今日到期':'逾期'}</small>}</td><td>{money(expected)}</td><td><span>已收 {money(actual)}</span>{remaining===0?<small className="finance-paid">{expected===0?'免繳':'已繳齊'}</small>:<small>待收 {money(remaining)}</small>}</td><td>{receipts.length?<><span>{receipts[0].occurred_on} · {receipts[0].bank==='sinopac'?'永豐':receipts[0].bank==='taishin'?'台新':receipts[0].bank==='legacy'?'歷史來源':'原來源'}</span>{receipts.length>1&&<details><summary>{receipts.length} 筆入帳</summary>{receipts.map(row=><p key={row.identity}>{row.occurred_on} · {money(row.amount_ntd)}</p>)}</details>}{monthPending.length>0&&<div className="finance-pending-match-cell" data-testid={`pending-match-${stage}`}><span>待核對入款 {money(pendingSum)}</span><small className={diff<0?'finance-diff-under':diff>0?'finance-diff-over':'finance-paid'}>{diff<0?`短少 ${money(Math.abs(diff))}`:diff>0?`超收 ${money(diff)}`:'金額相符'}</small></div>}</>:monthPending.length>0?<div className="finance-pending-match-cell" data-testid={`pending-match-${stage}`}><span>待核對入款 {money(pendingSum)}</span><small className={diff<0?'finance-diff-under':diff>0?'finance-diff-over':'finance-paid'}>{diff<0?`短少 ${money(Math.abs(diff))}`:diff>0?`超收 ${money(diff)}`:'金額相符'}</small></div>:<span>{item||exempt?'尚無已核銷入帳':'來源待確認'}</span>}</td><td>{last?notificationTime(last):notice?(notice.history.length?'尚無成功通知':'尚未通知'):'待確認'}{notice&&notificationStatus(notice)&&<small>{notificationStatus(notice)}</small>}</td><td><div className="finance-case-period-actions">{hasDiff&&<button type="button" className="finance-btn-secondary finance-case-diff-button" aria-label={'處置'+stageNames[stage]+'差額'} onClick={()=>setActiveDiffStage(activeDiffStage===stage?null:stage)}>{activeDiffStage===stage?'收合處置':'處置差額'}</button>}<button type="button" className="finance-btn-primary finance-case-notice-button" aria-label={'通知'+stageNames[stage]} disabled={remaining==null||remaining<=0||!notice?.can_send||!!state.loading} title={remaining===0?(expected===0?'本期免繳':'本期已繳齊'):notice?.unavailable_reason??(notice?'查看本期通知內容與紀錄':'通知來源待確認')} onClick={()=>open(stage)}>{hasDiff&&diff<0?'通知補繳':'通知'}</button></div></td></tr>;
  })}</tbody></table></div>{activeDiffStage&&<CaseDifferenceResolutionWorkbench caseNo={initialCase} stageName={stageNames[activeDiffStage]} stageKey={activeDiffStage} expectedNtd={data.client_items.find(row=>row.direction==='receivable'&&row.payment_stage===activeDiffStage)?.expected_ntd??0} actualNtd={data.client_items.find(row=>row.direction==='receivable'&&row.payment_stage===activeDiffStage)?.actual_ntd??0} remainingNtd={data.client_items.find(row=>row.direction==='receivable'&&row.payment_stage===activeDiffStage)?.remaining_ntd??0} diffNtd={(()=>{const item=data.client_items.find(row=>row.direction==='receivable'&&row.payment_stage===activeDiffStage);const rem=item?.remaining_ntd??0;const monthP=item?.due_date?state.receiptFacts?.bank_facts.filter(b=>isSameMonth(b.transaction_date,item.due_date))??[]:[];const pSum=monthP.reduce((s,r)=>s+r.amount_ntd,0);return pSum>0?(pSum-(item?.expected_ntd??0)):-rem;})()} diffClient={state.diffClient} recipientLabel={state.registry?.client?.values?.name?`${state.registry.client.values.name}（客戶LINE）`:undefined} onOpenNotice={()=>open(activeDiffStage)} onChanged={refresh} onClose={()=>setActiveDiffStage(null)}/>}{state.noticeError&&<p role="status">通知資料暫時無法取得，時間保留待確認。<button className="finance-btn-link" onClick={()=>setRevision(v=>v+1)}>重新讀取通知</button></p>}
<div className="finance-case-reconciliation-wrapper">
  <ClientReceiptReconciliationPanel caseNo={initialCase} onChanged={refresh} refreshVersion={revision}/>
</div></div></details>
 <details className="finance-case-block" open><summary>02　補助退款方案</summary><div className="finance-case-block-body"><div className="finance-compact-plan"><div><small>本案補助 {money(data.subsidy_ntd)}</small><strong>{selected?subsidyPlanLabels[selected]:'尚未設定'}</strong><p>{selected?subsidyPlanTargets[selected]:'由人員設定補助款歸屬，不從歷史金流自動代選。'}</p></div><button type="button" className="finance-btn-primary" disabled={!data.subsidy_plan||!!state.loading} onClick={()=>open('plan')}>{selected?'修改補助退款方案':'設定補助退款方案'}</button></div><p>可提前設定，不改各期應繳。案件結束後再處理補助與應付清單。</p>{selected&&<p role="status">{data.ongoing_completed?'客戶款已齊且方案已保存，已移出進行中案件。':'方案已保存，客戶款未齊時仍保留在進行中案件。'}</p>}</div></details>
 <details className="finance-case-block" open><summary>03　月嫂薪資</summary><div className="finance-case-block-body">
  <div className="finance-staff-summary-cards" aria-label="月嫂薪資匯總">
    <div className="finance-staff-summary-card">
      <small>應付月嫂總額</small>
      <strong>{money(staffPayableTotal || data.payable_ntd)}</strong>
    </div>
    <div className="finance-staff-summary-card">
      <small>已出款金額</small>
      <strong>{money(staffPaidTotal || data.paid_ntd)}</strong>
    </div>
    <div className="finance-staff-summary-card">
      <small>尚待出款</small>
      <strong className={staffRemainingTotal === 0 ? 'finance-paid' : ''}>
        {staffRemainingTotal === 0 ? '已付齊' : money(staffRemainingTotal)}
      </strong>
    </div>
  </div>

  <div className="finance-table-container" tabIndex={0} role="region" aria-label="月嫂薪資與核銷明細，可左右捲動">
    <table className="finance-table finance-case-periods">
      <thead>
        <tr>
          <th>服務項目</th>
          <th>預計撥款日</th>
          <th>應付</th>
          <th>已付／待付</th>
          <th>出款資訊</th>
          <th>核銷狀態</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        {staffItems.length > 0 ? (
          staffItems.map(item => {
            const diff = item.expected_ntd - item.actual_ntd;
            const isFeeSettled = diff > 0 && diff <= 100;
            const isSettled = item.settled || item.remaining_ntd === 0 || (item.actual_ntd >= item.expected_ntd && item.has_payment);
            return (
              <tr key={item.identity}>
                <td>
                  <strong>{item.party}</strong>
                  <small>{item.label || '月嫂服務費'}</small>
                </td>
                <td>
                  <span>{item.due_date ?? '服務結束次月15日'}</span>
                  {item.due_date && (
                    <small>{item.due_date > today ? '未到期' : item.due_date === today ? '今日到期' : '已屆撥款日'}</small>
                  )}
                </td>
                <td>{money(item.expected_ntd)}</td>
                <td>
                  <span>已付 {money(item.actual_ntd)}</span>
                  {isFeeSettled ? (
                    <small className="finance-paid">手續費內扣結清</small>
                  ) : isSettled ? (
                    <small className="finance-paid">已結清</small>
                  ) : item.remaining_ntd != null && item.remaining_ntd > 0 ? (
                    <small>待付 {money(item.remaining_ntd)}</small>
                  ) : diff < 0 ? (
                    <small className="finance-diff-over">超付 {money(Math.abs(diff))}</small>
                  ) : (
                    <small>{money(item.remaining_ntd)}</small>
                  )}
                </td>
                <td>
                  {staffTransactions.length > 0 ? (
                    <>
                      <span>{staffTransactions[0].occurred_on} · {staffTransactions[0].bank === 'taishin' ? '台新銀行' : staffTransactions[0].bank === 'sinopac' ? '永豐銀行' : (staffTransactions[0].bank ?? '銀行出款')}</span>
                      {staffTransactions.length > 1 && (
                        <details>
                          <summary>{staffTransactions.length} 筆出款</summary>
                          {staffTransactions.map(t => (
                            <p key={t.identity}>{t.occurred_on} · {t.bank === 'taishin' ? '台新' : (t.bank ?? '銀行')} · {money(t.amount_ntd)}</p>
                          ))}
                        </details>
                      )}
                    </>
                  ) : (
                    <span>尚無已核銷出款</span>
                  )}
                </td>
                <td>
                  {isFeeSettled ? (
                    <span className="finance-tag-imported" title="跨行轉帳 100 元以內手續費由收款方負擔並結清">手續費內扣結清</span>
                  ) : diff < 0 ? (
                    <span className="finance-tag-warn">超付款待核對</span>
                  ) : isSettled ? (
                    <span className="finance-paid">出款已結清</span>
                  ) : item.has_payment ? (
                    <span>部分出款</span>
                  ) : (
                    <span>待排程出款</span>
                  )}
                </td>
                <td>
                  <div className="finance-case-period-actions">
                    {diff !== 0 && !isFeeSettled && (
                      <button
                        type="button"
                        className="finance-btn-secondary finance-case-diff-button"
                        title="處置月嫂薪資差額"
                        onClick={() => alert(`月嫂款項差額 ${money(Math.abs(diff))}，請核對銀行出款流水。`) }
                      >
                        處置差額
                      </button>
                    )}
                    <button
                      type="button"
                      className="finance-btn-primary finance-case-notice-button"
                      disabled
                      title="月嫂撥款通知由系統排程批次發送"
                    >
                      通知
                    </button>
                  </div>
                </td>
              </tr>
            );
          })
        ) : (
          <tr>
            <td colSpan={7} className="finance-state">本案目前無月嫂應付項目。</td>
          </tr>
        )}
      </tbody>
    </table>
  </div>
 </div></details>

 <details className="finance-case-block" open><summary>04　補助退款與核銷</summary><div className="finance-case-block-body">
  <div className="finance-refund-summary-bar"><span>客戶退款待結：<strong>{refundRemainingTotal === 0 ? '已結清' : money(refundRemainingTotal)}</strong></span><span>政府款待入：<strong>{subsidyTotal > 0 ? (govReceivedNtd >= subsidyTotal ? '已全額入帳' : money(Math.max(0, subsidyTotal - govReceivedNtd))) : '無補助'}</strong></span></div>
  <div className="finance-table-container" tabIndex={0} role="region" aria-label="補助退款與政府核銷明細，可左右捲動">
    <table className="finance-table finance-case-periods">
      <thead>
        <tr>
          <th>項目</th>
          <th>原到期日</th>
          <th>應退／應收</th>
          <th>已退(收)／待退(收)</th>
          <th>出款／入帳資訊</th>
          <th>核銷狀態</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        {refundClientItems.length > 0 ? (
          refundClientItems.map(row => {
            const isRefundSettled = row.settled || row.remaining_ntd === 0 || (row.actual_ntd >= row.expected_ntd && row.has_payment);
            return (
              <tr key={row.identity}>
                <td>
                  <strong>客戶退款</strong>
                  <small>{row.party || refundName} · {row.label}</small>
                </td>
                <td>
                  <span>{row.due_date ?? '市府核撥後退款'}</span>
                  <small>{isRefundSettled ? '已結算' : '案件結束結算'}</small>
                </td>
                <td>{money(row.expected_ntd)}</td>
                <td>
                  <span>已退 {money(row.actual_ntd)}</span>
                  {isRefundSettled ? (
                    <small className="finance-paid">已結清</small>
                  ) : (
                    <small>待退 {money(row.remaining_ntd)}</small>
                  )}
                </td>
                <td>
                  {refundTransactions.length > 0 ? (
                    <>
                      <span>{refundTransactions[0].occurred_on} · {refundTransactions[0].bank === 'taishin' ? '台新銀行' : (refundTransactions[0].bank ?? '銀行退款')}</span>
                      {refundTransactions.length > 1 && (
                        <details>
                          <summary>{refundTransactions.length} 筆退款</summary>
                          {refundTransactions.map(t => (
                            <p key={t.identity}>{t.occurred_on} · {money(t.amount_ntd)}</p>
                          ))}
                        </details>
                      )}
                    </>
                  ) : (
                    <div>
                      <span>{refundBankCode ? formatBankDisplay(refundBankCode) : '未登記退款銀行'}</span>
                      <small className="finance-mono-text">{refundAccountNo ? `末四碼 ${refundAccountNo.slice(-4)}` : '待補齊帳號'}</small>
                    </div>
                  )}
                </td>
                <td>
                  {isRefundSettled ? (
                    <span className="finance-paid">已完成退款</span>
                  ) : refundAccountStatus === 'complete' ? (
                    <span>待出款（帳戶齊全）</span>
                  ) : (
                    <span className="finance-diff-under">帳戶待補齊</span>
                  )}
                </td>
                <td>
                  <div className="finance-case-period-actions">
                    <button
                      type="button"
                      className="finance-btn-primary finance-case-notice-button"
                      disabled={isRefundSettled}
                      title={isRefundSettled ? '退款已結清' : '退款進度通知'}
                    >
                      通知
                    </button>
                  </div>
                </td>
              </tr>
            );
          })
        ) : (
          <tr>
            <td>
              <strong>客戶退款</strong>
              <small>正常履約無扣減</small>
            </td>
            <td>不需退款</td>
            <td>NT$ 0</td>
            <td>
              <span>已退 NT$ 0</span>
              <small className="finance-paid">無退款義務</small>
            </td>
            <td>
              <span>預先登記備查</span>
              <small>{refundBankCode ? formatBankDisplay(refundBankCode) : '未填銀行'} {refundAccountNo ? `(${refundAccountNo.slice(-4)})` : ''}</small>
            </td>
            <td>
              <span className="finance-paid">免退款</span>
            </td>
            <td>
              <div className="finance-case-period-actions">
                <button type="button" className="finance-btn-secondary" disabled>免操作</button>
              </div>
            </td>
          </tr>
        )}

        <tr>
          <td>
            <strong>政府補助款</strong>
            <small>{selected ? subsidyPlanLabels[selected] : (data.scheme ?? '尚未設定方案')}</small>
          </td>
          <td>
            <span>依市府審查期程</span>
            <small>{subsidyTotal > 0 && govReceivedNtd >= subsidyTotal ? '款項已撥入' : '審核撥付中'}</small>
          </td>
          <td>{money(subsidyTotal)}</td>
          <td>
            <span>實撥 {money(govReceivedNtd)}</span>
            {subsidyTotal === 0 ? (
              <small className="finance-paid">自費案免請領</small>
            ) : govReceivedNtd >= subsidyTotal ? (
              <small className="finance-paid">已全額撥入</small>
            ) : (
              <small>待撥入 {money(Math.max(0, subsidyTotal - govReceivedNtd))}</small>
            )}
          </td>
          <td>
            {govBankFacts.length > 0 ? (
              <>
                <span>{govBankFacts[0].occurred_on} · 永豐 (G)</span>
                {govBankFacts.length > 1 && (
                  <details>
                    <summary>{govBankFacts.length} 筆公款</summary>
                    {govBankFacts.map((b, i) => (
                      <p key={i}>{b.occurred_on} · {money(b.amount_ntd)}</p>
                    ))}
                  </details>
                )}
              </>
            ) : (
              <span>{subsidyTotal === 0 ? '自費案無公款' : '待市府公款撥入'}</span>
            )}
          </td>
          <td>
            {subsidyTotal === 0 ? (
              <span className="finance-paid">自費案免核銷</span>
            ) : govReceivedNtd >= subsidyTotal ? (
              <span className="finance-paid">已全額沖正</span>
            ) : govReceivedNtd > 0 ? (
              <span>部分撥入沖正</span>
            ) : (
              <span>待撥入沖正</span>
            )}
          </td>
          <td>
            <div className="finance-case-period-actions">
              <button
                type="button"
                className="finance-btn-secondary"
                onClick={() => open('plan')}
                title="修改補助款歸屬方案"
              >
                {selected ? '修改方案' : '設定方案'}
              </button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <div className="finance-subsidy-flow-note">
    <small><strong>金流規則說明：</strong>
      {selected === 'advance'
        ? '客戶先墊後退（方案二）：客戶繳全額，工會先撥付月嫂薪資，政府補助撥入 (G) 後，由工會自台新退款 (R台) 予客戶。'
        : selected === 'split'
        ? '分拆撥付（方案一）：客戶僅繳自備款，補助款由月嫂向政府申請領取；工會無墊付亦無退款。'
        : selected === 'direct'
        ? '政府直撥（方案三）：政府款逕付月嫂帳戶；工會不經手補助款流水。'
        : '由人員設定補助款歸屬方案，結算時依方案進行金流沖正與核銷。'}
    </small>
  </div>
 </div></details>
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

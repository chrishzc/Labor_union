import {useEffect,useRef,useState} from 'react';
import {differenceResolutionClient,type ClientDifferenceView,type PayrollAmountView,type StaffRecoveryView,type DifferenceCommand} from '../api/client_finance/difference_resolution_client';
import {ApiHttpError} from '../api/shared/typed_errors';
import {useUnsavedChanges,useUnsavedNavigation} from './UnsavedChanges';
import {ClientOverRefundRecoveryWorkbench} from './ClientOverRefundRecoveryWorkbench';
import {StaffOverpaymentRecoveryActions} from './StaffOverpaymentRecoveryActions';

const money=(n:number)=>`NT$ ${n.toLocaleString('zh-TW')}`;
const labels:Record<string,string>={loss:'確認收不回，記錄損失',reduce_service_fee:'同意減收服務費',union_bank_fee:'由工會負擔手續費',absorb_overpayment:'工會承擔超付款，不再追回',close_refund:'確認不用再補付／退款',manual_amount:'人工更正系統金額',adopt_calculation:'採用最新計算，恢復自動更新',source_update:'來源重新計算'};
const descriptions:Record<string,string>={loss:'這次金額記為損失；原欠款及銀行實收付保留，剩餘款項仍可追收。',reduce_service_fee:'只減少客戶應收，差額由工會承擔，月嫂薪資不變。',union_bank_fee:'用確認的手續費抵除待收差額；不增加一筆銀行出款。已另扣的銀行手續費不重複列支。',absorb_overpayment:'由工會承擔這次金額；未承擔的餘額繼續追償，原付款保留。',close_refund:'只結清此筆客戶待退款；不另外保存同意證明、放棄金額明細或這次操作紀錄。此為可選方式，系統沒有預設選項。',manual_amount:'原銀行收付不變。已核銷款的更正另列差額；之後來源變動保留人工金額並顯示最新計算。',adopt_calculation:'採用目前的計算結果並恢復自動更新；以後來源變動直接更新，已核銷紀錄保留。'};
type Owner='client'|'payroll'|'staff';
type Target={identity:string;label:string;options:string[];version:number;remaining:number;effective?:number;computed?:number};

export function AccountingDifferencePanel({caseNo,onChanged,refreshVersion=0}:{caseNo:string;onChanged:()=>void;refreshVersion?:number}){
  const [client,setClient]=useState<ClientDifferenceView|null>(null);
  const [payroll,setPayroll]=useState<PayrollAmountView|null>(null);
  const [staff,setStaff]=useState<StaffRecoveryView|null>(null);
  const [owner,setOwner]=useState<Owner>('client');
  const [identity,setIdentity]=useState('');const [action,setAction]=useState('');const [amount,setAmount]=useState('');const [reason,setReason]=useState('');
  const [confirmed,setConfirmed]=useState(false);const [busy,setBusy]=useState(false);const [unknown,setUnknown]=useState(false);
  const [error,setError]=useState('');const [message,setMessage]=useState('');const [revision,setRevision]=useState(0);
  const command=useRef<{owner:Owner;body:DifferenceCommand}|null>(null);
  const {requestLeave}=useUnsavedNavigation();
  useUnsavedChanges('帳務差額與金額更正',[identity,action,amount,reason].map((after,i)=>({label:['款項','方式','金額','原因'][i],before:'',after})).filter(x=>!!x.after),{busy:busy||unknown,discard:clear});
  const operationPending=useRef(false);operationPending.current=busy||unknown;
  useEffect(()=>{if(operationPending.current)return;const controller=new AbortController();setError('');setConfirmed(false);queueMicrotask(()=>{if(controller.signal.aborted)return;void Promise.all([differenceResolutionClient.client(caseNo,controller.signal),differenceResolutionClient.payroll(caseNo,controller.signal),differenceResolutionClient.staff(caseNo,controller.signal)]).then(([c,p,s])=>{if(!controller.signal.aborted){setClient(c);setPayroll(p);setStaff(s);}}).catch(()=>{if(!controller.signal.aborted)setError('差額資料暫時無法取得，請重新查詢。');});});return()=>controller.abort();},[caseNo,revision,refreshVersion]);
  const targets:Target[]=owner==='client'?(client?.items??[]).map(i=>({identity:i.identity,label:i.label,options:i.options,version:client!.version,remaining:i.remaining_ntd,effective:i.effective_ntd,computed:i.computed_ntd})):
    owner==='payroll'?(payroll?.items??[]).map(i=>({identity:i.identity,label:`${i.party} · 月嫂薪資`,options:['manual_amount','adopt_calculation'],version:payroll!.version,remaining:i.remaining_ntd,effective:i.effective_ntd,computed:i.computed_ntd})):
    (staff?.items??[]).filter(i=>i.remaining_ntd>0).map(i=>({identity:i.identity,label:`${i.party} · 超付追償`,options:['loss','absorb_overpayment'],version:i.version,remaining:i.remaining_ntd}));
  const target=targets.find(i=>i.identity===identity);
  const needsAmount=!['close_refund','adopt_calculation'].includes(action);
  const validAmount=/^\d+$/.test(amount)&&Number.isSafeInteger(Number(amount))&&(action==='manual_amount'?Number(amount)>=0:Number(amount)>0&&Number(amount)<=(target?.remaining??0));
  const canApply=!!target&&!!action&&target.options.includes(action)&&(!needsAmount||validAmount)&&(action==='close_refund'||!!reason.trim())&&confirmed;
  function clear(){setIdentity('');setAction('');setAmount('');setReason('');setConfirmed(false);}
  async function apply(){
    if(busy||(!unknown&&!canApply))return;
    if(!command.current&&target)command.current={owner,body:{identity,action,amount_ntd:needsAmount?Number(amount):null,reason:action==='close_refund'?'':reason.trim(),expected_version:target.version,key:crypto.randomUUID()}};
    if(!command.current)return;
    setBusy(true);setError('');setMessage('');
    try{await differenceResolutionClient.apply(caseNo,command.current.owner,command.current.body);setMessage('處理已完成，金額與剩餘款項已更新。');command.current=null;setUnknown(false);clear();setRevision(v=>v+1);onChanged();}
    catch(caught){const unresolved=!(caught instanceof ApiHttpError)||caught.status>=500||caught.status===408;setUnknown(unresolved);if(!unresolved)command.current=null;setError(unresolved?'尚未確認儲存結果。請按「查回原次處理結果」，原操作會保留。':caught instanceof ApiHttpError?caught.message:'處理失敗，請重新查詢。');}
    finally{setBusy(false);}
  }
  return <section className="case-accounting-card accounting-difference-panel" aria-label="差額處理與人工金額更正"><h3>差額處理與人工金額更正</h3><p>先核對本案已匯入銀行款與合計，再選擇適用方式。差額不會自動認列，也不會修改銀行原始紀錄。</p>
    <div className="finance-filter-bar"><label>款項類型<select className="finance-select" value={owner} disabled={busy||unknown} onChange={e=>requestLeave(()=>{setOwner(e.target.value as Owner);clear();})}><option value="client">客戶收付款與退款追償</option><option value="payroll">月嫂薪資金額</option><option value="staff">薪資超付追償</option></select></label><button className="finance-btn-secondary" type="button" disabled={busy||unknown} onClick={()=>requestLeave(()=>{clear();setRevision(v=>v+1);})}>重新查詢差額</button></div>
    {error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
    {owner==='client'&&client&&<div className="finance-table-container"><table className="finance-table"><thead><tr><th>款項</th><th className="finance-num">原應收／應付</th><th className="finance-num">實際收付</th><th className="finance-num">已認列差額</th><th className="finance-num">尚待處理</th><th>金額模式／目前狀態</th></tr></thead><tbody>{client.items.map(i=><tr key={i.identity}><td>{i.label}</td><td className="finance-num">{money(i.expected_ntd)}</td><td className="finance-num">{money(i.actual_ntd)}</td><td className="finance-num">{money(i.noncash_ntd)}</td><td className="finance-num">{money(i.remaining_ntd)}</td><td>{i.mode==='manual'?`人工 ${money(i.effective_ntd)}；最新計算 ${money(i.computed_ntd)}`:'自動計算'}<br/>{i.status}{!!i.service_reduction_ntd&&<small>已減收 {money(i.service_reduction_ntd)} · 有效應收 {money(i.effective_charge_ntd??0)} · 月嫂薪資不變</small>}</td></tr>)}</tbody></table></div>}
    {owner==='payroll'&&payroll&&<div className="finance-table-container"><table className="finance-table"><thead><tr><th>對象</th><th className="finance-num">目前有效金額</th><th className="finance-num">最新系統計算</th><th>模式</th><th className="finance-num">實付</th></tr></thead><tbody>{payroll.items.map(i=><tr key={i.identity}><td>{i.party}</td><td className="finance-num">{money(i.effective_ntd)}</td><td className="finance-num">{money(i.computed_ntd)}</td><td>{i.mode==='manual'?'人工更正':'自動計算'}</td><td className="finance-num">{money(i.actual_ntd)}</td></tr>)}</tbody></table></div>}
    {owner==='staff'&&staff&&staff.items.map(i=><div key={i.identity}><strong>{i.party} · {i.status}</strong><p>原追償 {money(i.original_ntd)}；已作差額處理 {money(i.noncash_ntd)}；尚待追償 {money(i.remaining_ntd)}。關聯案件：{i.related_cases.join('、')}</p></div>)}
    <div className="finance-filter-bar"><label>選擇款項<select className="finance-select" disabled={busy||unknown} value={identity} onChange={e=>{setIdentity(e.target.value);setAction('');setAmount('');setConfirmed(false);}}><option value="">請選擇款項</option>{targets.map(i=><option value={i.identity} key={i.identity}>{i.label} · 待處理 {money(i.remaining)}</option>)}</select></label><label>處理方式<select className="finance-select" disabled={!target||busy||unknown} value={action} onChange={e=>{setAction(e.target.value);setAmount('');setConfirmed(false);}}><option value="">請由人員選擇</option>{target?.options.map(value=><option key={value} value={value}>{labels[value]??value}</option>)}</select></label></div>
    {action&&<><p>{descriptions[action]}</p>{needsAmount&&<label>{action==='manual_amount'?'更正後的應收／應付總額':'本次處理差額'}<input className="finance-input" type="number" min="0" step="1" value={amount} disabled={busy||unknown} onChange={e=>{setAmount(e.target.value);setConfirmed(false);}}/></label>}{action==='adopt_calculation'&&<p>目前有效金額 {money(target?.effective??0)}；採用最新計算 {money(target?.computed??0)}。</p>}{action!=='close_refund'&&<label className="case-accounting-field">更正原因／處理依據<textarea value={reason} maxLength={500} disabled={busy||unknown} onChange={e=>{setReason(e.target.value);setConfirmed(false);}}/></label>}<label><input type="checkbox" checked={confirmed} disabled={busy||unknown} onChange={e=>setConfirmed(e.target.checked)}/>我已核對款項、金額及處理方式</label><p><button className="finance-btn-primary" type="button" disabled={busy||(!unknown&&!canApply)} onClick={()=>void apply()}>{busy?'處理中…':unknown?'查回原次處理結果':labels[action]}</button></p></>}
    {owner==='client'&&client?.items.filter(i=>i.kind==='over_refund_recovery'&&i.remaining_ntd>0).map(i=><details className="accounting-recovery-cash" key={i.identity}><summary>登記已追回的客戶退款 · 尚待追回 {money(i.remaining_ntd)}</summary><p>以已匯入的銀行入款記錄實際追回金額；工會承擔或損失請使用上方差額處理。</p><ClientOverRefundRecoveryWorkbench caseNo={caseNo} recoveryIdentity={i.identity} cashOnly onCommitted={()=>{setRevision(v=>v+1);onChanged();}}/></details>)}
    {owner==='staff'&&staff?.items.filter(i=>i.remaining_ntd>0).map(i=><details className="accounting-recovery-cash" key={i.identity}><summary>登記已追回的月嫂超付款 · {i.party}</summary><p>以已匯入的銀行入款記錄實際追回金額；工會承擔或損失請使用上方差額處理。</p><StaffOverpaymentRecoveryActions staffId={i.staff_id} recoveryIdentity={i.identity} cashOnly onCommitted={()=>{setRevision(v=>v+1);onChanged();}}/></details>)}
    {!targets.length&&<p>目前沒有可處理的款項。</p>}
    <details><summary>金額更正與差額紀錄</summary>{owner==='payroll'?payroll?.events.map(e=><p key={e.identity}>{e.confirmed_on} · {labels[e.action]} · {money(e.before_ntd)} → {money(e.after_ntd)} · {e.reason} · {e.actor}</p>):(owner==='client'?client?.events:staff?.events)?.map(e=><p key={e.identity}>{e.confirmed_on} · {labels[e.action]} · {e.before_ntd!=null&&e.after_ntd!=null?`${money(e.before_ntd)} → ${money(e.after_ntd)}`:money(e.amount_ntd)} · {e.reason} · {e.actor}</p>)}</details>
  </section>;
}

import {useEffect,useRef,useState} from 'react';
import {financeAccountingClient,type CaseSubsidyPlan,type SubsidyPlanCommand,type CaseBankMemo,type SubsidyPlanPreview,type CaseArrangement,type ArrangementCommand} from '../api/finance_import/finance_accounting_client';
import {ApiHttpError} from '../api/shared/typed_errors';
import {useUnsavedDraft} from './UnsavedChanges';
export const subsidyPlanLabels={split:'客戶與政府分別入款',advance:'客戶先墊後退',direct:'政府直接付客戶'};
export const subsidyPlanTargets={split:'補助轉交月嫂，已包含在案件總額內',advance:'補助退還先墊款的客戶',direct:'政府直接付客戶，工會無補助退款應付'};
export function FinanceSubsidyPlanForm({caseNo,source,onSaved,onBack,bankMemos=[],subsidyAmount,arrangement,canConfirmDirect=false}:{
 caseNo:string;source:CaseSubsidyPlan;onSaved:(source:CaseSubsidyPlan|CaseArrangement)=>void;onBack:()=>void;bankMemos?:CaseBankMemo[];
 subsidyAmount?:number|null;arrangement?:CaseArrangement|null;canConfirmDirect?:boolean;
}){
 const[plan,setPlan]=useState(source),[choice,setChoice]=useState(source.events.at(-1)?.scheme??''),[busy,setBusy]=useState(false),[unknown,setUnknown]=useState(false),[error,setError]=useState('');
 const original=useRef<{command:SubsidyPlanCommand;key:string}|null>(null);
 const baseline=plan.events.at(-1)?.scheme??'';
 const[preview,setPreview]=useState<SubsidyPlanPreview|null>(null),[checking,setChecking]=useState(false);
 useEffect(()=>{setPreview(null);if(!choice||choice===baseline)return;const controller=new AbortController();setChecking(true);setError('');void financeAccountingClient.previewSubsidyPlan(caseNo,{scheme:choice as SubsidyPlanCommand['scheme'],expected_version:plan.version},controller.signal).then(result=>{if(!controller.signal.aborted)setPreview(result);}).catch(()=>{if(!controller.signal.aborted)setError('預檢未完成，請重新選擇方案或讀取目前資料。');}).finally(()=>{if(!controller.signal.aborted)setChecking(false);});return()=>controller.abort();},[caseNo,choice,baseline,plan.version]);
 const form=useUnsavedDraft('人工補助退款方案',{'補助方案':choice},{baseline:{'補助方案':baseline},busy:busy||unknown,discard:()=>{setChoice(baseline);original.current=null;}});
 async function execute(command:SubsidyPlanCommand,key:string){setBusy(true);setError('');try{const result=await financeAccountingClient.saveSubsidyPlan(caseNo,command,key);setPlan(result.plan);setChoice(result.plan.events.at(-1)?.scheme??'');setUnknown(false);original.current=null;onSaved(result.plan);}catch(failure){const status=failure instanceof ApiHttpError?failure.status:0;const uncertain=status===0||status>=500||status===408;setUnknown(uncertain);setError(uncertain?'保存結果尚未確認，請查回原操作結果，勿另建新次操作。':status===409?'方案版本已變更；選擇已保留，請重新讀取後核對。':'目前無法保存，請確認登入或權限。');}finally{setBusy(false);}}
 async function submit(){if(!choice||busy||unknown||checking||!preview||choice===baseline)return;const command={scheme:choice as SubsidyPlanCommand['scheme'],expected_version:plan.version,preview_fingerprint:preview.preview_fingerprint};const pending={command,key:crypto.randomUUID()};original.current=pending;await execute(pending.command,pending.key);}
 async function reload(){setBusy(true);setError('');try{setPlan(await financeAccountingClient.subsidyPlan(caseNo));original.current=null;}catch{setError('方案來源暫時無法讀取。');}finally{setBusy(false);}}
 const amount=preview?preview.subsidy_ntd:subsidyAmount;
 return <section className="finance-case-subview" aria-label="設定補助退款方案"><h3 tabIndex={-1}>設定補助退款方案</h3>
  <p>本案補助金額：{amount==null?'待確認':new Intl.NumberFormat('zh-TW').format(amount)+' 元'}。方案決定補助款對象，不改各期應繳、已核銷金額或日期。</p>
  <FinanceCaseBankMemos notes={bankMemos}/>
  {arrangement?.events.at(-1)?.action === 'confirm_direct' ? (
    <FinanceDirectArrangement caseNo={caseNo} action="withdraw_direct" version={arrangement.version} onSaved={onSaved} />
  ) : <>
  <form ref={form} onSubmit={e=>{e.preventDefault();void submit();}}>
   <fieldset className="finance-manual-plan-options" disabled={busy||unknown}><legend>補助款歸屬</legend>{(['split','advance'] as const).map(scheme=><label key={scheme}><input type="radio" name="subsidy-plan" value={scheme} checked={choice===scheme} onChange={()=>setChoice(scheme)}/><span><strong>{subsidyPlanLabels[scheme]}</strong><small>{subsidyPlanTargets[scheme]}</small></span></label>)}</fieldset>
   {checking&&<p role="status">正在確認補助給付條件…</p>}
   {preview&&<div aria-label="方案保存前預檢">
    {preview.blocker?<p role="alert">{preview.blocker}。仍可儲存補助方案，給付金額待核對。</p>:preview.confirmation_only?<p>服務尚未結束。本次只確認補助方案，給付金額仍待確認。</p>:preview.payables.length>0?<p>儲存方案時會記錄下列給付金額。付款與核銷另行辦理。</p>:<p>本次只確認補助方案。付款與核銷另行辦理。</p>}
    {preview.payables.length>0&&<ul>{preview.payables.map((item,i)=><li key={item.identity+':'+i}>{item.recipient==='client'?'應退客戶補助':item.recipient==='staff:subsidy'?'應付月嫂補助':'應付月嫂自備款'}：{new Intl.NumberFormat('zh-TW').format(item.amount_ntd)} 元，日期 {item.due_date??'待確認'}</li>)}</ul>}
   </div>}
   {error&&<p role="alert">{error}</p>}
   <div className="finance-row-actions"><button type="button" disabled={busy||unknown} className="finance-btn-secondary" onClick={onBack}>返回案件</button><button className="finance-btn-primary" disabled={busy||unknown||checking||!preview||!choice||choice===baseline}>{busy?'正在保存…':'儲存方案'}</button>{error&&!unknown&&<button type="button" disabled={busy} onClick={()=>void reload()}>重新讀取方案</button>}{unknown&&<button type="button" disabled={busy} onClick={()=>{const pending=original.current;if(pending)void execute(pending.command,pending.key);}}>確認原操作結果</button>}</div>
  </form>
  {arrangement && (canConfirmDirect
    ? <FinanceDirectArrangement caseNo={caseNo} action="confirm_direct" version={arrangement.version} onSaved={onSaved} />
    : <p>政府直接退給客戶需先確認本案實收及同案補助金流。</p>)}
  </>}
  {arrangement?.events.at(-1)?.action === 'confirm_direct' && <button type="button" className="finance-btn-secondary" onClick={onBack}>返回案件</button>}
 </section>;
}

function FinanceDirectArrangement({caseNo,action,version,onSaved}: {
 caseNo:string;action:ArrangementCommand['action'];version:number;onSaved:(arrangement:CaseArrangement)=>void;
}) {
 const [reason,setReason] = useState('');
 const [busy,setBusy] = useState(false);
 const [unknown,setUnknown] = useState(false);
 const [error,setError] = useState('');
 const pending = useRef<{command:ArrangementCommand;key:string}|null>(null);
 const confirm = action === 'confirm_direct';
 const form = useUnsavedDraft('政府直接退給客戶', {原因:reason}, {
   baseline:{原因:''},busy:busy||unknown,discard:()=>{setReason('');pending.current=null;},
 });
 async function submit() {
   if (busy || !reason.trim()) return;
   const request = pending.current ?? {
     command: {action,reason:reason.trim(),expected_version:version}, key:crypto.randomUUID(),
   };
   pending.current = request;
   setBusy(true);
   setError('');
   try {
     const receipt = await financeAccountingClient.confirmArrangement(caseNo,request.command,request.key);
     pending.current = null;
     onSaved(receipt.arrangement);
   } catch (failure) {
     const status = failure instanceof ApiHttpError ? failure.status : 0;
     const uncertain = status===0 || status===408 || status>=500;
     setUnknown(uncertain);
     if (!uncertain) pending.current = null;
     setError(uncertain
       ? '尚未查到正式結果，請查回原操作。'
       : '安排未儲存，請重新讀取本案，確認目前版本與收付款來源。');
   } finally {
     setBusy(false);
   }
 }
 return <form ref={form} onSubmit={event=>{event.preventDefault();void submit();}}>
   <fieldset disabled={busy}>
     <legend>{confirm?'確認政府直接退給客戶':'撤回政府直接退給客戶安排'}</legend>
     <label>{confirm?'直退確認原因':'撤回原因'}
       <textarea value={reason} maxLength={500} disabled={unknown} onChange={event=>setReason(event.target.value)} />
     </label>
     {error && <p role="alert">{error}</p>}
     <button type="submit" className="finance-btn-primary" disabled={!reason.trim()}>
       {unknown?'確認原直退操作結果':confirm?'確認政府直接退給客戶':'撤回直退安排'}
     </button>
   </fieldset>
 </form>;
}

export function FinanceCaseBankMemos({notes}:{notes:CaseBankMemo[]}){
 if(!notes.length)return null;
 return <section aria-label="銀行原始備註"><h4>銀行原始備註</h4><p>歷史記載的「月嫂薪資」也可能是補助款，請依原文及本案資料確認補助方案。</p>{notes.map(note=><div key={note.identity}><small>{note.occurred_on??"交易日期未留存"}</small><p style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{note.memo}</p></div>)}</section>;
}

import {useRef,useState} from 'react';
import {financeAccountingClient,type CaseSubsidyPlan,type SubsidyPlanCommand,type CaseBankMemo} from '../api/finance_import/finance_accounting_client';
import {ApiHttpError} from '../api/shared/typed_errors';
import {useUnsavedDraft} from './UnsavedChanges';
export const subsidyPlanLabels={split:'客戶與政府分別入款',advance:'客戶先墊後退',direct:'政府直接付客戶'};
export const subsidyPlanTargets={split:'補助轉交月嫂，已包含在案件總額內',advance:'補助退還先墊款的客戶',direct:'政府直接付客戶，工會無補助退款應付'};
export function FinanceSubsidyPlanForm({caseNo,source,onSaved,onBack,bankMemos=[]}:{caseNo:string;source:CaseSubsidyPlan;onSaved:(plan:CaseSubsidyPlan)=>void;onBack:()=>void;bankMemos?:CaseBankMemo[]}){
 const[plan,setPlan]=useState(source),[choice,setChoice]=useState(source.events.at(-1)?.scheme??''),[busy,setBusy]=useState(false),[unknown,setUnknown]=useState(false),[error,setError]=useState('');
 const original=useRef<{command:SubsidyPlanCommand;key:string}|null>(null);
 const baseline=plan.events.at(-1)?.scheme??'';
 const form=useUnsavedDraft('人工補助退款方案',{'補助方案':choice},{baseline:{'補助方案':baseline},busy:busy||unknown,discard:()=>{setChoice(baseline);original.current=null;}});
 async function execute(command:SubsidyPlanCommand,key:string){setBusy(true);setError('');try{const result=await financeAccountingClient.saveSubsidyPlan(caseNo,command,key);setPlan(result.plan);setChoice(result.plan.events.at(-1)?.scheme??'');setUnknown(false);original.current=null;onSaved(result.plan);}catch(failure){const status=failure instanceof ApiHttpError?failure.status:0;const uncertain=status===0||status>=500||status===408;setUnknown(uncertain);setError(uncertain?'保存結果尚未確認，請查回原操作結果，勿另建新次操作。':status===409?'方案版本已變更；選擇已保留，請重新讀取後核對。':'目前無法保存，請確認登入或權限。');}finally{setBusy(false);}}
 async function submit(){if(!choice||busy||unknown||choice===baseline)return;const command={scheme:choice as SubsidyPlanCommand['scheme'],expected_version:plan.version};const pending={command,key:crypto.randomUUID()};original.current=pending;await execute(pending.command,pending.key);}
 async function reload(){setBusy(true);setError('');try{setPlan(await financeAccountingClient.subsidyPlan(caseNo));original.current=null;}catch{setError('方案來源暫時無法讀取。');}finally{setBusy(false);}}
 return <section className="finance-case-subview" aria-label="設定補助退款方案"><h3 tabIndex={-1}>設定補助退款方案</h3><p>一般在客戶款齊後設定，也可提前保存；不改各期應繳、已核銷金額或日期。</p><FinanceCaseBankMemos notes={bankMemos}/><form ref={form} onSubmit={e=>{e.preventDefault();void submit();}}><fieldset className="finance-manual-plan-options" disabled={busy||unknown}><legend>補助款歸屬</legend>{(Object.keys(subsidyPlanLabels) as Array<keyof typeof subsidyPlanLabels>).map(scheme=><label key={scheme}><input type="radio" name="subsidy-plan" value={scheme} checked={choice===scheme} onChange={()=>setChoice(scheme)}/><span><strong>{subsidyPlanLabels[scheme]}</strong><small>{subsidyPlanTargets[scheme]}</small></span></label>)}</fieldset>{error&&<p role="alert">{error}</p>}<p>案件結束後再處理補助與應付清單；這裡只保存安排，不執行付款、退款或核銷。</p><div className="finance-row-actions"><button type="button" disabled={busy||unknown} className="finance-btn-secondary" onClick={onBack}>返回案件</button><button className="finance-btn-primary" disabled={busy||unknown||!choice||choice===baseline}>{busy?'正在保存…':'儲存方案'}</button>{error&&!unknown&&<button type="button" disabled={busy} onClick={()=>void reload()}>重新讀取方案</button>}{unknown&&<button type="button" disabled={busy} onClick={()=>{const pending=original.current;if(pending)void execute(pending.command,pending.key);}}>確認原操作結果</button>}</div></form></section>;
}

export function FinanceCaseBankMemos({notes}:{notes:CaseBankMemo[]}){
 if(!notes.length)return null;
 return <section aria-label="銀行原始備註"><h4>銀行原始備註</h4><p>歷史記載的「月嫂薪資」也可能是補助款，請依原文及本案資料確認補助方案。</p>{notes.map(note=><div key={note.identity}><small>{note.occurred_on??"交易日期未留存"}</small><p style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{note.memo}</p></div>)}</section>;
}

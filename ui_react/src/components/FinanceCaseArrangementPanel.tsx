import { useRef, useState } from 'react';
import { financeAccountingClient, type ArrangementCommand, type CaseAccounting, type CaseArrangement } from '../api/finance_import/finance_accounting_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { useUnsavedDraft } from './UnsavedChanges';

export function ArrangementHistory({arrangement}:{arrangement:CaseArrangement|null}) {
 return <section aria-label="直付安排更正歷史"><h4>直付安排更正歷史</h4>{!arrangement?<p>安排來源待確認。</p>:!arrangement.events.length?<p>尚無逐案確認紀錄；歷史案件不自動套用預設。</p>:<div className="finance-table-container"><table className="finance-table"><thead><tr><th>版本</th><th>操作</th><th>依據／更正原因</th><th>確認人</th><th>記錄時間（台北）</th></tr></thead><tbody>{arrangement.events.map(event=><tr key={event.version}><td>{event.version}</td><td>{event.action==='confirm_direct'?'確認／更新政府直付安排':'撤回政府直付安排'}</td><td style={{whiteSpace:'normal',minWidth:180}}>{event.reason}</td><td>{event.actor}</td><td>{new Date(event.created_at).toLocaleString('zh-TW',{timeZone:'Asia/Taipei',hour12:false,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'})}</td></tr>)}</tbody></table></div>}</section>;
}

export function FinanceCaseArrangementPanel({data,onChanged}:{data:CaseAccounting;onChanged:()=>void}) {
 const [saved,setSaved]=useState<CaseArrangement>(),[action,setAction]=useState<ArrangementCommand['action']|''>(''),[reason,setReason]=useState('');
 const [busy,setBusy]=useState(false),[unknown,setUnknown]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
 const original=useRef<{key:string;command:ArrangementCommand}|null>(null);
 const history=saved??data.arrangement??null;
 const direct=history?.events.at(-1)?.action==='confirm_direct';
 function discard(){setReason('');setAction('');original.current=null;setError('');}
 const draft=useUnsavedDraft('逐案政府直付安排',{'安排操作':action,'確認依據':reason},{baseline:{'安排操作':'','確認依據':''},busy:busy||unknown,discard});
 async function execute(command:ArrangementCommand,key:string){
  setBusy(true);setError('');setMessage('');
  try{
   const result=await financeAccountingClient.confirmArrangement(data.case_no,command,key);
   setSaved(result.arrangement);setUnknown(false);discard();setMessage('已保存安排版本 '+result.applied_version+'；目前版本 '+result.arrangement.version+'，分類與收付款仍依最新事實核對。');onChanged();
  }catch(failure){
   const status=failure instanceof ApiHttpError?failure.status:0;
   const uncertain=status===0||status>=500||status===408;setUnknown(uncertain);
   setError(uncertain?'儲存結果尚未確認，已保留原操作，請確認原操作結果。':status===409?'安排已變更或原操作不一致；輸入已保留，請重新讀取安排後核對。':status===401||status===403?'目前登入或權限無法保存，請確認登入後再試。':'目前條件無法確認此安排；請核對齊款、金額、來源與工會是否經手補助。輸入已保留。');
  }finally{setBusy(false);}
 }
 async function submit(){
  if(busy||unknown||!action||!reason.trim()||!history)return;
  const command={action,reason:reason.trim(),expected_version:history.version};
  if(!original.current||JSON.stringify(original.current.command)!==JSON.stringify(command))original.current={key:crypto.randomUUID(),command};
  await execute(original.current.command,original.current.key);
 }
 async function reload(){
  if(busy||unknown)return;setBusy(true);setError('');
  try{setSaved(await financeAccountingClient.arrangement(data.case_no));original.current=null;setMessage('已重新讀取安排，原輸入保留，請核對目前版本再儲存。');onChanged();}
  catch{setError('安排暫時無法讀取，請稍後再試。');}finally{setBusy(false);}
 }
 return <section className="case-accounting-card" aria-label="逐案政府直付安排"><h3>逐案政府直付安排</h3><p>{direct?'政府直付安排已確認':history?.events.length?'政府直付安排已撤回':'尚未逐案確認政府直付安排'} · 目前讀取版本 {history?.version??'待確認'}</p>
 {data.scheme_conflict&&<p role="alert">已知直付安排與目前工會金流或金額不一致，方案待確認；原安排及核銷證據保留。</p>}
 <p>只記錄本案安排；不要求客戶實收補助證明，不產生收付款。更正追加紀錄，原人員、時間與依據保留。</p>
 <details><summary>確認／更正本案安排</summary><form ref={draft} className="finance-marker-form" onSubmit={event=>{event.preventDefault();void submit();}}>
 <label>安排操作<select aria-label="安排操作" value={action} disabled={busy||unknown||!history} onChange={event=>setAction(event.target.value as typeof action)}><option value="">請選擇操作</option><option value="confirm_direct" disabled={!data.can_confirm_direct}>確認／更新政府直接付客戶</option><option value="withdraw_direct" disabled={!direct}>撤回政府直付安排</option></select></label>
 <label>確認依據／更正原因<textarea rows={3} required maxLength={500} value={reason} disabled={busy||unknown||!history} onChange={event=>setReason(event.target.value)}/></label>
 {!data.can_confirm_direct&&<p>本案目前未符合直接確認條件。各期須收齊、應繳工會等於案件總額，且有足夠來源確認補助未經工會。</p>}
 <div className="finance-row-actions"><button type="submit" className="finance-btn-primary" disabled={busy||unknown||!action||!reason.trim()||!history||(action==='confirm_direct'&&!data.can_confirm_direct)}>{busy?'正在處理…':'儲存本案安排'}</button><button type="button" className="finance-btn-secondary" disabled={busy||unknown} onClick={()=>void reload()}>重新讀取安排</button></div>
 </form></details>
 {error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
 {unknown&&<button type="button" className="finance-btn-secondary" disabled={busy} onClick={()=>{const current=original.current;if(current)void execute(current.command,current.key);}}>確認原操作結果</button>}
 <ArrangementHistory arrangement={history}/>
 </section>;
}

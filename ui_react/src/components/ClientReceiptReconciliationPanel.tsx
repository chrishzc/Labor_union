import { useEffect, useRef, useState } from 'react';
import { clientReceiptQueryClient } from '../api/client_finance/client_receipt_query_client';
import type { ClientReceiptQuery } from '../api/client_finance/client_receipt_query_schemas';
import { clientReceiptReconciliationClient, type ReceiptAction, type ReceiptCommand, type ReceiptPreview, type ReceiptSelection } from '../api/client_finance/client_receipt_reconciliation_client';
import { financeMoney } from './FinanceReceiptsWorkspace';
import { useUnsavedChanges } from './UnsavedChanges';
import { ApiHttpError } from '../api/shared/typed_errors';

export function ClientReceiptReconciliationPanel({caseNo,onChanged,refreshVersion=0}:{caseNo:string;onChanged:()=>void;refreshVersion?:number}){
  const [facts,setFacts]=useState<ClientReceiptQuery>();
  const [selectedBanks,setSelectedBanks]=useState<number[]>([]);
  const [selectedItems,setSelectedItems]=useState<string[]>([]);
  const [preview,setPreview]=useState<ReceiptPreview>();
  const [action,setAction]=useState<ReceiptAction|''>('');
  const [busy,setBusy]=useState(false);
  const [unknown,setUnknown]=useState(false);
  const [error,setError]=useState('');
  const [result,setResult]=useState('');
  const [revision,setRevision]=useState(0);
  const command=useRef<ReceiptCommand|undefined>(undefined);
  const operationPending=useRef(false);operationPending.current=busy||unknown;
  useUnsavedChanges('客戶收款核銷',[],{busy:busy||unknown});
  useEffect(()=>{
    if(operationPending.current)return;
    command.current=undefined;setAction('');
    const controller=new AbortController();setFacts(undefined);setPreview(undefined);setError('');
    queueMicrotask(()=>{if(controller.signal.aborted)return;
    void clientReceiptQueryClient.query(caseNo,{signal:controller.signal}).then(value=>{if(!controller.signal.aborted){setFacts(value);setSelectedBanks(value.bank_facts.map(row=>row.finance_import_row_id));setSelectedItems(value.obligations.map(row=>row.obligation_identity));}}).catch(()=>{if(!controller.signal.aborted)setError('本案待核對入款暫時無法取得，請重新查詢。');});
    });
    return()=>controller.abort();
  },[caseNo,revision,refreshVersion]);
  const selection=():ReceiptSelection=>({payment_stage:null,finance_import_row_ids:selectedBanks,obligation_identities:selectedItems});
  const bankTotal=facts?.bank_facts.filter(row=>selectedBanks.includes(row.finance_import_row_id)).reduce((sum,row)=>sum+row.amount_ntd,0)??0;
  const dueTotal=facts?.obligations.filter(row=>selectedItems.includes(row.obligation_identity)).reduce((sum,row)=>sum+row.amount_due_ntd,0)??0;
  const invalidate=()=>{setPreview(undefined);setAction('');command.current=undefined;setResult('');};
  async function inspect(next:ReceiptAction='exact'){
    setBusy(true);setError('');
    try{setPreview(await clientReceiptReconciliationClient.preview(caseNo,selection(),next));setAction(next==='exact'?'':next);}
    catch{setError('核對失敗，資料可能已變更，請重新查詢。');}
    finally{setBusy(false);}
  }
  async function confirm(){
    if(!preview||preview.candidate.status==='review_required'||busy)return;
    setBusy(true);setError('');
    command.current??={selection:selection(),expected_account_version:preview.account_version,preview_fingerprint:preview.preview_fingerprint,reason:action==='partial'?'核銷實收，餘額續收':action==='overage'?'多收另列退款':'同案入款合計核銷',key:crypto.randomUUID(),action:action||'exact'};
    try{const receipt=await clientReceiptReconciliationClient.apply(caseNo,command.current);setUnknown(false);setPreview(undefined);command.current=undefined;setResult(receipt.status==='partial'?'已記錄實際收款，剩餘款項繼續待收。':receipt.status==='overage'?'原應收已核銷，多收款另列待退款。':'已核銷本次收款。');setRevision(value=>value+1);onChanged();}
    catch(failure){const status=Number((failure as {status?:number}).status??0);const missingAccount=failure instanceof ApiHttpError&&failure.code==='client_refund_recipient_snapshot_missing';setUnknown(status===0||status>=500);setError(missingAccount?'報名資料缺少客戶退款帳戶，本次未核銷。請先補齊退款帳戶資料，再回本案核對。':status===409?'帳務或銀行資料已變更，請重新查詢後核對。':status===401||status===403?'目前登入狀態或權限無法執行核銷。':status===0||status>=500?'尚未確認原操作結果；保留原操作，請勿重建另一筆。':'未能核銷選取款項，請重新查詢後核對。');}
    finally{setBusy(false);}
  }
  return <section className="case-accounting-card" aria-label="本案待核對客戶入款"><div className="finance-section-heading"><h3>本案待核對客戶入款</h3><button type="button" className="finance-btn-secondary" disabled={busy||unknown} onClick={()=>{invalidate();setRevision(value=>value+1);}}>重新查詢</button></div>
    {!facts&&!error&&<p role="status">正在查詢本案入款…</p>}{facts&&<>{!facts.bank_facts.length?<p>目前沒有已辨識為本案、尚未核銷的客戶入款。</p>:<>
      <p>同案各筆原始入款與合計一起核對，不要求每筆金額個別符合應收。</p><div className="finance-table-container"><table className="finance-table"><thead><tr><th>納入</th><th>日期</th><th>銀行來源</th><th>入款金額</th></tr></thead><tbody>{facts.bank_facts.map(row=><tr key={row.finance_import_row_id}><td><input aria-label={`納入銀行款 ${row.finance_import_row_id}`} type="checkbox" disabled={busy||unknown} checked={selectedBanks.includes(row.finance_import_row_id)} onChange={event=>{invalidate();setSelectedBanks(previous=>event.target.checked?[...previous,row.finance_import_row_id]:previous.filter(id=>id!==row.finance_import_row_id));}}/></td><td>{row.transaction_date}</td><td>bank:{row.finance_import_row_id}</td><td>{financeMoney(row.amount_ntd)}</td></tr>)}</tbody></table></div>
      <p>本次入款合計 <strong>{financeMoney(bankTotal)}</strong> · 核對待收 <strong>{financeMoney(dueTotal)}</strong></p>
      <details><summary>查看／調整本次核對款項</summary>{facts.obligations.map(item=><label className="finance-reconciliation-item" key={item.obligation_identity}><input type="checkbox" disabled={busy||unknown} checked={selectedItems.includes(item.obligation_identity)} onChange={event=>{invalidate();setSelectedItems(previous=>event.target.checked?[...previous,item.obligation_identity]:previous.filter(id=>id!==item.obligation_identity));}}/>{item.due_date??'未定到期日'} · {item.obligation_identity} · {financeMoney(item.amount_due_ntd)}</label>)}</details>
      {!preview&&<button type="button" className="finance-btn-primary" disabled={busy||unknown||!selectedBanks.length||!selectedItems.length} onClick={()=>void inspect()}>核對本案入款</button>}
      {preview&&<div className="finance-scope-note"><p>本次實收 {financeMoney(preview.candidate.bank_total.amount)}；待收 {financeMoney(preview.candidate.obligation_total.amount)}。</p>
        {preview.candidate.status==='review_required'&&<label>選擇差額處理<select aria-label="選擇差額處理" value={action} disabled={busy||unknown} onChange={event=>{const value=event.target.value as ReceiptAction|'';setAction(value);if(value)void inspect(value);}}><option value="">請選擇處理方式</option>{preview.candidate.bank_total.amount<preview.candidate.obligation_total.amount?<option value="partial">核銷實收，餘額續收</option>:<option value="overage">多收另列退款</option>}</select></label>}
        {preview.candidate.status!=='review_required'&&<><p>{preview.candidate.status==='partial'?'本次只核銷實收，剩餘繼續待收。':preview.candidate.status==='overage'?'原應收結清，多收另列退款待付。':'合計相符，可直接核銷。'}</p><button type="button" className="finance-btn-primary" disabled={busy||unknown} onClick={()=>void confirm()}>確認核銷本次收款</button></>}
      </div>}
    </>}</>}{error&&<p role="alert">{error}</p>}{unknown&&<button type="button" className="finance-btn-secondary" disabled={busy} onClick={()=>void confirm()}>確認原操作結果</button>}{result&&<p role="status">{result}</p>}
  </section>;
}

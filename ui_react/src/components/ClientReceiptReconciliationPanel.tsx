/**
 * File: ClientReceiptReconciliationPanel.tsx
 * Description: 本案銀行入款待核銷沖帳工作卡，支援多筆銀行流水與應收期款手動對帳沖銷。
 */
import { useEffect, useRef, useState } from 'react';
import { clientReceiptQueryClient } from '../api/client_finance/client_receipt_query_client';
import type { ClientReceiptQuery } from '../api/client_finance/client_receipt_query_schemas';
import { clientReceiptReconciliationClient, type ReceiptAction, type ReceiptCommand, type ReceiptPreview, type ReceiptSelection } from '../api/client_finance/client_receipt_reconciliation_client';
import { financeMoney } from './FinanceReceiptsWorkspace';
import { useUnsavedChanges } from './UnsavedChanges';
import { ApiHttpError } from '../api/shared/typed_errors';
import { financeAccountingClient, type CaseAccounting } from '../api/finance_import/finance_accounting_client';

function caseReceivableBalance(facts:ClientReceiptQuery,accounting:CaseAccounting|undefined,requiredIdentities:readonly string[]):bigint|undefined{
  if(!accounting||accounting.case_no!==facts.case_no||accounting.customer_amount_ntd==null
    ||accounting.customer_amount_ntd<0||typeof accounting.customer_fully_received!=='boolean')return undefined;
  const items=accounting.client_items.filter(item=>item.direction==='receivable');
  if(!items.length||items.some(item=>item.version.split(':')[0]!==String(facts.account_version)
    ||item.remaining_ntd==null||item.remaining_ntd<0))return undefined;
  if(new Set(items.map(item=>item.identity)).size!==items.length)return undefined;
  if(requiredIdentities.some(identity=>!items.some(item=>item.identity===identity)))return undefined;
  if(facts.obligations.some(row=>!items.some(item=>item.identity===row.obligation_identity
    &&BigInt(item.remaining_ntd!)===BigInt(row.amount_due_ntd))))return undefined;
  return items.reduce((sum,item)=>sum+BigInt(item.remaining_ntd!),0n);
}

async function queryReceiptScope(caseNo:string,signal?:AbortSignal,requiredIdentities:readonly string[]=[]){
  const [facts,accounting]=await Promise.all([
    clientReceiptQueryClient.query(caseNo,{signal}),
    financeAccountingClient.query(caseNo,signal).catch(()=>undefined),
  ]);
  return {facts,remaining:caseReceivableBalance(facts,accounting,requiredIdentities)};
}

const missingRefundAccountMessage='報名資料缺少客戶退款帳戶，本次未核銷。請先補齊退款帳戶資料，再回本案核對。';
function receiptFailureMessage(failure: unknown): string | undefined {
  if (!(failure instanceof ApiHttpError)) return undefined;
  return ({
    bank_transaction_date_missing:'原銀行流水缺少交易日，無法核銷客戶入款，請先查核來源資料。',
    bank_currency_not_twd:'原銀行流水幣別不是新臺幣，無法核銷客戶入款，請先查核來源資料。',
    client_refund_recipient_snapshot_missing:missingRefundAccountMessage,
    bank_fact_not_eligible:'原銀行來源未通過核銷資格，未留存更具體的阻擋原因。',
  } as Record<string,string>)[failure.code];
}

function getObligationLabel(identity: string, stage?: string | null): string {
  if (identity.startsWith('client-cancellation:create_adjustment:')) return '取消結算補收';
  const clean = identity.replace(/^client-obligation:[^:]+:/, '');
  const s = stage || clean;
  if (s === 'deposit') return '訂金期款';
  if (s === 'first') return '第一期期款';
  if (s === 'second') return '第二期期款';
  if (s === 'adjustment') return '調整應收款';
  if (s === 'subsidy_return') return '客戶退款';
  return identity;
}

function isSelectableReceiptObligation(
  item: ClientReceiptQuery['obligations'][number],
  initialObligationId?: string,
): boolean {
  if (item.obligation_identity === initialObligationId) return true;
  if (item.obligation_identity.startsWith('historical-service:')) return false;
  if (item.payment_stage === 'adjustment') {
    return item.obligation_identity.startsWith('client-cancellation:create_adjustment:');
  }
  return true;
}

export function ClientReceiptReconciliationPanel({caseNo,onChanged,refreshVersion=0,requiredBankRowId,initialObligationId,onBusyChange}:{
  caseNo:string;onChanged:()=>void;refreshVersion?:number;requiredBankRowId?:number;initialObligationId?:string;onBusyChange?:(busy:boolean)=>void;
}){
  const [facts,setFacts]=useState<ClientReceiptQuery>();
  const [caseBalance,setCaseBalance]=useState<bigint>();
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
  const postedReceipt=useRef<{caseNo:string;accountVersion:number;message:string;obligationIdentities:string[]}|undefined>(undefined);
  const operationPending=useRef(false);operationPending.current=busy||unknown;
  useUnsavedChanges('客戶收款核銷',[],{busy:busy||unknown});
  useEffect(() => { onBusyChange?.(busy || unknown); return () => onBusyChange?.(false); }, [busy, unknown, onBusyChange]);
  useEffect(()=>{
    if(operationPending.current)return;
    if(postedReceipt.current?.caseNo===caseNo)setResult(postedReceipt.current.message);
    else{postedReceipt.current=undefined;setResult('');}
    command.current=undefined;setAction('');
    const controller=new AbortController();setFacts(undefined);setCaseBalance(undefined);setPreview(undefined);setError('');
    queueMicrotask(()=>{if(controller.signal.aborted)return;
    void queryReceiptScope(caseNo,controller.signal,postedReceipt.current?.obligationIdentities).then(({facts:value,remaining})=>{
      if(controller.signal.aborted)return;
      const banks=value.bank_facts.map(row=>row.finance_import_row_id);
      const posted=postedReceipt.current?.caseNo===caseNo?postedReceipt.current:undefined;
      if(posted){
        setResult(`${posted.message} ${value.account_version<posted.accountVersion||remaining===undefined?'案件餘額尚待重新查詢確認。':remaining===0n?'案件已結清。':`案件尚有待收 ${financeMoney(remaining)}。`}`);
      }
      if(!posted&&requiredBankRowId!==undefined&&!banks.includes(requiredBankRowId)){
        const blocker=value.bank_fact_blockers?.find(row=>row.finance_import_row_id===requiredBankRowId);
        const messages={
          bank_transaction_date_missing:'原銀行流水缺少交易日，無法核銷客戶入款，請先查核來源資料。',
          bank_currency_not_twd:'原銀行流水幣別不是新臺幣，無法核銷客戶入款，請先查核來源資料。',
        };
        setError(blocker ? [...new Set(blocker.codes)].map(code=>messages[code]).join(' ')
          : '此筆交易尚未辨識為本案入款，請返回銀行對帳重新確認歸屬。');
        return;
      }
      const selectable=value.obligations.filter(item=>isSelectableReceiptObligation(item,initialObligationId));
      if(!posted&&initialObligationId!==undefined&&!selectable.some(item=>item.obligation_identity===initialObligationId)){
        setError('對應期款已變更，請返回銀行對帳重新查詢。');
        return;
      }
      setFacts(value);
      setCaseBalance(remaining);
      setSelectedBanks(requiredBankRowId===undefined?banks:banks.filter(id=>id===requiredBankRowId));
      setSelectedItems(initialObligationId ? selectable.filter(item=>item.obligation_identity===initialObligationId).map(item=>item.obligation_identity) : requiredBankRowId===undefined?selectable.map(row=>row.obligation_identity):[]);
    }).catch(()=>{if(!controller.signal.aborted)setError('本案待核對入款暫時無法取得，請重新查詢。');});
    });
    return()=>controller.abort();
  },[caseNo,revision,refreshVersion,requiredBankRowId,initialObligationId]);

  const selectableObligations=facts?.obligations.filter(item=>isSelectableReceiptObligation(item,initialObligationId))??[];
  const selection=():ReceiptSelection=>({payment_stage:null,finance_import_row_ids:selectedBanks,obligation_identities:selectedItems});
  const bankTotal=facts?.bank_facts.filter(row=>selectedBanks.includes(row.finance_import_row_id)).reduce((sum,row)=>sum+BigInt(row.amount_ntd),0n)??0n;
  const dueTotal=selectableObligations.filter(row=>selectedItems.includes(row.obligation_identity)).reduce((sum,row)=>sum+BigInt(row.amount_due_ntd),0n);
  const diff=bankTotal-dueTotal;
  const selectionHint=facts&&!selectableObligations.length
    ? '本案目前沒有未清期款，無款項可核銷。請回案件帳務查核。'
    : !selectedItems.length ? '請先選擇本次要核銷的期款，再核對金額。'
    : !selectedBanks.length ? '請先選擇本次要核銷的銀行入款，再核對金額。' : '';
  const previewRows=preview&&preview.candidate.status!=='review_required' ? selectableObligations.filter(item=>selectedItems.includes(item.obligation_identity)).map(item=>{
    const allocated=preview.candidate.allocations.filter(row=>row.obligation_identity===item.obligation_identity).reduce((sum,row)=>sum+BigInt(row.amount.amount),0n);
    return {...item,allocated,remaining:BigInt(item.amount_due_ntd)-allocated};
  }) : undefined;
  const allocatedTotal=previewRows?.reduce((sum,item)=>sum+item.allocated,0n)??0n;
  const caseRemaining=caseBalance===undefined||caseBalance<allocatedTotal?undefined:caseBalance-allocatedTotal;
  const invalidate=()=>{setPreview(undefined);setAction('');command.current=undefined;postedReceipt.current=undefined;setResult('');};

  async function inspect(next:ReceiptAction='exact'){
    setBusy(true);setError('');setPreview(undefined);
    try{
      const [candidate,current]=await Promise.all([
        clientReceiptReconciliationClient.preview(caseNo,selection(),next),
        queryReceiptScope(caseNo),
      ]);
      if(candidate.account_version!==current.facts.account_version)throw new Error('stale_receipt_preview');
      setFacts(current.facts);setCaseBalance(current.remaining);setPreview(candidate);setAction(next==='exact'?'':next);
    }
    catch(failure){setError(receiptFailureMessage(failure)??'核對失敗，資料可能已變更，請重新查詢。');}
    finally{setBusy(false);}
  }

  async function confirm(){
    if(!preview||preview.candidate.status==='review_required'||busy)return;
    setBusy(true);setError('');
    command.current??={selection:selection(),expected_account_version:preview.account_version,preview_fingerprint:preview.preview_fingerprint,reason:action==='partial'?'核銷實收，餘額續收':action==='overage'?'多收另列退款':'同案入款合計核銷',key:crypto.randomUUID(),action:action||'exact'};
    try{
      const receipt=await clientReceiptReconciliationClient.apply(caseNo,command.current);
      setUnknown(false);setPreview(undefined);command.current=undefined;
      const message=receipt.status==='partial'?'已記錄實際收款，剩餘款項繼續待收。'
        :receipt.status==='overage'?'本次選取期款已核銷，多收款另列待退款。':'已核銷本次收款。';
      postedReceipt.current={caseNo,accountVersion:receipt.account_version,message,obligationIdentities:facts?.obligations.map(item=>item.obligation_identity)??[]};
      setResult(message);setRevision(value=>value+1);onChanged();
    }
    catch(failure){const status=Number((failure as {status?:number}).status??0);setUnknown(status===0||status>=500);setError(receiptFailureMessage(failure)??(status===409?'帳務或銀行資料已變更，請重新查詢後核對。':status===401||status===403?'目前登入狀態或權限無法執行核銷。':status===0||status>=500?'尚未確認原操作結果；保留原操作，請勿重建另一筆。':'未能核銷選取款項，請重新查詢後核對。'));}
    finally{setBusy(false);}
  }

  return (
    <section className="case-accounting-card finance-advanced-reconciliation-card" aria-label="本案待核對客戶入款">
      <div className="finance-section-heading">
        <div className="finance-reconciliation-heading-group">
          <h3>待沖銷銀行入款與期款對核</h3>
          <span className="finance-tag-imported">入款對帳沖銷</span>
        </div>
        <button type="button" className="finance-btn-secondary" disabled={busy||unknown} onClick={()=>{invalidate();setRevision(value=>value+1);}}>重新查詢</button>
      </div>

      <div className="finance-advanced-reconciliation-guide">
        <strong>💡 作用說明：</strong>銀行對帳單已辨識到本案的匯款流水（如下左側）。請確認要將此筆款項<strong>沖抵哪一期款項</strong>（如下右側）。核對確認後，系統將正式記錄實收並更新期款狀態。
      </div>

      {!facts&&!error&&<p role="status">正在查詢本案入款…</p>}
      {facts&&<>
        {!facts.bank_facts.length ? (
          <div className="finance-reconciliation-empty-box">
            <p>目前沒有已辨識為本案、尚未核銷的客戶入款。</p>
            <small>若客戶已匯款，請確認匯入流水與案件虛擬帳號是否相符。</small>
          </div>
        ) : (
          <div className="finance-recon-deck">
            <div className="finance-recon-deck-grid">
              {/* 左側：銀行收到的入款 */}
              <div className="finance-recon-col finance-recon-col-bank">
                <div className="finance-recon-col-header">
                  <span className="finance-recon-badge-step">步驟 1</span>
                  <h4>銀行已收到款項（來源流水）</h4>
                </div>
                <div className="finance-table-container">
                  <table className="finance-table finance-recon-table">
                    <thead>
                      <tr>
                        <th>納入</th>
                        <th>入帳日期</th>
                        <th>銀行來源</th>
                        <th>入款金額</th>
                      </tr>
                    </thead>
                    <tbody>
                      {facts.bank_facts.map(row => (
                        <tr key={row.finance_import_row_id} className={selectedBanks.includes(row.finance_import_row_id) ? 'is-selected-row' : ''}>
                          <td>
                            <input
                              aria-label={`納入銀行款 ${row.finance_import_row_id}`}
                              type="checkbox"
                              disabled={busy||unknown||row.finance_import_row_id===requiredBankRowId}
                              checked={selectedBanks.includes(row.finance_import_row_id)}
                              onChange={event => {
                                invalidate();
                                setSelectedBanks(previous => event.target.checked ? [...previous, row.finance_import_row_id] : previous.filter(id => id !== row.finance_import_row_id));
                              }}
                            />
                          </td>
                          <td><strong>{row.transaction_date}</strong></td>
                          <td>
                            <span>永豐銀行入款</span>
                            <small className="finance-mono-sub">bank:{row.finance_import_row_id}</small>
                          </td>
                          <td><strong className="finance-paid">{financeMoney(row.amount_ntd)}</strong></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="finance-recon-col-summary">
                  <span>已勾選入款合計：<strong>{financeMoney(bankTotal)}</strong>（共 {selectedBanks.length} 筆）</span>
                </div>
              </div>

              {/* 中間箭頭 */}
              <div className="finance-recon-arrow-divider" aria-hidden="true">
                <span className="finance-recon-arrow-icon">➔</span>
                <small>沖抵核銷</small>
              </div>

              {/* 右側：欲沖抵的案件期款 */}
              <div className="finance-recon-col finance-recon-col-target">
                <div className="finance-recon-col-header">
                  <span className="finance-recon-badge-step">步驟 2</span>
                  <h4>預計沖抵案件期款（核銷目標）</h4>
                </div>
                <details open className="finance-recon-obligations-card">
                  <summary>查看／調整本次核對款項</summary>
                  <div className="finance-recon-obligations-list">
                    {selectableObligations.map(item => {
                      const isChecked = selectedItems.includes(item.obligation_identity);
                      return (
                        <label className={`finance-recon-obligation-item ${isChecked ? 'is-selected-item' : ''}`} key={item.obligation_identity}>
                          <input
                            type="checkbox"
                            disabled={busy||unknown}
                            checked={isChecked}
                            onChange={event => {
                              const checked=event.target.checked;
                              invalidate();
                              setSelectedItems(previous => checked ? [...previous, item.obligation_identity] : previous.filter(id => id !== item.obligation_identity));
                            }}
                          />
                          <div className="finance-recon-ob-info">
                            <div className="finance-recon-ob-name">
                              <strong>{getObligationLabel(item.obligation_identity, item.payment_stage)}</strong>
                              <small>{item.due_date ? `到期日：${item.due_date}` : '未定到期日'}</small>
                            </div>
                            <div className="finance-recon-ob-meta">
                              <span>待收 <strong>{financeMoney(item.amount_due_ntd)}</strong></span>
                            </div>
                          </div>
                        </label>
                      );
                    })}
                  </div>
                </details>
                <div className="finance-recon-col-summary">
                  <span>已勾選期款待收：<strong>{financeMoney(dueTotal)}</strong>（共 {selectedItems.length} 項）</span>
                </div>
              </div>
            </div>

            {/* 試算與決策條 */}
            <div className="finance-recon-calculation-bar">
              <div className="finance-recon-calc-metrics">
                <div>
                  <small>勾選銀行實收</small>
                  <strong>{financeMoney(bankTotal)}</strong>
                </div>
                <span className="finance-recon-calc-operator">−</span>
                <div>
                  <small>對應期款待收</small>
                  <strong>{financeMoney(dueTotal)}</strong>
                </div>
                <span className="finance-recon-calc-operator">=</span>
                <div>
                  <small>沖銷差額</small>
                  <strong className={selectionHint ? undefined : diff < 0 ? 'finance-diff-under' : diff > 0 ? 'finance-diff-over' : 'finance-paid'}>
                    {selectionHint ? '尚未核對' : diff < 0 ? `短少 ${financeMoney(-diff)}` : diff > 0 ? `超收 ${financeMoney(diff)}` : '金額相符'}
                  </strong>
                </div>
              </div>

              <div className="finance-recon-calc-explanation">
                {selectionHint ? (
                  <span>{selectionHint}</span>
                ) : diff === 0n ? (
                  <span>入款金額與本次選取期款相符；核對預覽後，確認本次核銷金額與案件剩餘待收。</span>
                ) : diff < 0 ? (
                  <span>⚠️ 入款金額少於期款應繳：確認後將<strong>認列實收 {financeMoney(bankTotal)}</strong>，剩餘差額 <strong>{financeMoney(-diff)}</strong> 繼續待收（可於上方期款點「處置差額」或通知客戶補繳）。</span>
                ) : (
                  <span>⚠️ 入款金額多於本次選取期款：選擇多收另列退款後，本次期款將核銷，多收之 <strong>{financeMoney(diff)}</strong> 將另列為待退款。</span>
                )}
              </div>

              {!preview && (
                <div className="finance-recon-action-row">
                  <button
                    type="button"
                    className="finance-btn-primary finance-btn-lg"
                    disabled={busy||unknown||!selectedBanks.length||!selectedItems.length}
                    onClick={() => void inspect()}
                  >
                    核對本案入款
                  </button>
                </div>
              )}
            </div>

            {/* 預覽與確認核銷結果 */}
            {preview && (
              <div className="finance-scope-note finance-recon-preview-box">
                <div className="finance-recon-preview-header">
                  <h5>核對預覽結果</h5>
                  <span>本次實收 {financeMoney(preview.candidate.bank_total.amount)}；待收 {financeMoney(preview.candidate.obligation_total.amount)}。</span>
                </div>

                {preview.candidate.status === 'review_required' && (
                  <div className="finance-recon-action-select-row">
                    <label>
                      <strong>選擇差額處理方式：</strong>
                      <select
                        aria-label="選擇差額處理"
                        value={action}
                        disabled={busy||unknown}
                        onChange={event => {
                          const value = event.target.value as ReceiptAction | '';
                          setAction(value);
                          if (value) void inspect(value);
                        }}
                      >
                        <option value="">請選擇處理方式</option>
                        {preview.candidate.bank_total.amount < preview.candidate.obligation_total.amount ? (
                          <option value="partial">核銷實收，餘額續收（推薦）</option>
                        ) : (
                          <option value="overage">多收另列退款</option>
                        )}
                      </select>
                    </label>
                  </div>
                )}

                {preview.candidate.status !== 'review_required' && (
                  <>
                  <div className="finance-table-container">
                  <table className="finance-table" aria-label="本次期款核銷明細">
                    <thead><tr><th>本次期款</th><th>到期日</th><th>核銷金額</th><th>核銷後待收餘額</th></tr></thead>
                    <tbody>{previewRows?.map(item=><tr key={item.obligation_identity}>
                      <td>{getObligationLabel(item.obligation_identity,item.payment_stage)}</td>
                      <td>{item.due_date??'未定到期日'}</td>
                      <td>{financeMoney(item.allocated)}</td><td>{financeMoney(item.remaining)}</td>
                    </tr>)}</tbody>
                  </table>
                  </div>
                  <dl aria-label="本次核銷後餘額">
                    <dt>本次核銷合計</dt><dd>{financeMoney(allocatedTotal)}</dd>
                    <dt>本次選取期款剩餘待收</dt><dd>{financeMoney(dueTotal-allocatedTotal)}</dd>
                    <dt>其他未選期款待收</dt><dd>{caseRemaining===undefined?'待確認':financeMoney(caseRemaining-(dueTotal-allocatedTotal))}</dd>
                    <dt>核銷後案件全部應收餘額</dt><dd>{caseRemaining===undefined?'待確認':financeMoney(caseRemaining)}</dd>
                  </dl>
                  <div className="finance-recon-confirm-row">
                    <p className="finance-recon-preview-desc">
                      {preview.candidate.status === 'partial'
                        ? '本次只核銷實收，剩餘繼續待收。'
                        : preview.candidate.status === 'overage'
                        ? '本次選取期款核銷，多收另列退款待付。'
                        : '合計相符，可直接核銷。'}
                    </p>
                    <p>{caseRemaining===undefined?'案件應收來源或餘額尚待確認；本次僅核銷所選期款。':caseRemaining===0n?'本次核銷後，案件所有應收餘額將歸零。':'本次核銷後，案件仍有待收款項。'}</p>
                    <button
                      type="button"
                      className="finance-btn-primary finance-btn-lg"
                      disabled={busy||unknown}
                      onClick={() => void confirm()}
                    >
                      確認核銷本次收款
                    </button>
                  </div>
                  </>
                )}
              </div>
            )}
          </div>
        )}
      </>}

      {error && <p role="alert">{error}</p>}
      {unknown && (
        <button type="button" className="finance-btn-secondary" disabled={busy} onClick={() => void confirm()}>
          確認原操作結果
        </button>
      )}
      {result && (!postedReceipt.current||postedReceipt.current.caseNo===caseNo) && <p role="status">{result}</p>}
    </section>
  );
}

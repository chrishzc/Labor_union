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

function getObligationLabel(identity: string, stage?: string | null): string {
  const clean = identity.replace(/^client-obligation:[^:]+:/, '');
  const s = stage || clean;
  if (s === 'deposit') return '訂金期款';
  if (s === 'first') return '第一期期款';
  if (s === 'second') return '第二期期款';
  if (s === 'subsidy_return') return '客戶退款';
  return identity;
}

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
  const diff=bankTotal-dueTotal;
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
            <small>• 單期差額處理：若各期款已核銷但金額有短少或超收，請直接在上方各期款表格點選「處置差額」進行直接銷帳或認列差額。<br/>• 若客戶表示已匯款但未出現：請確認客戶匯入之虛擬帳號是否相符，或至銀行匯入對帳查詢。</small>
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
                              disabled={busy||unknown}
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
                    {facts.obligations.map(item => {
                      const isChecked = selectedItems.includes(item.obligation_identity);
                      return (
                        <label className={`finance-recon-obligation-item ${isChecked ? 'is-selected-item' : ''}`} key={item.obligation_identity}>
                          <input
                            type="checkbox"
                            disabled={busy||unknown}
                            checked={isChecked}
                            onChange={event => {
                              invalidate();
                              setSelectedItems(previous => event.target.checked ? [...previous, item.obligation_identity] : previous.filter(id => id !== item.obligation_identity));
                            }}
                          />
                          <div className="finance-recon-ob-info">
                            <div className="finance-recon-ob-name">
                              <strong>{getObligationLabel(item.obligation_identity, item.payment_stage)}</strong>
                              <small>{item.due_date ? `到期日：${item.due_date}` : '未定到期日'}</small>
                            </div>
                            <div className="finance-recon-ob-meta">
                              <span>待收 <strong>{financeMoney(item.amount_due_ntd)}</strong></span>
                              <small className="finance-mono-sub">{item.obligation_identity}</small>
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
                  <strong className={diff < 0 ? 'finance-diff-under' : diff > 0 ? 'finance-diff-over' : 'finance-paid'}>
                    {diff < 0 ? `短少 ${financeMoney(Math.abs(diff))}` : diff > 0 ? `超收 ${financeMoney(diff)}` : '金額相符'}
                  </strong>
                </div>
              </div>

              <div className="finance-recon-calc-explanation">
                {diff === 0 ? (
                  <span>✅ 入款金額與待收款項完全相符，確認後將直接全額銷帳結清。</span>
                ) : diff < 0 ? (
                  <span>⚠️ 入款金額少於期款應繳：確認後將<strong>認列實收 {financeMoney(bankTotal)}</strong>，剩餘差額 <strong>{financeMoney(Math.abs(diff))}</strong> 繼續待收（可於上方期款點「處置差額」或通知客戶補繳）。</span>
                ) : (
                  <span>⚠️ 入款金額多於期待繳：確認後期款全額結清，多收之 <strong>{financeMoney(diff)}</strong> 將另列為待退款。</span>
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
                  <div className="finance-recon-confirm-row">
                    <p className="finance-recon-preview-desc">
                      {preview.candidate.status === 'partial'
                        ? '本次只核銷實收，剩餘繼續待收。'
                        : preview.candidate.status === 'overage'
                        ? '原應收結清，多收另列退款待付。'
                        : '合計相符，可直接核銷。'}
                    </p>
                    <button
                      type="button"
                      className="finance-btn-primary finance-btn-lg"
                      disabled={busy||unknown}
                      onClick={() => void confirm()}
                    >
                      確認核銷本次收款
                    </button>
                  </div>
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
      {result && <p role="status">{result}</p>}
    </section>
  );
}

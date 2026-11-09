/** Select the original same-case refund for one immutable bank return. */
import { useEffect, useRef, useState } from 'react';
import { clientRefundReturnClient, ClientSettlementRemediationError } from '../api/client_finance/client_settlement_remediation_client';
import type { ClientRefundReturnPreview, ClientRefundReturnQuery } from '../api/client_finance/client_settlement_remediation_schemas';
import { financeMoney } from './FinanceReceiptsWorkspace';
import { useUnsavedChanges } from './UnsavedChanges';

type ReturnCommand = Parameters<typeof clientRefundReturnClient.apply>;
export function ClientRefundReturnReconciliationPanel({ caseNo, bankRowId, onPosted, onBusyChange }: {
  caseNo: string; bankRowId: number; onPosted: () => void; onBusyChange: (busy: boolean) => void;
}) {
  const [facts, setFacts] = useState<ClientRefundReturnQuery>();
  const [selected, setSelected] = useState('');
  const [preview, setPreview] = useState<ClientRefundReturnPreview>();
  const [busy, setBusy] = useState(false);
  const [unknown, setUnknown] = useState(false);
  const [message, setMessage] = useState('');
  const [revision, setRevision] = useState(0);
  const command = useRef<ReturnCommand | undefined>(undefined);
  useUnsavedChanges('客戶退匯核銷', [], { busy: busy || unknown });
  useEffect(() => { onBusyChange(busy || unknown); return () => onBusyChange(false); }, [busy, unknown, onBusyChange]);
  useEffect(() => {
    const controller = new AbortController();
    setFacts(undefined); setSelected(''); setPreview(undefined); setMessage(''); command.current = undefined;
    void clientRefundReturnClient.query(caseNo, { signal: controller.signal }).then(value => {
      if (!controller.signal.aborted) setFacts(value);
    }).catch(() => { if (!controller.signal.aborted) setMessage('本案原退款資料暫時無法取得，請重新查詢。'); });
    return () => controller.abort();
  }, [caseNo, bankRowId, revision]);

  function errorMessage(error: unknown) {
    if (error instanceof ClientSettlementRemediationError && error.status === 409 && error.code !== 'client_refund_return_invalid') return '銀行或原退款資料已變更，請重新查詢後核對。';
    return '原流水或原退款未通過退匯核銷檢查，請重新查核。';
  }
  async function inspect() {
    if (!selected || busy || unknown) return;
    setBusy(true); setMessage(''); setPreview(undefined);
    try { setPreview(await clientRefundReturnClient.preview(caseNo, { finance_import_row_id: bankRowId, refund_ledger_entry_id: Number(selected) })); }
    catch (error) { setMessage(errorMessage(error)); }
    finally { setBusy(false); }
  }
  async function confirm() {
    if ((!preview && !command.current) || busy) return;
    setBusy(true); setMessage('');
    command.current ??= [caseNo, { finance_import_row_id: bankRowId, refund_ledger_entry_id: Number(selected),
      expected_account_version: preview!.account_version, preview_fingerprint: preview!.preview_fingerprint,
      reason: '核對銀行退匯與原客戶退款' }, { idempotencyKey: crypto.randomUUID(), correlationId: crypto.randomUUID() }];
    try {
      await clientRefundReturnClient.apply(...command.current);
      const fresh = await clientRefundReturnClient.query(caseNo);
      if (fresh.refund_return_targets.some(item => item.id === Number(selected))) {
        setUnknown(true); setMessage('尚未確認原退款已完成退匯核銷，請查回原操作結果。'); return;
      }
      command.current = undefined; setUnknown(false); onPosted();
    } catch (error) {
      const status = error instanceof ClientSettlementRemediationError ? error.status : undefined;
      const uncertain = status === undefined || status >= 500;
      setUnknown(uncertain);
      if (!uncertain) { command.current = undefined; setPreview(undefined); }
      setMessage(uncertain ? '核銷結果尚未確認，請使用原操作查回結果。' : errorMessage(error));
    } finally { setBusy(false); }
  }
  const selectedTarget = facts?.refund_return_targets.find(item => item.id === Number(selected));

  return (
    <section
      className="case-accounting-card finance-advanced-reconciliation-card"
      aria-label="客戶退匯核對"
    >
      <div className="finance-section-heading">
        <div className="finance-reconciliation-heading-group">
          <h3>待沖銷銀行退匯與原客戶退款對核</h3>
          <span className="finance-tag-imported">客戶退匯沖正</span>
        </div>
        <button
          type="button"
          className="finance-btn-secondary"
          disabled={busy || unknown}
          onClick={() => setRevision((value) => value + 1)}
        >
          重新查詢原退款
        </button>
      </div>

      <div className="finance-advanced-reconciliation-guide">
        <strong>💡 作用說明：</strong>銀行對帳單已辨識到本案的退匯入款流水（如下左側）。請選擇對應的原退款紀錄（如下右側）。核銷確認後，系統將正式沖正該筆退款並重開原退款應付款項。
      </div>

      {!facts && !message && <p role="status">正在查詢本案原退款…</p>}
      {message && <p role="alert">{message}</p>}

      {facts && (
        <div className="finance-recon-deck">
          <div className="finance-recon-deck-grid">
            {/* 左側：銀行退匯入款 */}
            <div className="finance-recon-col finance-recon-col-bank">
              <div className="finance-recon-col-header">
                <span className="finance-recon-badge-step">步驟 1</span>
                <h4>銀行退匯款項（來源流水）</h4>
              </div>
              <div className="finance-table-container">
                <table className="finance-table finance-recon-table">
                  <thead>
                    <tr>
                      <th>納入</th>
                      <th>銀行來源</th>
                      <th>流水編號</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="is-selected-row">
                      <td>
                        <input type="checkbox" checked disabled readOnly aria-label="納入銀行款" />
                      </td>
                      <td>
                        <span>銀行退匯入款</span>
                      </td>
                      <td>
                        <small className="finance-mono-sub">bank:{bankRowId}</small>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div className="finance-recon-col-summary">
                <span>使用已辨識之銀行退匯流水。</span>
              </div>
            </div>

            {/* 中間箭頭 */}
            <div className="finance-recon-arrow-divider" aria-hidden="true">
              <span className="finance-recon-arrow-icon">➔</span>
              <small>沖抵沖正</small>
            </div>

            {/* 右側：原退款紀錄 */}
            <div className="finance-recon-col finance-recon-col-target">
              <div className="finance-recon-col-header">
                <span className="finance-recon-badge-step">步驟 2</span>
                <h4>原客戶退款紀錄（核銷目標）</h4>
              </div>

              <label style={{ display: 'grid', gap: 4, marginBottom: 12 }}>
                <span style={{ fontSize: '0.84rem', fontWeight: 600 }}>原退款</span>
                <select
                  aria-label="原退款"
                  value={selected}
                  disabled={busy || unknown}
                  onChange={(event) => {
                    setSelected(event.target.value);
                    setPreview(undefined);
                    setMessage('');
                    command.current = undefined;
                  }}
                  style={{ padding: '6px 10px', border: '1px solid #ebdcd1', borderRadius: 6 }}
                >
                  <option value="">請選擇原退款</option>
                  {facts.refund_return_targets.map((item, index) => (
                    <option key={item.id} value={item.id}>
                      退款 {index + 1} · {item.occurred_on} · {financeMoney(item.amount_ntd)}
                    </option>
                  ))}
                </select>
              </label>

              {!facts.refund_return_targets.length ? (
                <div className="finance-reconciliation-empty-box">
                  <p>本案目前沒有可對應的有效原退款。</p>
                  <small>請回案件帳務查核原退款紀錄或確認流水歸屬。</small>
                </div>
              ) : (
                <div className="finance-recon-obligations-list">
                  {facts.refund_return_targets.map((item, index) => {
                    const isChecked = selected === String(item.id);
                    return (
                      <label
                        key={item.id}
                        className={`finance-recon-obligation-item ${isChecked ? 'is-selected-item' : ''}`}
                        style={{ cursor: 'pointer' }}
                      >
                        <input
                          type="radio"
                          name="refund_target"
                          aria-label={`原退款 ${index + 1}`}
                          value={item.id}
                          checked={isChecked}
                          disabled={busy || unknown}
                          onChange={(e) => {
                            setSelected(e.target.value);
                            setPreview(undefined);
                            setMessage('');
                            command.current = undefined;
                          }}
                        />
                        <div className="finance-recon-ob-info">
                          <div className="finance-recon-ob-name">
                            <strong>退款紀錄 #{index + 1}</strong>
                            <small>退款日：{item.occurred_on}</small>
                          </div>
                          <div className="finance-recon-ob-meta">
                            <span>原退款金額 <strong>{financeMoney(item.amount_ntd)}</strong></span>
                          </div>
                        </div>
                      </label>
                    );
                  })}
                </div>
              )}
              <div className="finance-recon-col-summary">
                <span>已選取原退款：<strong>{selectedTarget ? financeMoney(selectedTarget.amount_ntd) : '未選取'}</strong></span>
              </div>
            </div>
          </div>

          {/* 試算與決策條 */}
          <div className="finance-recon-calculation-bar">
            <div className="finance-recon-calc-metrics">
              <div>
                <small>銀行退匯流水</small>
                <strong>bank:{bankRowId}</strong>
              </div>
              <span className="finance-recon-calc-operator">➔</span>
              <div>
                <small>對應原退款金額</small>
                <strong>{selectedTarget ? financeMoney(selectedTarget.amount_ntd) : '—'}</strong>
              </div>
            </div>

            <div className="finance-recon-calc-explanation">
              {!selected ? (
                <span>請先選擇要對核的原退款紀錄。核銷後將依正式規則沖正原退款並重新開立對應退款應付。</span>
              ) : (
                <span>已選取原退款。點擊預覽確認後，將依正式規則重開原退款應付。</span>
              )}
            </div>

            {!preview && (
              <div className="finance-recon-action-row">
                <button
                  type="button"
                  className="finance-btn-primary finance-btn-lg"
                  disabled={!selected || busy || unknown}
                  onClick={() => void inspect()}
                >
                  預覽退匯核銷
                </button>
              </div>
            )}
          </div>

          {/* 預覽與確認結果 */}
          {preview && !unknown && (
            <div className="finance-scope-note finance-recon-preview-box">
              <div className="finance-recon-preview-header">
                <h5>本次退匯核對明細</h5>
                <span>本次退回 {financeMoney(preview.candidate.amount.amount)}，將重開原退款應付。</span>
              </div>
              <div className="finance-recon-confirm-row">
                <button
                  type="button"
                  className="finance-btn-primary finance-btn-lg"
                  disabled={busy}
                  onClick={() => void confirm()}
                >
                  確認退匯核銷
                </button>
              </div>
            </div>
          )}

          {unknown && (
            <div className="finance-scope-note finance-recon-preview-box" style={{ borderColor: '#eab308' }}>
              <p>尚未確認核銷結果，請查回原操作結果。</p>
              <button
                type="button"
                className="finance-btn-secondary"
                disabled={busy}
                onClick={() => void confirm()}
              >
                查回原次核銷結果
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
};

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
  return <section className="case-accounting-card" aria-label="客戶退匯核對">
    <h3>核對退回款與原退款</h3>
    <p>原銀行流水已固定，請選擇本案對應的原退款。核銷後依正式規則重開原退款應付。</p>
    <button type="button" disabled={busy || unknown} onClick={() => setRevision(value => value + 1)}>重新查詢原退款</button>
    {!facts && !message && <p role="status">正在查詢本案原退款…</p>}
    {facts && <>
      <label>原退款<select aria-label="原退款" value={selected} disabled={busy || unknown} onChange={event => {
        setSelected(event.target.value); setPreview(undefined); setMessage(''); command.current = undefined;
      }}><option value="">請選擇原退款</option>{facts.refund_return_targets.map((item, index) =>
        <option key={item.id} value={item.id}>退款 {index + 1} · {item.occurred_on} · {financeMoney(item.amount_ntd)}</option>)}</select></label>
      {!facts.refund_return_targets.length && <p>本案目前沒有可對應的有效原退款，請回案件帳務查核。</p>}
      <button type="button" disabled={!selected || busy || unknown} onClick={() => void inspect()}>預覽退匯核銷</button>
    </>}
    {preview && !unknown && <div><p>本次退回 {financeMoney(preview.candidate.amount.amount)}，將重開原退款應付。</p>
      <button type="button" disabled={busy} onClick={() => void confirm()}>確認退匯核銷</button></div>}
    {unknown && <button type="button" disabled={busy} onClick={() => void confirm()}>查回原次核銷結果</button>}
    {message && <p role="alert">{message}</p>}
  </section>;
}

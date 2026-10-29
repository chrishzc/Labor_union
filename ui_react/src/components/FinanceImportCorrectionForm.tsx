import { useUnsavedDraft } from './UnsavedChanges';
import { useState } from 'react';
import { financeImportCorrectionClient, type FinanceImportCorrectionPreview, type FinanceImportCorrectionSelection } from '../api/finance_import/finance_import_correction_client';
import { clientReceiptQueryClient } from '../api/client_finance/client_receipt_query_client';
import { StaffPayoutRemediationWorkbench, type StaffPayoutRemediationTarget } from './StaffPayoutRemediationWorkbench';
import { staffPayablesQueryClient } from '../api/staff_payables/staff_payables_query_client';
import { clientSettlementRemediationClient } from '../api/client_finance/client_settlement_remediation_client';

type CorrectionCommand = {
  preview: FinanceImportCorrectionPreview;
  selection: FinanceImportCorrectionSelection;
  identity: { idempotencyKey: string; correlationId: string };
};

export function FinanceImportCorrectionForm({ rowIdentity, sourceLabel, staff, initialKind = 'client_receipt', onPosted }: {
  rowIdentity: string; sourceLabel: string; staff: readonly { id: number; label: string }[];
  initialKind?: 'client_receipt' | 'staff_payout' | 'client_refund';
  onPosted?: () => void;
}) {
  const [payoutTarget, setPayoutTarget] = useState<StaffPayoutRemediationTarget | null>(null);
  const [payoutBusy, setPayoutBusy] = useState(false);
  const bankRow = /^finance-import-row:([1-9][0-9]*)$/.exec(rowIdentity);
  const [kind, setKind] = useState(initialKind);
  const [partialRefund, setPartialRefund] = useState(false);
  const [target, setTarget] = useState('');
  const [options, setOptions] = useState<{ id: string; label: string }[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [reason, setReason] = useState('');
  const [preview, setPreview] = useState<FinanceImportCorrectionPreview | null>(null);
  const [selection, setSelection] = useState<FinanceImportCorrectionSelection | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [jobId, setJobId] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [identity] = useState(() => ({ idempotencyKey: `finance-correction-${crypto.randomUUID()}`, correlationId: `finance-correction-${crypto.randomUUID()}` }));
  const [retryCommand, setRetryCommand] = useState<CorrectionCommand | null>(null);
  const invalidate = () => { setPayoutTarget(null); setPreview(null); setSelection(null); setMessage(''); };
  const load = async () => {
    if (retryCommand) return;
    setBusy(true); invalidate(); setOptions([]); setSelected([]);
    try {
      if (kind === 'client_receipt') {
        const data = await clientReceiptQueryClient.query(target);
        setOptions(data.obligations.map((item) => ({ id: item.obligation_identity, label: `${data.case_no} · ${{ deposit: '訂金', first: '第一期', second: '第二期', adjustment: '調整款' }[item.payment_stage] ?? item.payment_stage} · NT$ ${item.amount_due_ntd.toLocaleString()}` })));
      } else if (kind === 'client_refund') {
        const data = await clientSettlementRemediationClient.query(target, { includeNotDue: true });
        setOptions(data.refund_obligations.map((item) => ({ id: item.obligation_identity, label: `${data.case_no} · 客戶退款 · 待退 NT$ ${item.amount_due_ntd.toLocaleString()}` })));
      } else {
        const data = await staffPayablesQueryClient.query(Number(target));
        setOptions(data.obligations.filter((item) => item.balance_ntd > 0).map((item) => ({ id: item.obligation_identity, label: `${item.case_no} · 未付 NT$ ${item.balance_ntd.toLocaleString()}` })));
      }
    } catch (error) { setMessage(error instanceof Error ? error.message : '款項查詢失敗。'); }
    finally { setBusy(false); }
  };
  const review = async () => {
    if (retryCommand) return;
    setBusy(true); invalidate();
    const request: FinanceImportCorrectionSelection = { row_identity: rowIdentity, classification_type: kind,
      target_obligation_identities: selected, refund_ledger_entry_identity: null, allow_partial_refund_recovery: kind === 'client_refund' && partialRefund,
      allow_refund_overage_recovery: false, allow_client_receipt_overage: false, reason: reason.trim(), evidence: [sourceLabel] };
    try {
      const result = await financeImportCorrectionClient.preview(request);
      if (result.candidate.row_identity !== rowIdentity || result.candidate.classification_type !== kind) throw new Error('更正預覽對象不一致。');
      if (!result.candidate.allocations.length || result.candidate.allocations.some((item) => !selected.includes(item.obligation_identity))) throw new Error('更正預覽包含未選取的款項。');
      setSelection(request); setPreview(result);
      await apply({ preview: result, selection: request, identity });
    } catch (error) { setMessage(error instanceof Error ? error.message : '更正預覽失敗。'); }
    finally { setBusy(false); }
  };
  const apply = async (checked?: CorrectionCommand) => {
    const command = retryCommand ?? checked ?? (preview && selection ? { preview, selection, identity } : null);
    if (!command || submitted) return;
    setBusy(true); setSubmitted(true);
    try {
      const job = await financeImportCorrectionClient.apply(command.preview, command.selection, command.identity);
      setRetryCommand(null); setJobId(job.job_id); setMessage('更正已受理，正在確認核銷結果。');
      await readOutcome(job.job_id, command.preview);
    }
    catch (error) {
      setRetryCommand(command);
      setSubmitted(false);
      setMessage(`${error instanceof Error ? error.message : '更正結果未知。'} 請使用同一個確認更正操作重新確認。`);
    }
    finally { setBusy(false); }
  };
  const readOutcome = async (selectedJob = jobId, checkedPreview = preview) => {
    if (!selectedJob || !checkedPreview) return;
    setBusy(true);
    try {
      let outcome = await financeImportCorrectionClient.queryOutcome(selectedJob);
      for (let attempt = 0; attempt < 9 && !['succeeded', 'failed', 'cancelled'].includes(outcome.status); attempt++) {
        await new Promise(resolve => setTimeout(resolve, 500));
        outcome = await financeImportCorrectionClient.queryOutcome(selectedJob);
      }
      if (outcome.status === 'succeeded') {
        if (
          !outcome.receipt
          || outcome.receipt.row_identity !== rowIdentity
          || outcome.receipt.batch_identity !== checkedPreview.candidate.batch_identity
          || outcome.receipt.preview_fingerprint !== checkedPreview.preview_fingerprint
        ) throw new Error('更正收據尚未確認，不能判定完成。');
        if (kind === 'client_refund') {
          const fresh = await clientSettlementRemediationClient.query(target, { includeNotDue: true });
          setOptions(fresh.refund_obligations.map((item) => ({ id: item.obligation_identity, label: `${fresh.case_no} · 客戶退款 · 待退 NT$ ${item.amount_due_ntd.toLocaleString()}` })));
          setSelected([]);
          setMessage(fresh.refund_obligations.length ? '退款核銷完成；已更新剩餘待退款，後續清冊只列餘額。' : '退款核銷完成；本案一般退款已退清。');
        } else setMessage('帳務更正完成，已確認核銷收據。');
        setCompleted(true); onPosted?.();
      } else { if (outcome.status === 'failed' || outcome.status === 'cancelled') setCompleted(true); setMessage(outcome.status === 'failed' || outcome.status === 'cancelled' ? '更正未完成，請重新查詢帳務資料。' : '更正仍在處理中。'); }
    } catch (error) { setMessage(error instanceof Error ? error.message : '無法讀取結果。'); }
    finally { setBusy(false); }
  };
  useUnsavedDraft('匯入帳務修正', { '款項類別': kind, '指定對象': target, '選取項目': selected, '部分退款': partialRefund, '原因': reason }, { enabled: kind !== 'staff_payout' || !payoutTarget, busy: busy || payoutBusy || (!!retryCommand && !submitted) || (!!jobId && !completed), resetKey: completed, save: review, discard: () => { setSelected([]); setTarget(''); setReason(''); setPartialRefund(false); invalidate(); } });

  return <section aria-label="銀行款項更正" className="order-case-review-note finance-correction-form">
    <p>將這筆銀行紀錄對應至正確的客戶收款、客戶退款或月嫂付款。金額由後端核對，不可手動標記已付。</p>
    <fieldset disabled={busy || payoutBusy || submitted || retryCommand !== null}>
      <label>款項用途<select value={kind} onChange={(event) => { if (retryCommand) return; setKind(event.target.value as typeof kind); setPartialRefund(false); setTarget(''); setOptions([]); setSelected([]); invalidate(); }}><option value="client_receipt">客戶收款</option><option value="client_refund">客戶退款</option><option value="staff_payout">月嫂付款</option></select></label>
      {kind !== 'staff_payout' ? <label>案件編號<input value={target} onChange={(event) => { if (retryCommand) return; setTarget(event.target.value); setOptions([]); setSelected([]); invalidate(); }} /></label> : <label>月嫂<select aria-label="月嫂" value={target} onChange={(event) => { if (retryCommand) return; setTarget(event.target.value); setOptions([]); setSelected([]); invalidate(); }}><option value="">請選擇</option>{staff.map((person) => <option key={person.id} value={person.id}>{person.label}</option>)}</select></label>}
      <button type="button" disabled={!target.trim()} onClick={() => void load()}>查詢待核銷款項</button>
      {options.map((item) => <label key={item.id}><input type="checkbox" checked={selected.includes(item.id)} onChange={() => { if (retryCommand) return; setSelected((items) => items.includes(item.id) ? items.filter((id) => id !== item.id) : [...items, item.id]); invalidate(); }} />{item.label}</label>)}
      {kind === 'staff_payout' && bankRow && <button type="button" disabled={!selected.length} onClick={() => setPayoutTarget({ staffId: Number(target), obligationIdentity: selected[0], obligationIdentities: selected })}>處理付款不足或超額</button>}
      {kind === 'client_refund' && <label>退款核銷方式<select value={partialRefund ? 'partial' : 'exact'} onChange={(event) => { setPartialRefund(event.target.value === 'partial'); invalidate(); }}><option value="exact">足額核銷待退款</option><option value="partial">退款不足，先核銷實退</option></select></label>}
      <label>更正原因（選填）<input maxLength={500} value={reason} onChange={(event) => { if (retryCommand) return; setReason(event.target.value); invalidate(); }} /></label>
      <button type="button" disabled={!selected.length} onClick={() => void review()}>儲存更正並核銷</button>
    </fieldset>
    {payoutTarget && bankRow && <div><StaffPayoutRemediationWorkbench target={payoutTarget} financeImportRowId={Number(bankRow[1])} onBusyChange={setPayoutBusy} onPosted={() => setSubmitted(true)}/><button type="button" disabled={payoutBusy} onClick={() => setPayoutTarget(null)}>關閉差額核銷</button></div>}
    {preview && <div><p>銀行金額 NT$ {preview.candidate.bank_amount_ntd.toLocaleString()}，將核銷 {preview.candidate.allocations.length} 筆款項。</p><ul>{preview.candidate.allocations.map((item) => <li key={item.obligation_identity}>{options.find((option) => option.id === item.obligation_identity)?.label ?? '待確認款項'}：本次核銷 NT$ {item.amount_ntd.toLocaleString()}</li>)}</ul></div>}
    {retryCommand && <button type="button" disabled={busy || submitted} onClick={() => void apply()}>以原操作確認更正結果</button>}
    {jobId && <button type="button" disabled={busy} onClick={() => void readOutcome()}>重新查詢更正結果</button>}
    {message && <p role="status">{message}</p>}
  </section>;
}

import { useState } from 'react';
import { financeImportCorrectionClient, type FinanceImportCorrectionPreview, type FinanceImportCorrectionSelection } from '../api/finance_import/finance_import_correction_client';
import { clientReceiptQueryClient } from '../api/client_finance/client_receipt_query_client';
import { staffPayablesQueryClient } from '../api/staff_payables/staff_payables_query_client';

type CorrectionCommand = {
  preview: FinanceImportCorrectionPreview;
  selection: FinanceImportCorrectionSelection;
  identity: { idempotencyKey: string; correlationId: string };
};

export function FinanceImportCorrectionForm({ rowIdentity, sourceLabel, staff }: {
  rowIdentity: string; sourceLabel: string; staff: readonly { id: number; label: string }[];
}) {
  const [kind, setKind] = useState<'client_receipt' | 'staff_payout'>('client_receipt');
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
  const [identity] = useState(() => ({ idempotencyKey: `finance-correction-${crypto.randomUUID()}`, correlationId: `finance-correction-${crypto.randomUUID()}` }));
  const [retryCommand, setRetryCommand] = useState<CorrectionCommand | null>(null);
  const invalidate = () => { setPreview(null); setSelection(null); setMessage(''); };
  const load = async () => {
    if (retryCommand) return;
    setBusy(true); invalidate(); setOptions([]); setSelected([]);
    try {
      if (kind === 'client_receipt') {
        const data = await clientReceiptQueryClient.query(target);
        setOptions(data.obligations.map((item) => ({ id: item.obligation_identity, label: `${data.case_no} · ${{ deposit: '訂金', first: '第一期', second: '第二期', adjustment: '調整款' }[item.payment_stage] ?? item.payment_stage} · NT$ ${item.amount_due_ntd.toLocaleString()}` })));
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
      target_obligation_identities: selected, refund_ledger_entry_identity: null, allow_partial_refund_recovery: false,
      allow_refund_overage_recovery: false, allow_client_receipt_overage: false, reason: reason.trim(), evidence: [sourceLabel] };
    try {
      const result = await financeImportCorrectionClient.preview(request);
      if (result.candidate.row_identity !== rowIdentity || result.candidate.classification_type !== kind) throw new Error('更正預覽對象不一致。');
      if (!result.candidate.allocations.length || result.candidate.allocations.some((item) => !selected.includes(item.obligation_identity))) throw new Error('更正預覽包含未選取的款項。');
      setSelection(request); setPreview(result);
    } catch (error) { setMessage(error instanceof Error ? error.message : '更正預覽失敗。'); }
    finally { setBusy(false); }
  };
  const apply = async () => {
    if (!preview || !selection || submitted) return;
    const command = retryCommand ?? { preview, selection, identity };
    setBusy(true); setSubmitted(true);
    try {
      const job = await financeImportCorrectionClient.apply(command.preview, command.selection, command.identity);
      setRetryCommand(null); setJobId(job.job_id); setMessage('更正已受理，請查詢處理結果；尚未完成核銷。');
    }
    catch (error) {
      setRetryCommand(command);
      setSubmitted(false);
      setMessage(`${error instanceof Error ? error.message : '更正結果未知。'} 請使用同一個確認更正操作重新確認。`);
    }
    finally { setBusy(false); }
  };
  const readOutcome = async () => {
    if (!jobId || !preview) return;
    setBusy(true);
    try {
      const outcome = await financeImportCorrectionClient.queryOutcome(jobId);
      if (outcome.status === 'succeeded') {
        if (
          !outcome.receipt
          || outcome.receipt.row_identity !== rowIdentity
          || outcome.receipt.batch_identity !== preview.candidate.batch_identity
          || outcome.receipt.preview_fingerprint !== preview.preview_fingerprint
        ) throw new Error('更正收據尚未確認，不能判定完成。');
        setMessage('帳務更正完成，已確認核銷收據。');
      } else setMessage(outcome.status === 'failed' || outcome.status === 'cancelled' ? '更正未完成，請重新查詢帳務資料。' : '更正仍在處理中。');
    } catch (error) { setMessage(error instanceof Error ? error.message : '無法讀取結果。'); }
    finally { setBusy(false); }
  };
  return <section aria-label="銀行款項更正" className="order-case-review-note">
    <p>將這筆銀行紀錄對應至正確的客戶收款或月嫂付款。金額由後端核對，不可手動標記已付。</p>
    <fieldset disabled={busy || submitted || retryCommand !== null}>
      <label>款項用途<select value={kind} onChange={(event) => { if (retryCommand) return; setKind(event.target.value as typeof kind); setTarget(''); setOptions([]); setSelected([]); invalidate(); }}><option value="client_receipt">客戶收款</option><option value="staff_payout">月嫂付款</option></select></label>
      {kind === 'client_receipt' ? <label>案件編號<input value={target} onChange={(event) => { if (retryCommand) return; setTarget(event.target.value); setOptions([]); setSelected([]); invalidate(); }} /></label> : <label>月嫂<select value={target} onChange={(event) => { if (retryCommand) return; setTarget(event.target.value); setOptions([]); setSelected([]); invalidate(); }}><option value="">請選擇</option>{staff.map((person) => <option key={person.id} value={person.id}>{person.label}</option>)}</select></label>}
      <button type="button" disabled={!target.trim()} onClick={() => void load()}>查詢待核銷款項</button>
      {options.map((item) => <label key={item.id}><input type="checkbox" checked={selected.includes(item.id)} onChange={() => { if (retryCommand) return; setSelected((items) => items.includes(item.id) ? items.filter((id) => id !== item.id) : [...items, item.id]); invalidate(); }} />{item.label}</label>)}
      <label>更正原因<input maxLength={500} value={reason} onChange={(event) => { if (retryCommand) return; setReason(event.target.value); invalidate(); }} /></label>
      <button type="button" disabled={!selected.length || !reason.trim()} onClick={() => void review()}>預覽更正</button>
    </fieldset>
    {preview && <div><p>銀行金額 NT$ {preview.candidate.bank_amount_ntd.toLocaleString()}，將核銷 {preview.candidate.allocations.length} 筆款項。</p><ul>{preview.candidate.allocations.map((item) => <li key={item.obligation_identity}>{options.find((option) => option.id === item.obligation_identity)?.label ?? '待確認款項'}：本次核銷 NT$ {item.amount_ntd.toLocaleString()}</li>)}</ul><button type="button" disabled={busy || submitted} onClick={() => void apply()}>確認更正並核銷</button></div>}
    {jobId && <button type="button" disabled={busy} onClick={() => void readOutcome()}>重新查詢更正結果</button>}
    {message && <p role="status">{message}</p>}
  </section>;
}

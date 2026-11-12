import { useState } from 'react';
import {
  historicalServiceAccountingClient as client,
  type HistoricalAttributionCommand, type HistoricalAttributionPreview, type HistoricalServiceAccountingQuery,
} from '../api/orders/historical_service_accounting_client';
import { useStaffIdentityDirectory, useStaffIdentityLabels } from './StaffIdentityProvider';

export function HistoricalServiceAttributionPanel({ facts, onSaved, onBusyChange }: {
  facts: HistoricalServiceAccountingQuery;
  onSaved: () => void;
  onBusyChange: (busy: boolean) => void;
}) {
  const directory = useStaffIdentityDirectory();
  const staff = useStaffIdentityLabels();
  const [rows, setRows] = useState(() => facts.assignments.map(item => ({ staff_id: item.staff_id, actual_service_days: 0 })));
  const [nextStaff, setNextStaff] = useState(0);
  const [evidence, setEvidence] = useState('');
  const [reason, setReason] = useState('');
  const [pending, setPending] = useState<{ command: HistoricalAttributionCommand; preview: HistoricalAttributionPreview; reason: string; key: string } | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [adoptCalculatedAmounts, setAdoptCalculatedAmounts] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const originalStaff = new Set(facts.assignments.map(item => item.staff_id));
  async function submit() {
    setBusy(true);
    onBusyChange(true);
    setError('');
    try {
      if (pending) {
        setSubmitted(true);
        await client.applyAttribution(facts.case_no, pending.command, pending.preview, pending.reason, pending.key, adoptCalculatedAmounts);
        onSaved();
      } else {
        const command = { caregivers: rows, evidence: evidence.trim() };
        const preview = await client.previewAttribution(facts.case_no, command);
        setAdoptCalculatedAmounts(false);
        setPending({ command, preview, reason: reason.trim(), key: crypto.randomUUID() });
      }
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : '歷史服務歸屬未儲存。');
    } finally {
      setBusy(false);
      onBusyChange(false);
    }
  }
  return <section className="formal-recommendation-inline-form" aria-label="按月嫂天數拆應付">
    <h3>按月嫂天數拆應付</h3>
    <p>輸入各月嫂可證實的天數。歷史訂單以天數計薪，畫面維持「未建立排班」。</p>
    {!pending ? <fieldset disabled={busy}>
      {rows.map(row => <div key={row.staff_id} className="order-case-action-row">
        <label>{staff.label(row.staff_id, facts.assignments.find(item => item.staff_id === row.staff_id)?.staff_name)} · 服務天數
          <input type="number" min={1} step={1} value={row.actual_service_days || ''}
            onChange={event => setRows(current => current.map(item => item.staff_id === row.staff_id
              ? { ...item, actual_service_days: Number(event.target.value) } : item))} />
        </label>
        {!originalStaff.has(row.staff_id) && <button type="button" onClick={() => setRows(current => current.filter(item => item.staff_id !== row.staff_id))}>移除</button>}
      </div>)}
      <label>新增月嫂 <select value={nextStaff} onChange={event => setNextStaff(Number(event.target.value))}>
        <option value={0}>選擇月嫂</option>
        {[...(directory?.people.values() ?? [])].filter(person => !rows.some(item => item.staff_id === person.id))
          .map(person => <option key={person.id} value={person.id}>{staff.label(person.id)}</option>)}
      </select></label>
      <button type="button" disabled={!nextStaff || rows.length >= 20} onClick={() => {
        setRows(current => [...current, { staff_id: nextStaff, actual_service_days: 0 }]); setNextStaff(0);
      }}>加入月嫂</button>
      <label>天數證據 <input maxLength={500} value={evidence} onChange={event => setEvidence(event.target.value)} /></label>
      <label>更正原因 <input maxLength={500} value={reason} onChange={event => setReason(event.target.value)} /></label>
    </fieldset> : <>
      <h4>核對月嫂應付</h4>
      {pending.preview.caregivers.map(item => <p key={item.staff_id}>{staff.label(item.staff_id)} · {item.actual_service_days} 日 · {pending.preview.accounting_pending.length ? '試算' : '應付'} NT$ {item.entitlement_ntd.toLocaleString('zh-TW')}</p>)}
      {pending.preview.accounting_pending.includes('historical_attribution_actual_payout_evidence_missing') &&
        <p>服務天數可先儲存。原款項缺可核對的實付與核銷連結，補齊後請重新預覽帳務。</p>}
      {pending.preview.paid_obligations.map((item, index) => <p key={index}>{staff.label(item.staff_id)} · 原實付 NT$ {item.paid_ntd.toLocaleString('zh-TW')} · 待付 NT$ {item.remaining_payable_ntd.toLocaleString('zh-TW')} · 新增追償 NT$ {item.new_recovery_ntd.toLocaleString('zh-TW')}</p>)}
      {pending.preview.reopen_accounting && <p>確認後重開帳務，保留原服務完工紀錄。</p>}
      {pending.preview.manual_amounts.map((item, index) => <p key={index}>{staff.label(item.staff_id)} · 原人工金額 NT$ {item.manual_ntd.toLocaleString('zh-TW')} · 原系統計算 NT$ {item.previous_calculated_ntd.toLocaleString('zh-TW')}</p>)}
      {pending.preview.funding.map(item => <p key={`${item.staff_id}:${item.funding_kind}`}>{staff.label(item.staff_id)} · {item.funding_kind === 'client' ? '自備款' : '補助款'} · 應付 NT$ {item.entitlement_ntd.toLocaleString('zh-TW')} · 原核銷 NT$ {item.settled_ntd.toLocaleString('zh-TW')} · {item.due_date ?? '付款日待確認'}</p>)}
      {pending.preview.manual_amounts.length > 0 && <label>
        <input type="checkbox" checked={adoptCalculatedAmounts} disabled={busy || submitted}
          onChange={event => setAdoptCalculatedAmounts(event.target.checked)} />採用拆分後的新計算金額
      </label>}
      {!submitted && <button type="button" disabled={busy} onClick={() => setPending(null)}>返回編輯</button>}
    </>}
    <button type="button" disabled={busy || (!!pending?.preview.manual_amounts.length && !adoptCalculatedAmounts) || (!pending && (rows.length < 2 || rows.some(item => !Number.isInteger(item.actual_service_days) || item.actual_service_days < 1) || !reason.trim() || !evidence.trim()))}
      onClick={() => void submit()}>{submitted ? '以原操作重新確認' : pending ? '確認更正' : '預覽帳務影響'}</button>
    {error && <p role="alert">{error}</p>}
  </section>;
}

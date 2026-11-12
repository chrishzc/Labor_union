import { useState } from 'react';
import {
  officialServiceDateCorrectionClient as client,
  type AttributionChange,
  type AttributionPreview,
} from '../api/orders/official_service_date_correction_client';
import type { AssignmentSegment } from '../api/orders/order_query_schemas';
import { useStaffIdentityDirectory, useStaffIdentityLabels } from './StaffIdentityProvider';

interface Props {
  caseNo: string;
  segments: AssignmentSegment[];
  onSaved: () => void;
  onBusyChange: (busy: boolean) => void;
}

export function OrderServiceAttributionPanel({ caseNo, segments, onSaved, onBusyChange }: Props) {
  const directory = useStaffIdentityDirectory();
  const staff = useStaffIdentityLabels();
  const [assignmentId, setAssignmentId] = useState(segments[0]?.assignment_id ?? 0);
  const [staffId, setStaffId] = useState(0);
  const [days, setDays] = useState<string[]>([]);
  const [evidence, setEvidence] = useState('');
  const [reason, setReason] = useState('');
  const [pending, setPending] = useState<{ change: AttributionChange; preview: AttributionPreview; key: string; reason: string } | null>(null);
  const [applying, setApplying] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const segment = segments.find(item => item.assignment_id === assignmentId);
  async function submit() {
    setBusy(true);
    onBusyChange(true);
    setMessage('');
    try {
      if (pending) {
        setApplying(true);
        await client.applyAttribution(caseNo, pending.change, pending.preview, pending.reason, pending.key);
        onSaved();
      } else {
        const change = { source_assignment_id: assignmentId, staff_id: staffId, service_dates: [...days].sort(), evidence: evidence.trim() };
        const preview = await client.previewAttribution(caseNo, change);
        setPending({ change, preview, key: crypto.randomUUID(), reason: reason.trim() });
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '更正未完成，請重新核對。');
    } finally {
      setBusy(false);
      onBusyChange(false);
    }
  }
  return <section className="formal-recommendation-inline-form" aria-label="更正已服務紀錄">
    <h3>更正已服務紀錄</h3>
    {!pending ? <fieldset disabled={busy}>
      <label>原服務區段 <select value={assignmentId} onChange={event => { setAssignmentId(Number(event.target.value)); setDays([]); setStaffId(0); }}>
        {segments.map(item => <option key={item.assignment_id} value={item.assignment_id ?? 0}>{staff.label(item.staff_id)} · {item.assigned_start_date} ～ {item.assigned_end_date}</option>)}
      </select></label>
      <label>實際服務月嫂 <select value={staffId} onChange={event => setStaffId(Number(event.target.value))}>
        <option value={0}>選擇月嫂</option>
        {[...(directory?.people.values() ?? [])].filter(person => person.id !== segment?.staff_id).map(person =>
          <option key={person.id} value={person.id}>{staff.label(person.id)}</option>)}
      </select></label>
      <fieldset><legend>實際服務日</legend>
        {segment?.official_service_dates.map(day => <label key={day}>
          <input type="checkbox" checked={days.includes(day)} onChange={event =>
            setDays(current => event.target.checked ? [...current, day] : current.filter(value => value !== day))} />{day}
        </label>)}
      </fieldset>
      <label>更正依據 <input maxLength={500} value={evidence} onChange={event => setEvidence(event.target.value)} /></label>
      <label>更正原因 <input maxLength={500} value={reason} onChange={event => setReason(event.target.value)} /></label>
    </fieldset> : <div>
      <h4>核對月嫂款項</h4>
      {pending.preview.staff_entitlements.map(item => <p key={item.staff_id}>{staff.label(item.staff_id)} · 更正後應付 NT$ {item.amount_ntd.toLocaleString('zh-TW')}</p>)}
      {pending.preview.paid_obligations.map((item, index) => <p key={index}>{staff.label(item.staff_id)} · 原應付 NT$ {item.before_ntd.toLocaleString('zh-TW')} · 原實付 NT$ {item.paid_ntd.toLocaleString('zh-TW')} · 新增追償 NT$ {item.recovery_increase_ntd.toLocaleString('zh-TW')}</p>)}
      {!applying && <button type="button" disabled={busy} onClick={() => setPending(null)}>返回編輯</button>}
    </div>}
    <button type="button" disabled={busy || (!pending && (!staffId || !days.length || !evidence.trim() || !reason.trim()))}
      onClick={() => void submit()}>{applying ? '以原操作重新確認' : pending ? '確認更正' : '預覽帳務影響'}</button>
    {message && <p role="alert">{message}</p>}
  </section>;
}

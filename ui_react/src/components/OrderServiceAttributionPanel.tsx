import { useState } from 'react';
import {
  officialServiceDateCorrectionClient as client,
  type AttributionChange,
  type AttributionPreview,
} from '../api/orders/official_service_date_correction_client';
import type { AssignmentSegment } from '../api/orders/order_query_schemas';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { useStaffIdentityDirectory, useStaffIdentityLabels } from './StaffIdentityProvider';

interface Props {
  caseNo: string;
  segments: AssignmentSegment[];
  onSaved: () => void;
  onBusyChange: (busy: boolean) => void;
  completed?: boolean;
  upcomingOnly?: boolean;
}

export function OrderServiceAttributionPanel({ caseNo, segments, onSaved, onBusyChange, completed = false, upcomingOnly = false }: Props) {
  const directory = useStaffIdentityDirectory();
  const staff = useStaffIdentityLabels();
  const [assignmentId, setAssignmentId] = useState(segments[0]?.assignment_id ?? 0);
  const [staffId, setStaffId] = useState(0);
  const [days, setDays] = useState<string[]>([]);
  const [scope, setScope] = useState<'served' | 'upcoming'>(upcomingOnly ? 'upcoming' : 'served');
  const [replacements, setReplacements] = useState<Record<string, string>>({});
  const [adoptCalculatedAmounts, setAdoptCalculatedAmounts] = useState(false);
  const [evidence, setEvidence] = useState('');
  const [reason, setReason] = useState('');
  const [pending, setPending] = useState<{ change: AttributionChange; preview: AttributionPreview; key: string; reason: string } | null>(null);
  const [applying, setApplying] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const segment = segments.find(item => item.assignment_id === assignmentId);
  const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Taipei' }).format(new Date());
  const availableDays = segment?.official_service_dates.filter(day => scope === 'upcoming' ? day >= today : completed ? day <= today : day < today) ?? [];
  const proposedDays = days.map(day => replacements[day] ?? day);
  const canPreview = staffId > 0 && days.length > 0 && proposedDays.every(Boolean)
    && new Set(proposedDays).size === proposedDays.length && !!evidence.trim() && !!reason.trim();
  async function submit() {
    setBusy(true);
    onBusyChange(true);
    setMessage('');
    let applied = false;
    try {
      if (pending) {
        setApplying(true);
        const receipt = await client.applyAttribution(caseNo, pending.change, pending.preview, pending.reason, pending.key, adoptCalculatedAmounts);
        applied = true;
        const observed = await ordersQueryClient.getAssignmentPlan(caseNo);
        if (observed.scheduling_version !== receipt.scheduling_version || observed.case_no !== caseNo
          || !receipt.effective_assignments.every(saved => observed.assignments.some(item => item.assignment_id === saved.assignment_id
            && item.official_service_dates.join() === saved.service_dates.join()))
          || observed.assignments.length !== pending.preview.proposed_assignments.length
          || !pending.preview.proposed_assignments.every(saved => observed.assignments.some(item => item.staff_id === saved.staff_id
            && item.official_service_dates.join() === saved.service_dates.join()))) {
          throw new Error('班表已提交，尚未確認最新結果。請重新確認原操作。');
        }
        onSaved();
      } else {
        const sourceDates = [...days].sort();
        const change = { source_assignment_id: assignmentId, staff_id: staffId, service_dates: sourceDates,
          replacement_dates: sourceDates.map(day => replacements[day] ?? day), scope, evidence: evidence.trim() };
        const preview = await client.previewAttribution(caseNo, change);
        setAdoptCalculatedAmounts(false);
        setPending({ change, preview, key: crypto.randomUUID(), reason: reason.trim() });
      }
    } catch (error) {
      if (pending && !applied && error instanceof ApiHttpError && error.status >= 400 && error.status < 500) {
        setPending(null);
        setApplying(false);
      }
      setMessage(error instanceof Error ? error.message : '更正未完成，請重新核對。');
    } finally {
      setBusy(false);
      onBusyChange(false);
    }
  }
  return <section className="formal-recommendation-inline-form order-service-attribution-panel" aria-label="多月嫂排班">
    <h3>多月嫂排班</h3>
    {!pending ? <fieldset disabled={busy}>
      {!completed && !upcomingOnly && <label>調整範圍 <select value={scope} onChange={event => {
        setScope(event.target.value === 'upcoming' ? 'upcoming' : 'served'); setDays([]); setReplacements({});
      }}><option value="served">更正已服務紀錄</option><option value="upcoming">調整後續排班</option></select></label>}
      <label>原服務區段 <select value={assignmentId} onChange={event => { setAssignmentId(Number(event.target.value)); setDays([]); setStaffId(0); setReplacements({}); }}>
        {segments.map(item => <option key={item.assignment_id} value={item.assignment_id ?? 0}>{staff.label(item.staff_id)} · {item.assigned_start_date} ～ {item.assigned_end_date}</option>)}
      </select></label>
      <label>{scope === 'upcoming' ? '接任月嫂' : '實際服務月嫂'} <select value={staffId} onChange={event => setStaffId(Number(event.target.value))}>
        <option value={0}>選擇月嫂</option>
        {segment && <option value={segment.staff_id}>沿用 {staff.label(segment.staff_id)}</option>}
        {[...(directory?.people.values() ?? [])].filter(person => person.id !== segment?.staff_id).map(person =>
          <option key={person.id} value={person.id}>{staff.label(person.id)}</option>)}
      </select></label>
      <fieldset><legend>選擇要調整的服務日</legend>
        {availableDays.length > 1 && <button type="button" onClick={() => {
          if (days.length === availableDays.length) { setDays([]); setReplacements({}); }
          else setDays(availableDays);
        }}>{days.length === availableDays.length ? '取消全選' : '選取此區段可調整的日期'}</button>}
        {availableDays.map(day => <div key={day}>
          <label><input type="checkbox" checked={days.includes(day)} onChange={event =>
            setDays(current => event.target.checked ? [...current, day] : current.filter(value => value !== day))} />{day}</label>
          {days.includes(day) && <label>新服務日 {day}<input type="date" value={replacements[day] ?? day}
            onChange={event => setReplacements(current => ({ ...current, [day]: event.target.value }))} /></label>}
        </div>)}
      </fieldset>
      <a href={`#clients?case=${encodeURIComponent(caseNo)}&field=intake&from=workbench`}>變更約定天數、時數或價金</a>
      <label>更正依據 <input maxLength={500} value={evidence} onChange={event => setEvidence(event.target.value)} /></label>
      <label>更正原因 <input maxLength={500} value={reason} onChange={event => setReason(event.target.value)} /></label>
    </fieldset> : <div>
      <h4>核對月嫂款項</h4>
      {pending.preview.proposed_assignments.map((item, index) => <p key={index}>{staff.label(item.staff_id)} · {item.service_dates.length} 日 · {item.service_dates.join('、')}</p>)}
      {pending.preview.staff_entitlements.map(item => <p key={item.staff_id}>{staff.label(item.staff_id)} · 更正後應付 NT$ {item.amount_ntd.toLocaleString('zh-TW')}</p>)}
      {pending.preview.funding.map(item => <p key={`${item.staff_id}:${item.kind}`}>
        {staff.label(item.staff_id)} · {item.kind === 'client' ? '自備款' : item.kind === 'subsidy' ? '補助款' : '未分來源'} ·
        原應付 NT$ {item.before_ntd.toLocaleString('zh-TW')} · 已核銷 {item.settled_ntd === null ? '待核對' : `NT$ ${item.settled_ntd.toLocaleString('zh-TW')}`} ·
        調整後應付 {item.after_ntd === null ? '待核對' : `NT$ ${item.after_ntd.toLocaleString('zh-TW')}`}
      </p>)}
      {pending.preview.funding_review_pending &&
        <p role="status">正式排班可先儲存。受影響的人工分期將列為帳務待核對，待補齊各區段補助金額後再拆付。</p>}
      {!pending.preview.funding_review_pending && pending.preview.paid_obligations.map((item, index) => <p key={index}>{staff.label(item.staff_id)} · 原應付 NT$ {item.before_ntd.toLocaleString('zh-TW')} · 原實付 NT$ {item.paid_ntd.toLocaleString('zh-TW')} · 新增追償 NT$ {item.recovery_increase_ntd.toLocaleString('zh-TW')}</p>)}
      {pending.preview.manual_amounts.map((item, index) => <p key={index}>{staff.label(item.staff_id)} · 原人工金額 NT$ {item.manual_ntd.toLocaleString('zh-TW')} · 原試算 NT$ {item.previous_calculated_ntd.toLocaleString('zh-TW')}</p>)}
      {!pending.preview.funding_review_pending && pending.preview.manual_amounts.length > 0 && <label><input type="checkbox" checked={adoptCalculatedAmounts}
        disabled={busy || applying} onChange={event => setAdoptCalculatedAmounts(event.target.checked)} />採用新計算金額</label>}
      {!applying && <button type="button" disabled={busy} onClick={() => setPending(null)}>返回編輯</button>}
    </div>}
    <button type="button" disabled={busy || (pending
      ? !pending.preview.funding_review_pending && pending.preview.manual_amounts.length > 0 && !adoptCalculatedAmounts : !canPreview)}
      onClick={() => void submit()}>{applying ? '以原操作重新確認' : pending
        ? pending.preview.funding_review_pending ? '儲存排班，帳務待核對' : '確認更正'
        : '預覽帳務影響'}</button>
    {message && <p role="alert">{message}</p>}
  </section>;
}

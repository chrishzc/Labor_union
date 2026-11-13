import { useState } from 'react';
import {
  officialServiceDateCorrectionClient as client,
  type AttributionChange,
  type AttributionMove,
  type AttributionPreview,
} from '../api/orders/official_service_date_correction_client';
import type { AssignmentSegment } from '../api/orders/order_query_schemas';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { useStaffIdentityDirectory, useStaffIdentityLabels } from './StaffIdentityProvider';

import { OrderCaregiverScheduleCalendars } from './OrderCaregiverScheduleCalendars';

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
  const [addedStaff, setAddedStaff] = useState<number[]>([]);
  const [removedBlocks, setRemovedBlocks] = useState<number[]>([]);
  const [overrides, setOverrides] = useState<Record<string, number | null>>({});
  const [scope, setScope] = useState<'served' | 'upcoming'>(upcomingOnly ? 'upcoming' : 'served');
  const [editDates, setEditDates] = useState(false);
  const [replacements, setReplacements] = useState<Record<string, string>>({});
  const [adoptCalculatedAmounts, setAdoptCalculatedAmounts] = useState(false);
  const [evidence, setEvidence] = useState('');
  const [reason, setReason] = useState('');
  const [pending, setPending] = useState<{ change: AttributionChange; preview: AttributionPreview; key: string; reason: string } | null>(null);
  const [applying, setApplying] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Taipei' }).format(new Date());
  const original = new Map(segments.flatMap(segment => segment.official_service_dates.map(date => [date, segment] as const)));
  const availableDays = [...original.keys()].filter(day => scope === 'upcoming' ? day >= today : completed ? day <= today : day < today).sort();
  const blocks = [
    ...segments.flatMap(segment => segment.assignment_id === null || removedBlocks.includes(segment.assignment_id)
      ? [] : [{ key: segment.assignment_id, staffId: segment.staff_id }]),
    ...addedStaff.map(staffId => ({ key: -staffId, staffId })),
  ];
  const byKey = new Map(blocks.map(block => [block.key, block]));
  const allocation: Record<string, number> = {};
  const moves: AttributionMove[] = [];
  for (const day of availableDays) {
    const source = original.get(day)?.assignment_id;
    const key = Object.hasOwn(overrides, day) ? overrides[day] : source;
    if (source == null || key == null) continue;
    const target = byKey.get(key);
    if (!target) continue;
    allocation[day] = key;
    const replacement = editDates ? replacements[day] ?? day : day;
    if (key !== source || replacement !== day) {
      moves.push({ source_assignment_id: source, source_date: day, staff_id: target.staffId,
        replacement_date: replacement, target_assignment_id: key > 0 ? key : null });
    }
  }
  const replacementDates = availableDays.map(day => editDates ? replacements[day] ?? day : day);
  const allDates = [...original.keys()].filter(day => !availableDays.includes(day)).concat(replacementDates);
  const datesValid = replacementDates.every(Boolean) && new Set(allDates).size === allDates.length;
  const canPreview = moves.length > 0 && Object.keys(allocation).length === availableDays.length
    && addedStaff.every(id => Object.values(allocation).includes(-id))
    && datesValid && !!evidence.trim() && !!reason.trim();
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
        const change: AttributionChange = { moves, scope, evidence: evidence.trim() };
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
    {!pending ? <fieldset className="service-attribution-form" disabled={busy}>
      {!completed && !upcomingOnly && <label>調整範圍 <select value={scope} onChange={event => {
        setScope(event.target.value === 'upcoming' ? 'upcoming' : 'served');
        setAddedStaff([]); setRemovedBlocks([]); setOverrides({}); setReplacements({}); setEditDates(false);
      }}><option value="served">更正已服務紀錄</option><option value="upcoming">調整後續排班</option></select></label>}
      <OrderCaregiverScheduleCalendars key={scope} blocks={blocks} dates={availableDays} allocation={allocation}
        onSelect={(day, key) => setOverrides(current => ({ ...current, [day]: allocation[day] === key ? null : key }))}
        management={{
          options: [...(directory?.people.values() ?? [])].map(person => ({ staffId: person.id, name: person.name ?? undefined })),
          limit: 4,
          onAdd: id => {
            const removed = segments.find(segment => segment.staff_id === id && segment.assignment_id !== null
              && removedBlocks.includes(segment.assignment_id));
            if (removed) setRemovedBlocks(current => current.filter(key => key !== removed.assignment_id));
            else setAddedStaff(current => [...current, id]);
          },
          canRemove: key => !Object.values(allocation).includes(key) && (key < 0 ||
            (segments.find(segment => segment.assignment_id === key)?.official_service_dates.every(date => availableDays.includes(date)) ?? false)),
          onRemove: key => {
            if (key < 0) setAddedStaff(current => current.filter(id => id !== -key));
            else setRemovedBlocks(current => [...current, key]);
          },
        }} />
      {availableDays.length > 0 && <label><input type="checkbox" checked={editDates} onChange={event => {
        setEditDates(event.target.checked);
        if (!event.target.checked) setReplacements({});
      }} />調整服務日期</label>}
      {editDates && <div className="service-attribution-fields">
        {availableDays.map(day => <label key={day}>{day} 改至<input type="date" value={replacements[day] ?? day}
          onChange={event => setReplacements(current => ({ ...current, [day]: event.target.value }))} /></label>)}
      </div>}
      {editDates && !datesValid && <p role="status">請填妥改期日期，並排除重複的服務日。</p>}
      <div className="service-attribution-fields">
        <label>調整依據（必填） <input maxLength={500} value={evidence} onChange={event => setEvidence(event.target.value)} /></label>
        <label>調整原因（必填） <input maxLength={500} value={reason} onChange={event => setReason(event.target.value)} /></label>
      </div>
      <a href={`#clients?case=${encodeURIComponent(caseNo)}&field=intake&from=workbench`}>變更約定天數、時數或價金</a>
    </fieldset> : <div>
      <h4>核對逐日排班異動</h4>
      <table className="service-attribution-preview">
        <thead><tr><th scope="col">原排班</th><th scope="col">調整後</th></tr></thead>
        <tbody>{'moves' in pending.change && pending.change.moves.map(move =>
          <tr key={move.source_date}><td>{move.source_date} · {staff.label(original.get(move.source_date)?.staff_id)}</td>
            <td>{move.replacement_date} · {staff.label(move.staff_id)}</td></tr>)}</tbody>
      </table>
      <h4>調整後全案班表</h4>
      {pending.preview.proposed_assignments.map((item, index) => <p key={index}>{staff.label(item.staff_id)} · {item.service_dates.length} 日 · {item.service_dates.join('、')}</p>)}
      <h4>核對月嫂款項</h4>
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
        ? pending.preview.funding_review_pending ? '儲存排班，帳務待核對' : '確認並儲存排班'
        : '預覽排班與帳務'}</button>
    {message && <p role="alert">{message}</p>}
  </section>;
}

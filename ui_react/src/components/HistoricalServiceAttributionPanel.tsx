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
  const [rows, setRows] = useState(() => facts.assignments.map(item => ({ staff_id: item.staff_id, actual_service_days: item.actual_service_days ?? 0 })));
  const [correctServiceFacts, setCorrectServiceFacts] = useState(false);
  const [serviceRows, setServiceRows] = useState(() => facts.assignments.map(item => ({
    enabled: false, assignment_identity: item.assignment_identity, staff_id: item.staff_id,
    actual_start_date: item.service_fact?.actual_start_date ?? item.adopted_start_date ?? '',
    actual_end_date: item.service_fact?.actual_end_date ?? item.adopted_end_date ?? '',
    service_start_time: item.service_fact?.service_start_time ?? '',
    service_end_time: item.service_fact?.service_end_time ?? '',
    service_end_day_offset: item.service_fact?.service_end_day_offset ?? 0,
    service_hours_per_day: item.service_fact?.service_hours_per_day ?? '',
  })));
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
        const command: HistoricalAttributionCommand = { caregivers: correctServiceFacts
          ? rows.filter(item => facts.assignments.some(value => value.staff_id === item.staff_id && value.actual_service_days != null))
          : rows, evidence: evidence.trim(),
          ...(correctServiceFacts ? { service_facts: serviceRows.filter(item => item.enabled).map(({ enabled, ...item }) => {
            void enabled;
            return item;
          }) } : {}),
        };
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
      {facts.lifecycle_status === '歷史訂單－服務完成' && <label><input type="checkbox" checked={correctServiceFacts}
        onChange={event => { setCorrectServiceFacts(event.target.checked); setRows(facts.assignments.map(item => ({ staff_id: item.staff_id, actual_service_days: item.actual_service_days ?? 0 }))); }} />更正已完成服務的實際起訖、時段及每日時數，保留各人天數</label>}
      {rows.map(row => <div key={row.staff_id} className="order-case-action-row">
        <label>{staff.label(row.staff_id, facts.assignments.find(item => item.staff_id === row.staff_id)?.staff_name)} · 服務天數
          <input type="number" min={1} step={1} disabled={correctServiceFacts} value={row.actual_service_days || ''}
            onChange={event => setRows(current => current.map(item => item.staff_id === row.staff_id
              ? { ...item, actual_service_days: Number(event.target.value) } : item))} />
        </label>
        {!originalStaff.has(row.staff_id) && <button type="button" onClick={() => setRows(current => current.filter(item => item.staff_id !== row.staff_id))}>移除</button>}
      </div>)}
      {correctServiceFacts && serviceRows.map(row => <fieldset key={row.assignment_identity}>
        <label><input type="checkbox" checked={row.enabled} onChange={event => setServiceRows(current => current.map(item => item.assignment_identity === row.assignment_identity ? { ...item, enabled: event.target.checked } : item))} />更正 {staff.label(row.staff_id)} 的已確認服務事實</label>
        {row.enabled && <>
          {(['actual_start_date', 'actual_end_date', 'service_start_time', 'service_end_time', 'service_hours_per_day'] as const).map(field => <label key={field}>
            {{ actual_start_date: '實際開始日', actual_end_date: '實際結束日', service_start_time: '開始時間', service_end_time: '結束時間', service_hours_per_day: '每日時數' }[field]}
            <input type={field.includes('date') ? 'date' : field.includes('time') ? 'time' : 'number'} min={field === 'service_hours_per_day' ? 0.5 : undefined} max={field === 'service_hours_per_day' ? 24 : undefined} step={field === 'service_hours_per_day' ? 0.5 : undefined} value={row[field]}
              onChange={event => setServiceRows(current => current.map(item => item.assignment_identity === row.assignment_identity ? { ...item, [field]: event.target.value } : item))} />
          </label>)}
          <label><input type="checkbox" checked={row.service_end_day_offset === 1} onChange={event => setServiceRows(current => current.map(item => item.assignment_identity === row.assignment_identity ? { ...item, service_end_day_offset: event.target.checked ? 1 : 0 } : item))} />結束時間為隔日</label>
        </>}
      </fieldset>)}
      {!correctServiceFacts && <><label>新增月嫂 <select value={nextStaff} onChange={event => setNextStaff(Number(event.target.value))}>
        <option value={0}>選擇月嫂</option>
        {[...(directory?.people.values() ?? [])].filter(person => !rows.some(item => item.staff_id === person.id))
          .map(person => <option key={person.id} value={person.id}>{staff.label(person.id)}</option>)}
      </select></label>
      <button type="button" disabled={!nextStaff || rows.length >= 20} onClick={() => {
        setRows(current => [...current, { staff_id: nextStaff, actual_service_days: 0 }]); setNextStaff(0);
      }}>加入月嫂</button></>}
      <label>天數證據 <input maxLength={500} value={evidence} onChange={event => setEvidence(event.target.value)} /></label>
      <label>更正原因 <input maxLength={500} value={reason} onChange={event => setReason(event.target.value)} /></label>
    </fieldset> : <>
      <h4>核對月嫂應付</h4>
      {pending.preview.service_facts.map(item => <p key={item.assignment_identity}>{staff.label(item.after.staff_id)} · 原服務事實 {item.before ? `${item.before.actual_start_date} 至 ${item.before.actual_end_date}，${item.before.service_start_time} 至 ${item.before.service_end_time}，每日 ${item.before.service_hours_per_day} 小時` : '原逐人時段及時數尚未確認'}；更正為 {item.after.actual_start_date} 至 {item.after.actual_end_date}，{item.after.service_start_time} 至 {item.after.service_end_time}{item.after.service_end_day_offset ? ' 隔日' : ''}，每日 {item.after.service_hours_per_day} 小時。</p>)}
      {pending.command.service_facts?.length ? <p>客戶應收差額 NT$ {pending.preview.client_delta_ntd === null ? '待核對' : pending.preview.client_delta_ntd.toLocaleString('zh-TW')}；補助差額 NT$ {pending.preview.subsidy_delta_ntd === null ? '待核對' : pending.preview.subsidy_delta_ntd.toLocaleString('zh-TW')}。{pending.preview.accounting_pending.length > 0 && `待核對：${pending.preview.accounting_pending.join('、')}`}</p> : null}
      {pending.preview.caregivers.map(item => <p key={item.staff_id}>{staff.label(item.staff_id)} · {item.actual_service_days === null ? '服務天數待核對' : `${item.actual_service_days} 日`} · {pending.preview.accounting_pending.length ? '試算' : '應付'} {item.entitlement_ntd === null ? '待核對原應付' : `NT$ ${item.entitlement_ntd.toLocaleString('zh-TW')}`}{item.delta_ntd !== undefined && item.delta_ntd !== null ? `，差額 NT$ ${item.delta_ntd.toLocaleString('zh-TW')}` : ''}</p>)}
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
    <button type="button" disabled={busy || (!!pending?.preview.manual_amounts.length && !adoptCalculatedAmounts) || (!pending && (rows.length < (correctServiceFacts ? 1 : 2) || (correctServiceFacts && !serviceRows.some(item => item.enabled)) || (!correctServiceFacts && rows.some(item => !Number.isInteger(item.actual_service_days) || item.actual_service_days < 1)) || !reason.trim() || !evidence.trim()))}
      onClick={() => void submit()}>{submitted ? '以原操作重新確認' : pending ? '確認更正' : '預覽帳務影響'}</button>
    {error && <p role="alert">{error}</p>}
  </section>;
}

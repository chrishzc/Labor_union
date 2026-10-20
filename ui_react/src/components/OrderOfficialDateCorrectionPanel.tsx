import { useUnsavedDraft } from './UnsavedChanges';
import { useRef as useValidationRef } from 'react';
import { useSaveValidation } from './useSaveValidation';
import { useStaffIdentityLabels } from './StaffIdentityProvider';
import { useEffect, useRef, useState, type FC } from 'react';
import {
  officialServiceDateCorrectionClient,
  type OfficialDatePreview,
  type OfficialDateQuery,
  type OfficialDateSelection,
} from '../api/orders/official_service_date_correction_client';
import { OrderServiceDateCalendar } from './OrderServiceDateCalendar';

interface Props {
  caseNo: string;
  revision?: number;
  onObserved?: () => void;
  onBusyChange?: (busy: boolean) => void;
  view?: 'dates' | 'arrangement';
  onOpenArrangement?: () => void;
  onOpenDates?: () => void;
}

export const OrderOfficialDateCorrectionPanel: FC<Props> = ({ caseNo, revision, onObserved, onBusyChange, view, onOpenArrangement, onOpenDates }) => {
  const staffIdentity = useStaffIdentityLabels();
  const [facts, setFacts] = useState<OfficialDateQuery | null>(null);
  const [selections, setSelections] = useState<OfficialDateSelection[]>([]);
  const [preview, setPreview] = useState<OfficialDatePreview | null>(null);
  const [reason, setReason] = useState('');
  const saveValidation = useSaveValidation();
  const saveFieldRef = useValidationRef<HTMLInputElement>(null);
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [reload, setReload] = useState(0);
  const [activeAssignmentId, setActiveAssignmentId] = useState<number | null>(null);
  const [month, setMonth] = useState('');
  const [localView, setLocalView] = useState<'dates' | 'arrangement'>('dates');
  const observedSave = useRef<{ caseNo: string; revision: number | undefined } | null>(null);
  const datesView = (view ?? localView) === 'dates';
  useEffect(() => { onBusyChange?.(busy); }, [busy, onBusyChange]);

  useEffect(() => {
    let active = true;
    setFacts(null);
    setPreview(null);
    setKey('');
    setReason('');
    if (observedSave.current?.caseNo !== caseNo || observedSave.current.revision === revision) setMessage('');
    observedSave.current = null;
    void officialServiceDateCorrectionClient.query(caseNo).then((result) => {
      if (!active) return;
      setFacts(result);
      setActiveAssignmentId(result.assignments[0]?.assignment_id ?? null);
      setMonth(result.assignments[0]?.service_dates[0]?.slice(0, 7) ?? '');
      setSelections(result.assignments.map((item) => ({
        assignment_id: item.assignment_id,
        service_dates: [...item.service_dates],
      })));
    }).catch((error: unknown) => {
      if (active) setMessage(error instanceof Error ? error.message : '排班讀取失敗');
    });
    return () => { active = false; };
  }, [caseNo, revision, reload]);

  const activeAssignment = facts?.assignments.find(item => item.assignment_id === activeAssignmentId);
  const activeDates = selections.find(item => item.assignment_id === activeAssignmentId)?.service_dates ?? [];
  const countsValid = Boolean(facts?.assignments.length) && facts!.assignments.every(original =>
    selections.find(item => item.assignment_id === original.assignment_id)?.service_dates.length === original.service_dates.length);
  const blocked = !facts || facts.order_status !== '訂單完成' || facts.monetary_change_blocker;
  const changeDate = (date: string) => {
    setSelections(current => current.map(item => item.assignment_id === activeAssignmentId
      ? { ...item, service_dates: item.service_dates.includes(date) ? item.service_dates.filter(day => day !== date) : [...item.service_dates, date].sort() }
      : item));
    setPreview(null);
    setKey('');
    setMessage('');
  };

  const createPreview = async () => {
    setBusy(true);
    setMessage('');
    try {
      const result = await officialServiceDateCorrectionClient.preview(caseNo, selections.map((item) => ({
        ...item,
        service_dates: [...item.service_dates].sort(),
      })));
      setPreview(result);
      setKey(crypto.randomUUID());
      setLocalView('arrangement');
      onOpenArrangement?.();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '更正預覽失敗');
    } finally {
      setBusy(false);
    }
  };

  const apply = async () => {
    if (!preview || !key || busy) return;
    if (!saveValidation.validate([{ value: reason, label: '更正原因', ref: saveFieldRef }])) return;
    setBusy(true);
    setMessage('');
    try {
      const receipt = await officialServiceDateCorrectionClient.apply(caseNo, preview, reason.trim(), key);
      const fresh = await officialServiceDateCorrectionClient.query(caseNo);
      const observed = new Map(fresh.assignments.map((item) => [item.assignment_id, [...item.service_dates].sort()]));
      const expected = new Map(receipt.effective_assignments.map((item) => [item.assignment_id, [...item.service_dates].sort()]));
      if (fresh.generation_id !== receipt.generation_id || observed.size !== expected.size ||
        [...expected].some(([assignmentId, dates]) => JSON.stringify(observed.get(assignmentId)) !== JSON.stringify(dates))) {
        throw new Error('提交後排班回讀不一致，請重新查詢');
      }
      setFacts(fresh);
      setSelections(fresh.assignments.map((item) => ({ assignment_id: item.assignment_id, service_dates: [...item.service_dates] })));
      setPreview(null);
      setKey('');
      setActiveAssignmentId(fresh.assignments[0]?.assignment_id ?? null);
      setMonth(fresh.assignments[0]?.service_dates[0]?.slice(0, 7) ?? '');
      setLocalView('dates');
      onOpenDates?.();
      setMessage('排班日期已更正；重新查詢週報即可看到新週的服務工時。');
      observedSave.current = { caseNo, revision };
      onObserved?.();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '更正提交或回讀失敗；請重新查詢');
    } finally {
      setBusy(false);
    }
  };
  useUnsavedDraft('正式服務日期修正', { '服務日期選擇': selections, '修正原因': reason }, { enabled: !!facts, resetKey: facts, busy });


  return <section className="order-service-dates-panel" aria-label={`案件 ${caseNo} 排班日期更正`}>
    <div className="service-date-heading"><p className="service-date-instruction">請在原有月曆調整已完成的服務日期。更正會保留原完工紀錄，並更新有效排班與週報。</p></div>
    {!facts && !message && <p role="status">正在讀取完工服務日期…</p>}
    {facts?.order_status !== '訂單完成' && facts && <p role="status">目前案件尚未完成，不能使用完工後日期更正。</p>}
    {facts?.monetary_change_blocker && <p role="status">{facts.monetary_blockers.map(blocker => <span key={blocker.code}>
      {blocker.message}{' '}<a href={blocker.repair_target === 'case_profile'
        ? `#clients?case=${encodeURIComponent(caseNo)}&from=workbench`
        : `#finance?tab=${blocker.repair_target === 'subsidy' ? 'subsidy-advance' : 'client-receipts'}&case_no=${encodeURIComponent(caseNo)}&from=workbench`}>
        {blocker.repair_target === 'case_profile' ? '核對案件服務與費用資料 →' : blocker.repair_target === 'subsidy' ? '核對本案補助明細 →' : '核對本案月嫂應付款 →'}
      </a><br />
    </span>)}<button type="button" disabled={busy} onClick={() => setReload(value => value + 1)}>重新讀取排班日期</button></p>}
    {facts && datesView && <>
      {facts.assignments.length > 1 && <label>服務月嫂與分段<select aria-label="服務月嫂與分段" disabled={busy} value={activeAssignmentId ?? ''} onChange={event => {
        const assignmentId = Number(event.target.value);
        setActiveAssignmentId(assignmentId);
        setMonth(selections.find(item => item.assignment_id === assignmentId)?.service_dates[0]?.slice(0, 7)
          ?? facts.assignments.find(item => item.assignment_id === assignmentId)!.service_dates[0].slice(0, 7));
      }}>{facts.assignments.map((item, index) => ({ item, index })).sort((a, b) => staffIdentity.compare(a.item.staff_id, b.item.staff_id)).map(({ item, index }) => <option key={item.assignment_id} value={item.assignment_id}>{staffIdentity.label(item.staff_id, item.staff_name)}（第 {index + 1} 段）</option>)}</select></label>}
      <dl className="service-date-summary-strip" aria-label="此次選定服務日期摘要" aria-live="polite">
        <div><dt>服務開始</dt><dd>{activeDates[0] ?? '尚未選取'}</dd></div>
        <div><dt>最後服務日</dt><dd>{activeDates.at(-1) ?? '尚未選取'}</dd></div>
        <div><dt>服務天數</dt><dd>{activeDates.length} / {activeAssignment?.service_dates.length ?? 0} 天</dd></div>
      </dl>
      {month && <OrderServiceDateCalendar month={month} onMonthChange={setMonth} selectedDates={activeDates}
        isDateDisabled={() => busy || blocked} onToggle={changeDate}
        hint={`${activeAssignment ? staffIdentity.label(activeAssignment.staff_id, activeAssignment.staff_name) : ''}：點選日期可取消或補選，需保留原本 ${activeAssignment?.service_dates.length ?? 0} 天。`} />}
      <div className="service-date-footer"><small>{countsValid ? '原紀錄會保留；預覽通過後仍需填寫更正原因並確認儲存。' : '每段服務天數必須與原紀錄相同，請在月曆取消或補選日期。'}</small>
        <button type="button" className="order-v2-open-drawer service-date-primary" disabled={busy || blocked || !countsValid} onClick={() => void createPreview()}>預覽更正</button>
      </div>
    </>}
    {facts && !datesView && !preview && <div className="service-date-footer"><p role="status">請先在「設定服務日期」核對月曆並預覽更正，再確認儲存。</p>
      <button type="button" disabled={busy} onClick={() => { setLocalView('dates'); onOpenDates?.(); }}>返回設定服務日期</button>
    </div>}
    {preview && !datesView && <>
      {preview.proposed_assignments.map(item => <p key={item.assignment_id}>{staffIdentity.label(facts?.assignments.find(original => original.assignment_id === item.assignment_id)?.staff_id, facts?.assignments.find(original => original.assignment_id === item.assignment_id)?.staff_name)}：{item.service_dates.join('、')}</p>)}
      <p>客戶與月嫂金額義務：維持原狀。</p>
      <><label>更正原因<input ref={saveFieldRef} aria-required="true" value={reason} maxLength={500} disabled={busy} onChange={event => setReason(event.target.value)} /></label>{saveValidation.feedback}</>
      <div className="service-date-footer">
        <button type="button" disabled={busy} onClick={() => { setLocalView('dates'); onOpenDates?.(); }}>返回設定服務日期</button>
        <button type="button" className="order-v2-open-drawer service-date-primary" disabled={busy} onClick={() => void apply()}>確認更正完工服務日期</button>
      </div>
    </>}
    {message && <div><p role="status">{message}</p><button type="button" disabled={busy} onClick={() => { setLocalView('dates'); onOpenDates?.(); setReload(value => value + 1); }}>重新讀取排班日期</button><p>重新讀取會還原尚未儲存的日期。</p></div>}
  </section>;
};

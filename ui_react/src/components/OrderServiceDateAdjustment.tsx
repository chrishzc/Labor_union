import { useRef, useState } from 'react';
import { applyServiceDateAdjustment, previewServiceDateAdjustment } from '../api/orders/order_mutation_client';
import type {
  ServiceDateAdjustmentPayload, ServiceDateAdjustmentPreview, ServiceDateAdjustmentQuery, ServiceDateConfirmationQueryView,
} from '../api/orders/order_mutation_schemas';
import { coordinatedServiceTime, OrderServiceDateCalendar } from './OrderServiceDateCalendar';
import { useUnsavedDraft } from './UnsavedChanges';

interface Props {
  caseNo: string;
  query: ServiceDateAdjustmentQuery;
  initialDates?: readonly string[];
  onCancel: () => void;
  onBusyChange?: (busy: boolean) => void;
  onSaved: (observation: ServiceDateAdjustmentObservation) => Promise<void>;
}

type Operation = 'merge' | 'split';
type Submission = { payload: ServiceDateAdjustmentPayload; preview: ServiceDateAdjustmentPreview; key: string };
type Day = ServiceDateAdjustmentQuery['days'][number];
export type ServiceDateAdjustmentObservation = {
  preview: ServiceDateAdjustmentPreview;
  receipt: Awaited<ReturnType<typeof applyServiceDateAdjustment>>;
};

export function assertServiceDateAdjustmentObserved(
  caseNo: string, query: ServiceDateConfirmationQueryView, { preview, receipt }: ServiceDateAdjustmentObservation,
) {
  const days = new Map(query.date_adjustment?.days.map(day => [day.service_date, day]));
  const insertedDates = new Set(preview.inserted.map(day => day.service_date));
  if (query.case_no !== caseNo || query.order_version !== preview.order_version
    || query.scheduling_version !== receipt.scheduling_version || query.current_version !== receipt.confirmed_version
    || !query.date_adjustment || preview.inserted.some(expected => {
      const current = days.get(expected.service_date);
      return !current || current.staff_id !== expected.staff_id || current.hours_override !== expected.hours_override
        || current.service_hours !== expected.service_hours;
    }) || preview.removed.some(day => !insertedDates.has(day.service_date) && days.has(day.service_date))) {
    throw new Error('正式讀回的版本或服務日期與本次調整不一致。');
  }
}

export function OrderServiceDateAdjustment({ caseNo, query, initialDates, onCancel, onBusyChange, onSaved }: Props) {
  const [operation, setOperation] = useState<Operation>('merge');
  const [sources, setSources] = useState<string[]>([]);
  const [firstTarget, setFirstTarget] = useState({ service_date: '', staff_id: 0 });
  const [secondTarget, setSecondTarget] = useState({ service_date: '', staff_id: 0 });
  const [month, setMonth] = useState(query.days[0]?.service_date.slice(0, 7) ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [rearrange, setRearrange] = useState(false);
  const [observation, setObservation] = useState<ServiceDateAdjustmentObservation | null>(null);
  const pending = useRef<Submission | null>(null);
  const sourceLimit = operation === 'merge' ? 2 : 1;
  const expectedHours = operation === 'merge' ? 4 : 8;
  const targetRows = operation === 'merge' ? [firstTarget] : [firstTarget, secondTarget];
  const reverse = !rearrange && query.pairs.find(pair => pair.inserted.length === sourceLimit
    && sources.some(source => pair.inserted.some(day => day.service_date === source)));
  const selected = reverse ? reverse.inserted.map(day => day.service_date) : sources;
  const staffName = (day: Day) => query.staff.find(staff => staff.staff_id === day.staff_id)?.staff_name ?? '尚未指定';
  const ready = Boolean(reverse) || (
    sources.length === sourceLimit
    && targetRows.every(target => target.service_date && target.staff_id > 0)
    && new Set(targetRows.map(target => target.service_date)).size === targetRows.length
  );
  useUnsavedDraft('服務日期調整', { '來源日期': sources, '目標安排': targetRows }, { busy });

  const resetSubmission = () => {
    pending.current = null;
    setError('');
  };

  const chooseOperation = (value: Operation) => {
    setOperation(value);
    setRearrange(false);
    setSources([]);
    setFirstTarget({ service_date: '', staff_id: 0 });
    setSecondTarget({ service_date: '', staff_id: 0 });
    resetSubmission();
  };

  const sourceAllowed = (day: string) => query.days.some(value =>
    value.service_date === day && value.service_hours === expectedHours);

  const selectSource = (day: string) => {
    resetSubmission();
    setSources(current => {
      if (selected.includes(day)) return reverse ? [] : current.filter(value => value !== day);
      if (rearrange) return [...current.slice(Math.max(0, current.length - sourceLimit + 1)), day];
      const isReverseDay = query.pairs.some(pair => pair.inserted.length === sourceLimit
        && pair.inserted.some(value => value.service_date === day));
      if (reverse || isReverseDay || sourceLimit === 1) return [day];
      return [...current.slice(-(sourceLimit - 1)), day];
    });
  };

  const save = async () => {
    if ((!ready && observation === null) || busy) return;
    setBusy(true);
    onBusyChange?.(true);
    setError('');
    let acknowledged = observation;
    try {
      if (acknowledged === null) {
        let submission = pending.current;
        if (!submission) {
          const payload = {
            source_dates: sources, targets: reverse ? [] : targetRows, reverse_receipt_id: reverse ? reverse.receipt_id : null,
            ...(initialDates ? { initial_dates: [...initialDates] } : {}),
          };
          const preview = await previewServiceDateAdjustment(caseNo, payload);
          submission = { payload, preview, key: crypto.randomUUID() };
          pending.current = submission;
        }
        const receipt = await applyServiceDateAdjustment(caseNo, submission.payload, submission.preview, submission.key);
        acknowledged = { preview: submission.preview, receipt };
        setObservation(acknowledged);
      }
      await onSaved(acknowledged);
    } catch (cause) {
      const detail = cause instanceof Error ? cause.message : '服務日期調整失敗。';
      setError(acknowledged ? `已收到調整回執 #${acknowledged.receipt.receipt_id}。${detail}請重新讀取調整結果。` : detail);
    } finally {
      setBusy(false);
      onBusyChange?.(false);
    }
  };

  return <fieldset aria-label="合併或分裂日期" disabled={busy}>
    <legend>合併或分裂日期</legend>
    <fieldset disabled={observation !== null}>
    <button type="button" aria-pressed={operation === 'merge'} onClick={() => chooseOperation('merge')}>合併日期</button>
    <button type="button" aria-pressed={operation === 'split'} onClick={() => chooseOperation('split')}>分裂日期</button>
    <p>{operation === 'merge' ? '選取兩個各 4 小時的服務日。' : '選取一個 8 小時的服務日。'}</p>
    {month && <OrderServiceDateCalendar month={month} onMonthChange={setMonth} selectedDates={selected}
      isDateDisabled={day => !sourceAllowed(day)} onToggle={selectSource} showHolidays={false}
      dayDetails={date => {
        const day = query.days.find(value => value.service_date === date);
        return day ? { annotation: `${staffName(day)}・${day.service_hours} 小時${day.hours_override ? `・${coordinatedServiceTime}` : ''}` } : {};
      }} />}
    {reverse
      ? <section aria-label="復原原來的服務日期">
        <h4>將恢復的服務日期</h4>
        <ul>{reverse.removed.map(day => <li key={day.service_date}>
          {day.service_date}・{staffName(day)}・{day.service_hours} 小時
          {day.hours_override ? `・${coordinatedServiceTime}` : ''}
        </li>)}</ul>
        <button type="button" onClick={() => { setRearrange(true); resetSubmission(); }}>改為指定新日期</button>
      </section>
      : targetRows.map((target, index) => {
        const setTarget = index === 0 ? setFirstTarget : setSecondTarget;
        return <div key={index}>
          <label>目標日期 {index + 1}
            <input type="date" value={target.service_date} onChange={event => {
              const serviceDate = event.target.value;
              setTarget(current => ({ ...current, service_date: serviceDate }));
              resetSubmission();
            }} />
          </label>
          <label>月嫂 {index + 1}
            <select value={target.staff_id || ''} onChange={event => {
              const staffId = Number(event.target.value);
              setTarget(current => ({ ...current, staff_id: staffId }));
              resetSubmission();
            }}>
              <option value="">請選擇本案月嫂</option>
              {query.staff.map(staff => <option key={staff.staff_id} value={staff.staff_id}>{staff.staff_name}</option>)}
            </select>
          </label>
        </div>;
      })}
    </fieldset>
    {error && <p role="alert">{error}</p>}
    <button type="button" onClick={onCancel}>{observation ? '關閉日期調整' : '取消日期調整'}</button>
    <button type="button" disabled={!ready && observation === null} onClick={() => void save()}>
      {observation ? '重新讀取調整結果' : busy ? '儲存中…' : '儲存日期調整'}
    </button>
  </fieldset>;
}

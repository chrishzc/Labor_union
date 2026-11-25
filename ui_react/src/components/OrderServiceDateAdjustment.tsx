import { useRef, useState } from 'react';
import { applyServiceDateAdjustment, previewServiceDateAdjustment } from '../api/orders/order_mutation_client';
import type {
  ServiceDateAdjustmentPayload, ServiceDateAdjustmentPreview, ServiceDateAdjustmentQuery, ServiceDateConfirmationQueryView,
} from '../api/orders/order_mutation_schemas';
import { coordinatedServiceTime, OrderServiceDateCalendar } from './OrderServiceDateCalendar';
import { useUnsavedDraft } from './UnsavedChanges';
import './OrderServiceDateAdjustment.css';
import { HolidayRepricingResults } from './HolidayRepricingResults';

interface Props {
  caseNo: string;
  query: ServiceDateAdjustmentQuery;
  initialDates?: readonly string[];
  onCancel: () => void;
  onBusyChange?: (busy: boolean) => void;
  onSaved: (observation: ServiceDateAdjustmentObservation) => Promise<void>;
}

type Operation = 'merge' | 'split';
const operationLabels: Record<Operation, string> = {
  merge: '合併日期 4+4→8',
  split: '分裂日期 8→4+4',
};

type Submission = { payload: ServiceDateAdjustmentPayload; preview: ServiceDateAdjustmentPreview; key: string };
type Day = ServiceDateAdjustmentQuery['days'][number];
export type ServiceDateAdjustmentObservation = {
  preview: ServiceDateAdjustmentPreview;
  receipt: Awaited<ReturnType<typeof applyServiceDateAdjustment>>;
};

export function assertServiceDateAdjustmentObserved(
  caseNo: string, query: ServiceDateConfirmationQueryView, { preview, receipt }: ServiceDateAdjustmentObservation,
) {
  const expectedOrderVersion = preview.order_version + (receipt.scheduling_version - preview.scheduling_version);
  const days = new Map(query.date_adjustment?.days.map(day => [day.service_date, day]));
  const insertedDates = new Set(preview.inserted.map(day => day.service_date));
  if (query.case_no !== caseNo || query.order_version !== expectedOrderVersion
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
  const availableMerge = query.days.filter(day => day.service_hours === 4).length >= 2;
  const availableSplit = query.days.some(day => day.service_hours === 8);
  const [requestedOperation, setRequestedOperation] = useState<Operation>(availableSplit && !availableMerge ? 'split' : 'merge');
  const operation = availableMerge && availableSplit ? requestedOperation
    : availableMerge ? 'merge' : availableSplit ? 'split' : null;
  const [sources, setSources] = useState<string[]>([]);
  const [firstTarget, setFirstTarget] = useState({ service_date: '', staff_id: 0 });
  const [secondTarget, setSecondTarget] = useState({ service_date: '', staff_id: 0 });
  const [viewedMonth, setViewedMonth] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [rearrange, setRearrange] = useState(false);
  const [observation, setObservation] = useState<ServiceDateAdjustmentObservation | null>(null);
  const pending = useRef<Submission | null>(null);
  if (operation && operation !== requestedOperation && !busy && observation === null) {
    setRequestedOperation(operation);
    setRearrange(false);
    setSources([]);
    setFirstTarget({ service_date: '', staff_id: 0 });
    setSecondTarget({ service_date: '', staff_id: 0 });
    setViewedMonth('');
    setError('');
  }

  const merging = operation === 'merge';
  const sourceLimit = merging ? 2 : 1;
  const eligibleDays = operation ? query.days.filter(day => day.service_hours === (merging ? 4 : 8)) : [];
  const sourceAllowed = (date: string) => eligibleDays.some(day => day.service_date === date);
  const currentSources = sources.filter(sourceAllowed);
  const month = viewedMonth || eligibleDays[0]?.service_date.slice(0, 7);
  const targetRows = merging ? [firstTarget] : [firstTarget, secondTarget];
  const reverse = !rearrange && query.pairs.find(pair => pair.inserted.length === sourceLimit
    && currentSources.some(source => pair.inserted.some(day => day.service_date === source)));
  const selected = reverse ? reverse.inserted.map(day => day.service_date) : currentSources;
  const sourceComplete = selected.length === sourceLimit;
  const staffName = (day: Day) => query.staff.find(staff => staff.staff_id === day.staff_id)?.staff_name ?? '尚未指定';
  const ready = Boolean(reverse) || (
    sourceComplete
    && targetRows.every(target => target.service_date && target.staff_id > 0)
    && new Set(targetRows.map(target => target.service_date)).size === targetRows.length
  );
  useUnsavedDraft('服務日期調整', { '來源日期': sources, '目標安排': targetRows }, { busy });

  const resetSubmission = () => {
    pending.current = null;
    setError('');
  };

  const chooseOperation = (value: Operation) => {
    setRequestedOperation(value);
    setRearrange(false);
    setSources([]);
    setFirstTarget({ service_date: '', staff_id: 0 });
    setSecondTarget({ service_date: '', staff_id: 0 });
    resetSubmission();
  };

  const selectSource = (day: string) => {
    resetSubmission();
    setSources(current => {
      const eligible = current.filter(sourceAllowed);
      if (selected.includes(day)) return reverse ? [] : eligible.filter(value => value !== day);
      if (rearrange) return [...eligible.slice(Math.max(0, eligible.length - sourceLimit + 1)), day];
      const isReverseDay = query.pairs.some(pair => pair.inserted.length === sourceLimit
        && pair.inserted.some(value => value.service_date === day));
      if (reverse || isReverseDay || sourceLimit === 1) return [day];
      return [...eligible.slice(-(sourceLimit - 1)), day];
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
            source_dates: currentSources, targets: reverse ? [] : targetRows, reverse_receipt_id: reverse ? reverse.receipt_id : null,
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

  return <fieldset className="service-date-adjustment" aria-label="合併或分裂日期" disabled={busy}>
    <header className="service-date-adjustment-header">
      <div>
        <h3>{operation ? (merging ? '合併服務日期' : '分裂服務日期') : '調整服務日期'}</h3>
        {operation && <p>選擇服務日期並安排調整後的日期</p>}
      </div>
      <button type="button" className="service-date-adjustment-cancel" onClick={onCancel}>
        {observation ? '關閉日期調整' : '取消調整'}
      </button>
    </header>
    {operation ? <fieldset className="service-date-adjustment-editor" disabled={observation !== null}>
      <div className="service-date-adjustment-modes">
        {availableMerge && availableSplit ? (['merge', 'split'] as const).map(mode =>
          <button type="button" key={mode} aria-pressed={operation === mode} onClick={() => chooseOperation(mode)}>
            {operationLabels[mode]}
          </button>
        ) : <span>{operationLabels[operation]}</span>}
      </div>
      <div className="service-date-adjustment-steps">
        <section className="service-date-adjustment-step">
          <div className="service-date-adjustment-step-header">
            <span className="service-date-adjustment-step-number" aria-hidden="true">1</span>
            <div>
              <h4>{merging ? '選擇要合併的日期' : '選擇要分裂的日期'}</h4>
              <p>{merging ? '在月曆點選 2 個各 4 小時的服務日' : '在月曆點選 1 個 8 小時的服務日'}</p>
            </div>
          </div>
          {month && <OrderServiceDateCalendar month={month} onMonthChange={setViewedMonth} selectedDates={selected}
            isDateDisabled={day => !sourceAllowed(day)} onToggle={selectSource} showHolidays={false}
            dayDetails={date => {
              const day = query.days.find(value => value.service_date === date);
              return day ? { annotation: `${staffName(day)}・${day.service_hours} 小時` } : {};
            }} />}
          <div className="service-date-adjustment-selection">
            <strong aria-live="polite">已選 {selected.length}/{sourceLimit}</strong>
            {selected.map(date => <span key={date}>
              <time dateTime={date}>{date.replaceAll('-', '/')}</time>
              <button type="button" aria-label={`移除 ${date}`} onClick={() => selectSource(date)}>×</button>
            </span>)}
          </div>
        </section>
        <section className="service-date-adjustment-step">
          <div className="service-date-adjustment-step-header">
            <span className="service-date-adjustment-step-number" aria-hidden="true">2</span>
            <div>
              <h4>選擇要套用的日期</h4>
              <p>{merging ? '合併後安排為 1 天 8 小時，請選擇日期與 1 位月嫂' : '分裂後安排為 2 天各 4 小時，請選擇各日日期與月嫂'}</p>
            </div>
          </div>
          <div className="service-date-adjustment-targets">
            {!sourceComplete && <p className="service-date-adjustment-notice">請先完成步驟1的日期選擇。</p>}
            {reverse
              ? <section className="service-date-adjustment-restore" aria-label="復原原來的服務日期">
                <h5>將恢復的服務日期</h5>
                <ul>{reverse.removed.map(day => <li key={day.service_date}>
                  {day.service_date}・{staffName(day)}・{day.service_hours} 小時
                  {day.hours_override ? `・${coordinatedServiceTime}` : ''}
                </li>)}</ul>
                <button type="button" onClick={() => { setRearrange(true); resetSubmission(); }}>改為指定新日期</button>
              </section>
              : <>
                {targetRows.map((target, index) => {
                  const setTarget = index === 0 ? setFirstTarget : setSecondTarget;
                  const targetDay = `第${index + 1}天`;
                  return <div className="service-date-adjustment-target-row" key={index}>
                    <label>{merging ? '套用日期' : targetDay}
                      <input type="date" aria-label={merging ? undefined : `${targetDay}日期`} value={target.service_date}
                        onChange={event => {
                          const serviceDate = event.target.value;
                          setTarget(current => ({ ...current, service_date: serviceDate }));
                          resetSubmission();
                        }} />
                    </label>
                    <label>服務月嫂
                      <select aria-label={merging ? '服務月嫂' : `${targetDay}服務月嫂`} value={target.staff_id || ''}
                        onChange={event => {
                          const staffId = Number(event.target.value);
                          setTarget(current => ({ ...current, staff_id: staffId }));
                          resetSubmission();
                        }}>
                        <option value="">請選擇本案月嫂</option>
                        {query.staff.map(staff => <option key={staff.staff_id} value={staff.staff_id}>{staff.staff_name}</option>)}
                      </select>
                    </label>
                    <span className="service-date-adjustment-target-hours">{merging ? 8 : 4} 小時</span>
                  </div>;
                })}
                <p className="service-date-adjustment-coordination">{coordinatedServiceTime}</p>
              </>}
          </div>
        </section>
      </div>
    </fieldset> : !observation && <p className="service-date-adjustment-empty">
      目前沒有可合併的 4 小時日期或可分裂的 8 小時日期。
    </p>}
    {observation?.receipt.case_result && <HolidayRepricingResults results={[observation.receipt.case_result]} />}
    {error && <p role="alert">{error}</p>}
    {(operation || observation) && <div className="service-date-adjustment-footer">
      <button type="button" disabled={!ready && observation === null} onClick={() => void save()}>
        {observation ? '重新讀取調整結果' : busy ? '儲存中…' : '儲存日期調整'}
      </button>
    </div>}
  </fieldset>;
}

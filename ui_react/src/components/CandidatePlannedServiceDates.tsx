import { useEffect, useRef, useState } from 'react';
import { ordersQueryClient } from '../api/orders/order_query_client';
import type { OrderTerms, OrderCalendarDetail } from '../api/orders/order_query_schemas';
import { ordersMutationClient } from '../api/orders/order_mutation_client';
import type { ServiceDateConfirmationQueryView } from '../api/orders/order_mutation_schemas';
import { candidateContactPoolClient, type CandidateWeeklyServicePreview } from '../api/scheduling/candidate_contact_pool_client';
import { schedulePrecisionClient } from '../api/scheduling/schedule_precision_client';
import { applyServiceDatesFlow, previewServiceDatesFlow, selectServiceDates, updateServiceDatesReason, retryServiceDatesApplyFlow, retryServiceDatesObservationFlow } from '../adapters/orders/order_mutation_adapter';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';

const WEEKDAYS = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日'];
const PENDING = new Set(['outcome_unknown', 'observation_failed', 'apply_pending', 'receipt_received', 'requery_loading']);
const sameDates = (a: string[], b: string[]) => a.length === b.length && a.every((value, index) => value === b[index]);
const message = (error: unknown) => error instanceof Error ? error.message : '預計日期操作失敗，請重新讀取。';

/** Only dates enter the existing Orders writer; weekday choices stay in this view. */
export function CandidatePlannedServiceDates({ caseNo, candidateId, startDate, onPreview }: {
  caseNo: string; candidateId: number; startDate: string;
  onPreview: (preview: CandidateWeeklyServicePreview | null) => void;
}) {
  const [facts, setFacts] = useState<{ terms: OrderTerms; mode: OrderCalendarDetail; dates: ServiceDateConfirmationQueryView } | null>(null);
  const [weekdays, setWeekdays] = useState<number[] | null>(null);
  const [dates, setDates] = useState<string[]>([]);
  const [busy, setBusy] = useState<'load' | 'calculate' | 'save' | null>('load');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [, refreshRecovery] = useState(0);
  const sequence = useRef(0);
  const saving = useRef(false);
  const identity = `${caseNo}:${candidateId}`;
  const currentIdentity = useRef(identity);
  currentIdentity.current = identity;
  const draft = orderMutationFlowStore.getServiceDatesDraft(caseNo);
  const unresolved = draft !== undefined && PENDING.has(draft.status);
  const formal = (facts?.terms.assignments?.length ?? 0) > 0 || (facts?.terms.scheduling_generation ?? 0) > 0;

  useEffect(() => {
    currentIdentity.current = identity;
    const controller = new AbortController();
    sequence.current += 1;
    setFacts(null); setWeekdays(null); setDates([]); setError(null); setSuccess(null); setBusy('load'); onPreview(null);
    const unsubscribe = orderMutationFlowStore.subscribe(() => refreshRecovery(value => value + 1));
    void Promise.all([
      ordersQueryClient.getOrderTerms(caseNo, { signal: controller.signal }),
      ordersQueryClient.getOrderCalendarDetail(caseNo, { signal: controller.signal }),
      ordersMutationClient.getServiceDates(caseNo, { signal: controller.signal }),
      candidateContactPoolClient.previewWeeklyService(caseNo, candidateId, { signal: controller.signal }),
    ]).then(([terms, mode, saved, preview]) => {
      if (controller.signal.aborted) return;
      if ([terms.case_no, mode.case_no, saved.case_no].some(value => value !== caseNo)
        || terms.order_version !== saved.order_version || terms.scheduling_version !== saved.scheduling_version) {
        throw new Error('案件資料版本不同，請重新開啟每週服務時間說明。');
      }
      setFacts({ terms, mode, dates: saved }); setDates(saved.current_dates); onPreview(preview);
    }).catch(reason => { if (!controller.signal.aborted) setError(message(reason)); })
      .finally(() => { if (!controller.signal.aborted) setBusy(null); });
    return () => { controller.abort(); currentIdentity.current = ''; sequence.current += 1; unsubscribe(); };
  }, [caseNo, candidateId, onPreview, identity]);

  const recalculate = async (next: number[]) => {
    if (!facts || saving.current || unresolved || formal) return;
    const request = ++sequence.current;
    const active = () => currentIdentity.current === identity && sequence.current === request;
    setWeekdays(next); setDates([]); setError(null); setSuccess(null); onPreview(null);
    if (next.length === 7) { setBusy(null); setError('請至少保留一天可服務的星期。'); return; }
    setBusy('calculate');
    try {
      const result = await schedulePrecisionClient.calculate({
        case_no: caseNo, actual_start_date: startDate,
        target_service_days: facts.dates.contracted_service_days,
        service_mode: facts.mode.original_service_type ?? facts.mode.service_mode ?? '人工排休',
        custom_rest_weekdays: next,
      });
      if (!active()) return;
      const proposed = result.day_by_day.filter(day => day.is_work_day).map(day => day.date);
      if (result.actual_start_date !== startDate || result.target_service_days !== facts.dates.contracted_service_days
        || proposed.length !== facts.dates.contracted_service_days
        || proposed.some(value => !facts.dates.selectable_dates.includes(value))) {
        throw new Error('試算日期與案件天數或可選範圍不同，尚未保存。');
      }
      const preview = await candidateContactPoolClient.previewWeeklyService(caseNo, candidateId, { serviceDates: proposed });
      if (!active()) return;
      setDates(proposed); onPreview(preview);
    } catch (reason) { if (active()) setError(message(reason)); }
    finally { if (active()) setBusy(null); }
  };

  const save = async (recovery?: 'apply' | 'observe') => {
    if (!facts || saving.current || formal || (!recovery && (busy || unresolved || dates.length === 0))) return;
    saving.current = true; setBusy('save'); setError(null); setSuccess(null);
    const intended = recovery ? [...(draft?.receiptView?.service_dates ?? draft?.selectedDates ?? [])] : [...dates];
    try {
      if (recovery === 'apply') await retryServiceDatesApplyFlow(caseNo);
      else if (recovery === 'observe') await retryServiceDatesObservationFlow(caseNo);
      else {
        const fresh = await ordersMutationClient.getServiceDates(caseNo);
        if (currentIdentity.current !== identity) return;
        if (fresh.order_version !== facts.dates.order_version || fresh.scheduling_version !== facts.dates.scheduling_version
          || fresh.current_version !== facts.dates.current_version) throw new Error('案件日期已被更新，請重新開啟後再保存。');
        orderMutationFlowStore.resetServiceDatesDraft(caseNo);
        orderMutationFlowStore.setServiceDatesQueryReady(caseNo, fresh);
        selectServiceDates(caseNo, intended); updateServiceDatesReason(caseNo, '保存每週服務時間說明的預計日期');
        const preview = await previewServiceDatesFlow(caseNo);
        if (currentIdentity.current !== identity) return;
        if (preview.order_version !== fresh.order_version || preview.scheduling_version !== fresh.scheduling_version
          || preview.current_version !== fresh.current_version || !sameDates(preview.service_dates, intended)) {
          throw new Error('預計日期版本已變更，請重新開啟後再保存。');
        }
        await applyServiceDatesFlow(caseNo);
      }
      const observed = orderMutationFlowStore.getServiceDatesDraft(caseNo);
      const saved = observed?.queryView;
      if (!saved || saved.current_version !== observed.receiptView?.confirmed_version || !sameDates(saved.current_dates, intended)) {
        throw new Error('保存回讀與這次日期不同，請至服務安排讀取目前結果。');
      }
      if (currentIdentity.current !== identity) return;
      setFacts({ ...facts, dates: saved }); setDates(saved.current_dates);
      setSuccess('預計日期已保存，後續寄送將使用這份日期。');
      const preview = await candidateContactPoolClient.previewWeeklyService(caseNo, candidateId);
      if (currentIdentity.current === identity) onPreview(preview);
    } catch (reason) { if (currentIdentity.current === identity) setError(message(reason)); }
    finally { saving.current = false; if (currentIdentity.current === identity) setBusy(null); }
  };

  return <section aria-label="預計服務日期設定">
    <p>原始匯入服務方式：<strong aria-label="原始匯入服務方式">{facts?.mode.original_service_type ?? facts?.mode.service_mode ?? '尚未提供'}</strong></p>
    <fieldset disabled={!facts || busy === 'save' || busy === 'load' || unresolved || formal} aria-label="人工選定休假星期">
      <legend>人工選定休假星期</legend>
      {WEEKDAYS.map((label, value) => <label key={value}><input type="checkbox" checked={weekdays?.includes(value) ?? false}
        onChange={event => void recalculate(event.target.checked ? [...(weekdays ?? []), value].sort() : (weekdays ?? []).filter(day => day !== value))} />{label}</label>)}
      <button type="button" onClick={() => void recalculate([])}>無固定週休</button>
    </fieldset>
    <p>勾選後立即試算；保存預計日期後供後續寄送使用，星期選項不保存。</p>
    {busy === 'load' && <p role="status">正在讀取預計日期…</p>}
    {formal && <p role="status">目前已有正式安排，請到服務安排調整日期。</p>}
    {busy === 'calculate' && <p role="status">正在重算每週服務時間…</p>}
    {error && <p role="alert">{error}</p>}
    {success && <p role="status">{success}</p>}
    {dates.length > 0 && <details><summary>預計服務日期：{dates.length} 天（{dates[0]}～{dates.at(-1)}）</summary><p>{dates.join('、')}</p></details>}
    {unresolved && <p role="status">保存結果尚未完成回讀，請先接續原操作。</p>}
    {draft?.status === 'outcome_unknown' && <button type="button" disabled={busy !== null} onClick={() => void save('apply')}>接續保存預計日期</button>}
    {draft?.status === 'observation_failed' && <button type="button" disabled={busy !== null} onClick={() => void save('observe')}>重新取得保存結果</button>}
    <button type="button" disabled={!facts || busy !== null || unresolved || formal || !dates.length || sameDates(dates, facts.dates.current_dates)} onClick={() => void save()}>保存預計日期</button>
  </section>;
}

import { useEffect, useRef, useState, useSyncExternalStore, type FC } from 'react';
import { ordersQueryClient } from '../api/orders/order_query_client';
import type { ActualStart } from '../api/orders/order_query_schemas';
import { orderActualStartClient, type ActualStartPreview } from '../api/orders/order_actual_start_client';
import { OrderMutationError } from '../api/orders/order_mutation_errors';
import { ApiHttpError } from '../api/shared/typed_errors';
import { orderMutationFlowStore, type ActualStartCommand } from '../adapters/orders/order_mutation_flow_store';

interface Props {
  caseNo: string;
  onObserved?: (operation: 'date_only' | 'reschedule') => void;
  onBusyChange?: (busy: boolean) => void;
  onOpenServiceDates?: () => void;
}
type Phase = 'idle' | 'loading' | 'previewing' | 'applying' | 'outcome_unknown' | 'observation_failed' | 'observed';
const subscribeActualStart = (listener: () => void) => orderMutationFlowStore.subscribe(listener);
const actualStartErrorMessage = (caught: unknown, fallback: string) => {
  if (caught instanceof OrderMutationError) {
    const fields = caught.fieldErrors.map((item) => item.field).join('、');
    const suffix = fields ? `${caught.code}：${fields}` : caught.code;
    return `${caught.message}（${suffix}）`;
  }
  if (caught instanceof ApiHttpError) {
    return `${caught.message}（${caught.code}）`;
  }
  return caught instanceof Error ? caught.message : fallback;
};

export const OrderActualStartPanel: FC<Props> = ({ caseNo, onObserved, onBusyChange, onOpenServiceDates }) => {
  const [query, setQuery] = useState<ActualStart | null>(null);
  const [date, setDate] = useState('');
  const [preview, setPreview] = useState<ActualStartPreview | null>(null);
  const [phase, setPhase] = useState<Phase>('idle');
  const [error, setError] = useState<string | null>(null);
  const [missingAssignments, setMissingAssignments] = useState(false);
  const flow = useSyncExternalStore(subscribeActualStart, () => orderMutationFlowStore.getActualStart(caseNo));
  const inFlight = useRef(new Set<string>());
  const sequence = useRef(0);
  const observationSequence = useRef(0);
  const mounted = useRef(true);
  const activeCaseNo = useRef(caseNo);
  const flowPhase = flow?.status;
  const unresolved = flowPhase === 'applying' || flowPhase === 'outcome_unknown' || flowPhase === 'observation_failed' || flowPhase === 'observing'
    || phase === 'applying' || phase === 'outcome_unknown' || phase === 'observation_failed';
  const busy = unresolved || phase === 'loading' || phase === 'previewing';
  useEffect(() => { onBusyChange?.(unresolved); }, [unresolved, onBusyChange]);
  useEffect(() => {
    const previousCaseNo = activeCaseNo.current;
    if (previousCaseNo !== caseNo) {
      observationSequence.current += 1;
      inFlight.current.delete(previousCaseNo);
      const saved = orderMutationFlowStore.getActualStart(previousCaseNo);
      if (saved?.status === 'observing' && saved.receipt) {
        orderMutationFlowStore.setActualStart(previousCaseNo, {
          ...saved, status: 'observation_failed', error: '實際開始日回讀尚未完成，請只重新讀取結果。',
        });
      }
    }
    activeCaseNo.current = caseNo;
    sequence.current += 1;
    setQuery(null); setDate(''); setPreview(null); setPhase('idle'); setError(null); setMissingAssignments(false);
  }, [caseNo]);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      sequence.current += 1;
      observationSequence.current += 1;
      const saved = orderMutationFlowStore.getActualStart(activeCaseNo.current);
      if (saved?.status === 'observing' && saved.receipt) {
        orderMutationFlowStore.setActualStart(activeCaseNo.current, {
          ...saved, status: 'observation_failed', error: '實際開始日回讀尚未完成，請只重新讀取結果。',
        });
      }
      onBusyChange?.(false);
    };
  }, [onBusyChange]);
  const isActive = (request: number, requestCaseNo: string) => mounted.current && activeCaseNo.current === requestCaseNo && sequence.current === request;

  const load = async () => {
    if (unresolved) return;
    if (flow?.status === 'observed') orderMutationFlowStore.clearActualStart(caseNo);
    const request = ++sequence.current;
    setPhase('loading'); setError(null); setPreview(null); setMissingAssignments(false);
    try {
      const data = await ordersQueryClient.getActualStart(caseNo);
      if (data.case_no !== caseNo) throw new Error('實際開始日查詢案件識別不一致。');
      if (!isActive(request, caseNo)) return;
      setQuery(data); setDate(data.current_actual_start_date ?? data.planned_start_date); setPhase('idle');
    } catch (caught) {
      if (isActive(request, caseNo)) { setQuery(null); setError(caught instanceof Error ? caught.message : '實際開始日查詢失敗。'); setPhase('idle'); }
    }
  };

  const confirm = async () => {
    if (!query || query.service_data_locked || busy) return;
    if (orderMutationFlowStore.getActualStart(caseNo)?.status === 'observed') {
      orderMutationFlowStore.clearActualStart(caseNo);
    }
    const request = ++sequence.current;
    setPhase('previewing'); setPreview(null); setError(null); setMissingAssignments(false);
    try {
      const data = await orderActualStartClient.preview(caseNo, { new_actual_start_date: date });
      const previewCaseNo = data.operation === 'date_only' ? data.case_no : data.actual_start.case_no;
      if (previewCaseNo !== caseNo || data.after_actual_start_date !== date) throw new Error('實際開始日預覽 identity 不一致。');
      if (!isActive(request, caseNo)) return;
      if (data.operation === 'reschedule') {
        setPreview(data);
        setPhase('idle');
        return;
      }
      await execute({
        payload: {
          operation: 'date_only',
          new_actual_start_date: data.after_actual_start_date,
          expected_order_version: data.order_version,
          preview_fingerprint: data.preview_fingerprint,
        },
        idempotencyKey: `beta-actual-start-${crypto.randomUUID()}`,
      }, request, false);
    } catch (caught) {
      if (isActive(request, caseNo)) {
        const missingAssignments = (caught instanceof OrderMutationError || caught instanceof ApiHttpError)
          && caught.code === 'scheduling_assignments_required';
        setMissingAssignments(missingAssignments);
        setError(missingAssignments
          ? '目前缺少可接續的正式或歷史服務安排，本次未變更日期。請回服務日期入口輸入此次開始日並核對；歷史案件若仍缺少既定人員或排休資料，須先補齊該項資料。'
          : actualStartErrorMessage(caught, '實際開始日確認失敗。'));
        setPhase('idle');
      }
    }
  };

  const observe = async (command: ActualStartCommand, request: number) => {
    const observation = ++observationSequence.current;
    const saved = orderMutationFlowStore.getActualStart(caseNo);
    const receipt = saved?.receipt;
    if (!saved || !receipt || receipt.case_no !== caseNo || receipt.preview_fingerprint !== command.payload.preview_fingerprint) {
      throw new Error('實際開始日收據 identity 不一致，已停止操作。');
    }
    orderMutationFlowStore.setActualStart(caseNo, { ...saved, status: 'observing', error: null });
    let data: ActualStart;
    try {
      data = await ordersQueryClient.getActualStart(caseNo);
    } catch (caught) {
      if (observation !== observationSequence.current) return;
      throw caught;
    }
    if (observation !== observationSequence.current) return;
    const schedulingNotObserved = receipt.operation === 'reschedule'
      && (data.scheduling_version === null || data.scheduling_version < receipt.scheduling_version);
    if (data.case_no !== caseNo || data.current_actual_start_date !== command.payload.new_actual_start_date
      || data.order_version < receipt.order_version || schedulingNotObserved) {
      throw new Error('實際開始日已回傳收據，但正式回讀尚未觀察到該版本與日期。');
    }
    orderMutationFlowStore.setActualStart(caseNo, { ...saved, status: 'observed', error: null });
    if (!isActive(request, caseNo)) return;
    setQuery(data); setDate(data.current_actual_start_date ?? data.planned_start_date);
    setPreview(null); setPhase('observed');
    onBusyChange?.(false); onObserved?.(receipt.operation);
  };

  const execute = async (command: ActualStartCommand, request: number, recoveringUnknown: boolean) => {
    if (inFlight.current.has(caseNo)) return;
    inFlight.current.add(caseNo);
    setPhase('applying'); setError(null); onBusyChange?.(true);
    orderMutationFlowStore.setActualStart(caseNo, { status: 'applying', command, receipt: null, error: null });
    try {
      const receipt = await orderActualStartClient.apply(caseNo, command.payload, { idempotencyKey: command.idempotencyKey });
      orderMutationFlowStore.setActualStart(caseNo, { status: 'observation_failed', command, receipt, error: null });
    } catch (caught) {
      const rejected = (caught instanceof ApiHttpError || caught instanceof OrderMutationError)
        && caught.status >= 400 && caught.status < 500 && caught.status !== 408 && caught.status !== 429;
      if (rejected && !recoveringUnknown) {
        orderMutationFlowStore.clearActualStart(caseNo);
        if (isActive(request, caseNo)) {
          setPreview(null); setQuery(null); setPhase('idle'); onBusyChange?.(false);
          setError(`實際開始日未通過檢查，請重新讀取並預覽：${actualStartErrorMessage(caught, caught.message)}`);
        }
      } else {
        orderMutationFlowStore.setActualStart(caseNo, { status: 'outcome_unknown', command, receipt: null,
          error: recoveringUnknown
            ? '實際開始日結果仍未確認；請恢復權限後以原操作重新確認。'
            : `實際開始日套用結果未明；保留原操作，只能使用相同內容與原冪等鍵重新確認：${caught instanceof Error ? caught.message : '未知錯誤'}` });
        if (isActive(request, caseNo)) {
          setPhase('outcome_unknown');
          setError(recoveringUnknown
            ? '實際開始日結果仍未確認；請恢復權限後以原操作重新確認。'
            : `實際開始日套用結果未明；保留原操作，只能使用相同內容與原冪等鍵重新確認：${caught instanceof Error ? caught.message : '未知錯誤'}`);
        }
      }
      inFlight.current.delete(caseNo);
      return;
    }
    try {
      await observe(command, request);
    } catch (caught) {
      const saved = orderMutationFlowStore.getActualStart(caseNo);
      if (saved?.status === 'observing' && saved.receipt) {
        orderMutationFlowStore.setActualStart(caseNo, { ...saved, status: 'observation_failed', error: caught instanceof Error ? caught.message : '實際開始日回讀失敗。' });
      }
      if (isActive(request, caseNo)) { setPhase('observation_failed'); setError(caught instanceof Error ? caught.message : '實際開始日回讀失敗。'); }
    } finally { inFlight.current.delete(caseNo); }
  };

  const applyPreview = async () => {
    if (!preview || preview.operation !== 'reschedule' || preview.after_actual_start_date !== date || busy) return;
    const request = ++sequence.current;
    setPreview(null);
    await execute({
      payload: {
        operation: 'reschedule',
        new_actual_start_date: preview.after_actual_start_date,
        expected_order_version: preview.order_version,
        expected_scheduling_version: preview.scheduling_version,
        preview_fingerprint: preview.preview_fingerprint,
        reason: preview.before_actual_start_date === null
          ? `確認實際開始日：${preview.after_actual_start_date}`
          : `更正實際開始日：${preview.before_actual_start_date} → ${preview.after_actual_start_date}`,
      },
      idempotencyKey: `beta-actual-start-${crypto.randomUUID()}`,
    }, request, false);
  };

  const retryApply = async () => {
    const existing = orderMutationFlowStore.getActualStart(caseNo);
    if (existing?.status !== 'outcome_unknown' || existing.command === null || existing.receipt) return;
    if (existing.command.payload.operation === 'date_only') {
      let data: ActualStart;
      try {
        data = await ordersQueryClient.getActualStart(caseNo);
      } catch (caught) {
        setError(`實際開始日結果仍未確認，請稍後重新讀取：${caught instanceof Error ? caught.message : '未知錯誤'}`);
        return;
      }
      if (data.current_actual_start_date === existing.command.payload.new_actual_start_date
        && data.order_version > existing.command.payload.expected_order_version) {
        orderMutationFlowStore.setActualStart(caseNo, { ...existing, status: 'observed', error: null });
        setQuery(data); setDate(data.current_actual_start_date); setPhase('observed'); setError(null);
        onBusyChange?.(false); onObserved?.('date_only');
        return;
      }
      if (data.order_version !== existing.command.payload.expected_order_version) {
        setError('實際開始日結果與原操作不同，請重新讀取後確認。');
        return;
      }
    }
    await execute(existing.command, sequence.current, true);
  };

  const retryObservation = async () => {
    const current = orderMutationFlowStore.getActualStart(caseNo);
    if (inFlight.current.has(caseNo) || current?.status !== 'observation_failed' || !current.receipt) return;
    inFlight.current.add(caseNo);
    const request = sequence.current;
    setPhase('applying'); setError(null);
    try { await observe(current.command, request); }
    catch (caught) {
      const saved = orderMutationFlowStore.getActualStart(caseNo);
      if (saved?.status === 'observing' && saved.receipt) {
        orderMutationFlowStore.setActualStart(caseNo, { ...saved, status: 'observation_failed', error: caught instanceof Error ? caught.message : '實際開始日回讀失敗。' });
      }
      if (isActive(request, caseNo)) { setPhase('observation_failed'); setError(caught instanceof Error ? caught.message : '實際開始日回讀失敗。'); }
    }
    finally { inFlight.current.delete(caseNo); }
  };

  return (
    <section aria-label={`案件 ${caseNo} 實際開始日`}>
      <h4>確認／更正實際開始日</h4>
      <p>尚未正式排班時只保存日期；已有正式安排時才由後端預覽並重排服務日期及必要下游影響。</p>
      <button type="button" disabled={busy} onClick={() => void load()}>讀取實際開始日</button>
      {phase === 'loading' && <p role="status">讀取實際開始日中…</p>}
      {query && (
        <>
          <p>目前實際開始：{query.current_actual_start_date ?? '尚未確認'}；計畫開始：{query.planned_start_date}</p>
          {query.service_data_locked && <p role="status">服務資料已鎖定，不可修改實際開始日。</p>}
          <label>實際開始日期
            <input aria-label="Beta 實際開始日期" type="date" value={date} disabled={busy || query.service_data_locked}
              onChange={(event) => { sequence.current += 1; setDate(event.target.value); setPreview(null); setError(null); setMissingAssignments(false); setPhase('idle'); }} />
          </label>
          <button type="button" disabled={busy || query.service_data_locked || !date} onClick={() => void confirm()}>
            {query.has_formal_assignments ? '預覽新排班' : '確認實際開始日'}
          </button>
        </>
      )}
      {preview && (
        <>
          <p>實際開始：{preview.before_actual_start_date ?? '未確認'} → {preview.after_actual_start_date}</p>
          {preview.operation === 'date_only'
            ? <p>目前尚無正式排班；本次只保存日期，不建立排班、帳務、薪資或服務完成資料。</p>
            : <>
              <p>以下為尚未儲存的新排班，請逐段核對後再確認。</p>
              <ol>
                {preview.scheduling.assignments.map((assignment) => (
                  <li key={assignment.candidate_key}>
                    月嫂 {assignment.staff_id}：占用 {assignment.assigned_start_date} 至 {assignment.assigned_end_date}；
                    服務日 {assignment.service_dates.join('、')}
                  </li>
                ))}
              </ol>
              <p>正式結束：{preview.actual_end_date}；狀態：{preview.lifecycle_impact.before_status} → {preview.lifecycle_impact.after_status}</p>
              <button type="button" disabled={busy} onClick={() => void applyPreview()}>確認並儲存新排班</button>
              <button type="button" disabled={busy} onClick={() => setPreview(null)}>取消本次預覽</button>
            </>}
        </>
      )}
      {phase === 'previewing' && <p role="status">正在確認實際開始日…</p>}
      {(flowPhase === 'applying' || flowPhase === 'observing' || phase === 'applying') && <p role="status">實際開始日套用／回讀中…</p>}
      {(flowPhase === 'outcome_unknown' || phase === 'outcome_unknown') && <button type="button" onClick={() => void retryApply()}>以原操作重新確認實際開始日</button>}
      {(flowPhase === 'observation_failed' || phase === 'observation_failed') && <button type="button" onClick={() => void retryObservation()}>只重新讀取實際開始日結果</button>}
      {(flowPhase === 'observed' || phase === 'observed') && <p role="status">實際開始日已完成正式回讀{query?.current_actual_start_date ? `：${query.current_actual_start_date}` : '。'}</p>}
      {(flow?.error ?? error) && <p role="alert">{flow?.error ?? error}</p>}
      {missingAssignments && onOpenServiceDates && (
        <button type="button" onClick={onOpenServiceDates}>前往精算並確認服務日期</button>
      )}
    </section>
  );
};

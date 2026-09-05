import { useEffect, useRef, useState, type FC } from 'react';
import { ordersQueryClient } from '../api/orders/order_query_client';
import type { ActualStart } from '../api/orders/order_query_schemas';
import { orderActualStartClient, type ActualStartApplyPayload, type ActualStartPreview, type ActualStartReceipt } from '../api/orders/order_actual_start_client';
import { OrderMutationError } from '../api/orders/order_mutation_errors';
import { ApiHttpError } from '../api/shared/typed_errors';

interface Props { caseNo: string; onObserved?: () => void; onBusyChange?: (busy: boolean) => void }
type Attempt = { payload: ActualStartApplyPayload; idempotencyKey: string; receipt: ActualStartReceipt | null };
type Phase = 'idle' | 'loading' | 'previewing' | 'applying' | 'outcome_unknown' | 'observation_failed' | 'observed';

export const OrderActualStartPanel: FC<Props> = ({ caseNo, onObserved, onBusyChange }) => {
  const [query, setQuery] = useState<ActualStart | null>(null);
  const [date, setDate] = useState('');
  const [reason, setReason] = useState('');
  const [preview, setPreview] = useState<ActualStartPreview | null>(null);
  const [phase, setPhase] = useState<Phase>('idle');
  const [error, setError] = useState<string | null>(null);
  const attempt = useRef<Attempt | null>(null);
  const inFlight = useRef(false);
  const sequence = useRef(0);
  const unresolved = phase === 'applying' || phase === 'outcome_unknown' || phase === 'observation_failed';
  const busy = unresolved || phase === 'loading' || phase === 'previewing';
  useEffect(() => { onBusyChange?.(unresolved); }, [unresolved, onBusyChange]);
  useEffect(() => () => { sequence.current += 1; onBusyChange?.(false); }, [onBusyChange]);

  const load = async () => {
    if (inFlight.current || unresolved) return;
    const request = ++sequence.current;
    setPhase('loading'); setError(null); setPreview(null);
    try {
      const data = await ordersQueryClient.getActualStart(caseNo);
      if (data.case_no !== caseNo) throw new Error('實際開始日查詢案件識別不一致。');
      if (sequence.current !== request) return;
      setQuery(data); setDate(data.current_actual_start_date ?? data.planned_start_date); setPhase('idle');
    } catch (caught) {
      if (sequence.current === request) { setQuery(null); setError(caught instanceof Error ? caught.message : '實際開始日查詢失敗。'); setPhase('idle'); }
    }
  };

  const check = async () => {
    if (!query || query.service_data_locked || busy || inFlight.current) return;
    const request = ++sequence.current;
    setPhase('previewing'); setPreview(null); setError(null);
    try {
      const data = await orderActualStartClient.preview(caseNo, { new_actual_start_date: date });
      if (data.actual_start.case_no !== caseNo || data.after_actual_start_date !== date) throw new Error('實際開始日預覽 identity 不一致。');
      if (sequence.current === request) { setPreview(data); setPhase('idle'); }
    } catch (caught) {
      if (sequence.current === request) { setError(caught instanceof Error ? caught.message : '實際開始日預覽失敗。'); setPhase('idle'); }
    }
  };

  const observe = async (saved: Attempt, request: number) => {
    const receipt = saved.receipt;
    if (!receipt || receipt.case_no !== caseNo || receipt.preview_fingerprint !== saved.payload.preview_fingerprint) {
      throw new Error('實際開始日收據 identity 不一致，已停止操作。');
    }
    const data = await ordersQueryClient.getActualStart(caseNo);
    if (data.case_no !== caseNo || data.current_actual_start_date !== saved.payload.new_actual_start_date
      || data.order_version < receipt.order_version || data.scheduling_version < receipt.scheduling_version) {
      throw new Error('實際開始日已回傳收據，但正式回讀尚未觀察到該版本與日期。');
    }
    if (sequence.current !== request) return;
    setQuery(data); setDate(data.current_actual_start_date ?? data.planned_start_date);
    setPreview(null); setReason(''); setPhase('observed'); attempt.current = null;
    onBusyChange?.(false); onObserved?.();
  };

  const apply = async (retry = false) => {
    if (inFlight.current) return;
    if (!retry && (!preview || !query || query.service_data_locked || !reason.trim() || busy
      || preview.client_finance_impact.blockers.length > 0 || preview.payroll_impact.blockers.length > 0)) return;
    if (retry && phase !== 'outcome_unknown') return;
    const saved = attempt.current ?? (preview ? {
      payload: {
        new_actual_start_date: preview.after_actual_start_date,
        expected_order_version: preview.order_version,
        expected_scheduling_version: preview.scheduling_version,
        expected_client_finance_version: preview.client_finance_version,
        expected_payroll_version: preview.payroll_version,
        preview_fingerprint: preview.preview_fingerprint,
        reason: reason.trim(),
      },
      idempotencyKey: `beta-actual-start-${crypto.randomUUID()}`,
      receipt: null,
    } : null);
    if (!saved) return;
    attempt.current = saved;
    inFlight.current = true;
    const request = sequence.current;
    setPhase('applying'); setError(null); onBusyChange?.(true);
    try {
      saved.receipt = await orderActualStartClient.apply(caseNo, saved.payload, { idempotencyKey: saved.idempotencyKey });
    } catch (caught) {
      if (sequence.current === request) {
        const rejected = (caught instanceof ApiHttpError || caught instanceof OrderMutationError)
          && caught.status >= 400 && caught.status < 500 && caught.status !== 408 && caught.status !== 429;
        if (rejected) {
          attempt.current = null; setPreview(null); setQuery(null); setPhase('idle'); onBusyChange?.(false);
          setError(`實際開始日未通過檢查，請重新讀取並預覽：${caught.message}`);
        } else {
          setPhase('outcome_unknown');
          setError('實際開始日套用結果未明；保留原操作，只能使用相同內容與原冪等鍵重新確認。');
        }
      }
      inFlight.current = false;
      return;
    }
    try {
      await observe(saved, request);
    } catch (caught) {
      if (sequence.current === request) { setPhase('observation_failed'); setError(caught instanceof Error ? caught.message : '實際開始日回讀失敗。'); }
    } finally { inFlight.current = false; }
  };

  const retryObservation = async () => {
    if (inFlight.current || phase !== 'observation_failed' || !attempt.current?.receipt) return;
    inFlight.current = true;
    const request = sequence.current;
    setPhase('applying'); setError(null);
    try { await observe(attempt.current, request); }
    catch (caught) { if (sequence.current === request) { setPhase('observation_failed'); setError(caught instanceof Error ? caught.message : '實際開始日回讀失敗。'); } }
    finally { inFlight.current = false; }
  };

  return (
    <section aria-label={`案件 ${caseNo} 實際開始日`}>
      <h4>確認／更正實際開始日</h4>
      <p>與正式服務日期確認分開；日期位移、排班、帳務及薪資影響以後端預覽為準。</p>
      <button type="button" disabled={busy} onClick={() => void load()}>讀取實際開始日</button>
      {phase === 'loading' && <p role="status">讀取實際開始日中…</p>}
      {query && (
        <>
          <p>目前實際開始：{query.current_actual_start_date ?? '尚未確認'}；計畫開始：{query.planned_start_date}</p>
          {query.service_data_locked && <p role="status">服務資料已鎖定，不可修改實際開始日。</p>}
          <label>實際開始日期
            <input aria-label="Beta 實際開始日期" type="date" value={date} disabled={busy || query.service_data_locked}
              onChange={(event) => { setDate(event.target.value); setPreview(null); setError(null); setPhase('idle'); }} />
          </label>
          <button type="button" disabled={busy || query.service_data_locked || !date} onClick={() => void check()}>檢查實際開始日影響</button>
        </>
      )}
      {preview && (
        <>
          <p>實際開始：{preview.before_actual_start_date ?? '未確認'} → {preview.after_actual_start_date}</p>
          <p>正式服務日：{preview.actual_start.official_service_dates.join('、')}</p>
          <p>正式結束：{preview.actual_end_date}；狀態：{preview.lifecycle_impact.before_status} → {preview.lifecycle_impact.after_status}</p>
          <section aria-label="實際開始日帳務與薪資影響">
            {preview.client_finance_impact.actions.map((action, index) => <p key={`client-${index}`}>客戶 {action.payment_stage}：{action.direction} NT$ {action.direction_amount_ntd}</p>)}
            {preview.payroll_impact.actions.map((action, index) => <p key={`staff-${index}`}>月嫂 #{action.staff_id}：{action.direction} NT$ {action.amount.amount}</p>)}
            {[...preview.client_finance_impact.blockers, ...preview.payroll_impact.blockers].map((blocker, index) => <p role="alert" key={index}>{blocker}</p>)}
          </section>
          <label>實際開始日變更原因
            <textarea aria-label="Beta 實際開始日變更原因" value={reason} maxLength={500} disabled={busy} onChange={(event) => setReason(event.target.value)} />
          </label>
          <button type="button" disabled={busy || !reason.trim() || preview.client_finance_impact.blockers.length > 0 || preview.payroll_impact.blockers.length > 0}
            onClick={() => void apply()}>確認實際開始日</button>
        </>
      )}
      {phase === 'previewing' && <p role="status">檢查實際開始日影響中…</p>}
      {phase === 'applying' && <p role="status">實際開始日套用／回讀中…</p>}
      {phase === 'outcome_unknown' && <button type="button" onClick={() => void apply(true)}>以原操作重新確認實際開始日</button>}
      {phase === 'observation_failed' && <button type="button" onClick={() => void retryObservation()}>只重新讀取實際開始日結果</button>}
      {phase === 'observed' && <p role="status">實際開始日已完成正式回讀：{query?.current_actual_start_date}</p>}
      {error && <p role="alert">{error}</p>}
    </section>
  );
};

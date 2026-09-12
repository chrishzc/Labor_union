import { useEffect, useRef, useState, useSyncExternalStore, type FC } from 'react';
import { orderCancellationClient, type OrderCancellationPreview, type OrderCancellationQuery,
  type ServiceDay } from '../api/orders/order_cancellation_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { orderMutationFlowStore, type CancellationCommand } from '../adapters/orders/order_mutation_flow_store';
import { sessionClient } from '../api/auth/session_client';

interface Props { caseNo: string; onObserved?: () => void; onBusyChange?: (busy: boolean) => void }
type DayDraft = { service_date: string; staff_id: string; reason: string };
type Phase = 'idle' | 'loading' | 'previewing' | 'applying' | 'outcome_unknown' | 'observation_failed' | 'observed';
const drafts = (days: ServiceDay[]): DayDraft[] => days.map((day) => ({ service_date: day.service_date, staff_id: String(day.staff_id), reason: day.reason ?? '' }));
const subscribeCancellation = (listener: () => void) => orderMutationFlowStore.subscribe(listener);

export const OrderCancellationPanel: FC<Props> = ({ caseNo, onObserved, onBusyChange }) => {
  const [query, setQuery] = useState<OrderCancellationQuery | null>(null);
  const [days, setDays] = useState<DayDraft[]>([]);
  const [reason, setReason] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [preview, setPreview] = useState<OrderCancellationPreview | null>(null);
  const [phase, setPhase] = useState<Phase>('idle');
  const [error, setError] = useState<string | null>(null);
  const flow = useSyncExternalStore(subscribeCancellation, () => orderMutationFlowStore.getCancellation(caseNo));
  const inFlight = useRef(new Set<string>());
  const sequence = useRef(0);
  const mounted = useRef(true);
  const activeCaseNo = useRef(caseNo);
  const queryController = useRef<AbortController | null>(null);
  const previewController = useRef<AbortController | null>(null);
  const readbackController = useRef<AbortController | null>(null);
  const flowPhase = flow?.status;
  const unresolved = phase === 'applying' || phase === 'outcome_unknown' || phase === 'observation_failed'
    || flowPhase === 'applying' || flowPhase === 'outcome_unknown' || flowPhase === 'observation_failed' || flowPhase === 'observing';
  const busy = unresolved || phase === 'loading' || phase === 'previewing';
  const historicalRepair = query?.lifecycle_status === '訂單取消' && query.historical_mid_service_confirmation_available;
  const supportsServiceDays = query?.service_started === true || historicalRepair;
  const alreadyCancelled = query?.lifecycle_status === '訂單取消' && !historicalRepair;
  useEffect(() => { onBusyChange?.(unresolved); }, [unresolved, onBusyChange]);
  useEffect(() => {
    const previousCaseNo = activeCaseNo.current;
    if (previousCaseNo !== caseNo) {
      const previous = orderMutationFlowStore.getCancellation(previousCaseNo);
      if (previous?.status === 'applying') {
        orderMutationFlowStore.setCancellation(previousCaseNo, { ...previous, status: 'outcome_unknown',
          error: '取消結果未明；保留原內容與冪等鍵，先查詢原收據，不自動重送。' });
      } else if (previous?.status === 'observing' && previous.receipt) {
        orderMutationFlowStore.setCancellation(previousCaseNo, { ...previous, status: 'observation_failed',
          error: '取消回讀已中止；保留原收據，只能重新讀取取消結果。' });
      }
      inFlight.current.delete(previousCaseNo);
    }
    activeCaseNo.current = caseNo;
    sequence.current += 1;
    queryController.current?.abort();
    previewController.current?.abort();
    readbackController.current?.abort();
    queryController.current = null;
    previewController.current = null;
    readbackController.current = null;
    setQuery(null); setDays([]); setReason(''); setPreview(null); setConfirmed(false); setError(null); setPhase('idle');
  }, [caseNo]);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      const current = orderMutationFlowStore.getCancellation(activeCaseNo.current);
      if (current?.status === 'applying') {
        orderMutationFlowStore.setCancellation(activeCaseNo.current, { ...current, status: 'outcome_unknown',
          error: '取消結果未明；保留原內容與冪等鍵，先查詢原收據，不自動重送。' });
      } else if (current?.status === 'observing' && current.receipt) {
        orderMutationFlowStore.setCancellation(activeCaseNo.current, { ...current, status: 'observation_failed',
          error: '取消回讀已中止；保留原收據，只能重新讀取取消結果。' });
      }
      sequence.current += 1;
      queryController.current?.abort();
      previewController.current?.abort();
      readbackController.current?.abort();
    };
  }, []);
  useEffect(() => () => { onBusyChange?.(false); }, [onBusyChange]);

  const isActive = (request: number, requestCaseNo: string) => mounted.current
    && activeCaseNo.current === requestCaseNo && sequence.current === request;

  const invalidate = () => { setPreview(null); setConfirmed(false); setError(null); setPhase('idle'); };
  const load = async () => {
    if (busy || inFlight.current.has(caseNo)) return;
    if (flow?.status === 'observed') orderMutationFlowStore.clearCancellation(caseNo);
    const request = ++sequence.current;
    queryController.current?.abort();
    const controller = new AbortController();
    queryController.current = controller;
    setPhase('loading'); setPreview(null); setConfirmed(false); setError(null);
    try {
      const data = await orderCancellationClient.query(caseNo, controller.signal);
      if (data.case_no !== caseNo) throw new Error('訂單取消查詢案件識別不一致。');
      if (!isActive(request, caseNo)) return;
      setQuery(data); setDays(drafts(data.service_started || data.historical_mid_service_confirmation_available ? data.confirmed_service_days : [])); setPhase('idle');
    } catch (caught) {
      if (isActive(request, caseNo)) { setQuery(null); setError(caught instanceof Error ? caught.message : '取消查詢失敗。'); setPhase('idle'); }
    } finally {
      if (queryController.current === controller) queryController.current = null;
    }
  };

  const check = async () => {
    if (!query || alreadyCancelled || busy || inFlight.current.has(caseNo)) return;
    setError(null);
    if (days.some((day) => !/^\d{4}-\d{2}-\d{2}$/.test(day.service_date)
      || !Number.isInteger(Number(day.staff_id)) || Number(day.staff_id) <= 0)) {
      setError('請輸入有效且不重複的實際服務日期與月嫂。'); return;
    }
    const typed: ServiceDay[] = days.map((day) => ({ service_date: day.service_date, staff_id: Number(day.staff_id), reason: day.reason.trim() || null }));
    if (new Set(typed.map((day) => day.service_date)).size !== typed.length) { setError('實際服務日期不可重複。'); return; }
    if (!supportsServiceDays && typed.length !== 0) { setError('服務尚未開始，實際服務日必須為 0 天。'); return; }
    if (supportsServiceDays && typed.length === 0) { setError('服務已開始或歷史取消補登，至少保留一日實際服務事實。'); return; }
    const baseline = new Set(query.confirmed_service_days.map((day) => `${day.service_date}:${day.staff_id}`));
    if (typed.some((day) => !baseline.has(`${day.service_date}:${day.staff_id}`) && day.reason === null)) {
      setError('新增或變更實際服務日／月嫂，必須填寫該日人工原因。'); return;
    }
    const request = ++sequence.current;
    previewController.current?.abort();
    const controller = new AbortController();
    previewController.current = controller;
    setPhase('previewing'); setPreview(null); setConfirmed(false);
    try {
      const data = await orderCancellationClient.preview(caseNo, typed.sort((left, right) => left.service_date.localeCompare(right.service_date)), controller.signal);
      if (data.lifecycle_impact.case_no !== caseNo || data.scheduling.case_no !== caseNo
        || data.client_finance_impact.case_no !== caseNo || data.payroll_impact.case_no !== caseNo) throw new Error('取消預覽案件識別不一致。');
      if (isActive(request, caseNo)) { setPreview(data); setPhase('idle'); }
    } catch (caught) {
      if (isActive(request, caseNo)) { setError(caught instanceof Error ? caught.message : '取消預覽失敗。'); setPhase('idle'); }
    } finally {
      if (previewController.current === controller) previewController.current = null;
    }
  };

  const observe = async (command: CancellationCommand, request: number) => {
    const saved = orderMutationFlowStore.getCancellation(command.caseNo);
    const receipt = saved?.receipt;
    if (!saved || !receipt || receipt.case_no !== command.caseNo || receipt.preview_fingerprint !== command.payload.preview_fingerprint) {
      throw new Error('訂單取消收據 identity 不一致，已停止操作。');
    }
    orderMutationFlowStore.setCancellation(command.caseNo, { ...saved, status: 'observing', error: null });
    readbackController.current?.abort();
    const controller = new AbortController();
    readbackController.current = controller;
    const data = await orderCancellationClient.query(command.caseNo, controller.signal);
    if (data.case_no !== command.caseNo || data.lifecycle_status !== receipt.lifecycle_status
      || data.lifecycle_status !== '訂單取消' || data.order_version < receipt.order_version
      || data.scheduling_version < receipt.scheduling_version) throw new Error('取消已回傳收據，但正式回讀尚未觀察到該版本與取消狀態。');
    orderMutationFlowStore.setCancellation(command.caseNo, { ...saved, status: 'observed', error: null });
    if (!isActive(request, command.caseNo)) return;
    setQuery(data); setDays(drafts(data.confirmed_service_days)); setPreview(null); setConfirmed(false);
    setPhase('observed');
    onBusyChange?.(false); onObserved?.();
  };

  const apply = async (retry = false) => {
    if (inFlight.current.has(caseNo)) return;
    if (!retry && (!preview || !reason.trim() || !confirmed || busy
      || preview.client_finance_impact.blockers.length > 0 || preview.payroll_impact.blockers.length > 0)) return;
    const existing = orderMutationFlowStore.getCancellation(caseNo);
    if (retry && existing?.status !== 'outcome_unknown') return;
    if (existing?.status === 'applying' || existing?.status === 'observing' || existing?.receipt) return;
    const recoveringUnknown = existing?.status === 'outcome_unknown' && existing.command !== null;
    const command = existing?.command ?? (preview ? {
      caseNo,
      payload: {
        confirmed_service_days: preview.confirmed_service_days,
        expected_order_version: preview.order_version,
        expected_scheduling_version: preview.scheduling_version,
        expected_client_finance_version: preview.client_finance_version,
        expected_payroll_version: preview.payroll_version,
        preview_fingerprint: preview.preview_fingerprint,
        reason: reason.trim(),
      }, idempotencyKey: `beta-cancellation-${crypto.randomUUID()}`,
      actor: sessionClient.getUser()?.username.trim() ?? '',
    } : null);
    if (!command) return;
    inFlight.current.add(caseNo);
    const request = sequence.current;
    setPhase('applying'); setError(null); onBusyChange?.(true);
    orderMutationFlowStore.setCancellation(command.caseNo, { status: 'applying', command, receipt: null, error: null });
    try {
      if (retry) {
        try {
          const receipt = await orderCancellationClient.receipt(command.caseNo, command.idempotencyKey);
          orderMutationFlowStore.setCancellation(command.caseNo, { status: 'observation_failed', command, receipt, error: null });
        }
        catch (caught) {
          if (!(caught instanceof ApiHttpError) || caught.status !== 404) throw caught;
          const receipt = await orderCancellationClient.apply(command.caseNo, command.payload, {
            idempotencyKey: command.idempotencyKey, actor: command.actor,
          });
          orderMutationFlowStore.setCancellation(command.caseNo, { status: 'observation_failed', command, receipt, error: null });
        }
      } else {
        const receipt = await orderCancellationClient.apply(command.caseNo, command.payload, {
          idempotencyKey: command.idempotencyKey, actor: command.actor,
        });
        orderMutationFlowStore.setCancellation(command.caseNo, { status: 'observation_failed', command, receipt, error: null });
      }
    } catch (caught) {
      const rejected = caught instanceof ApiHttpError && caught.status >= 400 && caught.status < 500
        && caught.status !== 408 && caught.status !== 429;
      if (rejected && !recoveringUnknown) {
        orderMutationFlowStore.clearCancellation(command.caseNo);
        if (isActive(request, command.caseNo)) {
          setPreview(null); setConfirmed(false); setQuery(null); setPhase('idle'); onBusyChange?.(false);
          setError(`取消未通過檢查，請重新讀取並預覽：${caught.message}`);
        }
      } else {
        orderMutationFlowStore.setCancellation(command.caseNo, { status: 'outcome_unknown', command, receipt: null,
          error: recoveringUnknown
            ? '取消結果仍未確認；請恢復權限後以原操作重新確認。'
            : '取消結果未明；保留原內容與冪等鍵，先查詢原收據，不自動重送。' });
        if (isActive(request, command.caseNo)) {
          setPhase('outcome_unknown');
          setError(recoveringUnknown
            ? '取消結果仍未確認；請恢復權限後以原操作重新確認。'
            : '取消結果未明；保留原內容與冪等鍵，先查詢原收據，不自動重送。');
        }
      }
      inFlight.current.delete(command.caseNo);
      return;
    }
    try { await observe(command, request); }
    catch (caught) {
      const saved = orderMutationFlowStore.getCancellation(command.caseNo);
      if (saved?.receipt) orderMutationFlowStore.setCancellation(command.caseNo, { ...saved, status: 'observation_failed', error: caught instanceof Error ? caught.message : '取消回讀失敗。' });
      if (isActive(request, command.caseNo)) { setPhase('observation_failed'); setError(caught instanceof Error ? caught.message : '取消回讀失敗。'); }
    }
    finally { inFlight.current.delete(command.caseNo); }
  };

  const retryObservation = async () => {
    const current = orderMutationFlowStore.getCancellation(caseNo);
    if (inFlight.current.has(caseNo) || current?.status !== 'observation_failed' || !current.receipt) return;
    inFlight.current.add(caseNo);
    const request = sequence.current;
    setPhase('applying'); setError(null);
    try { await observe(current.command, request); }
    catch (caught) {
      const saved = orderMutationFlowStore.getCancellation(caseNo);
      if (saved?.receipt) orderMutationFlowStore.setCancellation(caseNo, { ...saved, status: 'observation_failed', error: caught instanceof Error ? caught.message : '取消回讀失敗。' });
      if (isActive(request, caseNo)) { setPhase('observation_failed'); setError(caught instanceof Error ? caught.message : '取消回讀失敗。'); }
    }
    finally { inFlight.current.delete(caseNo); }
  };

  return (
    <section aria-label={`案件 ${caseNo} 訂單取消`}>
      <h4>訂單取消／歷史取消實際服務補登</h4>
      <button type="button" disabled={busy} onClick={() => void load()}>讀取取消狀態</button>
      {phase === 'loading' && <p role="status">讀取取消狀態中…</p>}
      {query && (
        <>
          <p>目前狀態：{query.lifecycle_status}</p>
          {alreadyCancelled && <p role="status">案件已取消且無歷史服務補登能力；重新開始請使用受控重開。</p>}
          {historicalRepair && <p role="status">後端允許補登歷史取消的實際服務事實；不是重新取消或重開。</p>}
          {!supportsServiceDays && <p>服務尚未開始，取消實際服務日維持 0 天。</p>}
          {supportsServiceDays && !alreadyCancelled && (
            <fieldset disabled={busy}>
              <legend>實際服務日與月嫂</legend>
              {days.map((day, index) => (
                <div key={index}>
                  <input aria-label={`取消實際服務日 ${index + 1}`} type="date" value={day.service_date} onChange={(event) => {
                    setDays((current) => current.map((item, row) => row === index ? { ...item, service_date: event.target.value } : item)); invalidate();
                  }} />
                  <select aria-label={`取消實際月嫂 ${index + 1}`} value={day.staff_id} onChange={(event) => {
                    setDays((current) => current.map((item, row) => row === index ? { ...item, staff_id: event.target.value } : item)); invalidate();
                  }}>
                    <option value="">請選擇正式月嫂</option>
                    {query.caregiver_options.map((staff) => <option key={staff.staff_id} value={staff.staff_id}>{staff.display_name}</option>)}
                  </select>
                  <input aria-label={`取消實際服務日原因 ${index + 1}`} value={day.reason} maxLength={500} onChange={(event) => {
                    setDays((current) => current.map((item, row) => row === index ? { ...item, reason: event.target.value } : item)); invalidate();
                  }} />
                  <button type="button" aria-label={`移除取消實際服務日 ${index + 1}`} onClick={() => { setDays((current) => current.filter((_, row) => row !== index)); invalidate(); }}>移除此日</button>
                </div>
              ))}
              <button type="button" onClick={() => { setDays((current) => [...current, { service_date: '', staff_id: '', reason: '' }]); invalidate(); }}>新增實際服務日</button>
            </fieldset>
          )}
          <button type="button" disabled={busy || alreadyCancelled} onClick={() => void check()}>檢查取消影響</button>
        </>
      )}
      {preview && (
        <>
          <p>正式服務：{preview.official_service_day_count} 日／{preview.official_service_hours} 小時；取消日期：{preview.cancellation_date}</p>
          <p>狀態：{preview.lifecycle_impact.before_status} → {preview.lifecycle_impact.after_status}</p>
          <section aria-label="取消帳務與薪資影響">
            {preview.client_finance_impact.actions.map((action, index) => <p key={`client-${index}`}>客戶 {action.payment_stage}：{action.direction} NT$ {action.direction_amount_ntd}</p>)}
            {preview.payroll_impact.actions.map((action, index) => <p key={`staff-${index}`}>月嫂 #{action.staff_id}：{action.direction} NT$ {action.amount.amount}</p>)}
            {[...preview.client_finance_impact.blockers, ...preview.payroll_impact.blockers].map((blocker, index) => <p role="alert" key={index}>{blocker}</p>)}
          </section>
          <label>取消原因<textarea aria-label="Beta 取消原因" value={reason} disabled={busy} maxLength={500} onChange={(event) => { setReason(event.target.value); setConfirmed(false); }} /></label>
          <label><input type="checkbox" checked={confirmed} disabled={busy} onChange={(event) => setConfirmed(event.target.checked)} />我已核對實際服務日、帳務與取消影響</label>
          <button type="button" disabled={busy || !confirmed || !reason.trim() || preview.client_finance_impact.blockers.length > 0 || preview.payroll_impact.blockers.length > 0} onClick={() => void apply()}>確認取消／補登</button>
        </>
      )}
      {phase === 'previewing' && <p role="status">檢查取消影響中…</p>}
      {(flowPhase === 'applying' || flowPhase === 'observing' || phase === 'applying') && <p role="status">取消套用／回讀中…</p>}
      {(flowPhase === 'outcome_unknown' || phase === 'outcome_unknown') && <button type="button" onClick={() => void apply(true)}>查詢原取消收據並確認結果</button>}
      {(flowPhase === 'observation_failed' || phase === 'observation_failed') && <button type="button" onClick={() => void retryObservation()}>只重新讀取取消結果</button>}
      {(flowPhase === 'observed' || phase === 'observed') && <p role="status">訂單取消已完成正式回讀：{query?.lifecycle_status}</p>}
      {(flow?.error ?? error) && <p role="alert">{flow?.error ?? error}</p>}
    </section>
  );
};

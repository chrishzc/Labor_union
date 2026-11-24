import { useUnsavedDraft, useUnsavedNavigation } from './UnsavedChanges';
import { CancellationSettlementNotices } from './CancellationSettlementNotices';
import { useStaffIdentityLabels } from './StaffIdentityProvider';
import { useCallback, useEffect, useRef, useState, useSyncExternalStore, type FC } from 'react';
import { orderCancellationClient, type OrderCancellationPreview, type OrderCancellationQuery,
  type HistoricalUnservedCorrection, type ServiceDay } from '../api/orders/order_cancellation_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { orderMutationFlowStore, type CancellationCommand } from '../adapters/orders/order_mutation_flow_store';
import { sessionClient } from '../api/auth/session_client';
import './OrderCancellationPanel.css';

interface Props { caseNo: string; onObserved?: () => void; onBusyChange?: (busy: boolean) => void; allowHistoricalRepair?: boolean; inBankReconciliation?: boolean; historicalUnservedCorrection?: boolean }
type DayDraft = { service_date: string; staff_id: string; reason: string };
type Phase = 'idle' | 'loading' | 'previewing' | 'applying' | 'outcome_unknown' | 'observation_failed' | 'observed';
const drafts = (days: ServiceDay[]): DayDraft[] => days.map((day) => ({ service_date: day.service_date, staff_id: String(day.staff_id), reason: day.reason ?? '' }));
const subscribeCancellation = (listener: () => void) => orderMutationFlowStore.subscribe(listener);
const paymentStageLabels = new Map([
  ['deposit', '定金'],
  ['first', '第一期款'],
  ['second', '第二期款'],
]);
const historicalBlockerLabels = new Map([
  ['historical_unserved_status_ineligible', '案件目前的狀態無法執行這項更正。'],
  ['historical_unserved_cash_ledger_invalid', '本案收付款紀錄有誤，請先核對帳務。'],
  ['historical_unserved_prior_settlement_invalid', '本案原取消結算紀錄有誤，請先核對帳務。'],
]);
const historicalReviewLabels = new Map([
  ['historical_unserved_establishment_evidence_missing', '系統沒有正式成立紀錄。'],
  ['historical_unserved_actual_service_evidence', '系統留有實際服務紀錄，請核對是否應更正。'],
  ['historical_unserved_cash_evidence_requires_review', '收付款項待核對。更正後請確認對帳明細配對。'],
  ['historical_unserved_not_historical', '系統沒有歷史採納或未服務紀錄。'],
]);

export function isCancellationTerminalStatus(status: string | null | undefined) {
  return ['訂單完成', '訂單取消', '成立後未服務', '歷史訂單－服務完成', '歷史訂單－帳務完成'].includes(status ?? '');
}

export const OrderCancellationPanel: FC<Props> = ({ caseNo, onObserved, onBusyChange, allowHistoricalRepair = true, inBankReconciliation = false, historicalUnservedCorrection = false }) => {
  const { requestLeave } = useUnsavedNavigation();
  const staffIdentity = useStaffIdentityLabels();
  const [query, setQuery] = useState<OrderCancellationQuery | null>(null);
  const [days, setDays] = useState<DayDraft[]>([]);
  const [reason, setReason] = useState('');
  const [evidenceSource, setEvidenceSource] = useState('');
  const [confirmedUnserved, setConfirmedUnserved] = useState(false);
  const [chargeFee, setChargeFee] = useState(false);
  const [feeAmount, setFeeAmount] = useState('');
  const [feeNote, setFeeNote] = useState('');
  const [preview, setPreview] = useState<OrderCancellationPreview | null>(null);
  const [phase, setPhase] = useState<Phase>('idle');
  const [error, setError] = useState<string | null>(null);
  const [requiresEarlyFinish, setRequiresEarlyFinish] = useState(false);
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
  const historicalRepair = !historicalUnservedCorrection && allowHistoricalRepair && query?.lifecycle_status === '訂單取消' && query.historical_mid_service_confirmation_available;
  const saveHistoricalWithoutConfirmation = historicalRepair && !inBankReconciliation;
  const supportsServiceDays = !historicalUnservedCorrection && (query?.service_started === true || historicalRepair);
  const alreadyCancelled = query?.lifecycle_status === '訂單取消' && !historicalRepair;
  const correctionFacts = query?.historical_unserved_correction;
  const historicalCorrectionComplete = historicalUnservedCorrection && query?.lifecycle_status === '成立後未服務';
  const correctionIntent: HistoricalUnservedCorrection | undefined =
    historicalUnservedCorrection && confirmedUnserved
      ? { reason: reason.trim(), evidence_source: evidenceSource.trim(), confirmed_actual_service_day_count: 0 }
      : undefined;
  const cancellationUnavailable = historicalUnservedCorrection
    ? !correctionFacts || correctionFacts.blockers.length > 0
    : isCancellationTerminalStatus(query?.lifecycle_status) && !historicalRepair;
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
    setQuery(null); setDays([]); setReason(''); setEvidenceSource(''); setConfirmedUnserved(false);
    setPreview(null); setError(null); setRequiresEarlyFinish(false); setPhase('idle');
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

  const isActive = useCallback((request: number, requestCaseNo: string) => mounted.current
    && activeCaseNo.current === requestCaseNo && sequence.current === request, []);

  const invalidate = () => {
    sequence.current += 1; previewController.current?.abort();
    setPreview(null); setError(null); setRequiresEarlyFinish(false); setPhase('idle');
  };
  const load = useCallback(async () => {
    const current = orderMutationFlowStore.getCancellation(caseNo);
    if (inFlight.current.has(caseNo) || (current && current.status !== 'observed')) return;
    if (current?.status === 'observed') orderMutationFlowStore.clearCancellation(caseNo);
    const request = ++sequence.current;
    queryController.current?.abort();
    const controller = new AbortController();
    queryController.current = controller;
    setPhase('loading'); setPreview(null); setError(null); setRequiresEarlyFinish(false);
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
  }, [caseNo, isActive]);

  useEffect(() => { void load(); }, [load]);

  const check = async () => {
    const current = orderMutationFlowStore.getCancellation(caseNo);
    if (!query || cancellationUnavailable
      || inFlight.current.has(caseNo) || current) return;
    setError(null);
    const submittedDays = historicalUnservedCorrection ? [] : days;
    if (historicalUnservedCorrection && !correctionIntent) return;
    if (submittedDays.some((day) => !/^\d{4}-\d{2}-\d{2}$/.test(day.service_date)
      || !Number.isInteger(Number(day.staff_id)) || Number(day.staff_id) <= 0)) {
      setError('請輸入有效且不重複的實際服務日期與月嫂。'); return;
    }
    const typed: ServiceDay[] = submittedDays.map((day) => ({ service_date: day.service_date, staff_id: Number(day.staff_id), reason: day.reason.trim() || null }));
    if (new Set(typed.map((day) => day.service_date)).size !== typed.length) { setError('實際服務日期不可重複。'); return; }
    if (!supportsServiceDays && typed.length !== 0) { setError('服務尚未開始，實際服務日必須為 0 天。'); return; }
    if (historicalRepair && typed.length === 0) { setError('歷史取消補登至少需一日實際服務事實。'); return; }
    const fee = chargeFee && !historicalRepair && !historicalUnservedCorrection ? { fee_ntd: feeAmount.trim(), fee_reason: feeNote.trim() } : undefined;
    if (fee && (!/^\d+$/.test(fee.fee_ntd) || BigInt(fee.fee_ntd) === 0n || !fee.fee_reason)) {
      setError('收取違約金時，請填寫正整數金額及收取原因。'); return;
    }
    if (fee && BigInt(fee.fee_ntd) > 9_223_372_036_854_775_807n) {
      setError('違約金金額超出帳務可精確記錄的範圍。'); return;
    }
    const request = ++sequence.current;
    previewController.current?.abort();
    const controller = new AbortController();
    previewController.current = controller;
    setPhase('previewing'); setPreview(null); setRequiresEarlyFinish(false);
    try {
      const confirmed = typed.sort((left, right) => left.service_date.localeCompare(right.service_date));
      const change = correctionIntent ? { historical_unserved_correction: correctionIntent } : fee;
      const data = change
        ? await orderCancellationClient.preview(caseNo, confirmed, controller.signal, change)
        : await orderCancellationClient.preview(caseNo, confirmed, controller.signal);
      if (data.lifecycle_impact.case_no !== caseNo || (data.scheduling !== null && data.scheduling.case_no !== caseNo)
        || (data.client_finance_impact !== null && data.client_finance_impact.case_no !== caseNo) || (data.payroll_impact !== null && data.payroll_impact.case_no !== caseNo)) throw new Error('取消預覽案件識別不一致。');
      if (correctionIntent && (data.lifecycle_impact.after_status !== '成立後未服務' || data.official_service_day_count !== 0 || data.official_service_hours !== 0)) {
        throw new Error('歷史更正預覽未確認零服務結果。');
      }
      if (isActive(request, caseNo)) {
        setPreview(data); setPhase('idle');
        if (saveHistoricalWithoutConfirmation) await apply(false, data);
      }
    } catch (caught) {
      if (isActive(request, caseNo)) {
        setRequiresEarlyFinish(caught instanceof ApiHttpError && caught.code === 'order_cancellation_has_actual_service');
        setError(caught instanceof ApiHttpError && caught.code === 'cancellation_fee_finance_required'
          ? '案件缺少建立客戶帳務所需的正式資料。請先從客戶名冊補齊案件資料，再重新預覽。'
          : caught instanceof Error ? caught.message : '取消預覽失敗。');
        setPhase('idle');
      }
    } finally {
      if (previewController.current === controller) previewController.current = null;
    }
  };


  const observe = async (command: CancellationCommand, request: number) => {
    const saved = orderMutationFlowStore.getCancellation(command.caseNo);
    const receipt = saved?.receipt;
    if (!saved || !receipt || receipt.case_no !== command.caseNo || receipt.preview_fingerprint !== command.payload.preview_fingerprint
      || receipt.lifecycle_status !== command.expectedLifecycleStatus) {
      throw new Error('訂單取消收據識別資訊不一致，已停止操作。');
    }
    orderMutationFlowStore.setCancellation(command.caseNo, { ...saved, status: 'observing', error: null });
    readbackController.current?.abort();
    const controller = new AbortController();
    readbackController.current = controller;
    const data = await orderCancellationClient.query(command.caseNo, controller.signal);
    if (data.case_no !== command.caseNo || data.lifecycle_status !== receipt.lifecycle_status
      || data.order_version < receipt.order_version
      || (receipt.lifecycle_status === '成立後未服務' && (receipt.official_service_day_count !== 0 || receipt.official_service_hours !== 0 || data.confirmed_service_days.length !== 0))
      || (receipt.lifecycle_status === '成立後未服務' && receipt.payroll_version !== null && (data.payroll_version === null || data.payroll_version < receipt.payroll_version))
      || (receipt.scheduling_version !== null && (data.scheduling_version === null || data.scheduling_version < receipt.scheduling_version))
      || (receipt.client_finance_version !== null && (data.client_finance_version === null || data.client_finance_version < receipt.client_finance_version))) {
      throw new Error('取消已回傳收據，但正式回讀尚未觀察到該版本與取消狀態。');
    }
    orderMutationFlowStore.setCancellation(command.caseNo, { ...saved, status: 'observed', error: null });
    if (!isActive(request, command.caseNo)) return;
    setQuery(data); setDays(drafts(data.confirmed_service_days)); setPreview(null);
    setPhase('observed');
    onBusyChange?.(false); onObserved?.();
  };

  const apply = async (retry = false, calculatedPreview = preview) => {
    const preview = calculatedPreview;
    if (inFlight.current.has(caseNo)) return;
    if (!retry && (!preview || busy
      || (historicalUnservedCorrection && !correctionIntent)
      || (preview.client_finance_impact !== null && preview.client_finance_impact.blockers.length > 0) || (preview.payroll_impact !== null && preview.payroll_impact.blockers.length > 0))) return;
    const existing = orderMutationFlowStore.getCancellation(caseNo);
    if (retry && existing?.status !== 'outcome_unknown') return;
    if (existing?.status === 'applying' || existing?.status === 'observing' || existing?.receipt) return;
    const recoveringUnknown = existing?.status === 'outcome_unknown' && existing.command !== null;
    const command = existing?.command ?? (preview ? {
      caseNo,
      expectedLifecycleStatus: preview.lifecycle_impact.after_status,
      payload: {
        confirmed_service_days: preview.confirmed_service_days,
        expected_order_version: preview.order_version,
        expected_scheduling_version: preview.scheduling_version,
        expected_client_finance_version: preview.client_finance_version,
        expected_payroll_version: preview.payroll_version,
        preview_fingerprint: preview.preview_fingerprint,
        reason: reason.trim(),
        ...(correctionIntent ? { historical_unserved_correction: correctionIntent }
          : chargeFee && !historicalRepair ? { fee_ntd: feeAmount.trim(), fee_reason: feeNote.trim() } : {}),
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
          setPreview(null); setQuery(null); setPhase('idle'); onBusyChange?.(false);
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
  useUnsavedDraft(historicalUnservedCorrection ? '更正歷史零服務' : '取消訂單', historicalUnservedCorrection
    ? { '更正原因': reason, '證據來源': evidenceSource, '已確認零服務': confirmedUnserved }
    : { '服務天數確認': days.map((item) => `${item.service_date || '未填日期'}（月嫂 ${item.staff_id || '未填'}）`).join('、') || '無', '取消原因': reason, '收取違約金': chargeFee, '違約金金額': feeAmount, '違約金說明': feeNote },
  { enabled: !!query, resetKey: query, busy });

  const settlement = preview?.client_finance_impact?.cancellation_settlement;
  const blocked = !!preview?.client_finance_impact?.blockers.length || !!preview?.payroll_impact?.blockers.length;
  const cancellationObserved = flowPhase === 'observed' || phase === 'observed';
  const showFinanceLink = historicalCorrectionComplete || cancellationObserved;
  const showCopyCaseLink = showFinanceLink || query?.lifecycle_status === '訂單取消';
  const financeHref = `#finance?tab=case-accounting&case_no=${encodeURIComponent(caseNo)}&from=workbench`;
  const copyCaseHref = `#clients?tab=applications&source_case=${encodeURIComponent(caseNo)}`;
  const financeLink = <a href={financeHref}>查看本案帳務</a>;
  const copyCaseLink = <a href={copyCaseHref} aria-disabled={busy}
    onClick={event => {
      event.preventDefault();
      if (!busy) requestLeave(() => { window.location.hash = copyCaseHref; });
    }}>以此案資料建立非市民新案</a>;

  return (
    <section aria-label={`案件 ${caseNo} 訂單取消`} className={historicalUnservedCorrection ? 'historical-unserved-correction' : undefined}>
      {historicalUnservedCorrection ? <header className="historical-unserved-header">
        <h4>歷史零服務更正</h4>
        {query && <p>目前狀態 <strong>{query.lifecycle_status}</strong></p>}
      </header> : <h4>{historicalRepair ? '補登取消前的實際服務' : inBankReconciliation ? '取消結算' : '取消訂單'}</h4>}
      {!query && phase !== 'loading' && !unresolved && <button type="button" onClick={() => void load()}>重新讀取取消狀態</button>}
      {phase === 'loading' && <p role="status">讀取取消狀態中…</p>}
      {query && (
        <>
          {!historicalUnservedCorrection && <p>目前狀態：{query.lifecycle_status}</p>}
          {historicalCorrectionComplete && <p role="status" className="historical-unserved-success">本案已完成更正，無須再次操作。</p>}
          {historicalUnservedCorrection && !correctionFacts && !historicalCorrectionComplete &&
            <p role="status">目前無法取得更正資料。請重新開啟更正，若仍無法讀取，請聯絡系統管理員。</p>}
          {historicalUnservedCorrection && correctionFacts && <section aria-label="歷史更正證據" className="historical-unserved-evidence">
            <div className="historical-unserved-summary">
              <section className="historical-unserved-card">
                <h5>帳務摘要</h5>
                <dl>
                  <div><dt>客戶淨實收</dt><dd>{correctionFacts.net_cash_received_ntd === null ? '待核對' : `NT$ ${correctionFacts.net_cash_received_ntd.toLocaleString('zh-TW')}`}</dd></div>
                  <div><dt>原違約金</dt><dd>NT$ {correctionFacts.prior_fee_ntd.toLocaleString('zh-TW')}</dd></div>
                </dl>
                {correctionFacts.prior_fee_reason && <p>違約金原因：{correctionFacts.prior_fee_reason}</p>}
              </section>
              <section className="historical-unserved-card">
                <h5>實際服務紀錄</h5>
                <dl>
                  <div><dt>開始日期</dt><dd>{correctionFacts.actual_start_date ?? '無'}</dd></div>
                  <div><dt>結束日期</dt><dd>{correctionFacts.actual_end_date ?? '無'}</dd></div>
                </dl>
                {correctionFacts.actual_service_evidence.length > 0 && <p>服務證據：{correctionFacts.actual_service_evidence.join('、')}</p>}
              </section>
            </div>
            {correctionFacts.client_obligations.length > 0 && <section className="historical-unserved-card">
              <h5>客戶款項</h5>
              <ul className="historical-unserved-obligations">
                {correctionFacts.client_obligations.map(item => <li key={item.obligation_identity}>
                  <h6>{paymentStageLabels.get(item.payment_stage) ?? item.payment_stage}</h6>
                  <dl>
                    <div><dt>約定</dt><dd>NT$ {item.contracted_ntd.toLocaleString('zh-TW')}</dd></div>
                    <div><dt>已結</dt><dd>NT$ {item.settled_ntd.toLocaleString('zh-TW')}</dd></div>
                  </dl>
                </li>)}
              </ul>
            </section>}
            {correctionFacts.payroll_obligations.length > 0 && <section className="historical-unserved-card">
              <h5>月嫂薪資</h5>
              <ul className="historical-unserved-obligations">
                {correctionFacts.payroll_obligations.map(item => <li key={item.obligation_identity}>
                  <h6>{staffIdentity.label(item.staff_id)}</h6>
                  <dl>
                    <div><dt>約定</dt><dd>NT$ {item.contracted_ntd.toLocaleString('zh-TW')}</dd></div>
                    <div><dt>待結</dt><dd>NT$ {item.outstanding_ntd.toLocaleString('zh-TW')}</dd></div>
                    <div><dt>已付</dt><dd>NT$ {item.paid_ntd.toLocaleString('zh-TW')}</dd></div>
                  </dl>
                </li>)}
              </ul>
            </section>}
            <details className="historical-unserved-card">
              <summary>來源紀錄編號</summary>
              <dl className="historical-unserved-records">
                <div><dt>正式成立紀錄</dt><dd>{correctionFacts.establishment_lifecycle_event_ids.join('、') || '無'}</dd></div>
                <div><dt>正式成立的歷史採納</dt><dd>{correctionFacts.establishment_adoption_receipt_ids.join('、') || '無'}</dd></div>
                <div><dt>歷史採納紀錄</dt><dd>{correctionFacts.historical_adoption_receipt_ids.join('、') || '無'}</dd></div>
                <div><dt>未服務紀錄</dt><dd>{correctionFacts.historical_absence_event_ids.join('、') || '無'}</dd></div>
                <div><dt>已採納指派</dt><dd>{correctionFacts.adopted_assignment_ids?.join('、') || '無'}</dd></div>
              </dl>
            </details>
            {!!correctionFacts.review_codes?.length && <section className="historical-unserved-review">
              <h5>待核對事項</h5>
              <ul>{correctionFacts.review_codes.map(code => <li key={code}>{historicalReviewLabels.get(code) ?? code}</li>)}</ul>
            </section>}
            {correctionFacts.blockers.filter(blocker => !historicalCorrectionComplete || blocker !== 'historical_unserved_status_ineligible')
              .map(blocker => <p role="alert" key={blocker}>{historicalBlockerLabels.get(blocker) ?? blocker}</p>)}
            {!historicalCorrectionComplete && !cancellationUnavailable && <fieldset className="historical-unserved-card historical-unserved-form" disabled={busy}>
              <legend>更正資料</legend>
              <label>更正原因（選填）<textarea value={reason} maxLength={500} onChange={event => { setReason(event.target.value); invalidate(); }} /></label>
              <label>證據來源（選填）<input value={evidenceSource} maxLength={191} onChange={event => { setEvidenceSource(event.target.value); invalidate(); }} /></label>
              <label><input type="checkbox" checked={confirmedUnserved} onChange={event => { setConfirmedUnserved(event.target.checked); invalidate(); }} /> 我確認將本案更正為成立後未服務</label>
            </fieldset>}
          </section>}
          {!historicalUnservedCorrection && alreadyCancelled && <p role="status">{inBankReconciliation
            ? '案件已取消。請查看本案帳務，確認取消結算與待核銷款項。'
            : '案件已取消；重新開始請使用受控重開。'}</p>}
          {!historicalUnservedCorrection && cancellationUnavailable && !alreadyCancelled && <p role="status">{query.lifecycle_status === '成立後未服務'
            ? '本案已確認成立後未服務。請查看本案帳務。' : inBankReconciliation
            ? '系統已將此案標記為完工，現有取消結算無法處理。請先核對案件的完工紀錄。'
            : '案件已完成，無法辦理取消。'}</p>}
          {historicalRepair && <p role="status">後端允許補登歷史取消的實際服務事實；不是重新取消或重開。</p>}
          {!historicalUnservedCorrection && !supportsServiceDays && !cancellationUnavailable && <p>服務尚未開始，取消實際服務日維持 0 天。</p>}
          {supportsServiceDays && !cancellationUnavailable && <p>已自動排除取消日之後的排班。請核對已服務日期與月嫂；取消當日尚未服務可移除此日，確認完全未服務可保留 0 日。</p>}
          {supportsServiceDays && !cancellationUnavailable && (
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
                    {[...query.caregiver_options].sort((a, b) => staffIdentity.compare(a.staff_id, b.staff_id)).map((staff) => <option key={staff.staff_id} value={staff.staff_id}>{staffIdentity.label(staff.staff_id, staff.display_name)}</option>)}
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
          {!historicalUnservedCorrection && !cancellationUnavailable && <label>取消原因（選填）<textarea aria-label="取消原因" value={reason} disabled={busy} maxLength={500} onChange={(event) => { setReason(event.target.value); invalidate(); }} /></label>}
          {!historicalUnservedCorrection && !cancellationUnavailable && !historicalRepair && <fieldset disabled={busy}>
            <legend>取消違約金</legend>
            <label><input type="checkbox" checked={chargeFee} onChange={event => { setChargeFee(event.target.checked); invalidate(); }} /> 收取違約金</label>
            {chargeFee && <>
              <label>違約金金額（NT$）<input inputMode="numeric" value={feeAmount} onChange={event => { setFeeAmount(event.target.value); invalidate(); }} /></label>
              <label>收取原因<input value={feeNote} maxLength={500} onChange={event => { setFeeNote(event.target.value); invalidate(); }} /></label>
            </>}
          </fieldset>}
          {!historicalCorrectionComplete && !cancellationUnavailable && !preview && <button type="button" className={historicalUnservedCorrection ? 'historical-unserved-preview' : undefined} disabled={busy || (historicalUnservedCorrection && !correctionIntent)} onClick={() => void check()}>{historicalUnservedCorrection ? '預覽零服務更正' : saveHistoricalWithoutConfirmation ? '儲存實際服務事實' : '預覽取消帳務'}</button>}
        </>
      )}
      {preview && (
        <>
          <p>正式服務：{preview.official_service_day_count} 日／{preview.official_service_hours} 小時；取消日期：{preview.cancellation_date}</p>
          <p>狀態：{preview.lifecycle_impact.before_status} → {preview.lifecycle_impact.after_status}</p>
          {preview.historical_unserved_correction && <section aria-label="歷史事實更正" className="historical-unserved-card">
            {preview.historical_unserved_correction.classification_only && <p>更正訂單分類，沿用既有帳務結算。</p>}
            {preview.historical_unserved_correction.retired_adopted_assignment_ids.length > 0 &&
              <p>退出已採納指派：{preview.historical_unserved_correction.retired_adopted_assignment_ids.join('、')}</p>}
            {preview.historical_unserved_correction.payroll_recoveries.map(item => <p key={item.obligation_identity}>
              {staffIdentity.label(item.staff_id)} · 已實付 NT$ {item.paid_ntd.toLocaleString('zh-TW')} · 新增待追回 NT$ {item.recovery_increase_ntd.toLocaleString('zh-TW')}
            </p>)}
          </section>}
          <section aria-label="取消帳務與薪資影響" className={historicalUnservedCorrection ? 'historical-unserved-card' : undefined}>
            {preview.historical_unserved_correction?.client_cash_difference_requires_review === true && (
              <p>退款／補收金額為待核對目標。套用後會保留未能辨識的舊差額，暫緩新增退款以避免重複退款。請由對帳人員確認明細配對。</p>
            )}
            {preview.client_finance_impact === null && <p>沒有客戶帳務需要調整。</p>}
            {preview.payroll_impact === null && <p>沒有月嫂薪資需要調整。</p>}
            {settlement && <dl className={historicalUnservedCorrection ? 'historical-unserved-settlement' : undefined}>
              <dt>服務應付</dt><dd>NT$ {settlement.service_due_ntd}</dd>
              <dt>取消違約金</dt><dd>NT$ {settlement.fee_ntd.toLocaleString('zh-TW')}</dd>
              <dt>客戶淨實收</dt><dd>NT$ {settlement.net_received_ntd}</dd>
              <dt>已收違約金／公會營收</dt><dd>NT$ {settlement.fee_received_ntd}</dd>
              <dt>應退款</dt><dd>NT$ {settlement.refund_due_ntd}</dd>
              <dt>應補收</dt><dd>NT$ {settlement.additional_charge_due_ntd}</dd>
            </dl>}
            {!settlement && preview.client_finance_impact?.actions.map(action => <p key={action.obligation_identity}>
              {({ refund_due: '應退款', additional_charge_due: '應補收', no_finance_change: '無帳務差額' } as const)[action.direction]} NT$ {action.direction_amount_ntd}
            </p>)}
            {preview.payroll_impact?.actions.map((action, index) => <p key={`staff-${index}`}>{staffIdentity.label(action.staff_id)}：{({ payable_to_staff: '應付薪資', receivable_from_staff: '應收回款項' } as Record<string, string>)[action.direction] ?? '薪資調整'} NT$ {action.amount.amount}</p>)}
            {[...(preview.client_finance_impact?.blockers ?? []), ...(preview.payroll_impact?.blockers ?? [])].map((blocker, index) => <p role="alert" key={index}>{blocker === 'cancellation_amount_out_of_storage_range' ? '服務應付加違約金超出帳務可精確記錄的範圍。' : blocker}</p>)}
          </section>
          {!historicalCorrectionComplete && !saveHistoricalWithoutConfirmation && !cancellationUnavailable && !flow?.receipt && <>
            <button type="button" disabled={busy} onClick={invalidate}>返回調整</button>
            <button type="button" className="order-v2-danger" disabled={busy || blocked} onClick={() => void apply()}>{historicalUnservedCorrection ? '確認更正為成立後未服務' : historicalRepair ? '確認補登與結算' : '確認取消'}</button>
          </>}


        </>
      )}
      {phase === 'previewing' && <p role="status">檢查取消影響中…</p>}
      {(flowPhase === 'applying' || flowPhase === 'observing' || phase === 'applying') && <p role="status">取消套用／回讀中…</p>}
      {(flowPhase === 'outcome_unknown' || phase === 'outcome_unknown') && <button type="button" onClick={() => void apply(true)}>查詢原取消收據並確認結果</button>}
      {(flowPhase === 'observation_failed' || phase === 'observation_failed') && <button type="button" onClick={() => void retryObservation()}>只重新讀取取消結果</button>}
      {cancellationObserved && !historicalCorrectionComplete && <>
        <p role="status">{query?.lifecycle_status === '成立後未服務' ? '已讀回正式狀態' : '訂單取消已完成正式回讀'}：{query?.lifecycle_status}</p>
        {!historicalUnservedCorrection && financeLink}
        {query?.lifecycle_status === '訂單取消' && <CancellationSettlementNotices key={caseNo} caseNo={caseNo} settlementOnly />}
      </>}
      {showCopyCaseLink && (historicalUnservedCorrection ? <div className="historical-unserved-actions">
        {showFinanceLink && financeLink}
        {copyCaseLink}
      </div> : <p>{copyCaseLink}</p>)}
      {requiresEarlyFinish && <p><a href={`#clients?case=${encodeURIComponent(caseNo)}&from=workbench`}
        onClick={event => {
          event.preventDefault();
          requestLeave(() => { window.location.hash = `#clients?case=${encodeURIComponent(caseNo)}&from=workbench`; });
        }}>前往修改服務條件與完整班表</a></p>}
      {(flow?.error ?? error) && <p role="alert">{flow?.error ?? error}</p>}
    </section>
  );
};

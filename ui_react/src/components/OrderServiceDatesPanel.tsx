import { useEffect, useRef, useState, type FC } from 'react';
import type {
  ServiceDateConfirmationPreviewView,
  ServiceDateConfirmationQueryView,
} from '../api/orders/order_mutation_schemas';
import { ordersMutationClient } from '../api/orders/order_mutation_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import {
  schedulePrecisionClient,
  type SchedulePrecisionResult,
} from '../api/scheduling/schedule_precision_client';
import {
  applyServiceDatesFlow,
  previewServiceDatesFlow,
  retryServiceDatesApplyFlow,
  retryServiceDatesObservationFlow,
  selectServiceDates,
  updateServiceDatesReason,
} from '../adapters/orders/order_mutation_adapter';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';
import { orderActualStartClient, type ActualStartPreview } from '../api/orders/order_actual_start_client';
import type { ActualStart } from '../api/orders/order_query_schemas';
import { assertStartDates, isServiceDateConflict, refreshServiceDatesAfterStart, sameServiceDates, saveServiceDatesStart, serviceDateRange } from '../adapters/orders/service_date_start_flow';

interface OrderServiceDatesPanelProps {
  caseNo: string;
  onObserved?: () => void;
  onOpenActualStart?: () => void;
  calculationRevision?: number;
  projectionRevision?: number;
  onBusyChange?: (busy: boolean) => void;
}

type WorkingAction = 'load' | 'preview' | 'apply' | null;
type DateLoadMode = 'read' | 'calculate' | 'resume';
type ServiceMode = '休周六' | '休周日' | '週休2日' | '連續服務';
type ServiceDatesRecovery =
  | { caseNo: string; kind: 'outcome_unknown' }
  | { caseNo: string; kind: 'observation_failed'; confirmedVersion: number }
  | { caseNo: string; kind: 'superseded'; confirmedVersion: number; currentVersion: number }
  | { caseNo: string; kind: 'observation_in_progress' };
const AUTOMATIC_CONFIRMATION_REASON = '確認正式服務日期';

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message.trim()
    ? error.message.trim()
    : '服務日期操作失敗';
}

function recoveryFromServiceDatesDraft(caseNo: string): ServiceDatesRecovery | null {
  const draft = orderMutationFlowStore.getServiceDatesDraft(caseNo);
  if (draft?.status === 'outcome_unknown') {
    return { caseNo, kind: 'outcome_unknown' };
  }
  if (draft?.status === 'observation_failed' && draft.receiptView !== null) {
    const receipt = draft.receiptView;
    const current = draft.queryView;
    if (current !== null && current.case_no === caseNo && receipt.case_no === caseNo
      && current.current_version !== null && current.current_version > receipt.confirmed_version
      && current.order_version >= receipt.order_version && current.scheduling_version >= receipt.scheduling_version
      && (current.current_dates.length !== receipt.service_dates.length
        || current.current_dates.some((date) => !receipt.service_dates.includes(date)))) {
      return { caseNo, kind: 'superseded', confirmedVersion: receipt.confirmed_version, currentVersion: current.current_version };
    }
    return {
      caseNo,
      kind: 'observation_failed',
      confirmedVersion: draft.receiptView.confirmed_version,
    };
  }
  if (
    draft?.status === 'apply_pending'
    || draft?.status === 'receipt_received'
    || draft?.status === 'requery_loading'
  ) {
    return { caseNo, kind: 'observation_in_progress' };
  }
  return null;
}

export const OrderServiceDatesPanel: FC<OrderServiceDatesPanelProps> = ({ caseNo, onObserved, onOpenActualStart, calculationRevision = 0, projectionRevision = 0, onBusyChange }) => {
  const [working, setWorking] = useState<WorkingAction>(null);
  const [queryView, setQueryView] = useState<ServiceDateConfirmationQueryView | null>(null);
  const [precision, setPrecision] = useState<SchedulePrecisionResult | null>(null);
  const [serviceMode, setServiceMode] = useState<ServiceMode | null>(null);
  const [selectedDates, setSelectedDates] = useState<string[]>([]);
  const [preview, setPreview] = useState<ServiceDateConfirmationPreviewView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [basisNotice, setBasisNotice] = useState<string | null>(null);
  const [calculationBasis, setCalculationBasis] = useState<{ date: string; confirmed: boolean } | null>(null);
  const [hasManualChanges, setHasManualChanges] = useState(false);
  const [startDate, setStartDate] = useState('');
  const [actualStart, setActualStart] = useState<ActualStart | null>(null);
  const [startPreview, setStartPreview] = useState<ActualStartPreview | null>(null);
  const [startConfirmationReady, setStartConfirmationReady] = useState(false);
  const [suggestedDates, setSuggestedDates] = useState<string[]>([]);
  const [manualNeedsReview, setManualNeedsReview] = useState(false);
  const [inputInvalid, setInputInvalid] = useState(false);
  const [, setRecoveryRevision] = useState(0);
  const [attemptedCalculationRevision, setAttemptedCalculationRevision] = useState(0);
  const actionInFlight = useRef(new Set<string>());
  const readbackElement = useRef<HTMLDListElement | null>(null);
  const calculationSequence = useRef(0);
  const readController = useRef<AbortController | null>(null);
  const renderedCaseNo = useRef(caseNo);
  renderedCaseNo.current = caseNo;
  const recovery = recoveryFromServiceDatesDraft(caseNo);
  const isRecoveryActive = recovery?.caseNo === caseNo;
  const needsBasisUpdate = calculationRevision > attemptedCalculationRevision;
  const startFlow = orderMutationFlowStore.getActualStart(caseNo);
  const startUnresolved = startFlow !== undefined && startFlow.status !== 'observed';
  const saving = working === 'apply';

  useEffect(() => { onBusyChange?.(saving); return () => onBusyChange?.(false); }, [saving, onBusyChange]);
  useEffect(() => {
    if (success?.startsWith('服務日期已確認並回讀')) readbackElement.current?.focus();
  }, [success]);

  useEffect(() => {
    setAttemptedCalculationRevision(0);
    setWorking(null);
    setQueryView(null);
    setPrecision(null);
    setServiceMode(null);
    setSelectedDates([]);
    setPreview(null);
    setError(null);
    setSuccess(null);
    setBasisNotice(null);
    setCalculationBasis(null);
    setHasManualChanges(false);
    const retained = orderMutationFlowStore.getServiceDatesDraft(caseNo);
    setStartDate(retained?.calculation?.startDate ?? '');
    setStartPreview(retained?.calculation?.startPreview ?? null);
    setStartConfirmationReady(false);
    setActualStart(null);
    setManualNeedsReview(false);
    setInputInvalid(false);
    setSuggestedDates([]);
    if (retained?.calculation && retained.status !== 'observed') {
      setQueryView(retained.queryView);
      setSelectedDates(retained.selectedDates);
      setHasManualChanges(true);
      setBasisNotice('保留了尚未完成的日期草稿，請讀取目前結果並接續核對。');
    }
    setRecoveryRevision((revision) => revision + 1);

    const unsubscribe = orderMutationFlowStore.subscribe(() => {
      if (renderedCaseNo.current === caseNo) {
        setRecoveryRevision((revision) => revision + 1);
      }
    });
    // Opening an existing case reads saved dates; it does not regenerate them.
    if (calculationRevision === 0) void loadServiceDates('read');
    return () => {
      unsubscribe();
      readController.current?.abort();
      readController.current = null;
      calculationSequence.current += 1;
    };
    // A new case has its own read lifecycle; revisions are handled below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseNo]);

  const captureRecovery = () => {
    setRecoveryRevision((revision) => revision + 1);
  };

  const loadServiceDates = async (mode: DateLoadMode, inputDate?: string) => {
    const pending = recoveryFromServiceDatesDraft(caseNo);
    if (actionInFlight.current.has(caseNo) || startUnresolved
      || (pending !== null && !(mode === 'resume' && pending.kind === 'superseded'))
      || (mode === 'resume' && pending?.kind !== 'superseded')) return;
    const original = orderMutationFlowStore.getServiceDatesDraft(caseNo);
    const receipt = original?.receiptView;
    const previous = original?.queryView;
    const originalKey = original?.idempotencyKey;
    readController.current?.abort();
    const controller = new AbortController();
    readController.current = controller;
    const request = ++calculationSequence.current;
    const current = () => !controller.signal.aborted
      && readController.current === controller
      && renderedCaseNo.current === caseNo
      && calculationSequence.current === request;
    if (mode === 'calculate') setAttemptedCalculationRevision(calculationRevision);
    setWorking('load');
    setError(null); setPreview(null);
    if (mode !== 'read') setSuccess(null);
    setStartConfirmationReady(false);
    if (mode === 'calculate') {
      setBasisNotice(hasManualChanges
        ? '正在重新精算；先前人工調整將由新建議取代，請重新核對。'
        : '正在依目前日期基準更新服務日期與日曆。');
      setPrecision(null); setServiceMode(null); setCalculationBasis(null);
    }
    try {
      // Pure reads: stale responses must be discarded BEFORE any shared draft writes.
      const [serviceDates, currentStart] = await Promise.all([
        ordersMutationClient.getServiceDates(caseNo, { signal: controller.signal }),
        ordersQueryClient.getActualStart(caseNo, { signal: controller.signal }),
      ]);
      if (!current()) return;
      if (serviceDates.case_no !== caseNo) throw new Error('服務日期回讀案件編號不一致。');
      if (receipt && serviceDates.current_version !== receipt.confirmed_version) setSuccess(null);
      if (currentStart.case_no !== caseNo) throw new Error('服務日期精算回讀案件編號不一致。');
      if (currentStart.order_version !== serviceDates.order_version
        || (currentStart.scheduling_version ?? 0) !== serviceDates.scheduling_version) {
        throw new Error('實際開始日與服務日期版本不同，尚未更新；請重新精算。');
      }
      if (previous && (serviceDates.order_version < previous.order_version
        || serviceDates.scheduling_version < previous.scheduling_version)) {
        throw new Error('服務日期回讀版本落後，尚未更新；請重新讀取。');
      }
      if (pending?.kind === 'superseded' && (serviceDates.current_version === null
        || serviceDates.current_version < pending.currentVersion)) {
        throw new Error('尚未讀到目前正式日期版本；原收據仍保留，請重新讀取。');
      }
      let dates = serviceDates.current_dates;
      let calculated: SchedulePrecisionResult | null = null;
      let modeValue: ServiceMode | null = null;
      let basis: { date: string; confirmed: boolean } | null = null;
      let nextStartPreview: ActualStartPreview | null = null;
      let range = serviceDates.selectable_dates;
      let recommendation: string[] = [];
      if (mode === 'calculate') {
        const calendarDetail = await ordersQueryClient.getOrderCalendarDetail(caseNo, { signal: controller.signal });
        if (!current()) return;
        if (calendarDetail.case_no !== caseNo) {
          throw new Error('服務日期精算回讀案件編號不一致。');
        }
        const basisDate = inputDate ?? currentStart.current_actual_start_date ?? currentStart.planned_start_date;
        basis = { date: basisDate, confirmed: basisDate === currentStart.current_actual_start_date };
        modeValue = calendarDetail.service_mode;
        calculated = await schedulePrecisionClient.calculate({
          case_no: caseNo,
          actual_start_date: basis.date,
          target_service_days: serviceDates.contracted_service_days,
          service_mode: modeValue,
        });
        if (!current()) return;
        if (calculated.actual_start_date !== basis.date || calculated.target_service_days !== serviceDates.contracted_service_days) {
          throw new Error('精算結果與此次開始日或合約天數不一致，請重新精算。');
        }
        range = serviceDateRange(serviceDates, basis.date);
        recommendation = calculated.day_by_day.filter((day) => day.is_work_day).map((day) => day.date);
        if (basis.date !== currentStart.current_actual_start_date) {
          nextStartPreview = await orderActualStartClient.preview(caseNo, { new_actual_start_date: basis.date }, { signal: controller.signal });
          if (!current()) return;
          if ((nextStartPreview.operation === 'date_only' ? nextStartPreview.case_no : nextStartPreview.actual_start.case_no) !== caseNo
            || nextStartPreview.after_actual_start_date !== basis.date || nextStartPreview.order_version !== serviceDates.order_version
            || (nextStartPreview.scheduling_version ?? 0) !== serviceDates.scheduling_version) {
            throw new Error('開始日核對結果已變更，請重新精算。');
          }
          if (nextStartPreview.operation === 'reschedule') recommendation = nextStartPreview.actual_start.official_service_dates;
        }
        if (recommendation.length !== serviceDates.contracted_service_days || recommendation.some((date) => !range.includes(date))) {
          throw new Error('精算結果超出目前允許的日期範圍或天數；未刪除任何建議日期，也尚未保存。請核對排休條件。');
        }
        dates = hasManualChanges ? [...selectedDates] : recommendation;
      }
      const liveRecovery = recoveryFromServiceDatesDraft(caseNo);
      if (!current() || actionInFlight.current.has(caseNo)
        || (mode === 'resume'
          ? liveRecovery?.kind !== 'superseded' || orderMutationFlowStore.getServiceDatesDraft(caseNo)?.receiptView !== receipt
          : liveRecovery !== null)) return;
      const draft = orderMutationFlowStore.getServiceDatesDraft(caseNo);
      if (draft?.queryView !== previous || draft?.receiptView !== receipt
        || draft?.idempotencyKey !== originalKey) return;
      // A same-basis unsaved draft survives a read; a saved arrangement is never recalculated by a read.
      const continuingStart = draft?.calculation?.startPreview
        && orderMutationFlowStore.getActualStart(caseNo)?.command.payload.preview_fingerprint === draft.calculation.startPreview.preview_fingerprint;
      const keepDraft = mode === 'read' && draft?.receiptView === null && draft.selectedDates.length > 0
        && (!!draft.calculation || continuingStart || (draft.queryView?.order_version === serviceDates.order_version
          && draft.queryView?.scheduling_version === serviceDates.scheduling_version
          && draft.queryView?.current_version === serviceDates.current_version));
      if (keepDraft) dates = [...draft.selectedDates];
      const retainedCalculation = keepDraft ? draft?.calculation : undefined;
      if (retainedCalculation) {
        range = serviceDateRange(serviceDates, retainedCalculation.startDate);
        nextStartPreview = retainedCalculation.startPreview;
      }
      // This validated read starts a fresh preview lifecycle, never an unresolved command.
      orderMutationFlowStore.resetServiceDatesDraft(caseNo);
      orderMutationFlowStore.setServiceDatesQueryReady(caseNo, continuingStart && mode === 'read' && previous ? previous : serviceDates);
      orderMutationFlowStore.setServiceDatesCalculation(caseNo, basis ? { startDate: basis.date, startPreview: nextStartPreview } : retainedCalculation);
      selectServiceDates(caseNo, dates);
      updateServiceDatesReason(caseNo, AUTOMATIC_CONFIRMATION_REASON);
      setQueryView({ ...serviceDates, selectable_dates: range }); setSelectedDates(dates);
      setActualStart(currentStart);
      setStartDate(basis?.date ?? retainedCalculation?.startDate ?? currentStart.current_actual_start_date ?? currentStart.planned_start_date);
      setStartPreview(nextStartPreview);
      setInputInvalid(false);
      setSuggestedDates(recommendation);
      setManualNeedsReview(mode === 'calculate' && hasManualChanges);
      setPrecision(calculated); setServiceMode(modeValue); setCalculationBasis(basis);
      setHasManualChanges(keepDraft || (mode === 'calculate' && hasManualChanges));
      setBasisNotice(basis === null ? null
        : `${basis.confirmed ? '已依正式實際開始日更新' : '已依此次輸入開始日試算'}服務日期，請核對後再確認。${hasManualChanges ? '先前人工選日已保留，請選擇採用新建議或重新核對人工選日。' : ''}`);
      if (continuingStart && mode === 'read') {
        setBasisNotice(`此次開始日 ${currentStart.current_actual_start_date ?? '尚未確認'}；服務日期尚未完成，請接續核對保存。`);
      }
      if (retainedCalculation && !continuingStart && mode === 'read'
        && (previous?.order_version !== serviceDates.order_version || previous?.scheduling_version !== serviceDates.scheduling_version
          || previous?.current_version !== serviceDates.current_version)) {
        setInputInvalid(true); setStartPreview(null);
        setBasisNotice('案件資料已更新；已保留此次開始日與人工選日，請重新精算並核對後再保存。');
      }
      if (mode === 'resume') {
        // Explicitly adopting the current formal arrangement resolves the pending view update, without recalculating it.
        setAttemptedCalculationRevision(calculationRevision);
        setSuccess(`已載入目前正式日期版本 #${serviceDates.current_version}，請核對後再確認；未重送原操作。`);
        onObserved?.();
      }
    } catch (caught) {
      if (!current()) return;
      setError(errorMessage(caught));
      setSuccess(null);
      if (mode !== 'resume') setQueryView(null);
      setBasisNotice(mode === 'calculate' ? '服務日期尚未更新，請重新精算；目前正式日期未被此試算修改。' : null);
      setPrecision(null); setServiceMode(null); setCalculationBasis(null);
    } finally {
      if (current()) { readController.current = null; setWorking(null); }
    }
  };

  const previousProjection = useRef(projectionRevision);
  useEffect(() => {
    if (previousProjection.current === projectionRevision || working !== null || isRecoveryActive || startUnresolved || needsBasisUpdate) return;
    previousProjection.current = projectionRevision;
    // External mutations refresh formal facts; a read never recalculates a saved arrangement.
    void loadServiceDates('read');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectionRevision, working, isRecoveryActive, startUnresolved, needsBasisUpdate]);

  const changeStartDate = (value: string) => {
    readController.current?.abort();
    readController.current = null;
    calculationSequence.current += 1;
    setStartDate(value); setPreview(null); setStartPreview(null); setStartConfirmationReady(false);
    setPrecision(null); setSuccess(null); setInputInvalid(true); setWorking(null);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || !Number.isFinite(Date.parse(`${value}T00:00:00Z`))
      || new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) !== value) {
      setError('請輸入完整有效的開始日期。'); return;
    }
    void loadServiceDates('calculate', value);
  };

  const finishStartConfirmation = () => {
    setStartPreview(null); setStartConfirmationReady(false);
    setHasManualChanges(false); setManualNeedsReview(false); setInputInvalid(false);
    orderMutationFlowStore.setServiceDatesCalculation(caseNo, undefined);
    if (startPreview) {
      setActualStart((value) => value ? { ...value, current_actual_start_date: startPreview.after_actual_start_date } : value);
      setCalculationBasis({ date: startPreview.after_actual_start_date, confirmed: true });
      setBasisNotice('實際開始日與此次服務日期已保存並回讀。');
    }
  };

  useEffect(() => {
    if (!needsBasisUpdate) return;
    setPreview(null);
    setStartConfirmationReady(false);
    if (isRecoveryActive || actionInFlight.current.has(caseNo)) {
      setBasisNotice('日期基準已變更；待目前操作結果確認後，會接續更新。');
      return;
    }
    void loadServiceDates('calculate');
    // A blocked revision is not consumed. Resume when its write/readback settles,
    // but do not retry failed reads forever or recalculate on unrelated refreshes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseNo, calculationRevision, needsBasisUpdate, isRecoveryActive, working]);

  const changeDate = (date: string, checked: boolean) => {
    if (queryView === null || isRecoveryActive || needsBasisUpdate || readController.current !== null) return;
    const nextSet = new Set(selectedDates);
    if (checked) nextSet.add(date);
    else nextSet.delete(date);
    const nextDates = [...nextSet].sort();
    selectServiceDates(caseNo, nextDates);
    setSelectedDates(nextDates);
    setPreview(null);
    setStartConfirmationReady(false);
    setSuccess(null);
    setHasManualChanges(true);
  };

  const runPreview = async () => {
    if (actionInFlight.current.has(caseNo) || isRecoveryActive || needsBasisUpdate || readController.current !== null) return;
    actionInFlight.current.add(caseNo);
    const controller = new AbortController();
    readController.current = controller;
    const basisSequence = calculationSequence.current;
    setWorking('preview');
    setError(null);
    setSuccess(null);
    let conflictMessage: string | null = null;
    try {
      if (startPreview) {
        assertStartDates(startPreview, selectedDates);
        setStartConfirmationReady(true);
        setSuccess('服務日期確認內容已準備。');
        return;
      }
      const nextPreview = await previewServiceDatesFlow(caseNo, { signal: controller.signal });
      if (renderedCaseNo.current !== caseNo || calculationSequence.current !== basisSequence) return;
      if (nextPreview.case_no !== caseNo) {
        throw new Error('服務日期確認預覽案件識別不一致。');
      }
      setPreview(nextPreview);
      setSuccess('服務日期確認內容已準備。');
    } catch (caught) {
      if (renderedCaseNo.current !== caseNo || calculationSequence.current !== basisSequence) return;
      setError(errorMessage(caught));
      if (isServiceDateConflict(caught)) conflictMessage = errorMessage(caught);
    } finally {
      if (readController.current === controller) readController.current = null;
      actionInFlight.current.delete(caseNo);
      if (renderedCaseNo.current === caseNo && calculationSequence.current === basisSequence) setWorking(null);
      if (conflictMessage && renderedCaseNo.current === caseNo) {
        await loadServiceDates('read');
        if (renderedCaseNo.current === caseNo) setError(`${conflictMessage}；已重新讀取正式資料，請重新核對。`);
      }
    }
  };

  const runApply = async () => {
    if (actionInFlight.current.has(caseNo) || isRecoveryActive || needsBasisUpdate || readController.current !== null) return;
    actionInFlight.current.add(caseNo);
    const basisSequence = calculationSequence.current;
    setWorking('apply');
    setError(null);
    setSuccess(null);
    let conflictMessage: string | null = null;
    try {
      if (startPreview) {
        assertStartDates(startPreview, selectedDates);
        await saveServiceDatesStart(caseNo, startPreview);
        if (renderedCaseNo.current === caseNo) {
          setBasisNotice(`實際開始日 ${startPreview.after_actual_start_date} 已保存；服務日期正在接續確認。`);
          onObserved?.();
        }
        await refreshServiceDatesAfterStart(caseNo, startPreview);
        const freshPreview = await previewServiceDatesFlow(caseNo);
        if (freshPreview.case_no !== caseNo || !sameServiceDates(freshPreview.service_dates, selectedDates)) {
          throw new Error('開始日已保存，但服務日期核對結果不同，請重新核對；未套用新日期。');
        }
      }
      const receipt = await applyServiceDatesFlow(caseNo);
      if (renderedCaseNo.current !== caseNo || calculationSequence.current !== basisSequence) return;
      const observed = orderMutationFlowStore.getServiceDatesDraft(caseNo);
      if (observed?.status !== 'observed' || observed.queryView === null) {
        throw new Error('服務日期已套用，但未取得正式回讀狀態。');
      }
      setQueryView(observed.queryView);
      setSelectedDates(observed.queryView.current_dates);
      setPreview(null);
      finishStartConfirmation();
      setSuccess(`服務日期已確認並回讀版本 #${receipt.confirmed_version}。`);
      onObserved?.();
    } catch (caught) {
      if (renderedCaseNo.current !== caseNo || calculationSequence.current !== basisSequence) return;
      captureRecovery();
      const startResult = orderMutationFlowStore.getActualStart(caseNo);
      setError(`${startPreview && startResult?.status === 'observed' ? '實際開始日已保存，服務日期尚未完成。' : ''}${errorMessage(caught)}`);
      setStartConfirmationReady(false);
      if (isServiceDateConflict(caught)) conflictMessage = errorMessage(caught);
    } finally {
      actionInFlight.current.delete(caseNo);
      if (renderedCaseNo.current === caseNo && calculationSequence.current === basisSequence) setWorking(null);
      if (conflictMessage && renderedCaseNo.current === caseNo) {
        await loadServiceDates('read');
        if (renderedCaseNo.current === caseNo) setError(`${conflictMessage}；已重新讀取正式資料，請重新核對。`);
      }
    }
  };

  const retryApply = async () => {
    if (actionInFlight.current.has(caseNo) || recovery?.caseNo !== caseNo || recovery.kind !== 'outcome_unknown') return;
    actionInFlight.current.add(caseNo);
    setWorking('apply');
    setError(null);
    try {
      const receipt = await retryServiceDatesApplyFlow(caseNo);
      if (renderedCaseNo.current !== caseNo) return;
      const observed = orderMutationFlowStore.getServiceDatesDraft(caseNo);
      if (observed?.status !== 'observed' || observed.queryView === null) {
        throw new Error('服務日期已套用，但未取得正式回讀狀態。');
      }
      setQueryView(observed.queryView);
      setSelectedDates(observed.queryView.current_dates);
      setPreview(null);
      finishStartConfirmation();
      setSuccess(`服務日期已確認並回讀版本 #${receipt.confirmed_version}。`);
      onObserved?.();
    } catch (caught) {
      if (renderedCaseNo.current !== caseNo) return;
      captureRecovery();
      setError(errorMessage(caught));
    } finally {
      actionInFlight.current.delete(caseNo);
      if (renderedCaseNo.current === caseNo) setWorking(null);
    }
  };

  const retryObservation = async () => {
    if (actionInFlight.current.has(caseNo) || recovery?.caseNo !== caseNo || recovery.kind !== 'observation_failed') return;
    actionInFlight.current.add(caseNo);
    setWorking('apply');
    setError(null);
    try {
      const observed = await retryServiceDatesObservationFlow(caseNo);
      if (renderedCaseNo.current !== caseNo) return;
      if (observed.case_no !== caseNo) {
        throw new Error('服務日期正式回讀案件識別不一致。');
      }
      setQueryView(observed);
      setSelectedDates(observed.current_dates);
      setPreview(null);
      finishStartConfirmation();
      setSuccess(`服務日期已確認並回讀版本 #${recovery.confirmedVersion}。`);
      onObserved?.();
    } catch (caught) {
      if (renderedCaseNo.current !== caseNo) return;
      captureRecovery();
      setError(errorMessage(caught));
    } finally {
      actionInFlight.current.delete(caseNo);
      if (renderedCaseNo.current === caseNo) setWorking(null);
    }
  };

  const requiredDateCount = queryView?.contracted_service_days ?? 0;
  const canPreview = queryView !== null
    && selectedDates.length === requiredDateCount
    && selectedDates.length > 0
    && selectedDates.every((date) => queryView.selectable_dates.includes(date))
    && working === null
    && !isRecoveryActive
    && !needsBasisUpdate && !inputInvalid && !manualNeedsReview && !startUnresolved && !actualStart?.service_data_locked;
  const canApply = (preview !== null || startConfirmationReady) && canPreview;

  return (
    <section className="order-service-dates-panel" aria-label={`案件 ${caseNo} 服務日期設定`}>
      <label>此次試算開始日
        <input type="date" aria-label="此次試算開始日" value={startDate}
          disabled={saving || working === 'preview' || isRecoveryActive || startUnresolved || actualStart?.service_data_locked}
          onChange={(event) => changeStartDate(event.target.value)} />
      </label>
      {actualStart && <p>原訂日：{actualStart.planned_start_date}；已保存實際開始日：{actualStart.current_actual_start_date ?? '尚未確認'}。修改輸入會自動試算，完成確認後才保存。</p>}
      {actualStart?.service_data_locked && <p role="status">服務資料已鎖定，目前只能查看正式日期。</p>}
      <button
        type="button"
        className="order-v2-open-drawer"
        disabled={working !== null || isRecoveryActive || startUnresolved || actualStart?.service_data_locked}
        onClick={() => void loadServiceDates('calculate', startDate || undefined)}
      >
        {working === 'load' ? '正在更新服務日期…' : '精算天數並設定服務日期'}
      </button>

      {error !== null && <p role="alert">{error}</p>}
      {error !== null && !isRecoveryActive && !startUnresolved && (
        <button type="button" disabled={working !== null} onClick={() => void loadServiceDates('read')}>重新讀取正式服務日期</button>
      )}
      {basisNotice !== null && <p role="status">{basisNotice}</p>}
      {calculationBasis !== null && (
        <div className="order-case-review-note" aria-label="服務日期計算基準">
          <strong>{calculationBasis.confirmed ? '正式實際開始日' : '此次試算開始日（尚未保存）'}</strong>
          <span>：{calculationBasis.date}</span>
          {onOpenActualStart !== undefined && (
            <button type="button" className="order-v2-open-drawer" onClick={onOpenActualStart}>
              確認／更正實際開始日
            </button>
          )}
        </div>
      )}
      {success !== null && <p role="status">{success}</p>}
      {startPreview?.operation === 'reschedule' && <p role="status">本案確認開始日會同步建立或重排既定人員的正式服務安排。以下建議為後端正式重排日期，請核對後再保存。</p>}
      {startUnresolved && !saving && <div role="status">
        <p>開始日保存或回讀尚未完成，服務日期未確認。請先確認開始日結果再接續。</p>
        {startPreview && <button type="button" onClick={() => void runApply()}>讀取開始日結果並接續保存</button>}
        {onOpenActualStart && <button type="button" onClick={onOpenActualStart}>查看實際開始日操作</button>}
      </div>}
      {manualNeedsReview && <div role="status">
        <p>計算條件已變更，原人工選日尚未套用新建議。</p>
        <button type="button" disabled={working !== null} onClick={() => {
          selectServiceDates(caseNo, suggestedDates); setSelectedDates(suggestedDates);
          setManualNeedsReview(false); setHasManualChanges(false); setPreview(null); setStartConfirmationReady(false);
        }}>採用新建議</button>
        <button type="button" disabled={working !== null} onClick={() => {
          if (selectedDates.some((date) => !queryView?.selectable_dates.includes(date))) {
            setError('原人工選日包含新範圍以外的日期，請調整選日或採用新建議。'); return;
          }
          setManualNeedsReview(false); setError(null);
        }}>保留人工選日並重新核對</button>
      </div>}
      {recovery?.caseNo === caseNo && recovery.kind === 'outcome_unknown' && (
        <button
          type="button"
          className="order-v2-open-drawer"
          disabled={working !== null}
          onClick={() => void retryApply()}
        >
          {working === 'apply' ? '以原操作重新確認中…' : '以原操作重新確認服務日期'}
        </button>
      )}
      {recovery?.caseNo === caseNo && recovery.kind === 'observation_failed' && (
        <button
          type="button"
          className="order-v2-open-drawer"
          disabled={working !== null}
          onClick={() => void retryObservation()}
        >
          {working === 'apply' ? '重新讀取服務日期結果中…' : '只重新讀取服務日期結果'}
        </button>
      )}
      {recovery?.caseNo === caseNo && recovery.kind === 'superseded' && (
        <div role="status">
          <p>本次收據為版本 #{recovery.confirmedVersion}；目前正式日期已更新為版本 #{recovery.currentVersion}。請載入目前日期核對，不要重送原操作。</p>
          <button type="button" className="order-v2-open-drawer" disabled={working !== null}
            onClick={() => void loadServiceDates('resume')}>載入目前正式服務日期</button>
        </div>
      )}
      {recovery?.caseNo === caseNo && recovery.kind === 'observation_in_progress' && (
        <p role="status">服務日期確認正在處理或回讀中，暫不可建立新操作。</p>
      )}

      {queryView !== null && (
        <>
          {queryView.bound_staff.length > 0 && (
            <div role="status" className="order-v2-inline-notice">
              <strong>既定服務人員：</strong>
              {queryView.bound_staff.map((staff) => staff.staff_name).join('、')}
              <span>。此歷史綁定已保留，不需重新挑選候選或再次推薦。</span>
            </div>
          )}
          {precision !== null && serviceMode !== null && <dl className="order-v2-business-summary" aria-label="建議服務日期摘要">
            <div><dt>排休類型</dt><dd>{serviceMode}</dd></div>
            <div><dt>建議開始</dt><dd>{precision.actual_start_date}</dd></div>
            <div><dt>建議完工</dt><dd>{suggestedDates.at(-1) ?? precision.actual_end_date}</dd></div>
            <div><dt>合約服務日</dt><dd>{requiredDateCount} 天</dd></div>
          </dl>}
          <dl className="order-v2-business-summary" aria-label="此次選定服務日期摘要" aria-live="polite">
            <div><dt>選定開始</dt><dd>{selectedDates[0] ?? '尚未選取'}</dd></div>
            <div><dt>選定最後服務日</dt><dd>{selectedDates.at(-1) ?? '尚未選取'}</dd></div>
            <div><dt>已選服務日</dt><dd>{selectedDates.length} / {requiredDateCount} 天</dd></div>
            {selectedDates.length !== requiredDateCount && <div><dt>待調整</dt><dd>{selectedDates.length < requiredDateCount ? `尚差 ${requiredDateCount - selectedDates.length}` : `超出 ${selectedDates.length - requiredDateCount}`} 天</dd></div>}
          </dl>

          <div className="service-calendar-workbench-layout">
            <div className="calendar-matrix-card">
              <div className="calendar-month-header">
                <h3 style={{ fontSize: '1.05rem', fontWeight: 750, color: '#0f766e', margin: 0 }}>
                  📅 正式服務日期確認（日曆排盤）
                </h3>
                <span>已選 {selectedDates.length} / {requiredDateCount} 天</span>
              </div>
              <p className="order-case-review-note">請逐日核對服務安排；選取國定假日即代表已確認該日安排服務，不需另行登錄協調結果。</p>

              <div
                className="calendar-days-grid"
                role="group"
                aria-label="服務日期月曆"
                data-surface-id="orders.date.service-date-selection"
              >
                {['日', '一', '二', '三', '四', '五', '六'].map((weekday) => <span key={weekday} className="service-date-weekday" aria-hidden="true">{weekday}</span>)}
                {queryView.selectable_dates.length > 0 && Array.from({
                  length: new Date(`${queryView.selectable_dates[0]}T00:00:00`).getDay(),
                }).map((_, index) => <div key={`calendar-leading-${index}`} aria-hidden="true" />)}
                {[...new Set([...queryView.selectable_dates, ...selectedDates])].sort().map((date) => {
                  const selected = selectedDates.includes(date);
                  const day = precision?.day_by_day.find((value) => value.date === date);
                  return (
                    <button
                      key={date}
                      data-control-id="orders.date.service-date-select"
                      type="button"
                      aria-label={`服務日期 ${date}`}
                      aria-pressed={selected}
                      title={`${date}${day?.holiday_name ? ` ${day.holiday_name}` : day?.is_rest_day ? ' 建議休假' : ''}`}
                      className={`calendar-date-cell${selected ? ' selected' : ''}`}
                      disabled={working !== null || isRecoveryActive || needsBasisUpdate || inputInvalid || startUnresolved || actualStart?.service_data_locked}
                      onClick={() => changeDate(date, !selected)}
                    >
                      <time dateTime={date} title={date}>{date.slice(5).replace('-', '/')}</time>
                      {day?.holiday_name && <small className="service-date-holiday" aria-label={day.holiday_name}>假日</small>}
                      {!day?.holiday_name && day?.is_rest_day && !selected && <small>休</small>}
                      {selected && <span className="calendar-date-cell-badge">服務日</span>}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          <button
            type="button"
            className="order-v2-open-drawer"
            disabled={!canPreview}
            onClick={() => void runPreview()}
          >
            {working === 'preview' ? '檢查確認內容中…' : '確認服務日期'}
          </button>
        </>
      )}

      {(preview !== null || startConfirmationReady) && !needsBasisUpdate && (
        <>
          <dl className="order-v2-business-summary" aria-label="服務日期確認內容">
            <div><dt>目前版本</dt><dd>{queryView?.current_version == null ? '首次確認' : `#${queryView.current_version}`}</dd></div>
            {startPreview && <div><dt>此次確認實際開始日</dt><dd>{startPreview.after_actual_start_date}</dd></div>}
            <div><dt>確認日期</dt><dd>{(preview?.service_dates ?? selectedDates).join('、')}</dd></div>
          </dl>
          <p>系統會自動記錄「確認正式服務日期」，不需另外填寫原因。</p>
          <button
            type="button"
            className="order-v2-open-drawer"
            disabled={!canApply}
            onClick={() => void runApply()}
          >
            {working === 'apply' ? '確認並回讀中…' : '完成服務日期確認'}
          </button>
        </>
      )}

      {queryView !== null && queryView.current_dates.length > 0 && (
        <dl className="order-v2-business-summary" aria-label="正式服務日期回讀" tabIndex={-1} ref={readbackElement}>
          <div><dt>正式版本</dt><dd>{queryView.current_version === null ? '未建立' : `#${queryView.current_version}`}</dd></div>
          <div><dt>正式服務日期</dt><dd>{queryView.current_dates.join('、')}</dd></div>
        </dl>
      )}
    </section>
  );
};

export default OrderServiceDatesPanel;

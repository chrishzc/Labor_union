import { useUnsavedDraft } from './UnsavedChanges';
import { useSaveValidation } from './useSaveValidation';
import { useStaffIdentityLabels } from './StaffIdentityProvider';
import { useEffect, useRef, useState, type FC } from 'react';
import type {
  ServiceDateConfirmationQueryView,
} from '../api/orders/order_mutation_schemas';
import { ordersMutationClient } from '../api/orders/order_mutation_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import type { AssignmentPlan } from '../api/orders/order_query_schemas';
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
import { ApiHttpError } from '../api/shared/typed_errors';
import { orderActualStartClient, type ActualStartPreview } from '../api/orders/order_actual_start_client';
import type { ActualStart } from '../api/orders/order_query_schemas';
import { assertStartDates, isServiceDateConflict, refreshServiceDatesAfterStart, sameServiceDates, saveServiceDatesStart, serviceDateRange } from '../adapters/orders/service_date_start_flow';
import { HistoricalRestartArrangementPanel } from './HistoricalRestartArrangementPanel';
import { OrderServiceDateCalendar } from './OrderServiceDateCalendar';
import { OrderOfficialDateCorrectionPanel } from './OrderOfficialDateCorrectionPanel';

interface OrderServiceDatesPanelProps {
  caseNo: string;
  onObserved?: () => void;
  onOpenActualStart?: () => void;
  calculationRevision?: number;
  projectionRevision?: number;
  onBusyChange?: (busy: boolean) => void;
  currentAssignmentPlan?: AssignmentPlan | null;
  view?: 'dates' | 'arrangement';
  onOpenArrangement?: () => void;
  onOpenDates?: () => void;
  onArrangementPendingChange?: (pending: boolean) => void;
  completedCorrection?: boolean;
  coordinatedStart?: boolean;
}

type WorkingAction = 'load' | 'preview' | 'apply' | null;
type DateLoadMode = 'read' | 'calculate' | 'resume';
type ServiceMode = '休周六' | '休周日' | '週休2日' | '連續服務';
type ServiceDatesRecovery =
  | { caseNo: string; kind: 'outcome_unknown' }
  | { caseNo: string; kind: 'observation_failed'; confirmedVersion: number }
  | { caseNo: string; kind: 'superseded'; confirmedVersion: number; currentVersion: number }
  | { caseNo: string; kind: 'observation_in_progress' };
const REST_WEEKDAYS = [
  { value: 0, label: '星期一' }, { value: 1, label: '星期二' }, { value: 2, label: '星期三' },
  { value: 3, label: '星期四' }, { value: 4, label: '星期五' }, { value: 5, label: '星期六' },
  { value: 6, label: '星期日' },
];

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

export const OrderServiceDatesPanel: FC<OrderServiceDatesPanelProps> = (props) => props.completedCorrection
  ? <OrderOfficialDateCorrectionPanel caseNo={props.caseNo} revision={props.projectionRevision} view={props.view} onOpenArrangement={props.onOpenArrangement} onOpenDates={props.onOpenDates} onObserved={props.onObserved} onBusyChange={props.onBusyChange} />
  : <OrderPreCompletionServiceDatesPanel {...props} />;

const OrderPreCompletionServiceDatesPanel: FC<OrderServiceDatesPanelProps> = ({ caseNo, onObserved, onOpenActualStart, calculationRevision = 0, projectionRevision = 0, onBusyChange, currentAssignmentPlan, view = 'dates', onOpenArrangement, onOpenDates, onArrangementPendingChange, coordinatedStart = false }) => {
  const staffIdentity = useStaffIdentityLabels();
  const [working, setWorking] = useState<WorkingAction>(null);
  const [queryView, setQueryView] = useState<ServiceDateConfirmationQueryView | null>(null);
  const historicalArrangementCase=useRef<string|null>(null);
  if(queryView?.case_no===caseNo && queryView.arrangement_pending) historicalArrangementCase.current=caseNo;
  const [precision, setPrecision] = useState<SchedulePrecisionResult | null>(null);
  const initialCalculation = useRef('');
  const [serviceMode, setServiceMode] = useState<ServiceMode | null>(null);
  const [originalServiceType, setOriginalServiceType] = useState<string | null>(null);
  const [restWeekdays, setRestWeekdays] = useState<number[] | null>(null);
  const [selectedDates, setSelectedDates] = useState<string[]>([]);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [basisNotice, setBasisNotice] = useState<string | null>(null);
  const [calculationBasis, setCalculationBasis] = useState<{ date: string; confirmed: boolean } | null>(null);
  const [hasManualChanges, setHasManualChanges] = useState(false);
  const [startDate, setStartDate] = useState('');
  const [calendarMonth, setCalendarMonth] = useState('');
  useEffect(() => { if (startDate) setCalendarMonth(startDate.slice(0, 7)); }, [startDate]);
  const [actualStart, setActualStart] = useState<ActualStart | null>(null);
  const [startPreview, setStartPreview] = useState<ActualStartPreview | null>(null);
  const [suggestedDates, setSuggestedDates] = useState<string[]>([]);
  const [manualNeedsReview, setManualNeedsReview] = useState(false);
  const [inputInvalid, setInputInvalid] = useState(false);
  const [, setRecoveryRevision] = useState(0);
  const [attemptedCalculationRevision, setAttemptedCalculationRevision] = useState(0);
  const [arrangementBusy, setArrangementBusy] = useState(false);
  const actionInFlight = useRef(new Set<string>());
  const saveDatesIntent = useRef(true);
  const saveValidation = useSaveValidation();
  const startDateRef = useRef<HTMLInputElement>(null);
  const dateSelectionRef = useRef<HTMLDivElement>(null);
  const readbackElement = useRef<HTMLDivElement | null>(null);
  const nextStepElement = useRef<HTMLDivElement | null>(null);
  const calculationSequence = useRef(0);
  const readController = useRef<AbortController | null>(null);
  const renderedCaseNo = useRef(caseNo);
  renderedCaseNo.current = caseNo;
  const recovery = recoveryFromServiceDatesDraft(caseNo);
  const isRecoveryActive = recovery?.caseNo === caseNo;
  const needsBasisUpdate = calculationRevision > attemptedCalculationRevision;
  const startFlow = orderMutationFlowStore.getActualStart(caseNo);
  const startUnresolved = startFlow !== undefined && startFlow.status !== 'observed';
  const saving = working === 'apply' || arrangementBusy;
  const arrangementPending = queryView?.arrangement_pending ?? false;
  const effectiveServiceDates = queryView !== null
    && currentAssignmentPlan?.case_no === caseNo
    && currentAssignmentPlan.scheduling_version === queryView.scheduling_version
    && currentAssignmentPlan.assignments.length > 0
    ? [...new Set(currentAssignmentPlan.assignments.flatMap((segment) => segment.official_service_dates))].sort()
    : null;
  const confirmationSupersededBySchedule = effectiveServiceDates !== null
    && queryView !== null
    && queryView.current_dates.length > 0
    && !sameServiceDates(queryView.current_dates, effectiveServiceDates);
  const displayedDates = effectiveServiceDates ?? selectedDates;
  const routineCalculationNotice = basisNotice === '已依此次輸入開始日試算服務日期，請核對後再確認。'
    || basisNotice === '已依正式實際開始日更新服務日期，請核對後再確認。';

  useEffect(() => { onBusyChange?.(saving); return () => onBusyChange?.(false); }, [saving, onBusyChange]);
  useEffect(() => { onArrangementPendingChange?.(arrangementPending); }, [arrangementPending, onArrangementPendingChange]);
  useEffect(() => {
    if (success?.startsWith('服務日期已確認並回讀')) {
      (arrangementPending && onOpenArrangement ? nextStepElement.current : readbackElement.current)?.focus();
    }
  }, [success, arrangementPending, onOpenArrangement]);

  useEffect(() => {
    setAttemptedCalculationRevision(0);
    setWorking(null);
    setQueryView(null);
    setPrecision(null);
    setServiceMode(null);
    setOriginalServiceType(null);
    setRestWeekdays(null);
    setSelectedDates([]);

    setError(null);
    setSuccess(null);
    setBasisNotice(null);
    setCalculationBasis(null);
    setHasManualChanges(false);
    const retained = orderMutationFlowStore.getServiceDatesDraft(caseNo);
    setStartDate(retained?.calculation?.startDate ?? '');
    setStartPreview(retained?.calculation?.startPreview ?? null);

    setActualStart(null);
    setManualNeedsReview(false);
    setInputInvalid(false);
    setSuggestedDates([]);
    if (retained?.calculation && retained.status !== 'observed') {
      setQueryView(retained.queryView);
      setSelectedDates(retained.selectedDates);
      setHasManualChanges(true);
      setManualNeedsReview(retained.calculation.needsManualReview ?? false);
      setSuggestedDates(retained.calculation.suggestedDates ?? []);
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

  const loadServiceDates = async (mode: DateLoadMode, inputDate?: string, weekdayOverride = restWeekdays, replaceManualDates = false) => {
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
    setError(null);
    if (mode !== 'read') setSuccess(null);

    if (mode === 'calculate') {
      setBasisNotice(hasManualChanges
        ? '正在重新精算；先前人工調整將由新建議取代，請重新核對。'
        : '正在依目前日期基準更新服務日期與日曆。');
      setPrecision(null); setServiceMode(null); setCalculationBasis(null);
    }
    try {
      // Pure reads: stale responses must be discarded BEFORE any shared draft writes.
      const [serviceDates, currentStart, calendarDetail] = await Promise.all([
        ordersMutationClient.getServiceDates(caseNo, { signal: controller.signal }),
        ordersQueryClient.getActualStart(caseNo, { signal: controller.signal }),
        ordersQueryClient.getOrderCalendarDetail(caseNo, { signal: controller.signal }),
      ]);
      if (!current()) return;
      if (calendarDetail.case_no !== caseNo) throw new Error('服務方式回讀案件編號不一致。');
      setOriginalServiceType(calendarDetail.original_service_type ?? calendarDetail.service_mode);
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
      let modeValue: ServiceMode | null = calendarDetail.service_mode;
      let basis: { date: string; confirmed: boolean } | null = null;
      let nextStartPreview: ActualStartPreview | null = null;
      let range = serviceDates.selectable_dates;
      let recommendation: string[] = [];
      if (mode === 'calculate') {
        const basisDate = inputDate ?? currentStart.current_actual_start_date ?? currentStart.planned_start_date;
        basis = { date: basisDate, confirmed: basisDate === currentStart.current_actual_start_date };
        modeValue = calendarDetail.service_mode;
        if (weekdayOverride === null && modeValue === null) {
          throw new Error('請對照原始服務方式，人工選定休假星期；無固定週休請點選「無固定週休」。');
        }
        calculated = await schedulePrecisionClient.calculate({
          case_no: caseNo,
          actual_start_date: basis.date,
          target_service_days: serviceDates.contracted_service_days,
          service_mode: modeValue ?? calendarDetail.original_service_type ?? '人工排休',
          ...(weekdayOverride !== null ? { custom_rest_weekdays: weekdayOverride } : {}),
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
          if (nextStartPreview.operation === 'reschedule') {
            if (weekdayOverride !== null && !sameServiceDates(recommendation, nextStartPreview.actual_start.official_service_dates)) {
              throw new Error('人工選定的休假星期與既有正式重排不同，請使用既有排班異動流程；尚未保存。');
            }
            recommendation = nextStartPreview.actual_start.official_service_dates;
          }
        }
        if (recommendation.length !== serviceDates.contracted_service_days || recommendation.some((date) => !range.includes(date))) {
          throw new Error('精算結果超出目前允許的日期範圍或天數；未刪除任何建議日期，也尚未保存。請核對排休條件。');
        }
        dates = hasManualChanges && !replaceManualDates ? [...selectedDates] : recommendation;
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
      const reviewNeeded = mode === 'calculate' ? hasManualChanges && !replaceManualDates : retainedCalculation?.needsManualReview ?? false;
      const nextSuggestions = mode === 'read' ? retainedCalculation?.suggestedDates ?? recommendation : recommendation;
      orderMutationFlowStore.setServiceDatesCalculation(caseNo, basis ? { startDate: basis.date, startPreview: nextStartPreview, needsManualReview: reviewNeeded, suggestedDates: nextSuggestions } : retainedCalculation);
      selectServiceDates(caseNo, dates);
      updateServiceDatesReason(caseNo, '');
      setReason('');
      setQueryView({ ...serviceDates, selectable_dates: range }); setSelectedDates(dates);
      setActualStart(currentStart);
      setStartDate(basis?.date ?? retainedCalculation?.startDate ?? currentStart.current_actual_start_date ?? currentStart.planned_start_date);
      setStartPreview(nextStartPreview);
      setInputInvalid(false);
      setSuggestedDates(nextSuggestions);
      setManualNeedsReview(reviewNeeded);
      setPrecision(calculated); setServiceMode(modeValue); setCalculationBasis(basis);
      setHasManualChanges(keepDraft || (mode === 'calculate' && hasManualChanges && !replaceManualDates));
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
    setStartDate(value); setStartPreview(null);
    setPrecision(null); setSuccess(null); setInputInvalid(true); setWorking(null);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || !Number.isFinite(Date.parse(`${value}T00:00:00Z`))
      || new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) !== value) {
      setError('請輸入完整有效的開始日期。'); return;
    }
    void loadServiceDates('calculate', value);
  };

  const changeRestWeekdays = (next: number[]) => {
    readController.current?.abort(); readController.current = null;
    calculationSequence.current += 1;
    setRestWeekdays(next); setStartPreview(null);
    setPrecision(null); setSuccess(null); setInputInvalid(true); setWorking(null);
    if (next.length === 7) {
      setError('不能將每週七天全部設為休假，請保留至少一天服務日。'); return;
    }
    void loadServiceDates('calculate', startDate || undefined, next, true);
  };

  const finishStartConfirmation = (completedStart: ActualStartPreview | null = startPreview) => {
    setStartPreview(null);
    setHasManualChanges(false); setManualNeedsReview(false); setInputInvalid(false);
    orderMutationFlowStore.setServiceDatesCalculation(caseNo, undefined);
    if (completedStart) {
      setActualStart((value) => value ? { ...value, current_actual_start_date: completedStart.after_actual_start_date } : value);
      setCalculationBasis({ date: completedStart.after_actual_start_date, confirmed: true });
      setBasisNotice('實際開始日與此次服務日期已保存並回讀。');
    }
  };

  useEffect(() => {
    if (!needsBasisUpdate) return;


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


    setSuccess(null);
    setHasManualChanges(true);
  };

  const runApply = async (saveDates = saveDatesIntent.current) => {
    if (actionInFlight.current.has(caseNo) || isRecoveryActive || needsBasisUpdate || readController.current !== null) return;
    if (!saveValidation.validate([
      ...(actualStart && effectiveServiceDates === null ? [{ value: startDate, label: '實際開始日', ref: startDateRef, valid: /^\d{4}-\d{2}-\d{2}$/.test(startDate) && Number.isFinite(Date.parse(`${startDate}T00:00:00Z`)), message: '請填寫有效的實際開始日後再儲存。' }] : []),
      ...(saveDates ? [{ value: selectedDates.length, label: '服務日期', ref: dateSelectionRef, valid: selectedDates.length > 0 && selectedDates.length === (queryView?.contracted_service_days ?? 0), message: `請選滿 ${queryView?.contracted_service_days ?? 0} 天服務日期後再儲存。` }] : []),
    ])) return;
    saveDatesIntent.current = saveDates;
    actionInFlight.current.add(caseNo);
    const basisSequence = calculationSequence.current;
    setWorking('apply');
    setError(null);
    setSuccess(null);
    let conflictMessage: string | null = null;
    let candidate = startPreview;
    const stillCurrent = () => renderedCaseNo.current === caseNo && calculationSequence.current === basisSequence;
    try {
      if (!candidate && actualStart && startDate && actualStart.current_actual_start_date !== startDate) {
        candidate = await orderActualStartClient.preview(caseNo, { new_actual_start_date: startDate });
        if (!stillCurrent()) return;
        const previewCase = candidate.operation === 'date_only' ? candidate.case_no : candidate.actual_start.case_no;
        if (previewCase !== caseNo || candidate.after_actual_start_date !== startDate
          || candidate.order_version !== queryView?.order_version
          || (candidate.scheduling_version ?? 0) !== queryView?.scheduling_version) {
          throw new ApiHttpError(409, 'stale_preview', '開始日資料已變更，請重新讀取後核對。');
        }
        setStartPreview(candidate);
        orderMutationFlowStore.setServiceDatesCalculation(caseNo, { startDate, startPreview: candidate });
      }
      if (!saveDates && candidate?.operation === 'reschedule') {
        throw new Error('本案已有排班，請使用更正實際開始日核對各段排班調整。');
      }
      if (candidate) {
        assertStartDates(candidate, selectedDates);
        await saveServiceDatesStart(caseNo, candidate);
        if (renderedCaseNo.current === caseNo) {
          setBasisNotice(`實際開始日 ${candidate.after_actual_start_date} 已保存；服務日期正在接續確認。`);
          onObserved?.();
        }
        if (!stillCurrent()) return;
        if (!saveDates) {
          const current = await ordersMutationClient.getServiceDates(caseNo);
          if (!stillCurrent()) return;
          const startResult = orderMutationFlowStore.getActualStart(caseNo);
          if (current.case_no !== caseNo || current.order_version !== (startResult?.receipt?.order_version ?? candidate.order_version + 1)) {
            throw new Error('開始日已保存，但案件資料已更新，請重新讀取核對。');
          }
          orderMutationFlowStore.setServiceDatesQueryReady(caseNo, current);
          orderMutationFlowStore.updateServiceDatesSelection(caseNo, selectedDates);
          orderMutationFlowStore.setServiceDatesCalculation(caseNo, { startDate: candidate.after_actual_start_date, startPreview: candidate, needsManualReview: manualNeedsReview, suggestedDates });
          setQueryView(current);
          setActualStart(value => value ? { ...value, current_actual_start_date: candidate!.after_actual_start_date, order_version: current.order_version } : value);
          setCalculationBasis({ date: candidate.after_actual_start_date, confirmed: true });
          setBasisNotice('實際開始日已保存；請核對並儲存服務日期。');
          setSuccess('實際開始日已儲存；服務日期尚未儲存。');
          return;
        }
        await refreshServiceDatesAfterStart(caseNo, candidate);
        if (!stillCurrent()) return;
      }
      if (!saveDates) { setSuccess('實際開始日已儲存。'); return; }
      updateServiceDatesReason(caseNo, reason.trim());
      const freshPreview = await previewServiceDatesFlow(caseNo);
      if (!stillCurrent()) return;
      if (freshPreview.case_no !== caseNo || !sameServiceDates(freshPreview.service_dates, selectedDates)) {
        throw new Error('服務日期核對結果不同，請重新核對；未套用新日期。');
      }
      if (!candidate && (freshPreview.order_version !== queryView?.order_version || freshPreview.scheduling_version !== queryView?.scheduling_version)) {
        throw new ApiHttpError(409, 'stale_preview', '日期或案件資料已更新，請重新讀取後儲存。');
      }
      const receipt = await applyServiceDatesFlow(caseNo);
      if (renderedCaseNo.current !== caseNo || calculationSequence.current !== basisSequence) return;
      const observed = orderMutationFlowStore.getServiceDatesDraft(caseNo);
      if (observed?.status !== 'observed' || observed.queryView === null) {
        throw new Error('服務日期已套用，但未取得正式回讀狀態。');
      }
      setQueryView(observed.queryView);
      setSelectedDates(observed.queryView.current_dates);

      finishStartConfirmation(candidate);
      setSuccess(`服務日期已確認並回讀版本 #${receipt.confirmed_version}。`);
      onObserved?.();
      onOpenArrangement?.();
    } catch (caught) {
      if (renderedCaseNo.current !== caseNo || calculationSequence.current !== basisSequence) return;
      captureRecovery();
      const startResult = orderMutationFlowStore.getActualStart(caseNo);
      setError(`${candidate && startResult?.status === 'observed' ? saveDates ? '實際開始日已保存，服務日期尚未完成。' : '實際開始日已保存，回讀尚未完成。' : ''}${errorMessage(caught)}`);

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

      finishStartConfirmation();
      setSuccess(`服務日期已確認並回讀版本 #${receipt.confirmed_version}。`);
      onObserved?.();
      onOpenArrangement?.();
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

      finishStartConfirmation();
      setSuccess(`服務日期已確認並回讀版本 #${recovery.confirmedVersion}。`);
      onObserved?.();
      onOpenArrangement?.();
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
  const canSave = queryView !== null
    && selectedDates.every((date) => queryView.selectable_dates.includes(date))
    && working === null
    && !isRecoveryActive
    && !needsBasisUpdate && !inputInvalid && !manualNeedsReview && !startUnresolved && !actualStart?.service_data_locked;
  const arrangementReady = queryView !== null && !isRecoveryActive && !startUnresolved
    && !needsBasisUpdate && !inputInvalid && startPreview === null
    && sameServiceDates(selectedDates, queryView.current_dates);

  useEffect(() => {
    if (initialCalculation.current === caseNo || queryView?.case_no !== caseNo || queryView.current_dates.length > 0
      || selectedDates.length > 0 || serviceMode === null || !actualStart || actualStart.has_formal_assignments
      || working !== null || isRecoveryActive || startUnresolved || needsBasisUpdate || !startDate) return;
    initialCalculation.current = caseNo;
    void loadServiceDates('calculate', startDate);
    // Only the first empty date table is calculated; saved dates and manual drafts are preserved.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseNo, queryView, selectedDates.length, serviceMode, actualStart, working, isRecoveryActive, startUnresolved, needsBasisUpdate, startDate]);
  useUnsavedDraft('服務日期', { '開始日期': startDate, '休息星期': restWeekdays, '服務日期': selectedDates, '原因': reason }, { enabled: !!queryView, resetKey: queryView, busy: saving || startUnresolved || isRecoveryActive });


  if (coordinatedStart && queryView && !arrangementPending && historicalArrangementCase.current!==caseNo) return (
    <section aria-label="服務日期協調結果">
      <p>客戶與月嫂在原服務群組協調，由月嫂提交約定開始日；通過檢查即自動更新日期、排班及第一期款期限。</p>
      {queryView.current_dates.length>0 ? <details><summary>查看正式服務日期</summary><p>{queryView.current_dates.join('、')}</p></details> : <p>等待月嫂回報協調結果。</p>}
      <p>拒絕或檔期衝突的案件，請由下方代班待辦接續處理。</p>
    </section>
  );
  return (
    <section className="order-service-dates-panel" aria-label={`案件 ${caseNo} 服務日期設定`}
      hidden={view === 'arrangement' && !arrangementPending && success !== '歷史案件正式安排已建立並回讀。'}>
      <div hidden={view !== 'dates'}>
      {saveValidation.feedback}
      <div className="service-date-heading"><p className="service-date-instruction">{effectiveServiceDates ? '查看現行班表；更正開始日會同步調整各段排班。' : '依開始日與休假選擇計算服務日期，確認後儲存。'}</p>
        {effectiveServiceDates && onOpenActualStart && <button type="button" disabled={saving || working !== null || isRecoveryActive || startUnresolved} onClick={onOpenActualStart}>更正實際開始日</button>}
      </div>
      {effectiveServiceDates === null && <div className="service-date-settings">
        <div className="service-date-start-field">
          <label>實際開始日
            <input ref={startDateRef} aria-required="true" type="date" aria-label="實際開始日" value={startDate}
              disabled={saving || working === 'preview' || isRecoveryActive || startUnresolved || actualStart?.service_data_locked}
              onChange={(event) => changeStartDate(event.target.value)} />
          </label>
          {actualStart && <small>約定服務開始日 {actualStart.planned_start_date}</small>}
          {actualStart && !actualStart.has_formal_assignments && <button className="service-date-save-start" type="button"
            disabled={working !== null || saving || isRecoveryActive || needsBasisUpdate || startUnresolved || actualStart.service_data_locked}
            onClick={() => void runApply(false)}>儲存實際開始日</button>}
        </div>
        <div className="service-date-rest-settings">
          <div className="service-date-original-type" aria-label="原訂服務方式">
            <span>訂單原有服務方式</span><strong>{originalServiceType || '未提供'}</strong>
          </div>
      <fieldset aria-label="人工選定休假星期"
        disabled={saving || working === 'preview' || isRecoveryActive || startUnresolved || actualStart?.service_data_locked}>
        <legend>本次計算的休假星期</legend>
        <div className="service-date-weekday-choices">
          {REST_WEEKDAYS.map(({ value, label }) => <label key={value} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <input type="checkbox" checked={restWeekdays?.includes(value) ?? false} onChange={(event) => {
              const next = new Set(restWeekdays ?? []);
              if (event.target.checked) next.add(value); else next.delete(value);
              changeRestWeekdays([...next].sort((a, b) => a - b));
            }} />{label}
          </label>)}
          <button className="service-date-no-rest" type="button" onClick={() => changeRestWeekdays([])}>無固定週休</button>
        </div>
        <small>{restWeekdays === null ? '請依協調結果選擇休假星期。' : restWeekdays.length === 0 ? '此次試算：無固定週休。' : `此次休假：${REST_WEEKDAYS.filter((day) => restWeekdays.includes(day.value)).map((day) => day.label).join('、')}。`}日期會自動更新；這組選擇只用於本次計算。</small>
      </fieldset>
        </div>
      </div>}
      {actualStart?.service_data_locked && <p role="status">服務資料已鎖定，目前只能查看正式日期。</p>}


      {error !== null && <p role="alert">{error}</p>}
      {error !== null && !isRecoveryActive && !startUnresolved && (
        <button type="button" disabled={working !== null} onClick={() => void loadServiceDates('read')}>重新讀取服務日期</button>
      )}
      {basisNotice !== null && !routineCalculationNotice && effectiveServiceDates === null && <p className="service-date-inline-status" role="status">{basisNotice}</p>}
      {startPreview?.operation === 'reschedule' && <p role="status">本案確認開始日會同步建立或重排既定人員的正式服務安排。以下建議為後端正式重排日期，請核對後再保存。</p>}
      {startUnresolved && !saving && <div role="status">
        <p>開始日保存或回讀尚未完成，服務日期未確認。請先確認開始日結果再接續。</p>
        {startPreview && <button type="button" onClick={() => void runApply()}>讀取開始日結果並接續保存</button>}
        {!startPreview && onOpenActualStart && <button type="button" onClick={onOpenActualStart}>查看實際開始日操作</button>}
      </div>}
      {manualNeedsReview && <div role="status">
        <p>計算條件已變更，原人工選日尚未套用新建議。</p>
        <button type="button" disabled={working !== null} onClick={() => {
          selectServiceDates(caseNo, suggestedDates); setSelectedDates(suggestedDates);
          const calculation = orderMutationFlowStore.getServiceDatesDraft(caseNo)?.calculation;
          if (calculation) orderMutationFlowStore.setServiceDatesCalculation(caseNo, { ...calculation, needsManualReview: false });
          setManualNeedsReview(false); setHasManualChanges(false);
        }}>採用新建議</button>
        <button type="button" disabled={working !== null} onClick={() => {
          if (selectedDates.some((date) => !queryView?.selectable_dates.includes(date))) {
            setError('原人工選日包含新範圍以外的日期，請調整選日或採用新建議。'); return;
          }
          setManualNeedsReview(false); setError(null);
          const calculation = orderMutationFlowStore.getServiceDatesDraft(caseNo)?.calculation;
          if (calculation) orderMutationFlowStore.setServiceDatesCalculation(caseNo, { ...calculation, needsManualReview: false });
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
            onClick={() => void loadServiceDates('resume')}>載入目前服務日期</button>
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
              {queryView.bound_staff.map((staff) => staffIdentity.label(staff.staff_id, staff.staff_name)).join('、')}
              <span>。此歷史綁定已保留，不需重新挑選候選或再次推薦。</span>
            </div>
          )}
          {confirmationSupersededBySchedule && effectiveServiceDates === null && (
            <p role="status" className="order-case-review-note">
              先前確認的日期與目前排班不同；下方日曆保留事前確認紀錄，不代表目前服務安排。
            </p>
          )}
          {precision !== null && effectiveServiceDates === null && <details className="service-date-calculation-details"><summary>查看試算明細</summary>
          {routineCalculationNotice && <p>{basisNotice}</p>}
          {calculationBasis !== null && !calculationBasis.confirmed && <div aria-label="服務日期計算基準">此次試算開始日（尚未保存）：{calculationBasis.date}</div>}
          <dl className="order-v2-business-summary" aria-label="建議服務日期摘要">
            <div><dt>排休類型</dt><dd>{restWeekdays !== null ? '人工選定休假星期' : serviceMode}</dd></div>
            <div><dt>建議開始</dt><dd>{precision.actual_start_date}</dd></div>
            <div><dt>建議完工</dt><dd>{suggestedDates.at(-1) ?? precision.actual_end_date}</dd></div>
            <div><dt>合約服務日</dt><dd>{requiredDateCount} 天</dd></div>
          </dl></details>}
          <dl className="service-date-summary-strip" aria-label="此次選定服務日期摘要" aria-live="polite">
            <div><dt>服務開始</dt><dd>{displayedDates[0] ?? '尚未選取'}</dd></div>
            <div><dt>最後服務日</dt><dd>{displayedDates.at(-1) ?? '尚未選取'}</dd></div>
            <div><dt>服務天數</dt><dd>{displayedDates.length} / {requiredDateCount} 天</dd></div>
            {displayedDates.length !== requiredDateCount && <div><dt>待調整</dt><dd>{displayedDates.length < requiredDateCount ? `尚差 ${requiredDateCount - displayedDates.length}` : `超出 ${displayedDates.length - requiredDateCount}`} 天</dd></div>}
          </dl>

          <div ref={dateSelectionRef} tabIndex={-1} aria-label="服務日期選擇">
          <OrderServiceDateCalendar
            month={calendarMonth || startDate.slice(0, 7)} onMonthChange={setCalendarMonth} selectedDates={displayedDates}
            isDateDisabled={date => effectiveServiceDates !== null || !queryView.selectable_dates.includes(date) || working !== null || isRecoveryActive || needsBasisUpdate || inputInvalid || startUnresolved || Boolean(actualStart?.service_data_locked)}
            onToggle={date => changeDate(date, !displayedDates.includes(date))}
            dayDetails={date => {
              const day = precision?.day_by_day.find(value => value.date === date);
              const segmentIndex = currentAssignmentPlan?.assignments.findIndex(segment => segment.official_service_dates.includes(date)) ?? -1;
              return { holidayName: day?.holiday_name, rest: day?.is_rest_day, laterSegment: segmentIndex % 2 === 1 };
            }}
            hint={effectiveServiceDates ? '現行服務日期已保存；更正開始日會先核對各段調整結果。' : `選取國定假日即代表已確認該日安排服務；點選日期可調整，需選滿 ${requiredDateCount} 天。`}
          />

          </div>

          {effectiveServiceDates === null && <label>原因（選填）<textarea maxLength={500} value={reason} disabled={working !== null || saving || isRecoveryActive} onChange={event => setReason(event.target.value)} /></label>}
          <div className="service-date-footer">
            <small>{effectiveServiceDates ? '現行班表已保存。' : queryView.current_dates.length > 0 ? '服務日期表已保存；雙方確認後會依條件自動排班。' : '目前尚未保存服務日期。'}</small>
            {effectiveServiceDates ? onOpenArrangement && <button type="button" onClick={onOpenArrangement}>查看日期確認紀錄 →</button> : <button type="button" className="order-v2-open-drawer service-date-primary" disabled={!canSave} onClick={() => void runApply(true)}>
              {working === 'apply' ? '儲存並回讀中…' : '儲存服務日期'}
            </button>}
          </div>
        </>
      )}

      {queryView !== null && queryView.current_dates.length > 0 && (
        <div tabIndex={-1} ref={readbackElement}><details className="service-date-saved-details"><summary>查看已保存日期與版本</summary>
          {calculationBasis?.confirmed && <div aria-label="服務日期計算基準">正式實際開始日：{calculationBasis.date}</div>}
          <dl className="order-v2-business-summary" aria-label={confirmationSupersededBySchedule ? '先前確認日期與目前排班回讀' : '已確認服務日期回讀'}>
          <div><dt>{confirmationSupersededBySchedule ? '先前確認版本' : '日期確認版本'}</dt><dd>{queryView.current_version === null ? '未建立' : `#${queryView.current_version}`}</dd></div>
          <div><dt>{confirmationSupersededBySchedule ? '先前確認日期' : '已確認服務日期'}</dt><dd>{queryView.current_dates.join('、')}</dd></div>
          {effectiveServiceDates !== null && <div><dt>目前排班服務日</dt><dd>{effectiveServiceDates.join('、')}</dd></div>}
        </dl></details></div>
      )}
      {arrangementPending && onOpenArrangement && (
        <div className="order-v2-inline-notice" role="status" tabIndex={-1} ref={nextStepElement} aria-label="服務日期確認後下一步">
          <strong>{arrangementReady ? '服務日期已保存，排班尚未建立。' : '已有保存日期；此次調整尚未完成確認。'}</strong>
          <p>請接續核對既定月嫂並建立正式安排，完成後才能供週報與帳務使用。</p>
          <button type="button" className="order-v2-open-drawer" disabled={working !== null || !arrangementReady}
            onClick={onOpenArrangement}>前往排班</button>
        </div>
      )}
      </div>
      {success !== null && (view === 'dates' || success === '歷史案件正式安排已建立並回讀。') && <p role="status">{success}</p>}
      {arrangementPending && queryView && (
        <div hidden={view !== 'arrangement'}>
          {arrangementReady ? (
            queryView.bound_staff.length === 0
              ? <p role="alert">歷史案件缺少可核對的既定月嫂，請先處理配對證據，不能建立正式安排。</p>
              : <HistoricalRestartArrangementPanel caseNo={caseNo} dates={queryView}
                  onBusyChange={setArrangementBusy}
                  onObserved={(observed) => {
                    setQueryView(observed);
                    setSuccess('歷史案件正式安排已建立並回讀。');
                    onObserved?.();
                  }} />
          ) : <p role="status">開始日或服務日期尚未完成保存與回讀，請先回到「確認日期」接續確認。</p>}
          {onOpenDates && <button type="button" className="order-v2-open-drawer" disabled={saving}
            onClick={onOpenDates}>調整開始日與服務日期</button>}
        </div>
      )}
    </section>
  );
};

export default OrderServiceDatesPanel;

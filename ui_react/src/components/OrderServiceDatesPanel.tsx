import { HolidayRepricingResults } from './HolidayRepricingResults';
import { useUnsavedDraft } from './UnsavedChanges';
import { useSaveValidation } from './useSaveValidation';
import { useStaffIdentityDirectory, useStaffIdentityLabels } from './StaffIdentityProvider';
import { useEffect, useRef, useState, type FC } from 'react';
import type {
  HistoricalArrangementReceiptView,
  HistoricalScheduleSavePayload,
  ServiceDateConfirmationQueryView,
} from '../api/orders/order_mutation_schemas';
import { ordersMutationClient, saveHistoricalSchedule } from '../api/orders/order_mutation_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import type { AssignmentPlan } from '../api/orders/order_query_schemas';
import { assertServiceDateAdjustmentObserved, OrderServiceDateAdjustment, type ServiceDateAdjustmentObservation } from './OrderServiceDateAdjustment';
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
import { OrderMutationError } from '../api/orders/order_mutation_errors';
import { orderActualStartClient, type ActualStartPreview } from '../api/orders/order_actual_start_client';
import type { ActualStart } from '../api/orders/order_query_schemas';
import { assertStartDates, isServiceDateConflict, refreshServiceDatesAfterStart, sameServiceDates, saveServiceDateReset, saveServiceDatesStart, serviceDateRange } from '../adapters/orders/service_date_start_flow';
import { historicalScheduleSegments, HistoricalRestartArrangementPanel } from './HistoricalRestartArrangementPanel';
import { coordinatedServiceTime, OrderReadOnlyServiceDateCalendar, OrderServiceDateCalendar } from './OrderServiceDateCalendar';
import { OrderCaregiverScheduleCalendars } from './OrderCaregiverScheduleCalendars';
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
  onBoundStaffChange?: (staff: ServiceDateConfirmationQueryView['bound_staff']) => void;
  completedCorrection?: boolean;
  adjustmentOnly?: boolean;
  coordinatedStart?: boolean;
  officeScheduleStaff?: ServiceDateConfirmationQueryView['bound_staff'];
}

type WorkingAction = 'load' | 'apply' | null;
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

const OrderPreCompletionServiceDatesPanel: FC<OrderServiceDatesPanelProps> = ({ caseNo, onObserved, onOpenActualStart, calculationRevision = 0, projectionRevision = 0, onBusyChange, currentAssignmentPlan, view = 'dates', onOpenArrangement, onArrangementPendingChange, onBoundStaffChange, coordinatedStart = false, officeScheduleStaff = [], adjustmentOnly = false }) => {
  const staffIdentity = useStaffIdentityLabels();
  const staffDirectory = useStaffIdentityDirectory();
  const [officeStaff, setOfficeStaff] = useState<typeof officeScheduleStaff | null>(null);
  const [officeEditingOverride, setOfficeEditingOverride] = useState<boolean | null>(null);
  const [officeReasonRequired, setOfficeReasonRequired] = useState(false);
  useEffect(() => {
    setOfficeEditingOverride(null);
    setOfficeStaff(null);
    setOfficeReasonRequired(false);
  }, [caseNo]);
  const [working, setWorking] = useState<WorkingAction>(null);
  const [queryView, setQueryView] = useState<ServiceDateConfirmationQueryView | null>(null);
  const historicalArrangementCase=useRef<string|null>(null);
  const arrangementPending = queryView?.case_no === caseNo
    && (queryView.historical_schedule_pending ?? queryView.arrangement_pending);
  if (arrangementPending) historicalArrangementCase.current = caseNo;
  const [allocation, setAllocation] = useState<Record<string, number>>({});
  const [savedSchedule, setSavedSchedule] = useState<AssignmentPlan | null>(null);
  const [adjustmentCase, setAdjustmentCase] = useState<string | null>(null);
  const [adjustmentBusy, setAdjustmentBusy] = useState(false);
  const scheduleRequests = useRef(new Map<string, {
    key: string;
    office: boolean;
    payload: HistoricalScheduleSavePayload;
    receipt?: HistoricalArrangementReceiptView;
    adjustedDates?: NonNullable<ServiceDateConfirmationQueryView['date_adjustment']>['days'];
  }>());
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
  const actionInFlight = useRef(new Set<string>());
  const saveDatesIntent = useRef(true);
  const saveValidation = useSaveValidation();
  const startDateRef = useRef<HTMLInputElement>(null);
  const dateSelectionRef = useRef<HTMLDivElement>(null);
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
  const scheduleRecovery = scheduleRequests.current.get(caseNo);
  const assignmentPlan = currentAssignmentPlan?.scheduling_version === queryView?.scheduling_version
    ? currentAssignmentPlan : savedSchedule;
  const assignmentPlanDates = queryView !== null
    && assignmentPlan?.case_no === caseNo
    && assignmentPlan.scheduling_version === queryView.scheduling_version
    && assignmentPlan.assignments.length > 0
    && assignmentPlan.assignments.every(segment => segment.official_service_dates.length > 0)
    ? [...new Set(assignmentPlan.assignments.flatMap((segment) => segment.official_service_dates))].sort()
    : null;
  const queriedEffectiveDates = queryView?.case_no === caseNo ? queryView.effective_service_dates : undefined;
  const effectiveServiceDates = queriedEffectiveDates?.length ? queriedEffectiveDates : assignmentPlanDates;
  const officeSchedule = scheduleRecovery?.office ?? (!arrangementPending && officeScheduleStaff.length > 0 && effectiveServiceDates === null);
  const schedulePending = arrangementPending || officeSchedule;
  const displayedDates = effectiveServiceDates ?? selectedDates;
  const adjustment = queryView?.case_no === caseNo ? queryView.date_adjustment : null;
  const adjustmentEditing = adjustmentCase === caseNo;
  const hasAdjustedDays = adjustment?.days.some(day => day.hours_override !== null) ?? false;
  const reset = startPreview?.service_date_adjustment_reset
    ?? (startUnresolved ? startFlow.command.resetPreview?.service_date_adjustment_reset : null);
  const resetPending = !!reset || (inputInvalid && hasAdjustedDays && actualStart !== null
    && startDate !== (actualStart.current_actual_start_date ?? actualStart.planned_start_date));
  const initialAdjustmentDates = adjustment && queryView?.current_version === null && !adjustment.days.length
    && selectedDates.length === queryView.contracted_service_days
    && selectedDates.every(day => queryView.selectable_dates.includes(day)) ? selectedDates : undefined;
  const adjustmentDraft = adjustment && initialAdjustmentDates ? {
    ...adjustment,
    days: initialAdjustmentDates.map(service_date => ({
      service_date, staff_id: adjustment.staff.length === 1 ? adjustment.staff[0].staff_id : allocation[service_date] ?? null,
      hours_override: null, service_hours: adjustment.contracted_daily_hours,
    })),
  } : adjustment;
  const routineCalculationNotice = basisNotice === '已依此次輸入開始日試算服務日期，請核對後再確認。'
    || basisNotice === '已依正式實際開始日更新服務日期，請核對後再確認。';

  useEffect(() => { onBusyChange?.(saving || adjustmentBusy); return () => onBusyChange?.(false); }, [saving, adjustmentBusy, onBusyChange]);
  useEffect(() => { onArrangementPendingChange?.(arrangementPending); }, [arrangementPending, onArrangementPendingChange]);
  useEffect(() => { onBoundStaffChange?.(queryView?.bound_staff ?? []); }, [queryView, onBoundStaffChange]);
  useEffect(() => { setAllocation({}); }, [caseNo, queryView?.current_version, queryView?.order_version, queryView?.scheduling_version]);

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

  const loadServiceDates = async (mode: DateLoadMode, inputDate?: string, weekdayOverride = restWeekdays, replaceManualDates = false,
    adjustmentObservation?: ServiceDateAdjustmentObservation) => {
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
      setPrecision(null); setServiceMode(null);
    }
    try {
      // Pure reads: stale responses must be discarded BEFORE any shared draft writes.
      const [serviceDates, currentStart, calendarDetail] = await Promise.all([
        ordersMutationClient.getServiceDates(caseNo, { signal: controller.signal }),
        ordersQueryClient.getActualStart(caseNo, { signal: controller.signal }),
        ordersQueryClient.getOrderCalendarDetail(caseNo, { signal: controller.signal }),
      ]);
      if (!current()) return;
      if (adjustmentObservation) assertServiceDateAdjustmentObserved(caseNo, serviceDates, adjustmentObservation);
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
      const modeValue: ServiceMode | null = calendarDetail.service_mode
        ?? ((serviceDates.historical_schedule_pending ?? serviceDates.arrangement_pending) ? '休周日' : null);
      let basis: { date: string; confirmed: boolean } | null = null;
      let nextStartPreview: ActualStartPreview | null = null;
      let range = serviceDates.selectable_dates;
      let recommendation: string[] = [];
      if (mode === 'calculate') {
        const basisDate = inputDate ?? currentStart.current_actual_start_date ?? currentStart.planned_start_date;
        basis = { date: basisDate, confirmed: basisDate === currentStart.current_actual_start_date };
        const adjusted = serviceDates.date_adjustment?.days.some(day => day.hours_override !== null);
        if (adjusted && basisDate !== (currentStart.current_actual_start_date ?? currentStart.planned_start_date)) {
          nextStartPreview = await orderActualStartClient.preview(caseNo, { new_actual_start_date: basis.date }, { signal: controller.signal });
          if (!current()) return;
        }
        if (!nextStartPreview?.service_date_adjustment_reset) {
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
          if (!nextStartPreview && basis.date !== currentStart.current_actual_start_date && !officeSchedule) {
            nextStartPreview = await orderActualStartClient.preview(caseNo, { new_actual_start_date: basis.date }, { signal: controller.signal });
            if (!current()) return;
          }
        }
        const nextReset = nextStartPreview?.service_date_adjustment_reset;
        if (nextStartPreview) {
          if ((nextStartPreview.operation === 'date_only' ? nextStartPreview.case_no : nextStartPreview.actual_start.case_no) !== caseNo
            || nextStartPreview.after_actual_start_date !== basis.date || nextStartPreview.order_version !== serviceDates.order_version
            || (nextStartPreview.scheduling_version ?? 0) !== serviceDates.scheduling_version
            || (nextReset && (nextReset.confirmed_version !== serviceDates.current_version
              || nextReset.service_dates.length !== serviceDates.contracted_service_days
              || nextReset.contracted_daily_hours !== serviceDates.date_adjustment?.contracted_daily_hours))) {
            throw new Error('開始日核對結果已變更，請重新精算。');
          }
          if (!nextReset && nextStartPreview.operation === 'reschedule') {
            if (weekdayOverride !== null && !sameServiceDates(recommendation, nextStartPreview.actual_start.official_service_dates)) {
              throw new Error('人工選定的休假星期與既有正式重排不同，請使用既有排班異動流程；尚未保存。');
            }
            recommendation = nextStartPreview.actual_start.official_service_dates;
          }
        }
        if (!nextReset && (recommendation.length !== serviceDates.contracted_service_days || recommendation.some((date) => !range.includes(date)))) {
          throw new Error('精算結果超出目前允許的日期範圍或天數；未刪除任何建議日期，也尚未保存。請核對排休條件。');
        }
        dates = nextReset || (hasManualChanges && !replaceManualDates) ? [...selectedDates] : recommendation;
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
        nextStartPreview = retainedCalculation.startPreview;
        if (!nextStartPreview?.service_date_adjustment_reset) range = serviceDateRange(serviceDates, retainedCalculation.startDate);
      }
      // This validated read starts a fresh preview lifecycle, never an unresolved command.
      orderMutationFlowStore.resetServiceDatesDraft(caseNo);
      orderMutationFlowStore.setServiceDatesQueryReady(caseNo, continuingStart && mode === 'read' && previous ? previous : serviceDates);
      const reviewNeeded = mode === 'calculate' ? !nextStartPreview?.service_date_adjustment_reset && hasManualChanges && !replaceManualDates : retainedCalculation?.needsManualReview ?? false;
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
      setPrecision(calculated); setServiceMode(modeValue);
      setHasManualChanges(keepDraft || (mode === 'calculate' && hasManualChanges && !replaceManualDates));
      setBasisNotice(basis === null || nextStartPreview?.service_date_adjustment_reset ? null
        : `${basis.confirmed ? '已依正式實際開始日更新' : '已依此次輸入開始日試算'}服務日期，請核對後再確認。${hasManualChanges ? '先前人工選日已保留，請選擇採用新建議或重新核對人工選日。' : ''}`);
      if (continuingStart && mode === 'read' && !nextStartPreview?.service_date_adjustment_reset) {
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
      return true;
    } catch (caught) {
      if (adjustmentObservation) throw caught;
      if (!current()) return;
      setError(errorMessage(caught));
      setSuccess(null);
      if (mode !== 'resume') setQueryView(null);
      setBasisNotice(mode === 'calculate' ? '服務日期尚未更新，請重新精算；目前正式日期未被此試算修改。' : null);
      setPrecision(null); setServiceMode(null);
    } finally {
      if (current()) { readController.current = null; setWorking(null); }
    }
  };

  const previousProjection = useRef(projectionRevision);
  useEffect(() => {
    if (previousProjection.current === projectionRevision || working !== null || adjustmentEditing || isRecoveryActive || startUnresolved || needsBasisUpdate) return;
    previousProjection.current = projectionRevision;
    // External mutations refresh formal facts; a read never recalculates a saved arrangement.
    void loadServiceDates('read');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectionRevision, working, adjustmentEditing, isRecoveryActive, startUnresolved, needsBasisUpdate]);

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
      setBasisNotice('實際開始日與服務日期已儲存。');
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
    if (actionInFlight.current.has(caseNo) || isRecoveryActive || needsBasisUpdate || readController.current !== null || resetPending) return;
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
      if (candidate?.service_date_adjustment_reset) return;
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
      await applyServiceDatesFlow(caseNo);
      if (renderedCaseNo.current !== caseNo || calculationSequence.current !== basisSequence) return;
      const observed = orderMutationFlowStore.getServiceDatesDraft(caseNo);
      if (observed?.status !== 'observed' || observed.queryView === null) {
        throw new Error('服務日期已送出，結果待確認。請重新查詢。');
      }
      setQueryView(observed.queryView);
      setSelectedDates(observed.queryView.current_dates);

      finishStartConfirmation(candidate);
      setSuccess('服務日期已確認。');
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

  const applyReset = async (candidate?: ActualStartPreview) => {
    if (actionInFlight.current.has(caseNo) || working !== null || isRecoveryActive || actualStart?.service_data_locked
      || (candidate && candidate.after_actual_start_date !== startDate)) return;
    actionInFlight.current.add(caseNo);
    const request = calculationSequence.current;
    const current = () => renderedCaseNo.current === caseNo && calculationSequence.current === request;
    setWorking('apply'); setError(null); setSuccess(null);
    try {
      const { start, dates } = await saveServiceDateReset(caseNo, candidate, reason.trim());
      if (!current()) return;
      setQueryView(dates); setSelectedDates(dates.current_dates); setActualStart(start);
      setStartDate(start.current_actual_start_date ?? start.planned_start_date);
      setPrecision(null); setSuggestedDates([]); setRestWeekdays(null); setReason('');
      setAdjustmentCase(null); setOfficeStaff(null); setOfficeEditingOverride(null);
      setOfficeReasonRequired(false); setSavedSchedule(null);
      finishStartConfirmation();
      setBasisNotice(null);
      setSuccess('實際開始日及重排服務日期已儲存。');
      onObserved?.();
    } catch (caught) {
      if (!current()) return;
      if (!orderMutationFlowStore.getActualStart(caseNo)) {
        setStartPreview(null);
        setInputInvalid(true);
        orderMutationFlowStore.setServiceDatesCalculation(caseNo, undefined);
      }
      setError(errorMessage(caught));
    } finally {
      actionInFlight.current.delete(caseNo);
      if (current()) setWorking(null);
    }
  };

  const retryApply = async () => {
    if (actionInFlight.current.has(caseNo) || recovery?.caseNo !== caseNo || recovery.kind !== 'outcome_unknown') return;
    actionInFlight.current.add(caseNo);
    setWorking('apply');
    setError(null);
    try {
      await retryServiceDatesApplyFlow(caseNo);
      if (renderedCaseNo.current !== caseNo) return;
      const observed = orderMutationFlowStore.getServiceDatesDraft(caseNo);
      if (observed?.status !== 'observed' || observed.queryView === null) {
        throw new Error('服務日期已送出，結果待確認。請重新查詢。');
      }
      setQueryView(observed.queryView);
      setSelectedDates(observed.queryView.current_dates);

      finishStartConfirmation();
      setSuccess('服務日期已確認。');
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
      setSuccess('服務日期已確認。');
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

  const selectedOfficeStaff = officeStaff ?? officeScheduleStaff;
  const calendarStaff = officeSchedule ? selectedOfficeStaff : queryView?.bound_staff;
  const calendarStaffId = calendarStaff?.length === 1 ? calendarStaff[0].staff_id : undefined;
  const officeEditing = officeEditingOverride ?? (new Set(officeScheduleStaff.map(person => person.staff_id)).size > 1);
  const multiCaregiverEditing = officeSchedule && officeEditing;
  const scheduleBasis = adjustment?.first_schedule_days.length ? adjustment.first_schedule_days : undefined;
  const scheduleDates = scheduleBasis?.map(day => day.service_date) ?? selectedDates;
  const scheduleAllocation = scheduleBasis ? {
    ...allocation,
    ...Object.fromEntries(scheduleBasis.flatMap(day => day.staff_id ? [[day.service_date, day.staff_id]] : [])),
  } : allocation;
  const officeSegments = officeSchedule && selectedOfficeStaff.length > 1
    ? selectedOfficeStaff.map(person => ({
      staff_id: person.staff_id,
      service_dates: scheduleDates.filter(date => scheduleAllocation[date] === person.staff_id).sort(),
    })).sort((left, right) => (left.service_dates[0] ?? '').localeCompare(right.service_dates[0] ?? ''))
    : null;
  const scheduleSegments = schedulePending && queryView
    ? officeSegments
      ? officeSegments.every(segment => segment.service_dates.length > 0)
        && officeSegments.reduce((count, segment) => count + segment.service_dates.length, 0) === scheduleDates.length
        ? officeSegments : null
      : historicalScheduleSegments(officeSchedule ? selectedOfficeStaff : queryView.bound_staff, scheduleDates, scheduleAllocation)
    : null;
  const schedulePayload = queryView && scheduleSegments && scheduleDates.length === queryView.contracted_service_days ? {
    actual_start_date: startDate,
    segments: scheduleSegments,
    expected_order_version: queryView.order_version,
    expected_scheduling_version: queryView.scheduling_version,
    expected_confirmed_version: queryView.current_version,
    reason: reason.trim(),
  } : null;
  const cancelOfficeEditing = () => {
    setOfficeEditingOverride(false);
    setOfficeStaff(null);
    setOfficeReasonRequired(false);
    setAllocation({});
    setRestWeekdays(null);
    setSuccess(null);
    orderMutationFlowStore.resetServiceDatesDraft(caseNo);
    void loadServiceDates('read');
  };

  const runScheduleSave = async () => {
    if (!queryView || readController.current !== null || actionInFlight.current.has(caseNo)) return;
    let request = scheduleRequests.current.get(caseNo);
    if (!request) {
      if (!schedulePayload) return;
      request = {
        key: crypto.randomUUID(),
        office: officeSchedule,
        payload: schedulePayload,
        adjustedDates: scheduleBasis ? adjustment?.days : undefined,
      };
      scheduleRequests.current.set(caseNo, request);
    }
    actionInFlight.current.add(caseNo);
    setWorking('apply');
    setError(null);
    setSuccess(null);
    let conflict: string | null = null;
    try {
      const receipt = request.receipt ?? await (request.office
        ? saveHistoricalSchedule(caseNo, request.payload, { idempotencyKey: request.key }, true)
        : saveHistoricalSchedule(caseNo, request.payload, { idempotencyKey: request.key }));
      request.receipt = receipt;
      const [observed, plan] = await Promise.all([
        ordersMutationClient.getServiceDates(caseNo),
        ordersQueryClient.getAssignmentPlan(caseNo),
      ]);
      const expected = request.payload.segments;
      const expectedDates = request.adjustedDates?.map(day => day.service_date) ?? expected.flatMap(segment => segment.service_dates);
      const assignmentDatesMatch = request.adjustedDates
        ? sameServiceDates(plan.assignments.flatMap(segment => segment.official_service_dates), expectedDates)
          && request.adjustedDates.every(day => observed.date_adjustment?.days.some(saved =>
            saved.service_date === day.service_date && saved.hours_override === day.hours_override
            && (day.staff_id === null || saved.staff_id === day.staff_id)))
        : expected.every(segment => plan.assignments.some(assignment =>
          assignment.staff_id === segment.staff_id && assignment.assignment_id !== null
          && receipt.assignment_ids.includes(assignment.assignment_id)
          && sameServiceDates(assignment.official_service_dates, segment.service_dates)));
      if (receipt.case_no !== caseNo || observed.case_no !== caseNo || plan.case_no !== caseNo
        || observed.historical_schedule_pending || observed.arrangement_pending
        || observed.scheduling_version !== receipt.scheduling_version
        || plan.scheduling_version !== receipt.scheduling_version
        || plan.scheduling_generation !== receipt.generation_number
        || !sameServiceDates(observed.current_dates, expectedDates)
        || plan.assignments.length !== expected.length
        || !assignmentDatesMatch) {
        throw new Error('未能核對正式班表，請重新讀取結果。');
      }
      scheduleRequests.current.delete(caseNo);
      if (renderedCaseNo.current !== caseNo) return;
      orderMutationFlowStore.setServiceDatesQueryReady(caseNo, observed);
      setSavedSchedule(plan);
      setQueryView(observed);
      setSelectedDates(observed.current_dates);
      setStartPreview(null);
      setActualStart(value => value ? {
        ...value, current_actual_start_date: request.payload.actual_start_date,
        order_version: observed.order_version, has_formal_assignments: true,
      } : value);
      setSuccess('班表已儲存並回讀正式排班。');
      setOfficeEditingOverride(false);
      setOfficeStaff(null);
      setOfficeReasonRequired(false);
      onObserved?.();
    } catch (caught) {
      const rejected = !request.receipt && (caught instanceof OrderMutationError || caught instanceof ApiHttpError)
        && caught.status >= 400 && caught.status < 500;
      if (rejected) {
        scheduleRequests.current.delete(caseNo);
      }
      if (renderedCaseNo.current === caseNo) {
        setError(request.receipt ? '班表已提交，請重新讀取結果。' : errorMessage(caught));
        if (rejected && request.office && caught.code === 'office_schedule_reallocation_reason_required') {
          setOfficeReasonRequired(true);
        } else if (rejected && isServiceDateConflict(caught)) {
          conflict = errorMessage(caught);
        }
      }
    } finally {
      actionInFlight.current.delete(caseNo);
      if (renderedCaseNo.current === caseNo) setWorking(null);
      if (conflict && renderedCaseNo.current === caseNo) {
        await loadServiceDates('read');
        if (renderedCaseNo.current === caseNo) setError(conflict);
      }
    }
  };

  const requiredDateCount = queryView?.contracted_service_days ?? 0;
  const canSave = queryView !== null
    && scheduleDates.every((date) => queryView.selectable_dates.includes(date))
    && working === null
    && !isRecoveryActive
    && !needsBasisUpdate && !inputInvalid && !manualNeedsReview && !startUnresolved && !actualStart?.service_data_locked;
  const canSaveSchedule = canSave && !!startDate && scheduleSegments !== null
    && scheduleDates.length === requiredDateCount;
  const scheduleReasonRequired = officeSchedule && (officeStaff !== null || officeReasonRequired);
  const needsScheduleReason = scheduleReasonRequired && !reason.trim();
  const missingOfficeDates = multiCaregiverEditing && selectedOfficeStaff.length > 1
    && scheduleDates.some(date => !selectedOfficeStaff.some(person => person.staff_id === scheduleAllocation[date]));
  const emptyOfficeBlock = multiCaregiverEditing && selectedOfficeStaff.length > 1
    && selectedOfficeStaff.some(person => !scheduleDates.some(date => scheduleAllocation[date] === person.staff_id));
  const officeScheduleIssue = scheduleDates.length !== requiredDateCount
    ? `請先回到服務日期月曆選滿 ${requiredDateCount} 個服務日，再進行月嫂分配。`
    : missingOfficeDates ? '請分配所有服務日。'
    : emptyOfficeBlock ? '請為每位月嫂分配服務日，或移除未排班的月嫂。'
    : needsScheduleReason ? '請填寫調整原因及協調依據。' : null;

  useEffect(() => {
    if (initialCalculation.current === caseNo || queryView?.case_no !== caseNo || queryView.current_dates.length > 0
      || selectedDates.length > 0 || serviceMode === null || !actualStart || (actualStart.has_formal_assignments && !officeSchedule)
      || working !== null || isRecoveryActive || startUnresolved || needsBasisUpdate || !startDate) return;
    initialCalculation.current = caseNo;
    void loadServiceDates('calculate', startDate);
    // Only the first empty date table is calculated; saved dates and manual drafts are preserved.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseNo, queryView, selectedDates.length, serviceMode, actualStart, working, isRecoveryActive, startUnresolved, needsBasisUpdate, startDate, officeSchedule]);
  useUnsavedDraft('服務日期', { '開始日期': startDate, '休息星期': restWeekdays, '服務日期': selectedDates, '原因': reason, '月嫂分配': allocation, '首排月嫂': officeStaff }, { enabled: !!queryView, resetKey: queryView, busy: saving || startUnresolved || isRecoveryActive || !!scheduleRecovery });

  const adjustmentButton = !resetPending && Boolean(adjustmentDraft?.staff.length) && <button type="button"
    title={!adjustmentDraft?.days.length ? '請先選齊本案原訂服務日期' : undefined}
    disabled={working !== null || adjustmentEditing || isRecoveryActive || startUnresolved}
    onClick={() => {
      if (!adjustmentDraft?.days.length) {
        setError('請先選齊本案原訂服務日期，再合併或分裂日期。');
        return;
      }
      setSuccess(null);
      setAdjustmentCase(caseNo);
    }}>合併或分裂日期</button>;
  const adjustmentEditor = !resetPending && adjustmentEditing && adjustmentDraft && <OrderServiceDateAdjustment key={caseNo} caseNo={caseNo} query={adjustmentDraft}
    initialDates={initialAdjustmentDates} onBusyChange={setAdjustmentBusy}
    onCancel={() => setAdjustmentCase(null)}
    onSaved={async observation => {
      if (!await loadServiceDates('read', undefined, undefined, false, observation)) {
        throw new Error('本次服務日期調整尚未讀回。');
      }
      setAdjustmentCase(null);
      setSuccess('服務日期調整已儲存');
      onObserved?.();
    }} />;
  const datesSummary = <dl className="service-date-summary-strip" aria-label="此次選定服務日期摘要" aria-live="polite">
    <div><dt>服務開始</dt><dd>{displayedDates[0] ?? '尚未選取'}</dd></div>
    <div><dt>最後服務日</dt><dd>{displayedDates.at(-1) ?? '尚未選取'}</dd></div>
    <div><dt>原訂服務天數</dt><dd>{hasAdjustedDays ? requiredDateCount : displayedDates.length} / {requiredDateCount} 天</dd></div>
    {adjustment && adjustment.days.length > 0 && <div><dt>實際服務量</dt><dd>{adjustment.days.length} 日・{adjustment.total_hours} 小時</dd></div>}
    {!hasAdjustedDays && displayedDates.length !== requiredDateCount && <div><dt>待調整</dt><dd>{displayedDates.length < requiredDateCount ? `尚差 ${requiredDateCount - displayedDates.length}` : `超出 ${displayedDates.length - requiredDateCount}`} 天</dd></div>}
  </dl>;

  if (adjustmentOnly) return <section className="order-service-dates-panel" aria-label={`案件 ${caseNo} 服務日期設定`}>
    <div className="service-date-heading">{adjustmentButton}</div>
    {adjustmentEditor}
    {!adjustmentEditing && adjustment?.accounting_result && <HolidayRepricingResults results={[adjustment.accounting_result]} />}
    {queryView && datesSummary}
    {!adjustmentEditing && adjustment?.days.filter(day => day.hours_override !== null).map(day =>
      <p key={day.service_date}>{day.service_date}・{adjustment.staff.find(person => person.staff_id === day.staff_id)?.staff_name}・{day.service_hours} 小時・{coordinatedServiceTime}</p>)}
    {error && <p role="alert">{error}</p>}
    {success && <p role="status">{success}</p>}
  </section>;

  if (coordinatedStart && queryView && queryView.bound_staff.length === 0
    && !schedulePending && !adjustment?.staff.length && historicalArrangementCase.current !== caseNo) return (
    <section className="order-service-dates-panel" aria-label="服務日期協調結果">
      <p>客戶與月嫂在原服務群組協調，由月嫂提交約定開始日；通過檢查即自動更新日期、排班及第一期款期限。</p>
      {effectiveServiceDates ? <OrderReadOnlyServiceDateCalendar dates={effectiveServiceDates} />
        : queryView.current_dates.length === 0 ? <p>等待月嫂回報協調結果。</p> : null}
      {effectiveServiceDates === null && assignmentPlan && assignmentPlan.scheduling_version === queryView.scheduling_version
        && assignmentPlan.assignments.some(segment => segment.official_service_dates.length === 0)
        && <p role="status">已有月嫂指派，但缺少正式逐日班次。</p>}
      <p>遇到檔期衝突時，請由管理員從原案件調整排班。</p>
      {success !== null && <p role="status">{success}</p>}
    </section>
  );
  return (
    <section className="order-service-dates-panel" aria-label={`案件 ${caseNo} 服務日期設定`}
      hidden={view === 'arrangement' && !arrangementPending}>
      <div hidden={view !== 'dates'}>
      {saveValidation.feedback}
      <div className="service-date-heading">
        {!resetPending && effectiveServiceDates && onOpenActualStart && <button type="button" disabled={saving || working !== null || isRecoveryActive || startUnresolved} onClick={onOpenActualStart}>更正實際開始日</button>}
        {!resetPending && officeSchedule && <button type="button" disabled={working !== null || !!scheduleRecovery || isRecoveryActive || startUnresolved}
          onClick={officeEditing ? cancelOfficeEditing : () => setOfficeEditingOverride(true)}>
          {officeEditing ? '取消多月嫂編輯' : '多月嫂排班'}
        </button>}
        {adjustmentButton}
      </div>
      {adjustmentEditor}
    {!adjustmentEditing && adjustment?.accounting_result && <HolidayRepricingResults results={[adjustment.accounting_result]} />}
      {(effectiveServiceDates === null || resetPending) && <div className="service-date-settings">
        <div className="service-date-start-field">
          <label>實際開始日
            <input ref={startDateRef} aria-required="true" type="date" aria-label="實際開始日" value={startDate}
              disabled={saving || !!scheduleRecovery || isRecoveryActive || startUnresolved || actualStart?.service_data_locked}
              onChange={(event) => changeStartDate(event.target.value)} />
          </label>
          {!resetPending && !schedulePending && actualStart && !actualStart.has_formal_assignments && <button className="service-date-save-start" type="button"
            disabled={working !== null || saving || isRecoveryActive || needsBasisUpdate || startUnresolved || actualStart.service_data_locked}
            onClick={() => void runApply(false)}>儲存實際開始日</button>}
        </div>
        {!resetPending && <div className="service-date-rest-settings">
          {originalServiceType && <p className="service-date-original-type" aria-label="原訂服務方式">
            原訂服務方式 <strong>{originalServiceType}</strong>
          </p>}
      <fieldset aria-label="人工選定休假星期"
        disabled={saving || !!scheduleRecovery || isRecoveryActive || startUnresolved || actualStart?.service_data_locked}>
        <legend>本次計算的休假星期</legend>
        <div className="service-date-weekday-choices">
          {REST_WEEKDAYS.map(({ value, label }) => <label key={value} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <input type="checkbox" checked={restWeekdays?.includes(value) ?? false} onChange={(event) => {
              const next = new Set(restWeekdays ?? []);
              if (event.target.checked) next.add(value); else next.delete(value);
              changeRestWeekdays([...next].sort((a, b) => a - b));
            }} />{label}
          </label>)}
          <button className="service-date-no-rest" type="button" aria-pressed={restWeekdays?.length === 0}
            onClick={() => changeRestWeekdays([])}>無固定週休</button>
        </div>
      </fieldset>
        </div>}
      </div>}
      {actualStart?.service_data_locked && <p role="status">服務資料已鎖定，目前只能查看正式日期。</p>}


      {error !== null && <p role="alert">{error}</p>}
      {error !== null && !scheduleRecovery && !isRecoveryActive && !startUnresolved && (
        <button type="button" disabled={working !== null} onClick={() => void loadServiceDates('read')}>重新讀取服務日期</button>
      )}
      {basisNotice !== null && !routineCalculationNotice && effectiveServiceDates === null && <p className="service-date-inline-status" role="status">{basisNotice}</p>}
      {reset && <>
        <p role="status">重排後為 {reset.service_dates.length} 天，每天 {reset.contracted_daily_hours} 小時。</p>
        <OrderReadOnlyServiceDateCalendar dates={reset.service_dates} />
        {startUnresolved ? !saving && startFlow.status !== 'applying' && startFlow.status !== 'observing'
          && <button type="button" onClick={() => void applyReset()}>讀取重排結果</button>
          : startPreview && <button type="button" disabled={working !== null || needsBasisUpdate || inputInvalid || actualStart?.service_data_locked}
            onClick={() => void applyReset(startPreview)}>取消合併／分裂結果並重新排班</button>}
      </>}
      {!resetPending && startPreview?.operation === 'reschedule' && <p role="status">本案確認開始日會同步建立或重排既定人員的正式服務安排。以下建議為後端正式重排日期，請核對後再保存。</p>}
      {!resetPending && startUnresolved && !saving && <div role="status">
        <p>實際開始日的儲存結果待確認。請先確認開始日，再繼續設定服務日期。</p>
        {startPreview && <button type="button" onClick={() => void runApply()}>讀取開始日結果並接續保存</button>}
        {!startPreview && onOpenActualStart && <button type="button" onClick={onOpenActualStart}>查看實際開始日操作</button>}
      </div>}
      {!resetPending && manualNeedsReview && <div role="status">
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
        <p role="status">正在確認服務日期，請等候結果。</p>
      )}

      {!resetPending && queryView !== null && (
        <>
          {!arrangementPending && queryView.bound_staff.length > 0 && (
            <div role="status" className="order-v2-inline-notice">
              <strong>既定服務人員：</strong>
              {queryView.bound_staff.map((staff) => staffIdentity.label(staff.staff_id, staff.staff_name)).join('、')}
              <span>。此歷史綁定已保留，不需重新挑選候選或再次推薦。</span>
            </div>
          )}
          {datesSummary}

          {!multiCaregiverEditing && !adjustmentEditing && <div ref={dateSelectionRef} tabIndex={-1} aria-label="服務日期選擇">
          <OrderServiceDateCalendar
            month={calendarMonth || startDate.slice(0, 7)} onMonthChange={setCalendarMonth} selectedDates={displayedDates}
            staffSchedule={calendarStaffId ? { staffId: calendarStaffId, caseNo, actualStartDate: actualStart?.current_actual_start_date } : undefined}
            isDateDisabled={date => effectiveServiceDates !== null || !!scheduleRecovery || !queryView.selectable_dates.includes(date) || working !== null || isRecoveryActive || needsBasisUpdate || inputInvalid || startUnresolved || Boolean(actualStart?.service_data_locked)}
            onToggle={date => {
              const selected = displayedDates.includes(date);
              if (selected) setAllocation(current => {
                const next = { ...current };
                delete next[date];
                return next;
              });
              changeDate(date, !selected);
            }}
            dayDetails={date => {
              const day = precision?.day_by_day.find(value => value.date === date);
              const segmentIndex = assignmentPlan?.assignments.findIndex(segment => segment.official_service_dates.includes(date)) ?? -1;
              const adjusted = adjustment?.days.find(value => value.service_date === date && value.hours_override !== null);
              const person = adjustment?.staff.find(value => value.staff_id === adjusted?.staff_id);
              return { holidayName: day?.holiday_name, rest: day?.is_rest_day, laterSegment: segmentIndex % 2 === 1,
                annotation: adjusted ? `${person?.staff_name ?? ''}・${adjusted.service_hours} 小時・${coordinatedServiceTime}` : undefined };
            }}
            showHolidaySelectionHint={effectiveServiceDates === null}
          />

          </div>}

          {schedulePending && multiCaregiverEditing ? <fieldset disabled={working !== null || !!scheduleRecovery || isRecoveryActive}>
            <OrderCaregiverScheduleCalendars key={caseNo}
              caseNo={caseNo}
              actualStartDate={actualStart?.current_actual_start_date}
              blocks={selectedOfficeStaff.map(person => ({ key: person.staff_id, staffId: person.staff_id, name: person.staff_name }))}
              dates={scheduleDates}
              allocation={selectedOfficeStaff.length === 1
                ? Object.fromEntries(scheduleDates.map(date => [date, selectedOfficeStaff[0].staff_id])) : scheduleAllocation}
              onSelect={(date, id) => setAllocation(current => {
                if (selectedOfficeStaff.length === 1) return current;
                const next = { ...current };
                if (next[date] === id) delete next[date];
                else next[date] = id;
                return next;
              })}
              management={{
                options: [...(staffDirectory?.people.values() ?? [])].map(person => ({ staffId: person.id, name: person.name ?? undefined })),
                limit: 4,
                onAdd: id => {
                  if (selectedOfficeStaff.length === 1) {
                    setAllocation(Object.fromEntries(selectedDates.map(date => [date, selectedOfficeStaff[0].staff_id])));
                  }
                  setOfficeStaff([...selectedOfficeStaff, { staff_id: id, staff_name: staffDirectory?.people.get(id)?.name ?? '' }]);
                },
                onRemove: selectedOfficeStaff.length > 1 ? id => {
                  setOfficeStaff(selectedOfficeStaff.filter(person => person.staff_id !== id));
                  setAllocation(current => Object.fromEntries(Object.entries(current).filter(([, owner]) => owner !== id)));
                } : undefined,
              }} />
          </fieldset> : schedulePending && <HistoricalRestartArrangementPanel key={caseNo}
            staff={officeSchedule ? selectedOfficeStaff : queryView.bound_staff} dates={scheduleDates} allocation={scheduleAllocation}
            disabled={working !== null || !!scheduleRecovery}
            onSelect={(date, staffId) => setAllocation(current => {
              const next = { ...current };
              if (next[date] === staffId) delete next[date];
              else next[date] = staffId;
              return next;
            })} />}
          {effectiveServiceDates === null && <label className="service-date-reason">{scheduleReasonRequired ? '調整原因及協調依據（必填）' : '原因（選填）'}<textarea required={scheduleReasonRequired} maxLength={500} value={reason} disabled={working !== null || !!scheduleRecovery || isRecoveryActive} onChange={event => setReason(event.target.value)} /></label>}
          <div className="service-date-footer">
            {schedulePending && multiCaregiverEditing && !scheduleRecovery && working === null && officeScheduleIssue &&
              <p>{officeScheduleIssue}</p>}
            {schedulePending && !multiCaregiverEditing && (officeSchedule ? selectedOfficeStaff : queryView.bound_staff).length > 1 && !scheduleSegments &&
              <p>請完成每位月嫂的日期分配。</p>}
            {!schedulePending && effectiveServiceDates === null && queryView.current_dates.length > 0 &&
              <p>雙方確認後會依服務日期自動排班。</p>}
            {effectiveServiceDates ? onOpenArrangement && <button type="button" onClick={onOpenArrangement}>查看排班結果 →</button> : <button type="button" className="order-v2-open-drawer service-date-primary"
              disabled={schedulePending ? working !== null || (!scheduleRecovery && (!canSaveSchedule || needsScheduleReason)) : !canSave}
              onClick={() => void (schedulePending ? runScheduleSave() : runApply(true))}>
              {working === 'apply' ? '儲存並確認中…' : schedulePending
                ? scheduleRecovery ? scheduleRecovery.receipt ? '重新讀取班表' : '確認原儲存結果'
                  : '儲存班表'
                : '儲存服務日期'}
            </button>}
          </div>
        </>
      )}

      </div>
      {success !== null && <p role="status">{success}</p>}
    </section>
  );
};

export default OrderServiceDatesPanel;

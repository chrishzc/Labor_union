import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import {
  intakeBlockerMessage,
  intakeRepairErrorMessage,
  orderIntakeCompletionClient,
  type IntakeClientNamePreview,
  type IntakeCompletionPreview,
  type IntakeMissingField,
  type IntakeTermsPreview,
  type IntakeServiceTime,
} from '../api/orders/order_intake_completion_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { loadCurrentHcmReviewsForCases, type HcmCurrentReview } from '../api/case_import/hcm_resubmission_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { HcmIntakeProfileRepairPanel, canRepairHcmProfileField } from './HcmIntakeProfileRepairPanel';
import { calculateDailyServiceHours, validateServiceTimeWindow } from './OrderTermsMutationPanel';
import {
  orderMutationFlowStore,
  type IntakeRepairCommand,
  type IntakeRepairFlowState,
  type IntakeRepairOperation,
  type IntakeRepairReceipt,
} from '../adapters/orders/order_mutation_flow_store';

const FIELD_LABELS: Record<IntakeMissingField, string> = {
  client_name: '客戶姓名',
  start_date: '約定服務開始日',
  service_days: '服務天數',
};

function serviceTimeMatches(expected: IntakeServiceTime, actual: NonNullable<IntakeCompletionPreview['current_service_time']> | null | undefined): boolean {
  return actual?.service_hours_per_day === expected.service_hours_per_day
    && actual.start_time === expected.start_time && actual.end_time === expected.end_time
    && actual.end_day_offset === expected.end_day_offset;
}

function operationKey(caseNo: string, operation: string): string {
  return `orders-intake-${operation}-${caseNo}-${crypto.randomUUID()}`;
}

export interface OrderIntakeRepairPanelProps {
  caseNo: string;
  orderStatus?: string;
  onChanged?: () => Promise<void> | void;
  remainingServiceIssues?: readonly string[];
  repairServiceTime?: boolean;
  summaryHref?: string;
  registry?: boolean;
  focusMissing?: boolean;
  onEditStateChange?: (state: { dirty: boolean; busy: boolean }) => void;
  onNeedsRepair?: (needed: boolean) => void;
}

type IntakeOperation = 'name-preview' | 'name-apply' | 'terms-preview' | 'terms-apply' | 'completion-apply' | null;
type IntakeReadback = {
  completion: IntakeCompletionPreview;
  detail: {
    case_no: string;
    client_name: string;
    start_date: string | null;
    service_days: number;
  } | null;
};
const subscribeIntakeRepair = (listener: () => void) => orderMutationFlowStore.subscribe(listener);

function isDefinitiveRejection(error: unknown): boolean {
  return error instanceof ApiHttpError
    && error.status >= 400
    && error.status < 500
    && error.status !== 408
    && error.status !== 429;
}

function viewOperation(operation: IntakeRepairOperation): Exclude<IntakeOperation, null | 'name-preview' | 'terms-preview'> {
  if (operation === 'client_name') return 'name-apply';
  if (operation === 'terms') return 'terms-apply';
  return 'completion-apply';
}

function successMessage(operation: IntakeRepairOperation): string {
  if (operation === 'client_name') return '客戶姓名已補齊並完成回讀。';
  if (operation === 'terms') return '約定服務開始日／天數已更新並完成回讀。';
  return '進件缺件已完成，案件已回讀最新狀態。';
}

export function OrderIntakeRepairPanel({
  caseNo,
  orderStatus = '',
  onChanged,
  remainingServiceIssues = [],
  repairServiceTime = false,
  summaryHref,
  registry = false,
  focusMissing = false,
  onEditStateChange,
  onNeedsRepair,
}: OrderIntakeRepairPanelProps) {
  const [completion, setCompletion] = useState<IntakeCompletionPreview | null>(null);
  const [sourceReview, setSourceReview] = useState<HcmCurrentReview | null>(null);
  const [sourceReviewError, setSourceReviewError] = useState(false);
  const [profileBusy, setProfileBusy] = useState(false);
  const [clientName, setClientName] = useState('');
  const [startDate, setStartDate] = useState('');
  const [serviceDays, setServiceDays] = useState('');
  const [serviceHours, setServiceHours] = useState('');
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');
  const [endDayOffset, setEndDayOffset] = useState<'0' | '1'>('0');
  const [reason, setReason] = useState('');
  const [namePreview, setNamePreview] = useState<IntakeClientNamePreview | null>(null);
  const [termsPreview, setTermsPreview] = useState<IntakeTermsPreview | null>(null);
  const [editingTerms, setEditingTerms] = useState(false);
  const [loading, setLoading] = useState(true);
  const [operation, setOperation] = useState<IntakeOperation>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const nameFlow = useSyncExternalStore(
    subscribeIntakeRepair,
    () => orderMutationFlowStore.getIntakeRepair(caseNo, 'client_name'),
  );
  const termsFlow = useSyncExternalStore(
    subscribeIntakeRepair,
    () => orderMutationFlowStore.getIntakeRepair(caseNo, 'terms'),
  );
  const completionFlow = useSyncExternalStore(
    subscribeIntakeRepair,
    () => orderMutationFlowStore.getIntakeRepair(caseNo, 'completion'),
  );
  const mounted = useRef(true);
  const activeCaseNo = useRef(caseNo);
  const sequence = useRef(0);
  const readbackController = useRef<AbortController | null>(null);
  const previewController = useRef<AbortController | null>(null);
  const flows = [nameFlow, termsFlow, completionFlow].filter(
    (flow): flow is IntakeRepairFlowState => flow !== undefined,
  );
  const protectedFlow = flows.find((flow) => flow.status !== 'observed');
  const controlsLocked = operation !== null || protectedFlow !== undefined || profileBusy;
  const visibleError = protectedFlow?.error ?? error;
  const panelRef = useRef<HTMLElement>(null);
  const focusedMissing = useRef(false);
  const dirty = Boolean(reason.trim() || namePreview || termsPreview)
    || Boolean(completion && (
      (completion.missing_fields.includes('client_name') && clientName.trim())
      || startDate !== (completion.current_start_date ?? '')
      || serviceDays !== String(completion.current_service_days ?? '')
      || (repairServiceTime && (serviceHours !== String(completion.current_service_time?.service_hours_per_day ?? '')
        || startTime !== (completion.current_service_time?.start_time?.slice(0, 5) ?? '')
        || endTime !== (completion.current_service_time?.end_time?.slice(0, 5) ?? '')
        || endDayOffset !== String(completion.current_service_time?.end_day_offset ?? 0)))
    ));
  useEffect(() => { onEditStateChange?.({ dirty, busy: controlsLocked }); }, [dirty, controlsLocked, onEditStateChange]);
  useEffect(() => {
    if (!focusMissing || loading || focusedMissing.current) return;
    const field = panelRef.current?.querySelector<HTMLInputElement>('[data-intake-field]');
    if (field && !field.disabled) {
      focusedMissing.current = true;
      field.scrollIntoView?.({ block: 'center' });
      field.focus({ preventScroll: true });
    }
  }, [focusMissing, loading, completion]);
  useEffect(() => {
    if (registry && termsPreview) panelRef.current?.scrollIntoView?.({ block: 'start' });
  }, [registry, termsPreview]);

  const refresh = useCallback(async (
    signal?: AbortSignal,
    requireDetail = false,
  ): Promise<IntakeReadback | undefined> => {
    setLoading(true);
    setError(null);
    try {
      const currentCompletion = await orderIntakeCompletionClient.previewCompletion(caseNo, { signal });
      if (signal?.aborted) return;
      if (currentCompletion.case_no !== caseNo) throw new Error('進件補件回讀案件識別不一致。');
      setCompletion(currentCompletion);
      setEditingTerms(false);
      setSourceReview(null);
      setSourceReviewError(false);
      setStartDate(currentCompletion.current_start_date ?? '');
      setServiceDays(
        currentCompletion.current_service_days && currentCompletion.current_service_days > 0
          ? String(currentCompletion.current_service_days)
          : '',
      );
      setServiceHours(currentCompletion.current_service_time?.service_hours_per_day?.toString() ?? '');
      setStartTime(currentCompletion.current_service_time?.start_time?.slice(0, 5) ?? '');
      setEndTime(currentCompletion.current_service_time?.end_time?.slice(0, 5) ?? '');
      setEndDayOffset(currentCompletion.current_service_time?.end_day_offset === 1 ? '1' : '0');
      // Only editable missing fields consume detail to prefill the repair form.
      // Blockers and completed intake are fully described by the owner preview.
      let detail: IntakeReadback['detail'] = null;
      if (currentCompletion.blockers.length === 0 && (requireDetail || currentCompletion.missing_fields.length > 0)) {
        const [detailResult] = await Promise.allSettled([
          ordersQueryClient.getOrderDetail(caseNo, { signal }),
        ]);
        if (signal?.aborted) return;
        if (detailResult.status === 'fulfilled') {
          if (detailResult.value.case_no !== caseNo) throw new Error('進件補件明細回讀案件識別不一致。');
          detail = detailResult.value;
          setClientName(detail.client_name.startsWith('待補姓名') ? '' : detail.client_name);
        } else if (requireDetail) {
          throw detailResult.reason;
        }
      }
      if (currentCompletion.current_status === '待補件') {
        try {
          const reviews = await loadCurrentHcmReviewsForCases([caseNo], { signal });
          if (signal?.aborted) return;
          setSourceReview(reviews[0] ?? null);
        } catch {
          if (signal?.aborted) return;
          setSourceReviewError(true);
        }
      }
      return { completion: currentCompletion, detail };
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [caseNo]);

  useEffect(() => {
    activeCaseNo.current = caseNo;
    sequence.current += 1;
    readbackController.current?.abort();
    previewController.current?.abort();
    previewController.current = null;
    const controller = new AbortController();
    setOperation(null);
    setCompletion(null);
    setSourceReview(null);
    setSourceReviewError(false);
    setNamePreview(null);
    setTermsPreview(null);
    setReason('');
    setNotice(null);
    queueMicrotask(() => {
      if (controller.signal.aborted) return;
      void refresh(controller.signal).catch((caught) => {
        if (!controller.signal.aborted) {
          setLoading(false);
          setError(intakeRepairErrorMessage(caught));
        }
      });
    });
    return () => {
      controller.abort();
      readbackController.current?.abort();
      previewController.current?.abort();
    };
  }, [refresh]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      sequence.current += 1;
    };
  }, []);

  const isActive = (request: number, requestCaseNo: string) => (
    mounted.current && activeCaseNo.current === requestCaseNo && sequence.current === request
  );

  const receiptMatchesCommand = (command: IntakeRepairCommand, receipt: IntakeRepairReceipt): boolean => {
    if (receipt.case_no !== caseNo || receipt.preview_fingerprint !== command.preview.preview_fingerprint) return false;
    if (command.operation === 'client_name') {
      return 'client_name' in receipt
        && receipt.client_name === command.preview.after_client_name
        && receipt.lifecycle_version === command.preview.lifecycle_version;
    }
    if (command.operation === 'terms') {
      return 'start_date' in receipt
        && receipt.start_date === command.preview.after_start_date
        && receipt.service_days === command.preview.after_service_days
        && (!command.preview.after_service_time || ('service_time' in receipt
          && serviceTimeMatches(command.preview.after_service_time, receipt.service_time)))
        && receipt.lifecycle_version === command.preview.lifecycle_version + 1;
    }
    return 'status' in receipt
      && receipt.status === command.preview.target_status
      && receipt.lifecycle_version === command.preview.lifecycle_version + 1;
  };

  const readbackMatchesCommand = (
    command: IntakeRepairCommand,
    receipt: IntakeRepairReceipt,
    readback: IntakeReadback,
  ): boolean => {
    if (readback.completion.case_no !== caseNo || readback.completion.lifecycle_version < receipt.lifecycle_version) return false;
    if (command.operation === 'client_name') {
      return 'client_name' in receipt
        && readback.detail?.client_name === receipt.client_name
        && !readback.completion.missing_fields.includes('client_name');
    }
    if (command.operation === 'terms') {
      return 'start_date' in receipt
        && readback.completion.current_start_date === receipt.start_date
        && readback.completion.current_service_days === receipt.service_days
        && !readback.completion.missing_fields.includes('start_date')
        && (!command.preview.after_service_time || serviceTimeMatches(command.preview.after_service_time, readback.completion.current_service_time))
        && !readback.completion.missing_fields.includes('service_days');
    }
    return 'status' in receipt
      && readback.completion.current_status === receipt.status
      && readback.completion.missing_fields.length === 0;
  };

  const preserveReadbackOnly = (state: IntakeRepairFlowState, message: string) => {
    const saved = orderMutationFlowStore.getIntakeRepair(caseNo, state.command.operation);
    if (saved?.receipt) {
      orderMutationFlowStore.setIntakeRepair(caseNo, {
        ...saved,
        status: 'observation_failed',
        error: message,
      });
    }
  };

  const observe = async (
    state: IntakeRepairFlowState,
    request: number,
  ): Promise<void> => {
    const { command, receipt } = state;
    if (!receipt || !receiptMatchesCommand(command, receipt)) {
      throw new Error('進件補件收據識別不一致，已停止重新套用。');
    }
    readbackController.current?.abort();
    const controller = new AbortController();
    readbackController.current = controller;
    orderMutationFlowStore.setIntakeRepair(caseNo, { ...state, status: 'observing', error: null });
    try {
      await onChanged?.();
      if (controller.signal.aborted || !isActive(request, caseNo)) {
        preserveReadbackOnly(state, '案件已切換；保留收據，只能重新讀取補件結果。');
        return;
      }
      const readback = await refresh(controller.signal, command.operation === 'client_name');
      if (controller.signal.aborted || !isActive(request, caseNo)) {
        preserveReadbackOnly(state, '案件已切換；保留收據，只能重新讀取補件結果。');
        return;
      }
      if (!readback || !readbackMatchesCommand(command, receipt, readback)) {
        throw new Error('進件補件已收到收據，但正式回讀尚未觀察到相同版本與已補資料。');
      }
      orderMutationFlowStore.clearIntakeRepair(caseNo, command.operation);
      setNamePreview(null);
      setTermsPreview(null);
      setNotice(command.operation === 'terms' && command.preview.after_service_time ? '服務時間與每日時數已儲存並完成回讀。' : successMessage(command.operation));
      if (registry && command.operation !== 'completion' && readback.completion.apply_allowed
        && readback.completion.current_service_time
        && Object.values(readback.completion.current_service_time).every((value) => value !== null)) {
        await runApply({ operation: 'completion', preview: readback.completion, reason: command.reason,
          idempotencyKey: operationKey(caseNo, 'complete') });
      } else {
        setReason('');
      }
    } finally {
      if (readbackController.current === controller) readbackController.current = null;
    }
  };

  const runApply = async (command: IntakeRepairCommand, retry = false): Promise<void> => {
    const existing = orderMutationFlowStore.getIntakeRepair(caseNo, command.operation);
    if (retry) {
      if (existing?.status !== 'outcome_unknown') return;
    } else if (['client_name', 'terms', 'completion'].some((operation) => {
      const flow = orderMutationFlowStore.getIntakeRepair(caseNo, operation as IntakeRepairOperation);
      return flow && flow.status !== 'observed';
    }) || existing) {
      return;
    }
    const recoveringUnknown = retry && existing?.status === 'outcome_unknown';
    const request = sequence.current;
    setOperation(viewOperation(command.operation));
    setError(null);
    orderMutationFlowStore.setIntakeRepair(caseNo, {
      status: 'applying',
      command,
      receipt: null,
      error: null,
    });
    let receipt: IntakeRepairReceipt;
    try {
      if (command.operation === 'client_name') {
        receipt = await orderIntakeCompletionClient.applyClientName(
          caseNo, command.preview, command.reason, command.idempotencyKey,
        );
      } else if (command.operation === 'terms') {
        receipt = await orderIntakeCompletionClient.applyTerms(
          caseNo, command.preview, command.reason, command.idempotencyKey,
        );
      } else {
        receipt = await orderIntakeCompletionClient.applyCompletion(
          caseNo, command.preview, command.reason, command.idempotencyKey,
        );
      }
    } catch (caught) {
      if (isDefinitiveRejection(caught) && !recoveringUnknown) {
        orderMutationFlowStore.clearIntakeRepair(caseNo, command.operation);
        if (isActive(request, caseNo)) setError(intakeRepairErrorMessage(caught));
      } else {
        const message = recoveringUnknown
          ? '補件套用結果仍未確認；請恢復權限後使用相同內容與原操作識別重新確認。'
          : '補件套用結果未明；保留原操作，只能使用相同內容與原操作識別重新確認。';
        orderMutationFlowStore.setIntakeRepair(caseNo, {
          status: 'outcome_unknown', command, receipt: null, error: message,
        });
        if (isActive(request, caseNo)) setError(message);
      }
      if (isActive(request, caseNo)) setOperation(null);
      return;
    }
    const received: IntakeRepairFlowState = {
      status: 'observation_failed', command, receipt, error: null,
    };
    orderMutationFlowStore.setIntakeRepair(caseNo, received);
    if (!isActive(request, caseNo)) return;
    try {
      await observe(received, request);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : '補件已收到收據，但正式回讀失敗。';
      const saved = orderMutationFlowStore.getIntakeRepair(caseNo, command.operation);
      if (saved?.receipt) {
        orderMutationFlowStore.setIntakeRepair(caseNo, {
          ...saved, status: 'observation_failed', error: message,
        });
      }
      if (isActive(request, caseNo)) setError(message);
    } finally {
      if (isActive(request, caseNo)) setOperation(null);
    }
  };

  const retryObservation = async (state: IntakeRepairFlowState) => {
    if (state.status !== 'observation_failed' || !state.receipt || protectedFlow !== state) return;
    const request = sequence.current;
    setOperation(viewOperation(state.command.operation));
    setError(null);
    try {
      await observe(state, request);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : '補件正式回讀失敗。';
      const saved = orderMutationFlowStore.getIntakeRepair(caseNo, state.command.operation);
      if (saved?.receipt) {
        orderMutationFlowStore.setIntakeRepair(caseNo, {
          ...saved, status: 'observation_failed', error: message,
        });
      }
      if (isActive(request, caseNo)) setError(message);
    } finally {
      if (isActive(request, caseNo)) setOperation(null);
    }
  };

  const previewName = async () => {
    if (protectedFlow) return;
    previewController.current?.abort();
    const controller = new AbortController();
    previewController.current = controller;
    setOperation('name-preview');
    setNamePreview(null);
    setError(null);
    setNotice(null);
    try {
      const preview = await orderIntakeCompletionClient.previewClientName(caseNo, clientName, { signal: controller.signal });
      if (controller.signal.aborted) return;
      if (preview.case_no !== caseNo) throw new Error('姓名補件預覽案件識別不一致。');
      setNamePreview(preview);
    } catch (caught) {
      if (controller.signal.aborted) return;
      setNamePreview(null);
      setError(intakeRepairErrorMessage(caught));
    } finally {
      if (!controller.signal.aborted) setOperation(null);
    }
  };

  const applyName = async () => {
    if (!namePreview || !reason.trim()) return;
    await runApply({
      operation: 'client_name', preview: namePreview, reason: reason.trim(),
      idempotencyKey: operationKey(caseNo, 'client-name'),
    });
  };

  const previewTerms = async () => {
    if (protectedFlow) return;
    const parsedDays = Number(serviceDays);
    if (!startDate || !Number.isInteger(parsedDays) || parsedDays <= 0) {
      setError('請輸入有效的約定服務開始日與正整數服務天數。');
      return;
    }
    const repairingTime = repairServiceTime && completion?.current_service_time != null
      && Object.values(completion.current_service_time).some((value) => value === null);
    if (repairingTime && (!startTime || !endTime || !Number.isFinite(Number(serviceHours))
      || Number(serviceHours) <= 0 || Number(serviceHours) > 24 || !Number.isInteger(Number(serviceHours) * 2))) {
      setError('請補齊服務起訖時間，並填寫以半小時為單位的每日服務時數。');
      return;
    }
    if (repairingTime) {
      const invalid = validateServiceTimeWindow(startTime, endTime, endDayOffset);
      if (invalid) { setError(invalid); return; }
    }
    previewController.current?.abort();
    const controller = new AbortController();
    previewController.current = controller;
    setOperation('terms-preview');
    setTermsPreview(null);
    setError(null);
    setNotice(null);
    try {
      const preview = await orderIntakeCompletionClient.previewTerms(caseNo, startDate, parsedDays, {
        signal: controller.signal,
        ...(repairingTime ? { proposedServiceTime: { service_hours_per_day: Number(serviceHours),
          start_time: `${startTime}:00`, end_time: `${endTime}:00`, end_day_offset: Number(endDayOffset) as 0 | 1 } } : {}),
      });
      if (controller.signal.aborted) return;
      if (preview.case_no !== caseNo) throw new Error('日期／天數補件預覽案件識別不一致。');
      setTermsPreview(preview);
    } catch (caught) {
      if (controller.signal.aborted) return;
      setTermsPreview(null);
      setError(intakeRepairErrorMessage(caught));
    } finally {
      if (!controller.signal.aborted) setOperation(null);
    }
  };

  const applyTerms = async () => {
    if (!termsPreview || !reason.trim()) return;
    await runApply({
      operation: 'terms', preview: termsPreview, reason: reason.trim(),
      idempotencyKey: operationKey(caseNo, 'terms'),
    });
  };

  const applyCompletion = async () => {
    if (!completion || !completion.apply_allowed || completion.missing_fields.length > 0 || !reason.trim()) return;
    await runApply({
      operation: 'completion', preview: completion, reason: reason.trim(),
      idempotencyKey: operationKey(caseNo, 'completion'),
    });
  };

  const currentStatus = completion?.current_status ?? orderStatus;
  const historicalRestartAvailable = currentStatus === '歷史訂單－未服務' || currentStatus === '歷史訂單－服務中';
  const historicalCompleted = currentStatus === '歷史訂單－服務完成' || currentStatus === '歷史訂單－帳務完成';
  const repairAllowed = completion !== null && completion.blockers.length === 0;
  const termsRepairEligible = completion !== null
    && (completion.current_status === '待補件' || completion.current_status === '洽談中')
    && completion.blockers.every((blocker) => blocker === 'order_intake_completion_status_not_eligible');
  const missingStartDate = completion?.missing_fields.includes('start_date') ?? false;
  const missingServiceDays = completion?.missing_fields.includes('service_days') ?? false;
  const missingTerms = missingStartDate || missingServiceDays;
  const missingServiceTime = repairServiceTime && completion?.current_service_time != null
    && Object.values(completion.current_service_time).some((value) => value === null);
  const termsRepairAllowed = termsRepairEligible && (missingTerms || editingTerms || missingServiceTime);
  const visibleCompletionBlockers = completion?.blockers.filter(
    (blocker) => !(termsRepairEligible && blocker === 'order_intake_completion_status_not_eligible'),
  ) ?? [];
  const missingName = completion?.missing_fields.includes('client_name') ?? false;
  useEffect(() => {
    if (completion && !loading) onNeedsRepair?.(Boolean(protectedFlow
      || (repairAllowed && (missingName || completion.apply_allowed))
      || (termsRepairEligible && (missingTerms || missingServiceTime))));
  }, [completion, loading, protectedFlow, repairAllowed, termsRepairEligible, missingName, missingTerms, missingServiceTime, onNeedsRepair]);
  const shouldRender = loading
    || sourceReview !== null
    || sourceReviewError
    || visibleError !== null
    || completion === null
    || completion.missing_fields.length > 0
    || completion.apply_allowed
    || termsRepairEligible
    || ((historicalRestartAvailable || historicalCompleted) && completion.blockers.length > 0);

  if (summaryHref) {
    const missing = completion?.missing_fields.map((field) => FIELD_LABELS[field]) ?? [];
    if (missingServiceTime) missing.push('每日服務時段', '每日服務時數');
    sourceReview?.fields.forEach((field) => { if (!missing.includes(field)) missing.push(field); });
    return <section aria-label="進件缺件摘要" className="order-intake-summary">
      {loading && <p role="status">正在檢查缺件資料…</p>}
      {visibleError && <p role="alert">{visibleError}</p>}
      {completion && !loading && <>
        <div className="order-intake-summary-heading"><h3>{missing.length ? '尚待補齊的服務資料' : '進件資料檢查'}</h3>{missing.length > 0 && <span>{missing.length} 項待補</span>}</div>
        {missing.length > 0 ? <ul>{missing.map((field) => <li key={field}>{field}</li>)}</ul>
          : <p>{remainingServiceIssues.length ? remainingServiceIssues.join('；') : '基本資料已齊備，可查閱目前待辦。'}</p>}
        {sourceReviewError && <p role="status">原始進件問題暫時無法確認，請到名冊重新檢查。</p>}
        {visibleCompletionBlockers.length > 0 && <p role="status">{visibleCompletionBlockers.map(intakeBlockerMessage).join('；')}</p>}
      </>}
      <div className="order-intake-summary-actions"><p>請到客戶名冊補齊，完成後返回此頁接續辦理。</p><a href={summaryHref}>{completion && !missing.length && !missingServiceTime ? '編輯客戶與訂單資料 →' : '前往補齊案件資料 →'}</a></div>
    </section>;
  }

  if (!shouldRender) return null;

  return (
    <section
      ref={panelRef}
      className={registry ? 'registry-intake-panel' : undefined}
      aria-label="訂單缺件"
      data-surface-id="orders.intake-repair.drawer"
      style={{ border: '1px solid #fdba74', borderRadius: '12px', padding: '14px 16px', background: '#fffaf5', display: 'grid', gap: '10px' }}
    >
      <header>
        <strong style={{ color: '#9a3412' }}>
          {registry ? '補齊案件資料' : completion && completion.missing_fields.length === 0 && !sourceReview && remainingServiceIssues.length === 0 ? '服務資料' : '缺件'}
        </strong>
        {!registry && <div style={{ color: '#74593f', fontSize: '0.82rem', marginTop: '3px' }}>
          系統會依案件目前進度確認可補資料；已進入後續作業的案件，不一定能從進件頁修改。
        </div>}
      </header>

      {loading && <div role="status">正在檢查目前可用的補件流程…</div>}
      {visibleError && <div role="alert" style={{ color: '#991b1b' }}>{visibleError}</div>}
      {notice && <div role="status" style={{ color: '#166534' }}>{notice}</div>}
      {registry && completion && <dl className="registry-intake-current"><div><dt>約定服務開始日</dt><dd>{completion.current_start_date ?? '待補齊'}</dd></div><div><dt>服務天數</dt><dd>{completion.current_service_days == null ? '待補齊' : `${completion.current_service_days} 天`}</dd></div><div><dt>目前狀態</dt><dd>{completion.current_status}</dd></div></dl>}

      {completion && !loading && (
        <>
          {sourceReview && (
            <div role="status" style={{ color: '#9a3412' }}>
              <strong>原始進件欄位待修正：{sourceReview.fields.join('、')}</strong>
              <p style={{ margin: '4px 0 0' }}>可編輯欄位可在下方直接修正，儲存後會重新確認哪些問題已解除。</p>
            </div>
          )}
          {sourceReview && <HcmIntakeProfileRepairPanel
            key={`${caseNo}:${sourceReview.review_identity}`}
            caseNo={caseNo}
            fields={sourceReview.fields.filter((field) => !(field === '姓名' && repairAllowed && missingName))}
            disabled={operation !== null || protectedFlow !== undefined}
            onBusyChange={setProfileBusy}
            onSaved={async () => {
              await refresh();
              setNotice('缺件欄位已儲存並重新讀取目前問題。');
              await onChanged?.();
            }}
          />}
          {sourceReview?.fields.some((field) => !canRepairHcmProfileField(field)
            && !['預計服務日期', '希望服務天數'].includes(field)) && (
            <p>服務時間請使用本案的訂單條件修正；其他沒有編輯入口的來源欄位，請核對原始匯入資料。</p>
          )}
          {sourceReviewError && <div role="status">原始進件欄位問題讀取失敗，請重新讀取案件。</div>}
          <div style={{ fontSize: '0.84rem', color: '#57423b' }}>
            {completion.missing_fields.length > 0
              ? `${sourceReview ? '尚未補齊的案件資料：' : '缺少資料：'}${completion.missing_fields.map((field) => FIELD_LABELS[field]).join('、')}`
              : remainingServiceIssues.length > 0
                ? '姓名、日期與天數已齊備；仍需完成上方所列的服務條件。'
                : '姓名、日期與天數已齊備。'}
          </div>

          {visibleCompletionBlockers.length > 0 && (
            <div role="status" style={{ color: '#991b1b', display: 'grid', gap: '4px' }}>
              <strong>目前不可完成補件</strong>
              <ul style={{ margin: 0, paddingLeft: '20px' }}>
                {visibleCompletionBlockers.map((blocker) => <li key={blocker}>{intakeBlockerMessage(blocker)}</li>)}
              </ul>
            </div>
          )}

          {historicalCompleted && completion.blockers.length > 0 && (
            <div role="status" style={{ color: '#74593f', fontSize: '0.82rem' }}>
              此案已進入歷史完成階段，不提供 intake 或重啟倒退；後續帳務可用性由正式歷史帳務流程處理。
            </div>
          )}

          {((repairAllowed && (missingName || completion.apply_allowed)) || termsRepairAllowed) && (
            <label style={{ display: 'grid', gap: '4px', fontSize: '0.82rem', color: '#57423b' }}>
              修改原因（儲存時必填）
              <input
                value={reason}
                maxLength={500}
                disabled={controlsLocked}
                onChange={(event) => setReason(event.target.value)}
              />
            </label>
          )}

          {repairAllowed && missingName && (
            <div style={{ borderTop: '1px solid #fed7aa', paddingTop: '10px', display: 'grid', gap: '6px' }}>
              <label style={{ display: 'grid', gap: '4px', fontSize: '0.82rem' }}>
                客戶姓名
                <input
                  data-intake-field="client_name"
                  value={clientName}
                  maxLength={100}
                  disabled={controlsLocked}
                  onChange={(event) => { setClientName(event.target.value); setNamePreview(null); }}
                />
              </label>
              <button type="button" className="btn-secondary-action" disabled={controlsLocked || !clientName.trim()} onClick={() => void previewName()}>
                {operation === 'name-preview' ? '正在檢查姓名補件…' : '檢查姓名補件影響'}
              </button>
              {namePreview && (
                <div style={{ display: 'grid', gap: '6px' }}>
                  {namePreview.blockers.length > 0
                    ? <div role="status" style={{ color: '#991b1b' }}>{namePreview.blockers.map(intakeBlockerMessage).join('；')}</div>
                    : <div role="status">姓名：{namePreview.before_client_name || '未登錄'} → {namePreview.after_client_name}</div>}
                  <button
                    type="button"
                    className="btn-primary-action"
                    disabled={controlsLocked || !namePreview.apply_allowed || !reason.trim()}
                    onClick={() => void applyName()}
                  >
                    {operation === 'name-apply' ? '正在儲存姓名…' : '確認儲存姓名'}
                  </button>
                </div>
              )}
            </div>
          )}

          {!registry && termsRepairEligible && !missingTerms && !editingTerms && !missingServiceTime && (
            <button type="button" className="btn-secondary-action" disabled={controlsLocked}
              onClick={() => setEditingTerms(true)}>修改服務日期／天數</button>
          )}
          {termsRepairAllowed && (
            <div style={{ borderTop: '1px solid #fed7aa', paddingTop: '10px', display: 'grid', gap: '6px' }}>
              {missingServiceTime && <div hidden={registry && termsPreview !== null}>
                <strong>補齊服務時間</strong>
                <div className="order-intake-time-fields" style={registry ? undefined : { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(180px, 100%), 1fr))', gap: '8px' }}>
                  <label>每日開始時間<input data-intake-field="service_time" type="time" step="1800" value={startTime} disabled={controlsLocked} onChange={(event) => {
                    setStartTime(event.target.value); setTermsPreview(null);
                    const hours = calculateDailyServiceHours(event.target.value, endTime, endDayOffset);
                    if (hours !== null) setServiceHours(String(hours));
                  }} /></label>
                  <label>每日結束時間<input type="time" step="1800" value={endTime} disabled={controlsLocked} onChange={(event) => {
                    setEndTime(event.target.value); setTermsPreview(null);
                    const hours = calculateDailyServiceHours(startTime, event.target.value, endDayOffset);
                    if (hours !== null) setServiceHours(String(hours));
                  }} /></label>
                  <label>結束時間是否跨日<select value={endDayOffset} disabled={controlsLocked} onChange={(event) => {
                    const offset = event.target.value as '0' | '1'; setEndDayOffset(offset); setTermsPreview(null);
                    const hours = calculateDailyServiceHours(startTime, endTime, offset);
                    if (hours !== null) setServiceHours(String(hours));
                  }}><option value="0">同日</option><option value="1">隔日</option></select></label>
                  <label>每日服務時數<input type="number" min="0.5" max="24" step="0.5" value={serviceHours} disabled={controlsLocked} onChange={(event) => { setServiceHours(event.target.value); setTermsPreview(null); }} /></label>
                </div>
                <small>時數會依起訖時間試算；若含另行協調的休息時間，可修正為約定的實際服務時數。</small>
              </div>}
              <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: '8px', minWidth: 0 }}>
                {(missingStartDate || editingTerms) && <label style={{ display: 'grid', gap: '4px', fontSize: '0.82rem', minWidth: 0 }}>
                  約定服務開始日
                  <input data-intake-field="start_date" type="date" value={startDate} style={{ width: '100%', minWidth: 0, boxSizing: 'border-box' }} disabled={controlsLocked} onChange={(event) => { setStartDate(event.target.value); setTermsPreview(null); }} />
                </label>}
                {(missingServiceDays || editingTerms) && <label style={{ display: 'grid', gap: '4px', fontSize: '0.82rem', minWidth: 0 }}>
                  服務天數
                  <input data-intake-field="service_days" type="number" min="1" value={serviceDays} style={{ width: '100%', minWidth: 0, boxSizing: 'border-box' }} disabled={controlsLocked} onChange={(event) => { setServiceDays(event.target.value); setTermsPreview(null); }} />
                </label>}
              </div>
              {(!registry || !termsPreview) && <button type="button" className="btn-secondary-action" disabled={controlsLocked || !startDate || Number(serviceDays) <= 0} onClick={() => void previewTerms()}>
                {operation === 'terms-preview' ? '正在預覽服務資料變更…' : missingServiceTime ? '預覽服務資料變更' : '預覽日期與天數變更'}
              </button>}
              {termsPreview && (
                <div style={{ display: 'grid', gap: '6px' }}>
                  {termsPreview.blockers.length > 0
                    ? <div role="status" style={{ color: '#991b1b' }}>{termsPreview.blockers.map(intakeBlockerMessage).join('；')}</div>
                    : <div role="status">約定服務開始日 {termsPreview.after_start_date}；服務天數 {termsPreview.after_service_days} 天。</div>}
                  {registry && <div className="registry-intake-preview" aria-label="確認變更內容"><h4>確認變更內容</h4><dl>
                    {termsPreview.changed_fields.includes('start_date') && <div><dt>約定服務開始日</dt><dd>{termsPreview.before_start_date ?? '未填寫'} → {termsPreview.after_start_date}</dd></div>}
                    {termsPreview.changed_fields.includes('service_days') && <div><dt>服務天數</dt><dd>{termsPreview.before_service_days ?? '未填寫'} → {termsPreview.after_service_days} 天</dd></div>}
                    {termsPreview.after_service_time && <>
                      <div><dt>每日服務時段</dt><dd>{termsPreview.before_service_time?.start_time?.slice(0, 5) ?? '未填寫'}～{termsPreview.before_service_time?.end_time?.slice(0, 5) ?? '未填寫'} → {termsPreview.after_service_time.start_time.slice(0, 5)}～{termsPreview.after_service_time.end_time.slice(0, 5)}{termsPreview.after_service_time.end_day_offset === 1 ? '（隔日）' : '（同日）'}</dd></div>
                      <div><dt>每日服務時數</dt><dd>{termsPreview.before_service_time?.service_hours_per_day ?? '未填寫'} → {termsPreview.after_service_time.service_hours_per_day} 小時</dd></div>
                    </>}
                  </dl><p>儲存後重新檢查案件狀態與目前待辦。</p></div>}
                  {!registry && termsPreview.after_service_time && <p role="status">服務時間：{termsPreview.before_service_time?.start_time?.slice(0, 5) ?? '未填'}～{termsPreview.before_service_time?.end_time?.slice(0, 5) ?? '未填'}（{termsPreview.before_service_time?.service_hours_per_day ?? '未填'} 小時） → {termsPreview.after_service_time.start_time.slice(0, 5)}～{termsPreview.after_service_time.end_time.slice(0, 5)}（{termsPreview.after_service_time.end_day_offset === 1 ? '隔日，' : ''}{termsPreview.after_service_time.service_hours_per_day} 小時）</p>}
                  {registry && <button type="button" className="btn-secondary-action" disabled={controlsLocked} onClick={() => setTermsPreview(null)}>返回修改</button>}
                  <button
                    type="button"
                    className="btn-primary-action"
                    disabled={controlsLocked || !termsPreview.apply_allowed || !reason.trim()}
                    onClick={() => void applyTerms()}
                  >
                    {operation === 'terms-apply' ? '正在儲存服務資料…' : termsPreview.after_service_time ? '確認儲存服務資料' : '確認儲存日期與天數'}
                  </button>
                </div>
              )}
            </div>
          )}

          {repairAllowed && completion.missing_fields.length === 0 && completion.apply_allowed && (!registry || !missingServiceTime) && (
            <button
              type="button"
              className="btn-primary-action"
              disabled={controlsLocked || !reason.trim()}
              onClick={() => void applyCompletion()}
            >
              {operation === 'completion-apply' ? '正在完成進件補齊…' : '確認完成進件補齊'}
            </button>
          )}

        </>
      )}
      {protectedFlow?.status === 'applying' || protectedFlow?.status === 'observing' ? (
        <div role="status">正在儲存並確認補件結果…</div>
      ) : null}
      {protectedFlow?.status === 'outcome_unknown' ? (
        <button
          type="button"
          className="btn-primary-action"
          onClick={() => void runApply(protectedFlow.command, true)}
        >
          以原操作重新確認補件
        </button>
      ) : null}
      {protectedFlow?.status === 'observation_failed' ? (
        <button
          type="button"
          className="btn-secondary-action"
          onClick={() => void retryObservation(protectedFlow)}
        >
          只重新讀取補件結果
        </button>
      ) : null}
    </section>
  );
}

export default OrderIntakeRepairPanel;

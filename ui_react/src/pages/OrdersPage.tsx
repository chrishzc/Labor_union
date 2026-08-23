/**
 * File: OrdersPage.tsx
 * Description: 顯示 Orders 摘要與可操作 Drawer，媒合控制只使用 typed facts 與可靠任務。
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import './OrdersPage.css';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { contractSigningClient } from '../api/orders/contract_signing_client';
import {
  orderCancellationClient,
  type OrderCancellationPreview,
  type OrderCancellationQuery,
} from '../api/orders/order_cancellation_client';
import { orderCardProjectionClient } from '../api/orders/order_card_projection_client';
import { orderStageProjectionClient } from '../api/orders/order_stage_projection_client';
import {
  orderTermsMutationClient,
  type OrderTermsPreview,
  type OrderTermsQuery,
  type OrderTermsReceipt,
} from '../api/orders/order_terms_mutation_client';
import {
  orderActualStartClient,
  type ActualStartPreview,
  type ActualStartReceipt,
} from '../api/orders/order_actual_start_client';
import type { ActualStart, OrderDetail } from '../api/orders/order_query_schemas';
import { candidateContactPoolClient } from '../api/scheduling/candidate_contact_pool_client';
import {
  matchingCandidateWorkflowClient,
  type MatchingAvailability,
} from '../api/scheduling/matching_candidate_workflow_client';
import { waitingDepositLockClient } from '../api/scheduling/waiting_deposit_lock_client';
import { schedulePrecisionClient, type SchedulePrecisionResult } from '../api/scheduling/schedule_precision_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { OrderConflictError, OrderValidationError } from '../api/orders/order_query_errors';
import {
  adaptOrdersCardProjection,
  ORDERS_CARD_PROJECTION_UNAVAILABLE,
  type OrdersCardProjectionViewModel,
} from '../adapters/orders/order_card_projection_adapter';
import {
  indexOperationalTimelines,
  ORDER_STAGE_PROJECTION_UNAVAILABLE,
  stageCount,
} from '../adapters/orders/order_stage_projection_adapter';
import type {
  OrderOperationalTimeline,
  OrderOperationalTimelinePage,
} from '../api/orders/order_stage_projection_schemas';
import { Drawer } from '../components/Drawer';
import {
  ORDER_FILTER_OPTIONS,
  adaptOrderSummaryPage,
  ORDERS_TYPED_PROJECTION_UNAVAILABLE,
  type OrderSummaryCardViewModel,
  type OrderSummaryPageViewModel,
  type WorkflowStage,
} from '../adapters/orders/order_summary_adapter';
import {
  adaptMatchingWorkbenchDrawer,
  adaptOrderTermsContractDrawer,
  type MatchingWorkbenchDrawerViewModel,
  type OrderTermsContractDrawerViewModel,
} from '../adapters/orders/order_detail_adapter';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';
import {
  applyReopenFlow,
  applyServiceDatesFlow,
  fetchServiceDatesQuery,
  previewReopenFlow,
  previewServiceDatesFlow,
  retryReopenApplyFlow,
  retryReopenObservationFlow,
  retryServiceDatesApplyFlow,
  retryServiceDatesObservationFlow,
  selectServiceDates,
  updateReopenReason,
  updateServiceDatesReason,
} from '../adapters/orders/order_mutation_adapter';
import { OrderMutationError } from '../api/orders/order_mutation_errors';

function isOrderIntakeIncomplete(order: OrderSummaryCardViewModel): boolean {
  return order.orderStatus === '待補件'
    || order.serviceDays === null
    || order.clientName.startsWith('待補姓名');
}

function isClientFinanceBootstrapGap(error: unknown): boolean {
  return (error instanceof ApiHttpError
    || error instanceof OrderConflictError
    || error instanceof OrderValidationError)
    && error.code === 'client_finance_bootstrap_required';
}

interface OrderTermsDraft {
  plannedStartDate: string;
  serviceDays: string;
  serviceHoursPerDay: string;
  requiresCooking: '' | 'yes' | 'no';
  floorFeeNtd: string;
  startTime: string;
  endTime: string;
  endDayOffset: '0' | '1';
}

const EMPTY_ORDER_TERMS_DRAFT: OrderTermsDraft = {
  plannedStartDate: '',
  serviceDays: '',
  serviceHoursPerDay: '',
  requiresCooking: '',
  floorFeeNtd: '0',
  startTime: '',
  endTime: '',
  endDayOffset: '0',
};

const timeWithSeconds = (value: string) => value.length === 5 ? `${value}:00` : value;

export const OrdersPage: React.FC = () => {
  const [pageData, setPageData] = useState<OrderSummaryPageViewModel | null>(null);
  const [stagePage, setStagePage] = useState<OrderOperationalTimelinePage | null>(null);
  const [stageIndex, setStageIndex] = useState<ReadonlyMap<string, OrderOperationalTimeline>>(new Map());
  const [stageProjectionError, setStageProjectionError] = useState<string | null>(null);
  const [selectedStage, setSelectedStage] = useState<WorkflowStage | '全部'>('全部');
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [nextPageLoading, setNextPageLoading] = useState(false);
  const [nextPageError, setNextPageError] = useState<string | null>(null);

  // Active drawer orders
  const [matchingOrder, setMatchingOrder] = useState<OrderSummaryCardViewModel | null>(null);
  const [contractOrder, setContractOrder] = useState<OrderSummaryCardViewModel | null>(null);
  const [cancelOrder, setCancelOrder] = useState<OrderSummaryCardViewModel | null>(null);
  const [dateConfirmOrder, setDateConfirmOrder] = useState<OrderSummaryCardViewModel | null>(null);
  const [reopenOrder, setReopenOrder] = useState<OrderSummaryCardViewModel | null>(null);
  const [, setMutationRevision] = useState(0);

  // Drawer detail states
  const [drawerLoading, setDrawerLoading] = useState<boolean>(false);
  const [matchingDetail, setMatchingDetail] = useState<MatchingWorkbenchDrawerViewModel | null>(null);
  const [matchingDetailError, setMatchingDetailError] = useState<string | null>(null);
  const [activePlanQueryError, setActivePlanQueryError] = useState<string | null>(null);
  const [matchingContractQueryError, setMatchingContractQueryError] = useState<string | null>(null);
  const [matchingCorrectionNotice, setMatchingCorrectionNotice] = useState<string | null>(null);
  const [matchingAssignmentPlanCorrection, setMatchingAssignmentPlanCorrection] = useState(false);
  const [candidateFilter, setCandidateFilter] = useState<'all' | 'willing' | 'unwilling' | 'pending'>('all');
  const [candidateActionKey, setCandidateActionKey] = useState<string | null>(null);
  const [candidateActionError, setCandidateActionError] = useState<string | null>(null);
  const [candidateActionNotice, setCandidateActionNotice] = useState<string | null>(null);
  const [matchingOrderFacts, setMatchingOrderFacts] = useState<OrderDetail | null>(null);
  const [matchingAvailability, setMatchingAvailability] = useState<MatchingAvailability | null>(null);
  const [selectedCandidateStaffIds, setSelectedCandidateStaffIds] = useState<number[]>([]);
  const [candidateWillingnessDrafts, setCandidateWillingnessDrafts] = useState<Record<number, {
    willingness: 'willing' | 'unwilling';
    reason: string;
  }>>({});
  const [contractDetail, setContractDetail] = useState<OrderTermsContractDrawerViewModel | null>(null);
  const [contractQueryError, setContractQueryError] = useState<string | null>(null);
  const [contractCorrectionNotice, setContractCorrectionNotice] = useState<string | null>(null);
  const [activeContractTab, setActiveContractTab] = useState<'contract' | 'terms' | 'calendar'>('contract');
  const [precisionMode, setPrecisionMode] = useState<'週休1日' | '週休2日' | '連續服務'>('週休1日');
  const [precisionCalculating, setPrecisionCalculating] = useState(false);
  const [precisionResult, setPrecisionResult] = useState<SchedulePrecisionResult | null>(null);
  const [precisionError, setPrecisionError] = useState<string | null>(null);
  const [termsQuery, setTermsQuery] = useState<OrderTermsQuery | null>(null);
  const [termsDraft, setTermsDraft] = useState<OrderTermsDraft>(EMPTY_ORDER_TERMS_DRAFT);
  const [termsPreview, setTermsPreview] = useState<OrderTermsPreview | null>(null);
  const [termsReceipt, setTermsReceipt] = useState<OrderTermsReceipt | null>(null);
  const [termsReason, setTermsReason] = useState('');
  const [termsMutationStatus, setTermsMutationStatus] = useState<'idle' | 'previewing' | 'applying'>('idle');
  const [termsMutationError, setTermsMutationError] = useState<string | null>(null);
  const [actualStartQuery, setActualStartQuery] = useState<ActualStart | null>(null);
  const [actualStartDraft, setActualStartDraft] = useState('');
  const [actualStartPreview, setActualStartPreview] = useState<ActualStartPreview | null>(null);
  const [actualStartReceipt, setActualStartReceipt] = useState<ActualStartReceipt | null>(null);
  const [actualStartReason, setActualStartReason] = useState('');
  const [actualStartStatus, setActualStartStatus] = useState<'idle' | 'previewing' | 'applying'>('idle');
  const [actualStartError, setActualStartError] = useState<string | null>(null);
  const [cancellationQuery, setCancellationQuery] = useState<OrderCancellationQuery | null>(null);
  const [cancellationPreview, setCancellationPreview] = useState<OrderCancellationPreview | null>(null);
  const [cancellationStatus, setCancellationStatus] = useState<'idle' | 'querying' | 'previewing' | 'applying'>('idle');
  const [cancellationError, setCancellationError] = useState<string | null>(null);
  const [cardProjection, setCardProjection] = useState<OrdersCardProjectionViewModel | null>(null);
  const [cardProjectionLoading, setCardProjectionLoading] = useState<boolean>(false);
  const [cardProjectionError, setCardProjectionError] = useState<string | null>(null);

  // Generation guard refs to prevent race conditions on fast switching
  const currentSummaryRequestRef = useRef<number>(0);
  const currentDrawerRequestRef = useRef<number>(0);
  const summaryControllerRef = useRef<AbortController | null>(null);
  const nextPageControllerRef = useRef<AbortController | null>(null);
  const pendingCursorRef = useRef<string | null>(null);
  const drawerControllerRef = useRef<AbortController | null>(null);
  const serviceDatesPreviewControllerRef = useRef<AbortController | null>(null);
  const reopenPreviewControllerRef = useRef<AbortController | null>(null);
  const cardProjectionControllerRef = useRef<AbortController | null>(null);
  const currentCardProjectionRequestRef = useRef<number>(0);

  useEffect(
    () => orderMutationFlowStore.subscribe(() => setMutationRevision((value) => value + 1)),
    []
  );

  useEffect(() => () => {
    currentSummaryRequestRef.current += 1;
    currentDrawerRequestRef.current += 1;
    summaryControllerRef.current?.abort();
    nextPageControllerRef.current?.abort();
    drawerControllerRef.current?.abort();
    serviceDatesPreviewControllerRef.current?.abort();
    reopenPreviewControllerRef.current?.abort();
    cardProjectionControllerRef.current?.abort();
  }, []);

  // Load summaries from live API
  const fetchOrderSummaries = useCallback(async () => {
    summaryControllerRef.current?.abort();
    nextPageControllerRef.current?.abort();
    pendingCursorRef.current = null;
    const controller = new AbortController();
    summaryControllerRef.current = controller;
    const requestId = ++currentSummaryRequestRef.current;
    setLoading(true);
    setError(null);
    setNextPageError(null);
    setNextPageLoading(false);
    setStageProjectionError(null);

    try {
      const [summaryResult, stageResult] = await Promise.allSettled([
        ordersQueryClient.getOrderSummaries({}, { signal: controller.signal }),
        orderStageProjectionClient.getOperationalTimelines({ page_size: 50 }, { signal: controller.signal }),
      ]);
      if (summaryResult.status === 'rejected') throw summaryResult.reason;
      if (requestId === currentSummaryRequestRef.current) {
        const rawPage = summaryResult.value;
        const adapted = adaptOrderSummaryPage(rawPage);
        setPageData(adapted);
        if (stageResult.status === 'fulfilled') {
          try {
            const indexedStages = indexOperationalTimelines(stageResult.value, rawPage);
            setStagePage(stageResult.value);
            setStageIndex(indexedStages);
          } catch (stageError) {
            setStagePage(null);
            setStageIndex(new Map());
            setStageProjectionError(stageError instanceof Error ? stageError.message : ORDER_STAGE_PROJECTION_UNAVAILABLE);
          }
        } else {
          setStagePage(null);
          setStageIndex(new Map());
          setStageProjectionError(stageResult.reason instanceof Error ? stageResult.reason.message : ORDER_STAGE_PROJECTION_UNAVAILABLE);
        }
      }
    } catch (err) {
      if (requestId === currentSummaryRequestRef.current) {
        const message = err instanceof Error ? err.message : '載入訂單列表失敗';
        setError(message);
      }
    } finally {
      if (requestId === currentSummaryRequestRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) void fetchOrderSummaries();
    });
    return () => {
      cancelled = true;
      currentSummaryRequestRef.current += 1;
      summaryControllerRef.current?.abort();
    };
  }, [fetchOrderSummaries]);

  const fetchNextOrderSummaries = async () => {
    const cursor = pageData?.nextCursor;
    if (!cursor || pendingCursorRef.current === cursor) return;
    nextPageControllerRef.current?.abort();
    const controller = new AbortController();
    nextPageControllerRef.current = controller;
    pendingCursorRef.current = cursor;
    setNextPageLoading(true);
    setNextPageError(null);

    try {
      const [summaryResult, stageResult] = await Promise.allSettled([
        ordersQueryClient.getOrderSummaries({ after_case_no: cursor }, { signal: controller.signal }),
        orderStageProjectionClient.getOperationalTimelines({ page_size: 50, after_case_no: cursor }, { signal: controller.signal }),
      ]);
      if (controller.signal.aborted || pendingCursorRef.current !== cursor) return;
      if (summaryResult.status === 'rejected') throw summaryResult.reason;
      const rawPage = summaryResult.value;
      const adapted = adaptOrderSummaryPage(rawPage);
      setPageData((current) => {
        if (!current || current.nextCursor !== cursor) return current;
        const itemsByCaseNo = new Map(current.items.map((item) => [item.id, item]));
        adapted.items.forEach((item) => itemsByCaseNo.set(item.id, item));
        const items = [...itemsByCaseNo.values()];
        return { ...adapted, items, loadedCount: items.length };
      });
      if (stageResult.status === 'fulfilled') {
        try {
          const nextIndex = indexOperationalTimelines(stageResult.value, rawPage);
          setStagePage(stageResult.value);
          setStageIndex((current) => new Map([...current, ...nextIndex]));
        } catch (stageError) {
          setStageProjectionError(stageError instanceof Error ? stageError.message : ORDER_STAGE_PROJECTION_UNAVAILABLE);
        }
      } else {
        setStageProjectionError(stageResult.reason instanceof Error ? stageResult.reason.message : ORDER_STAGE_PROJECTION_UNAVAILABLE);
      }
    } catch (err) {
      if (!controller.signal.aborted && pendingCursorRef.current === cursor) {
        setNextPageError(err instanceof Error ? err.message : '載入下一頁訂單失敗');
      }
    } finally {
      if (pendingCursorRef.current === cursor) {
        pendingCursorRef.current = null;
        setNextPageLoading(false);
      }
    }
  };

  const beginDrawerRequest = () => {
    drawerControllerRef.current?.abort();
    const controller = new AbortController();
    drawerControllerRef.current = controller;
    const requestId = ++currentDrawerRequestRef.current;
    return { controller, requestId };
  };

  const invalidateDrawerRequest = () => {
    currentDrawerRequestRef.current += 1;
    drawerControllerRef.current?.abort();
    drawerControllerRef.current = null;
    setDrawerLoading(false);
    currentCardProjectionRequestRef.current += 1;
    cardProjectionControllerRef.current?.abort();
    cardProjectionControllerRef.current = null;
    setCardProjection(null);
    setCardProjectionError(null);
    setCardProjectionLoading(false);
  };

  const loadCardProjection = (caseNo: string) => {
    cardProjectionControllerRef.current?.abort();
    const controller = new AbortController();
    cardProjectionControllerRef.current = controller;
    const requestId = ++currentCardProjectionRequestRef.current;
    setCardProjection(null);
    setCardProjectionError(null);
    setCardProjectionLoading(true);
    void orderCardProjectionClient.getCardProjection(caseNo, { signal: controller.signal }).then((raw) => {
      if (controller.signal.aborted || requestId !== currentCardProjectionRequestRef.current) return;
      setCardProjection(adaptOrdersCardProjection(raw, caseNo));
    }).catch((error: unknown) => {
      if (controller.signal.aborted || requestId !== currentCardProjectionRequestRef.current) return;
      setCardProjectionError(error instanceof Error ? error.message : ORDERS_CARD_PROJECTION_UNAVAILABLE);
    }).finally(() => {
      if (!controller.signal.aborted && requestId === currentCardProjectionRequestRef.current) setCardProjectionLoading(false);
    });
  };

  const renderCardProjection = () => (
    <section data-surface-id="orders.card-projection" style={{ backgroundColor: '#f8fafc', padding: '16px', borderRadius: '12px', border: '1px solid #cbd5e1' }}>
      <h3 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '8px' }}>案件聯絡、條款與指派資料</h3>
      {cardProjectionLoading && <div role="status">⏳ 正在載入案件資料…</div>}
      {cardProjectionError && !cardProjectionLoading && (
        <div role="alert" style={{ color: '#991b1b' }}>{ORDERS_CARD_PROJECTION_UNAVAILABLE}：{cardProjectionError}</div>
      )}
      {cardProjection && (
        <>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '7px' }}>
            {cardProjection.rows.map((item) => (
              <div key={item.key}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                  <strong>{item.label}</strong><span>{item.valueText}</span>
                </div>
                <small style={{ color: '#64748b' }}>{item.metadataText}</small>
              </div>
            ))}
          </div>
          <div style={{ marginTop: '12px' }}>
            <strong>正式指派分段</strong>
            {cardProjection.assignmentSegments.length === 0 ? (
              <p style={{ marginBottom: 0 }}>
                {cardProjection.assignmentSegmentsAvailability === 'available'
                  ? '目前尚無正式指派分段。'
                  : cardProjection.assignmentSegmentsMessage}
              </p>
            ) : cardProjection.assignmentSegments.map((segment) => (
              <div key={segment.key} style={{ marginTop: '8px', paddingTop: '8px', borderTop: '1px solid #e2e8f0' }}>
                {segment.rows.map((item) => (
                  <div key={item.key}>
                    <span>{item.label}：{item.valueText}</span>
                    <small style={{ display: 'block', color: '#64748b' }}>{item.metadataText}</small>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );

  const previewServiceDates = (caseNo: string) => {
    serviceDatesPreviewControllerRef.current?.abort();
    const controller = new AbortController();
    serviceDatesPreviewControllerRef.current = controller;
    void previewServiceDatesFlow(caseNo, { signal: controller.signal }).catch(() => undefined);
  };

  const changeServiceDateSelection = (caseNo: string, dates: string[]) => {
    const currentDates = orderMutationFlowStore.getServiceDatesDraft(caseNo)?.selectedDates ?? [];
    const sortedCurrentDates = [...currentDates].sort();
    const sortedNextDates = [...dates].sort();
    const unchanged =
      sortedCurrentDates.length === sortedNextDates.length &&
      sortedCurrentDates.every((value, index) => value === sortedNextDates[index]);
    if (unchanged) return;

    serviceDatesPreviewControllerRef.current?.abort();
    serviceDatesPreviewControllerRef.current = null;
    selectServiceDates(caseNo, dates);
  };

  // Handle opening Drawer 1 / 3: Service Date Confirmation delegates to Unified Contract & Service Dates Workbench
  const handleOpenDateConfirmDrawer = async (order: OrderSummaryCardViewModel) => {
    await handleOpenContractDrawer(order, 'calendar');
  };

  const handleOpenReopen = (order: OrderSummaryCardViewModel) => {
    reopenPreviewControllerRef.current?.abort();
    const controller = new AbortController();
    reopenPreviewControllerRef.current = controller;
    setReopenOrder(order);
    loadCardProjection(order.id);
    void previewReopenFlow(order.id, { signal: controller.signal }).catch(() => undefined);
  };

  const handleCloseReopen = () => {
    if (!reopenOrder) return;
    const status = orderMutationFlowStore.getReopenDraft(reopenOrder.id)?.status;
    if (status === 'apply_pending' || status === 'outcome_unknown' || status === 'requery_loading') {
      return;
    }
    reopenPreviewControllerRef.current?.abort();
    reopenPreviewControllerRef.current = null;
    orderMutationFlowStore.closeReopenDialog(reopenOrder.id);
    setReopenOrder(null);
  };

  const serviceDatesDraft = dateConfirmOrder
    ? orderMutationFlowStore.getServiceDatesDraft(dateConfirmOrder.id)
    : undefined;
  const reopenDraft = reopenOrder
    ? orderMutationFlowStore.getReopenDraft(reopenOrder.id)
    : undefined;
  const serviceDatesLocked =
    serviceDatesDraft?.status === 'apply_pending' ||
    serviceDatesDraft?.status === 'outcome_unknown' ||
    serviceDatesDraft?.status === 'receipt_received' ||
    serviceDatesDraft?.status === 'requery_loading';
  const reopenLocked =
    reopenDraft?.status === 'apply_pending' ||
    reopenDraft?.status === 'outcome_unknown' ||
    reopenDraft?.status === 'receipt_received' ||
    reopenDraft?.status === 'requery_loading';
  const reopenTypedError =
    reopenDraft?.error instanceof OrderMutationError ? reopenDraft.error : null;
  const termsMutationLocked =
    termsMutationStatus !== 'idle' || termsQuery?.service_data_locked === true;
  const termsDraftReady =
    termsDraft.plannedStartDate.length > 0
    && Number(termsDraft.serviceDays) > 0
    && Number(termsDraft.serviceHoursPerDay) > 0
    && Number(termsDraft.floorFeeNtd) >= 0
    && termsDraft.requiresCooking !== ''
    && termsDraft.startTime.length > 0
    && termsDraft.endTime.length > 0;
  const actualStartLocked =
    actualStartStatus !== 'idle' || actualStartQuery?.service_data_locked === true;

  const previewActualStart = async () => {
    if (!dateConfirmOrder || !actualStartDraft) return;
    setActualStartStatus('previewing');
    setActualStartError(null);
    setActualStartPreview(null);
    setActualStartReceipt(null);
    try {
      setActualStartPreview(await orderActualStartClient.preview(dateConfirmOrder.id, {
        new_actual_start_date: actualStartDraft,
      }));
    } catch (previewError) {
      setActualStartError(previewError instanceof Error ? previewError.message : '實際開工日 Preview 失敗。');
    } finally {
      setActualStartStatus('idle');
    }
  };

  const applyActualStart = async () => {
    if (!dateConfirmOrder || !actualStartPreview || actualStartReason.trim().length === 0) return;
    setActualStartStatus('applying');
    setActualStartError(null);
    try {
      const receipt = await orderActualStartClient.apply(dateConfirmOrder.id, {
        new_actual_start_date: actualStartPreview.after_actual_start_date,
        expected_order_version: actualStartPreview.order_version,
        expected_scheduling_version: actualStartPreview.scheduling_version,
        expected_client_finance_version: actualStartPreview.client_finance_version,
        expected_payroll_version: actualStartPreview.payroll_version,
        preview_fingerprint: actualStartPreview.preview_fingerprint,
        reason: actualStartReason,
      }, {
        idempotencyKey: `orders-actual-start-${dateConfirmOrder.id}-${crypto.randomUUID()}`,
      });
      setActualStartReceipt(receipt);
      const observed = await ordersQueryClient.getActualStart(dateConfirmOrder.id);
      setActualStartQuery(observed);
      setActualStartDraft(observed.current_actual_start_date ?? observed.planned_start_date);
    } catch (applyError) {
      setActualStartError(applyError instanceof Error ? applyError.message : '實際開工日 Apply 失敗。');
    } finally {
      setActualStartStatus('idle');
    }
  };

  // Handle opening Drawer 2: Matching Workbench
  const handleOpenMatchingDrawer = async (
    order: OrderSummaryCardViewModel,
    options?: { preserveCandidateAction?: boolean },
  ) => {
    setContractOrder(null);
    setDateConfirmOrder(null);
    setCancelOrder(null);
    setReopenOrder(null);
    setMatchingOrder(order);
    setMatchingDetail(null);
    setMatchingDetailError(null);
    setActivePlanQueryError(null);
    setMatchingContractQueryError(null);
    setMatchingCorrectionNotice(null);
    setMatchingAssignmentPlanCorrection(false);
    setContractDetail(null);
    if (!options?.preserveCandidateAction) {
      setCandidateFilter('all');
      setCandidateActionError(null);
      setCandidateActionNotice(null);
      setMatchingAvailability(null);
      setSelectedCandidateStaffIds([]);
      setCandidateWillingnessDrafts({});
    }
    loadCardProjection(order.id);
    setDrawerLoading(true);
    const { controller, requestId } = beginDrawerRequest();

    try {
      const [detailRes, assignmentPlanRes, termsRes, candidatePoolRes, activePlanRes] = await Promise.allSettled([
        ordersQueryClient.getOrderDetail(order.id, { signal: controller.signal }),
        ordersQueryClient.getAssignmentPlan(order.id, { signal: controller.signal }),
        ordersQueryClient.getOrderTerms(order.id, { signal: controller.signal }),
        candidateContactPoolClient.query(order.id, { signal: controller.signal }),
        waitingDepositLockClient.queryPlan(order.id, controller.signal),
      ]);

      if (requestId !== currentDrawerRequestRef.current) return;

      const assignmentPlan = assignmentPlanRes.status === 'fulfilled' ? assignmentPlanRes.value : null;
      const terms = termsRes.status === 'fulfilled' ? termsRes.value : null;
      const candidateContactPool = candidatePoolRes.status === 'fulfilled' ? candidatePoolRes.value : null;
      const activePlan = activePlanRes.status === 'fulfilled' ? activePlanRes.value : null;
      const activePlanMissing = activePlanRes.status === 'rejected'
        && activePlanRes.reason instanceof ApiHttpError
        && activePlanRes.reason.status === 404;
      const activePlanFailed = activePlanRes.status === 'rejected' && !activePlanMissing;

      const termsHistoricalGap = termsRes.status === 'rejected' && isClientFinanceBootstrapGap(termsRes.reason);
      const assignmentHistoricalGap = assignmentPlanRes.status === 'rejected'
        && isClientFinanceBootstrapGap(assignmentPlanRes.reason);
      const matchingQueriesReady =
        detailRes.status === 'fulfilled'
        && detailRes.value.case_no === order.id
        && (assignmentPlanRes.status === 'fulfilled'
          ? assignmentPlanRes.value.case_no === order.id
          : assignmentHistoricalGap)
        && candidatePoolRes.status === 'fulfilled'
        && candidatePoolRes.value.case_no === order.id
        && (termsRes.status === 'fulfilled' ? termsRes.value.case_no === order.id : termsHistoricalGap);

      if (requestId === currentDrawerRequestRef.current) {
        setMatchingOrderFacts(detailRes.status === 'fulfilled' ? detailRes.value : null);
        setMatchingDetail(matchingQueriesReady ? adaptMatchingWorkbenchDrawer({
          caseNo: order.id,
          assignmentPlan,
          terms,
          candidateContactPool,
          activePlan,
        }) : null);
        setMatchingDetailError(matchingQueriesReady ? null : '正式排班資料載入失敗，請關閉後重試。');
        setMatchingCorrectionNotice((termsHistoricalGap || assignmentHistoricalGap) && matchingQueriesReady
          ? '此歷史案件缺少 Client Finance 根事實；既有 Scheduling 指派來源仍可檢視，料理、服務時段與完整排班 projection 保持待補正。'
          : null);
        setMatchingAssignmentPlanCorrection(assignmentHistoricalGap && matchingQueriesReady);
        setActivePlanQueryError(activePlanFailed
          ? '進行中媒合方案與等待訂金鎖資料載入失敗，請關閉後重試。'
          : null);
      }
    } finally {
      if (requestId === currentDrawerRequestRef.current) {
        setDrawerLoading(false);
      }
    }
  };

  const sendCandidateInformation = async (candidateId: number, infoType: 1 | 2) => {
    if (!matchingOrder) return;
    const actionKey = `${candidateId}:${infoType}`;
    setCandidateActionKey(actionKey);
    setCandidateActionError(null);
    setCandidateActionNotice(null);
    try {
      const result = await candidateContactPoolClient.sendInformation(
        matchingOrder.id,
        candidateId,
        infoType,
      );
      await handleOpenMatchingDrawer(matchingOrder, { preserveCandidateAction: true });
      setCandidateActionNotice(
        result.status === 'queued'
          ? `訂單資訊-${infoType} 已建立可靠發送任務 #${result.line_task_id}。`
          : `訂單資訊-${infoType} 已由既有冪等任務受理。`,
      );
    } catch (caught) {
      setCandidateActionError(
        caught instanceof Error ? caught.message : `訂單資訊-${infoType} 發送失敗。`,
      );
    } finally {
      setCandidateActionKey(null);
    }
  };

  const searchMatchingCandidates = async () => {
    if (!matchingOrder || !matchingOrderFacts) return;
    const startDate = matchingOrderFacts.actual_start_date ?? matchingOrderFacts.start_date;
    const endDate = matchingOrderFacts.actual_end_date ?? matchingOrderFacts.end_date;
    setCandidateActionError(null);
    setCandidateActionNotice(null);
    if (!startDate || !endDate) {
      setCandidateActionError('案件缺少完整服務起訖日，無法查詢可完整承接的月嫂。');
      return;
    }
    setCandidateActionKey('availability-search');
    try {
      const availability = await matchingCandidateWorkflowClient.searchSingleCaregiver(
        matchingOrder.id,
        startDate,
        endDate,
      );
      setMatchingAvailability(availability);
      setSelectedCandidateStaffIds([]);
      const eligibleCount = availability.candidate_options.filter(
        (candidate) => candidate.segment_index === 0 && candidate.full_case_coverage,
      ).length;
      setCandidateActionNotice(
        eligibleCount > 0
          ? `已依最新檔期查得 ${eligibleCount} 位可完整承接候選月嫂。`
          : '目前沒有月嫂能完整承接本案服務日期。',
      );
    } catch (caught) {
      setMatchingAvailability(null);
      setCandidateActionError(caught instanceof Error ? caught.message : '候選月嫂查詢失敗。');
    } finally {
      setCandidateActionKey(null);
    }
  };

  const addSelectedMatchingCandidates = async () => {
    if (!matchingOrder || !matchingAvailability) return;
    const candidates = matchingAvailability.candidate_options
      .filter((candidate) => selectedCandidateStaffIds.includes(candidate.staff_id))
      .map((candidate) => ({
        staff_id: candidate.staff_id,
        start_date: candidate.case_period_start,
        end_date: candidate.case_period_end,
      }));
    if (candidates.length === 0) {
      setCandidateActionError('請至少選擇一位可完整承接的候選月嫂。');
      return;
    }
    setCandidateActionKey('candidate-pool-add');
    setCandidateActionError(null);
    setCandidateActionNotice(null);
    try {
      await candidateContactPoolClient.addCandidates(matchingOrder.id, candidates);
      const observed = await candidateContactPoolClient.query(matchingOrder.id);
      if (!candidates.every((candidate) => observed.candidates.some((item) => item.staff_id === candidate.staff_id))) {
        throw new Error('候選聯繫池寫入後回讀不完整，請重新查詢。');
      }
      await handleOpenMatchingDrawer(matchingOrder, { preserveCandidateAction: true });
      setSelectedCandidateStaffIds([]);
      setCandidateActionNotice(`已回讀確認 ${candidates.length} 位月嫂加入候選聯繫池。`);
    } catch (caught) {
      setCandidateActionError(caught instanceof Error ? caught.message : '加入候選聯繫池失敗。');
    } finally {
      setCandidateActionKey(null);
    }
  };

  const recordMatchingCandidateWillingness = async (candidateId: number) => {
    if (!matchingOrder) return;
    const draft = candidateWillingnessDrafts[candidateId] ?? { willingness: 'willing' as const, reason: '' };
    setCandidateActionKey(`willingness:${candidateId}`);
    setCandidateActionError(null);
    setCandidateActionNotice(null);
    try {
      await candidateContactPoolClient.recordWillingness(
        matchingOrder.id,
        candidateId,
        draft.willingness,
        draft.reason,
      );
      const observed = await candidateContactPoolClient.query(matchingOrder.id);
      const candidate = observed.candidates.find((item) => item.id === candidateId);
      if (!candidate || candidate.willingness !== draft.willingness) {
        throw new Error('候選月嫂意願寫入後回讀不一致，請重新查詢。');
      }
      await handleOpenMatchingDrawer(matchingOrder, { preserveCandidateAction: true });
      setCandidateActionNotice(`已回讀確認 ${candidate.staff_name}意願為${draft.willingness === 'willing' ? '願意' : '無意願'}。`);
    } catch (caught) {
      setCandidateActionError(caught instanceof Error ? caught.message : '更新候選月嫂意願失敗。');
    } finally {
      setCandidateActionKey(null);
    }
  };

  const createFormalPlanFromWillingCandidate = async (candidateId: number) => {
    if (!matchingOrder || !matchingDetail) return;
    const candidate = matchingDetail.candidatePool.find((item) => item.candidateId === candidateId);
    if (!candidate || candidate.willingness !== 'willing' || candidate.contactStatus === 'withdrawn') {
      setCandidateActionError('僅能從目前願意且仍在候選池的月嫂建立正式方案。');
      return;
    }
    setCandidateActionKey(`formal-plan:${candidateId}`);
    setCandidateActionError(null);
    setCandidateActionNotice(null);
    try {
      const plan = await matchingCandidateWorkflowClient.createSingleCaregiverPlan(
        matchingOrder.id,
        {
          staff_id: candidate.staffId,
          start_date: candidate.serviceStartDate,
          end_date: candidate.serviceEndDate,
        },
      );
      const observed = await waitingDepositLockClient.queryPlan(matchingOrder.id);
      if (observed.planId !== plan.plan_id) {
        throw new Error('正式媒合方案建立後 active plan 回讀不一致，請重新查詢。');
      }
      await handleOpenMatchingDrawer(matchingOrder, { preserveCandidateAction: true });
      setCandidateActionNotice(`已回讀確認正式單月嫂方案 #${plan.plan_id}（版本 ${plan.version}）。`);
    } catch (caught) {
      setCandidateActionError(caught instanceof Error ? caught.message : '建立正式單月嫂方案失敗。');
    } finally {
      setCandidateActionKey(null);
    }
  };

  // Lazy loader for Contract SSOT & Terms queries
  const loadContractTabQueries = async (order: OrderSummaryCardViewModel) => {
    const { controller, requestId } = beginDrawerRequest();
    setDrawerLoading(true);
    try {
      const [termsRes, completionRes, orderDetailRes, signingRes] = await Promise.allSettled([
        ordersQueryClient.getOrderTerms(order.id, { signal: controller.signal }),
        ordersQueryClient.getContractCompletion(order.id, { signal: controller.signal }),
        ordersQueryClient.getOrderDetail(order.id, { signal: controller.signal }),
        contractSigningClient.query(order.id, { signal: controller.signal }),
      ]);

      if (requestId !== currentDrawerRequestRef.current) return;

      const termsHistoricalGap = termsRes.status === 'rejected' && isClientFinanceBootstrapGap(termsRes.reason);
      const completionHistoricalGap = completionRes.status === 'rejected' && isClientFinanceBootstrapGap(completionRes.reason);
      const historicalCorrectionReady =
        orderDetailRes.status === 'fulfilled'
        && signingRes.status === 'fulfilled'
        && orderDetailRes.value.case_no === order.id
        && signingRes.value.case_no === order.id
        && (termsRes.status === 'fulfilled' ? termsRes.value.case_no === order.id : termsHistoricalGap)
        && (completionRes.status === 'fulfilled' ? completionRes.value.case_no === order.id : completionHistoricalGap)
        && (termsHistoricalGap || completionHistoricalGap);
      if (historicalCorrectionReady) {
        setContractCorrectionNotice(
          '此案件缺少 Client Finance 契約與定金根事實，已隔離為歷史資料待補正；目前可檢視來源投影，但不可預覽或套用條款。'
        );
        return;
      }

      const requiredQueriesReady =
        termsRes.status === 'fulfilled'
        && completionRes.status === 'fulfilled'
        && orderDetailRes.status === 'fulfilled'
        && signingRes.status === 'fulfilled'
        && termsRes.value.case_no === order.id
        && completionRes.value.case_no === order.id
        && orderDetailRes.value.case_no === order.id
        && signingRes.value.case_no === order.id;
      if (!requiredQueriesReady) {
        setContractQueryError('契約與條款資料載入失敗，請關閉後重試。');
        return;
      }

      const terms = termsRes.value;
      const completion = completionRes.value;
      const orderDetail = orderDetailRes.value;
      const signing = signingRes.value;

      if (requestId === currentDrawerRequestRef.current) {
        if (terms) {
          setTermsQuery(terms);
          setTermsDraft({
            plannedStartDate: terms.terms.planned_start_date,
            serviceDays: String(terms.terms.service_days),
            serviceHoursPerDay: String(terms.terms.service_hours_per_day),
            requiresCooking: terms.terms.requires_cooking === null
              ? ''
              : terms.terms.requires_cooking ? 'yes' : 'no',
            floorFeeNtd: String(terms.terms.floor_fee_ntd),
            startTime: terms.terms.service_time.start_time?.slice(0, 5) ?? '',
            endTime: terms.terms.service_time.end_time?.slice(0, 5) ?? '',
            endDayOffset: terms.terms.service_time.end_day_offset === 1 ? '1' : '0',
          });
        }
        const adapted = adaptOrderTermsContractDrawer({
          caseNo: order.id,
          terms,
          completion,
          signing,
          summary: order,
          orderDetail,
        });
        setContractDetail(adapted);
      }
    } finally {
      if (requestId === currentDrawerRequestRef.current) {
        setDrawerLoading(false);
      }
    }
  };

  // Lazy loader for Service Dates & Actual Start queries
  const loadCalendarTabQueries = async (order: OrderSummaryCardViewModel) => {
    const { controller, requestId } = beginDrawerRequest();
    setDrawerLoading(true);
    try {
      const [actualStartRes] = await Promise.allSettled([
        ordersQueryClient.getActualStart(order.id, { signal: controller.signal }),
        fetchServiceDatesQuery(order.id, { signal: controller.signal }),
      ]);
      if (requestId !== currentDrawerRequestRef.current) return;
      const actualStart = actualStartRes.status === 'fulfilled' ? actualStartRes.value : null;
      setActualStartQuery(actualStart);
      setActualStartDraft(actualStart?.current_actual_start_date ?? actualStart?.planned_start_date ?? '');
      if (actualStartRes.status === 'rejected') {
        setActualStartError('實際開工日根事實查詢失敗，請關閉後重試。');
      }
    } finally {
      if (requestId === currentDrawerRequestRef.current) {
        setDrawerLoading(false);
      }
    }
  };

  // Handle opening Unified Drawer: Terms, Service Dates & Contract Progress
  const handleOpenContractDrawer = async (
    order: OrderSummaryCardViewModel,
    initialTab: 'contract' | 'terms' | 'calendar' = 'contract',
  ) => {
    serviceDatesPreviewControllerRef.current?.abort();
    setContractOrder(order);
    setDateConfirmOrder(order);
    setActiveContractTab(initialTab);
    setContractDetail(null);
    setContractQueryError(null);
    setContractCorrectionNotice(null);
    setTermsQuery(null);
    setTermsDraft(EMPTY_ORDER_TERMS_DRAFT);
    setTermsPreview(null);
    setTermsReceipt(null);
    setTermsReason('');
    setTermsMutationError(null);
    setTermsMutationStatus('idle');
    setActualStartQuery(null);
    setActualStartDraft('');
    setActualStartPreview(null);
    setActualStartReceipt(null);
    setActualStartReason('');
    setActualStartStatus('idle');
    setActualStartError(null);
    setPrecisionResult(null);
    setPrecisionError(null);
    loadCardProjection(order.id);

    if (initialTab === 'calendar') {
      await loadCalendarTabQueries(order);
    } else {
      await loadContractTabQueries(order);
    }
  };

  const switchContractTab = (tab: 'contract' | 'terms' | 'calendar') => {
    setActiveContractTab(tab);
    const activeOrder = contractOrder || dateConfirmOrder;
    if (!activeOrder) return;
    if ((tab === 'contract' || tab === 'terms') && contractDetail === null && !contractQueryError) {
      void loadContractTabQueries(activeOrder);
    } else if (tab === 'calendar' && actualStartQuery === null) {
      void loadCalendarTabQueries(activeOrder);
    }
  };

  const runSchedulePrecision = async (_caseNo: string) => {
    const startDate = actualStartDraft || termsDraft.plannedStartDate || '2026-08-01';
    const targetDays = Number(termsDraft.serviceDays) || 30;
    setPrecisionCalculating(true);
    setPrecisionError(null);
    try {
      const result = await schedulePrecisionClient.calculate({
        actual_start_date: startDate,
        target_service_days: targetDays,
        service_mode: precisionMode,
      });
      setPrecisionResult(result);
    } catch (err) {
      setPrecisionError(err instanceof Error ? err.message : '出勤天數精算失敗');
    } finally {
      setPrecisionCalculating(false);
    }
  };

  const updateTermsDraft = <K extends keyof OrderTermsDraft>(key: K, value: OrderTermsDraft[K]) => {
    setTermsDraft((current) => ({ ...current, [key]: value }));
    setTermsPreview(null);
    setTermsReceipt(null);
    setTermsMutationError(null);
  };

  const proposedTermsPayload = () => ({
    proposed_terms: {
      planned_start_date: termsDraft.plannedStartDate,
      service_days: Number(termsDraft.serviceDays),
      service_hours_per_day: Number(termsDraft.serviceHoursPerDay),
      requires_cooking: termsDraft.requiresCooking === 'yes',
      floor_fee_ntd: Number(termsDraft.floorFeeNtd),
      service_time: {
        start_time: timeWithSeconds(termsDraft.startTime),
        end_time: timeWithSeconds(termsDraft.endTime),
        end_day_offset: Number(termsDraft.endDayOffset),
      },
    },
  });

  const previewOrderTerms = async () => {
    if (!contractOrder) return;
    setTermsMutationStatus('previewing');
    setTermsMutationError(null);
    setTermsReceipt(null);
    try {
      setTermsPreview(await orderTermsMutationClient.preview(contractOrder.id, proposedTermsPayload()));
    } catch (caught) {
      setTermsPreview(null);
      setTermsMutationError(caught instanceof Error ? caught.message : '訂單條款 Preview 失敗。');
    } finally {
      setTermsMutationStatus('idle');
    }
  };

  const applyOrderTerms = async () => {
    if (!contractOrder || !termsPreview) return;
    setTermsMutationStatus('applying');
    setTermsMutationError(null);
    try {
      const receipt = await orderTermsMutationClient.apply(
        contractOrder.id,
        {
          ...proposedTermsPayload(),
          expected_order_version: termsPreview.order_version,
          expected_scheduling_version: termsPreview.scheduling_version,
          expected_client_finance_version: termsPreview.client_finance_version,
          expected_payroll_version: termsPreview.payroll_version,
          preview_fingerprint: termsPreview.preview_fingerprint,
          reason: termsReason,
        },
        { idempotencyKey: `orders-terms-ui-${contractOrder.id}-${crypto.randomUUID()}` },
      );
      setTermsReceipt(receipt);
      setTermsQuery((current) => current ? {
        ...current,
        order_version: receipt.order_version,
        scheduling_version: receipt.scheduling_version,
        client_finance_version: receipt.client_finance_version,
        payroll_version: receipt.payroll_version,
        terms: termsPreview.after,
      } : current);
    } catch (caught) {
      setTermsMutationError(caught instanceof Error ? caught.message : '訂單條款 Apply 失敗。');
    } finally {
      setTermsMutationStatus('idle');
    }
  };

  // Handle opening Drawer 4: Cancellation Query and zero-mutation Preview
  const handleOpenCancelDrawer = async (order: OrderSummaryCardViewModel) => {
    setCancelOrder(order);
    setCancellationQuery(null);
    setCancellationPreview(null);
    setCancellationError(null);
    setCancellationStatus('querying');
    loadCardProjection(order.id);
    const { controller, requestId } = beginDrawerRequest();
    try {
      const query = await orderCancellationClient.query(order.id, controller.signal);
      if (controller.signal.aborted || requestId !== currentDrawerRequestRef.current) return;
      setCancellationQuery(query);
      setCancellationStatus('idle');
    } catch {
      if (controller.signal.aborted || requestId !== currentDrawerRequestRef.current) return;
      setCancellationError('取消資料暫時無法取得，請關閉後重試。');
      setCancellationStatus('idle');
    }
  };

  const previewCancellation = async () => {
    if (!cancelOrder || !cancellationQuery) return;
    const { controller, requestId } = beginDrawerRequest();
    setCancellationStatus('previewing');
    setCancellationError(null);
    try {
      const preview = await orderCancellationClient.preview(cancelOrder.id, cancellationQuery.confirmed_service_days, controller.signal);
      if (controller.signal.aborted || requestId !== currentDrawerRequestRef.current) return;
      setCancellationPreview(preview);
      setCancellationStatus('idle');
    } catch {
      if (controller.signal.aborted || requestId !== currentDrawerRequestRef.current) return;
      setCancellationError('取消預覽未通過，請確認案件狀態與服務日資料。');
      setCancellationStatus('idle');
    }
  };

  const allItems = pageData?.items || [];
  const filteredOrders = selectedStage === '全部'
    ? allItems
    : allItems.filter((order) => stageIndex.get(order.id)?.current_stage_code === selectedStage);
  const depositAmountText = cardProjection?.rows.find((row) => row.key === 'deposit_amount_ntd')?.valueText
    ?? (cardProjectionError ? '資料載入失敗（定金金額）' : '正在確認定金金額…');
  const depositSettlementText = cardProjection?.rows.find((row) => row.key === 'deposit_settlement_state')?.valueText
    ?? (cardProjectionError ? '資料載入失敗（定金狀態）' : '正在確認定金狀態…');
  const visibleMatchingCandidates = matchingDetail?.candidatePool.filter((candidate) => (
    candidateFilter === 'all' || candidate.willingness === candidateFilter
  )) ?? [];
  const eligibleMatchingCandidates = matchingAvailability?.candidate_options.filter(
    (candidate) => candidate.segment_index === 0 && candidate.full_case_coverage,
  ) ?? [];

  return (
    <div>
      <div className="page-header-banner">
        <div>
          <h1 className="page-title">📦 訂單與客戶管理</h1>
          <p className="page-subtitle">查詢訂單階段、契約簽署、媒合進度與正式排班。</p>
        </div>
      </div>

      {/* Status Filter Chips */}
      <div className="orders-filter-bar">
        {ORDER_FILTER_OPTIONS.map((filter) => {
          const projectionReady = stagePage !== null;
          const count = filter.stage === '全部'
            ? pageData?.loadedCount
            : stagePage ? stageCount(stagePage, filter.stage) : null;
          return (
            <button
              key={filter.stage}
              type="button"
              data-control-id={`orders.filter.${filter.stage}`}
              className={`filter-chip ${selectedStage === filter.stage ? 'active' : ''}`}
              disabled={filter.stage !== '全部' && !projectionReady}
              aria-disabled={filter.stage !== '全部' && !projectionReady}
              title={filter.stage === '全部' ? '目前已載入的 Orders 摘要' : '使用後端 typed 七階段投影篩選'}
              onClick={() => setSelectedStage(filter.stage)}
            >
              {filter.label} {pageData ? `(${count ?? '—'})` : ''}
            </button>
          );
        })}
      </div>
      {stageProjectionError && !loading && (
        <div role="alert" data-surface-id="orders.stage-projection-error" style={{ padding: '12px 14px', marginBottom: '16px', borderRadius: '10px', backgroundColor: '#fff7ed', border: '1px solid #fdba74', color: '#9a3412' }}>
          {ORDER_STAGE_PROJECTION_UNAVAILABLE}：{stageProjectionError}
        </div>
      )}

      {/* Loading & Error States */}
      {loading && (
        <div style={{ textAlign: 'center', padding: '40px', color: '#64748b', fontSize: '1rem', fontWeight: 600 }}>
          ⏳ 正在載入即時訂單數據...
        </div>
      )}

      {error && !loading && (
        <div style={{ padding: '16px 20px', backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '12px', color: '#991b1b', marginBottom: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>⚠️ 載入訂單資料失敗：{error}</div>
          <button
            style={{ padding: '6px 14px', backgroundColor: '#dc2626', color: '#fff', border: 'none', borderRadius: '6px', fontWeight: 700, cursor: 'pointer' }}
            onClick={fetchOrderSummaries}
          >
            重試
          </button>
        </div>
      )}

      {/* Empty State */}
      {!loading && !error && filteredOrders.length === 0 && (
        <div style={{ textAlign: 'center', padding: '48px', backgroundColor: '#fff', borderRadius: '16px', border: '1px solid #e2e8f0', color: '#64748b' }}>
          <div style={{ fontSize: '2.5rem', marginBottom: '10px' }}>☕</div>
          <div style={{ fontSize: '1.1rem', fontWeight: 700 }}>目前無符合條件的訂單</div>
          <div style={{ fontSize: '0.85rem', marginTop: '6px' }}>目前沒有已載入的訂單摘要</div>
        </div>
      )}

      {/* Orders Grid Cards */}
      {!loading && !error && (
        <div className="orders-grid">
          {filteredOrders.map((order) => (
            <div key={order.id} className="order-card">
              <div className="order-card-top">
                <span className="order-id-badge">{order.id}</span>
                <span className="order-status-pill">伺服器狀態：{order.orderStatus}</span>
              </div>

              <div className="order-card-body">
                <div className="order-client-title">👤 {order.clientName}</div>
                <div>📅 約定服務：{order.serviceRange}（{order.serviceDaysLabel}）</div>

                {/* Actual Start Date Badge if exists */}
                {order.actualStartDate && (
                  <div style={{ color: '#0f766e', fontWeight: 700, fontSize: '0.85rem' }}>
                    🗓️ 實際服務開始日：{order.actualStartDate}
                  </div>
                )}

                {order.contractAmount !== null && <div>
                  💰 雇主自付應付額：<strong style={{ color: '#ff7f50', fontSize: '1.05rem' }}>{order.contractAmountFormatted}</strong>
                </div>}

                {/* Doula Assigned Box */}
                {order.assignedDoulaName && <div className="order-doula-box">
                    <div>
                      <div>👩‍🍼 摘要所列月嫂：<strong>{order.assignedDoulaName}</strong></div>
                      <div style={{ fontSize: '0.8rem', color: '#74593f' }}>正式推薦與分段方案請開啟媒合工作台查看</div>
                    </div>
                </div>}
              </div>

              {isOrderIntakeIncomplete(order) ? (
                <div className="order-card-actions" role="status">
                  案件仍待補齊姓名、服務日期等進件資料；完成補件後即可操作契約、媒合、排班與取消流程。
                </div>
              ) : (
              <div className="order-card-actions">
                <button
                  className="btn-secondary-action"
                  onClick={() => handleOpenContractDrawer(order)}
                >
                  📑 條款與契約
                </button>

                <button
                  className="btn-primary-action"
                  onClick={() => handleOpenMatchingDrawer(order)}
                >
                  👩‍🍼 媒合與正式排班
                </button>

                {/* Service Date Confirmation Button */}
                <button
                  style={{
                    padding: '6px 12px',
                    backgroundColor: '#f0fdfa',
                    color: '#0f766e',
                    border: '1px solid #99f6e4',
                    borderRadius: '8px',
                    fontWeight: 700,
                    fontSize: '0.8rem',
                    cursor: 'pointer',
                  }}
                  onClick={() => handleOpenDateConfirmDrawer(order)}
                >
                  📅 確認服務日期
                </button>

                <button
                  className="btn-cancel-preview"
                  onClick={() => handleOpenCancelDrawer(order)}
                  title="訂單取消與退款試算 (Zero-Mutation Preview)"
                >
                  🛑 取消試算
                </button>

                <button
                  data-control-id="orders.card.reopen"
                  style={{
                    padding: '6px 12px',
                    backgroundColor: '#fef2f2',
                    color: '#991b1b',
                    border: '1px solid #fecaca',
                    borderRadius: '8px',
                    fontWeight: 700,
                    fontSize: '0.8rem',
                    cursor: 'pointer',
                  }}
                  onClick={() => handleOpenReopen(order)}
                  title="由伺服器預覽判定是否可受控重開，不依前端訂單階段推測"
                >
                  🔄 重啟訂單
                </button>
              </div>
              )}
            </div>
          ))}
        </div>
      )}

      {!loading && !error && pageData?.nextCursor && (
        <div className="orders-pagination-container">
          {nextPageError && <div className="orders-pagination-error" role="alert">載入下一頁失敗：{nextPageError}</div>}
          <button
            type="button"
            className="orders-load-more-btn"
            data-control-id="orders.query.next-page"
            disabled={nextPageLoading}
            onClick={() => void fetchNextOrderSummaries()}
          >
            {nextPageLoading ? '正在載入下一頁…' : '載入下一頁'}
          </button>
        </div>
      )}


      {/* 2. 1280px Extra-Wide Matching Workbench (size="xl") */}
      <Drawer
        isOpen={matchingOrder !== null}
        onClose={() => { invalidateDrawerRequest(); setMatchingOrder(null); }}
        size="xl"
        title={`👩‍🍼 媒合與正式排班查詢工作台 — ${matchingOrder?.id || ''}`}
        footer={
          <button
            style={{
              padding: '12px 28px',
              border: '1px solid #dec0b6',
              borderRadius: '10px',
              background: '#fff',
              cursor: 'pointer',
              fontWeight: 700,
              fontSize: '0.95rem',
            }}
            onClick={() => { invalidateDrawerRequest(); setMatchingOrder(null); }}
          >
            關閉工作台
          </button>
        }
      >
        {matchingOrder && (
          <div className="matching-workbench-container">
            {drawerLoading && (
              <div style={{ textAlign: 'center', padding: '20px', color: '#ff7f50' }}>
                ⏳ 正在載入訂單 detail 與正式排班投影...
              </div>
            )}
            {matchingDetailError && !drawerLoading && (
              <div role="alert" data-surface-id="orders.matching.query-error" style={{ padding: '12px 14px', borderRadius: '10px', backgroundColor: '#fff7ed', border: '1px solid #fdba74', color: '#9a3412' }}>
                正式排班資料暫時無法取得，請關閉後重試。
              </div>
            )}
            {matchingCorrectionNotice && !drawerLoading && (
              <div role="status" data-surface-id="orders.matching.historical-correction" style={{ padding: '12px 14px', borderRadius: '10px', backgroundColor: '#fffbeb', border: '1px solid #fbbf24', color: '#92400e' }}>
                <strong>歷史資料待補正</strong>
                <div>{matchingCorrectionNotice}</div>
              </div>
            )}

            {/* Top Demand Summary Bar (4-Column Layout + Deposit Status) */}
            <div className="matching-facts-bar">
              <div className="matching-facts-col">
                <div className="matching-facts-label">產婦與服務地點</div>
                <div className="matching-facts-val">{matchingOrder.clientName}</div>
                <div className="matching-facts-sub">
                  📍 {cardProjection?.rows.find((row) => row.key === 'contact_address')?.valueText
                    ?? (cardProjectionError ? '資料載入失敗（服務地址）' : '正在確認服務地址…')}
                </div>
              </div>

              <div className="matching-facts-col">
                <div className="matching-facts-label">約定起訖與天數</div>
                <div className="matching-facts-val" style={{ color: '#ff7f50' }}>{matchingOrder.serviceDaysLabel}</div>
                <div className="matching-facts-sub">📅 {matchingOrder.serviceRange}</div>
              </div>

              <div className="matching-facts-col">
                <div className="matching-facts-label">每日時段與料理</div>
                <div className="matching-facts-val">
                  {matchingDetail?.serviceTimeText ?? '正在確認服務時段…'}
                </div>
                <div className="matching-facts-sub">
                  🍳 {matchingDetail?.requiresCookingText ?? '正在確認料理需求…'}
                </div>
              </div>

              <div className="matching-facts-col">
                <div className="matching-facts-label">雇主自付應付額與定金狀態</div>
                <div className="matching-facts-val" style={{ color: '#ff7f50' }}>{matchingOrder.contractAmountFormatted}</div>
                <div className="matching-facts-sub">
                  💰 定金：{depositAmountText}
                </div>
                <div className="matching-deposit-pill" style={{
                  color: cardProjection?.depositSettlementState === 'settled' ? '#166534' : '#9a3412',
                }}>
                  定金狀態：{depositSettlementText}
                </div>
              </div>
            </div>

            {/* 🎯 步驟一：設定配對篩選條件 */}
            <div className="matching-step-card">
              <div className="matching-step-header">
                <div>
                  <h3 className="matching-step-title">
                    <span className="matching-step-badge">1</span>
                    🎯 設定配對篩選條件與偏好
                  </h3>
                  <div className="matching-step-subtext">
                    依案件 owner 根事實重新載入候選聯繫池；檔期衝突仍由正式媒合 gate 判定。
                  </div>
                </div>
                <button
                  type="button"
                  className="orders-load-more-btn"
                  style={{ padding: '6px 20px', fontSize: '0.82rem' }}
                  disabled={drawerLoading || candidateActionKey !== null || matchingOrderFacts === null}
                  onClick={() => void searchMatchingCandidates()}
                >
                  {candidateActionKey === 'availability-search' ? '正在查詢最新檔期…' : '🔍 重新查詢符合條件月嫂'}
                </button>
              </div>

              <div className="matching-criteria-grid" role="list" aria-label="目前媒合查詢根事實">
                <div className="matching-criteria-item" role="listitem">📍 服務地點：{cardProjection?.rows.find((row) => row.key === 'contact_address')?.valueText ?? '正在確認…'}</div>
                <div className="matching-criteria-item" role="listitem">⏰ 每日時段：{matchingDetail?.serviceTimeText ?? '正在確認…'}</div>
                <div className="matching-criteria-item" role="listitem">📅 承接天數：{matchingOrder.serviceDaysLabel}</div>
                <div className="matching-criteria-item" role="listitem">🍳 料理需求：以上方案件根事實為準</div>
              </div>
            </div>

            {/* 👥 步驟二：查詢合格月嫂清單 ➜ 選入候選池 / 分段模式 */}
            <div className="matching-step-card">
              <div className="matching-step-header">
                <div>
                  <h3 className="matching-step-title">
                    <span className="matching-step-badge">2</span>
                    👥 查詢合格月嫂清單 ➜ 選入候選池 / 分段
                  </h3>
                  <div className="matching-step-subtext">
                    支援單一月嫂完整承接或 2～4 段多月嫂連續分段排班。
                  </div>
                </div>
              </div>

              <div className="matching-mode-strip">
                <span role="status" style={{ padding: '8px 18px', borderRadius: '9999px', backgroundColor: '#ffdbcf', color: '#6c2000', fontWeight: 700 }}>
                  {matchingDetail?.assignmentSegments.length
                    ? matchingDetail.assignmentSegments.length === 1
                      ? `單一月嫂正式指派（${matchingOrder.serviceDaysLabel}）`
                      : `${matchingDetail.assignmentSegments.length} 段多月嫂正式指派`
                    : '尚無正式指派模式'}
                </span>
              </div>

              <div className="matching-coverage-card">
                <div>
                  <strong style={{ color: '#1e1b19', fontSize: '0.92rem' }}>正式分段排程來源：</strong>
                  <div style={{ color: '#57423b', fontSize: '0.84rem', marginTop: '4px' }}>
                    {matchingDetail?.assignmentSegments.length
                      ? matchingDetail.assignmentSegments.map((s) => `第 ${s.sequence} 段 (Staff #${s.staffId} · ${s.serviceRange})`).join(' ＋ ')
                      : '目前尚無正式指派分段。'}
                  </div>
                </div>
                <span style={{
                  padding: '4px 12px',
                  borderRadius: '9999px',
                  backgroundColor: '#f8fafc',
                  color: '#57423b',
                  fontWeight: 700,
                  fontSize: '0.82rem',
                }}>
                  已載入 {matchingDetail?.assignmentSegments.length ?? 0} 段正式指派
                </span>
              </div>

              {matchingAvailability && (
                <div style={{ marginTop: '14px', display: 'grid', gap: '10px' }}>
                  <strong style={{ color: '#1e1b19' }}>最新完整承接候選（{eligibleMatchingCandidates.length} 位）</strong>
                  {eligibleMatchingCandidates.length > 0 ? eligibleMatchingCandidates.map((candidate) => {
                    const checked = selectedCandidateStaffIds.includes(candidate.staff_id);
                    const alreadyInPool = matchingDetail?.candidatePool.some((item) => item.staffId === candidate.staff_id) ?? false;
                    return (
                      <label key={candidate.staff_id} style={{ display: 'flex', gap: '10px', alignItems: 'center', padding: '10px 12px', border: '1px solid #ead8d1', borderRadius: '10px' }}>
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={alreadyInPool || candidateActionKey !== null}
                          onChange={(event) => setSelectedCandidateStaffIds((current) => event.target.checked
                            ? [...current, candidate.staff_id]
                            : current.filter((staffId) => staffId !== candidate.staff_id))}
                        />
                        <span>
                          <strong>{candidate.staff_name}</strong>（Staff #{candidate.staff_id}）
                          <span style={{ display: 'block', color: '#74593f', fontSize: '0.82rem' }}>
                            {candidate.case_period_start} ~ {candidate.case_period_end}｜覆蓋 {candidate.supported_day_count}/{candidate.required_day_count} 個正式服務日
                            {alreadyInPool ? '｜已在候選聯繫池' : ''}
                          </span>
                        </span>
                      </label>
                    );
                  }) : (
                    <div role="status" style={{ color: '#74593f' }}>目前沒有月嫂能完整承接本案，請改走多月嫂備案流程。</div>
                  )}
                  {eligibleMatchingCandidates.length > 0 && (
                    <button
                      type="button"
                      className="orders-load-more-btn"
                      disabled={selectedCandidateStaffIds.length === 0 || candidateActionKey !== null}
                      onClick={() => void addSelectedMatchingCandidates()}
                    >
                      {candidateActionKey === 'candidate-pool-add' ? '正在加入並回讀候選池…' : `加入候選聯繫池（${selectedCandidateStaffIds.length} 位）`}
                    </button>
                  )}
                </div>
              )}
            </div>

            {/* 📱 步驟三：已選入候選池的月嫂 ➜ 寄送訂單資訊與意願管理 */}
            <div className="matching-step-card">
              <div className="matching-step-header">
                <div>
                  <h3 className="matching-step-title">
                    <span className="matching-step-badge">3</span>
                    📱 已選入候選池的月嫂 ➜ 寄送訂單資訊與意願管理
                  </h3>
                  <div className="matching-step-subtext">
                    呈現媒合階段各月嫂之初篩徵詢、意願回覆與個資保護推播歷程。
                  </div>
                </div>
              </div>

              <div className="matching-candidate-tabs">
                <button type="button" className={`matching-tab-btn ${candidateFilter === 'all' ? 'active' : ''}`} aria-pressed={candidateFilter === 'all'} onClick={() => setCandidateFilter('all')}>
                  全部（{matchingDetail?.candidatePool.length ?? 0} 位）
                </button>
                <button type="button" className={`matching-tab-btn ${candidateFilter === 'willing' ? 'active' : ''}`} aria-pressed={candidateFilter === 'willing'} onClick={() => setCandidateFilter('willing')}>
                  🟢 願意（{matchingDetail?.candidatePool.filter((c) => c.willingness === 'willing').length ?? 0} 位）
                </button>
                <button type="button" className={`matching-tab-btn ${candidateFilter === 'unwilling' ? 'active' : ''}`} aria-pressed={candidateFilter === 'unwilling'} onClick={() => setCandidateFilter('unwilling')}>
                  🔴 無意願（{matchingDetail?.candidatePool.filter((c) => c.willingness === 'unwilling').length ?? 0} 位）
                </button>
                <button type="button" className={`matching-tab-btn ${candidateFilter === 'pending' ? 'active' : ''}`} aria-pressed={candidateFilter === 'pending'} onClick={() => setCandidateFilter('pending')}>
                  ⏳ 待回覆（{matchingDetail?.candidatePool.filter((c) => c.willingness === 'pending').length ?? 0} 位）
                </button>
              </div>

              {candidateActionNotice && <div role="status" style={{ color: '#166534', marginBottom: '10px' }}>{candidateActionNotice}</div>}
              {candidateActionError && <div role="alert" style={{ color: '#991b1b', marginBottom: '10px' }}>{candidateActionError}</div>}

              {matchingDetail && matchingDetail.candidatePool.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  {visibleMatchingCandidates.map((c) => (
                    <div
                      key={c.candidateId}
                      className={`matching-candidate-item ${c.contactStatus === 'selected' ? 'selected' : ''}`}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                          <div style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '6px',
                            backgroundColor: c.contactStatus === 'selected' ? '#ffedd5' : '#f5ece9',
                            padding: '6px 12px',
                            borderRadius: '8px',
                          }}>
                            <span style={{ fontSize: '0.85rem', fontWeight: 700, color: c.contactStatus === 'selected' ? '#c2410c' : '#57423b' }}>
                              {c.contactStatus === 'selected' ? '★ 已選定候選人' : c.contactStatus === 'withdrawn' ? '已退出候選池' : '候選聯繫紀錄'}
                            </span>
                          </div>

                          <div style={{ width: '42px', height: '42px', borderRadius: '50%', backgroundColor: '#ffdbcf', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.4rem' }}>
                            👩‍🍼
                          </div>

                          <div>
                            <div style={{ fontWeight: 700, fontSize: '1.1rem', color: '#1e1b19' }}>
                              {c.staffName}
                              <span style={{ fontSize: '0.82rem', color: '#888', fontWeight: 400, marginLeft: '8px' }}>Staff #{c.staffId}</span>
                            </div>
                            <div style={{ fontSize: '0.82rem', color: '#74593f', marginTop: '2px' }}>
                              📅 {c.serviceRange}{c.reason ? ` ｜ 回覆原因：${c.reason}` : ''}
                            </div>
                          </div>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                          <span style={{
                            padding: '5px 14px',
                            borderRadius: '9999px',
                            fontSize: '0.85rem',
                            fontWeight: 700,
                            backgroundColor: c.willingness === 'willing' ? '#dcfce7' : c.willingness === 'unwilling' ? '#fee2e2' : '#ffedd5',
                            color: c.willingness === 'willing' ? '#166534' : c.willingness === 'unwilling' ? '#991b1b' : '#c2410c',
                          }}>
                            月嫂意願：{c.willingnessLabel}
                          </span>
                        </div>
                      </div>

                      <div className="matching-subcard-grid">
                        <div className="matching-subcard">
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ fontWeight: 700, fontSize: '0.88rem', color: '#1e1b19' }}>📢 訂單資訊-1（粗篩案況徵詢）</span>
                            <span style={{ fontSize: '0.78rem', color: c.info1Status === 'sent' ? '#16a34a' : '#888', fontWeight: 600 }}>
                              {c.info1Status}
                            </span>
                          </div>
                          <div style={{ fontSize: '0.78rem', color: '#888' }}>
                            推播服務天數、時段與地區，保護產婦個資並徵詢初步接案意願。
                          </div>
                          <button
                            type="button"
                            className="matching-action-btn-sm"
                            disabled={candidateActionKey !== null || c.contactStatus === 'withdrawn'}
                            title={c.contactStatus === 'withdrawn' ? '已退出候選池，不建立新的發送任務。' : '建立可靠發送任務'}
                            onClick={() => void sendCandidateInformation(c.candidateId, 1)}
                          >
                            {candidateActionKey === `${c.candidateId}:1` ? '正在建立資訊-1 發送任務…' : '🔄 重新寄送資訊-1'}
                          </button>
                        </div>

                        <div className="matching-subcard">
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ fontWeight: 700, fontSize: '0.88rem', color: '#1e1b19' }}>📄 訂單資訊-2（精篩條款與地址）</span>
                            <span style={{ fontSize: '0.78rem', color: c.info2Status === 'sent' ? '#16a34a' : '#888', fontWeight: 600 }}>
                              {c.info2Status}
                            </span>
                          </div>
                          <div style={{ fontSize: '0.78rem', color: '#888' }}>
                            推播詳細合約條款、地址與特殊膳食需求，供月嫂二次確認。
                          </div>
                          <button
                            type="button"
                            className="matching-action-btn-sm"
                            disabled={candidateActionKey !== null || c.contactStatus === 'withdrawn'}
                            title={c.contactStatus === 'withdrawn' ? '已退出候選池，不建立新的發送任務。' : '建立可靠發送任務'}
                            onClick={() => void sendCandidateInformation(c.candidateId, 2)}
                          >
                            {candidateActionKey === `${c.candidateId}:2` ? '正在建立資訊-2 發送任務…' : '🔄 重新寄送資訊-2'}
                          </button>
                        </div>
                      </div>

                      {c.contactStatus !== 'withdrawn' && (
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', alignItems: 'end', marginTop: '12px', paddingTop: '12px', borderTop: '1px solid #ead8d1' }}>
                          <label style={{ display: 'grid', gap: '4px', fontSize: '0.82rem', color: '#57423b' }}>
                            人工補登意願
                            <select
                              value={candidateWillingnessDrafts[c.candidateId]?.willingness ?? 'willing'}
                              disabled={candidateActionKey !== null}
                              onChange={(event) => setCandidateWillingnessDrafts((current) => ({
                                ...current,
                                [c.candidateId]: {
                                  willingness: event.target.value as 'willing' | 'unwilling',
                                  reason: current[c.candidateId]?.reason ?? '',
                                },
                              }))}
                            >
                              <option value="willing">願意承接</option>
                              <option value="unwilling">無意願</option>
                            </select>
                          </label>
                          <label style={{ display: 'grid', gap: '4px', flex: '1 1 260px', fontSize: '0.82rem', color: '#57423b' }}>
                            拒絕理由（無意願時必填）
                            <input
                              type="text"
                              maxLength={500}
                              value={candidateWillingnessDrafts[c.candidateId]?.reason ?? ''}
                              disabled={candidateActionKey !== null}
                              onChange={(event) => setCandidateWillingnessDrafts((current) => ({
                                ...current,
                                [c.candidateId]: {
                                  willingness: current[c.candidateId]?.willingness ?? 'willing',
                                  reason: event.target.value,
                                },
                              }))}
                            />
                          </label>
                          <button
                            type="button"
                            className="matching-action-btn-sm"
                            disabled={candidateActionKey !== null}
                            onClick={() => void recordMatchingCandidateWillingness(c.candidateId)}
                          >
                            {candidateActionKey === `willingness:${c.candidateId}` ? '更新並回讀中…' : '更新候選意願'}
                          </button>
                          <button
                            type="button"
                            className="orders-load-more-btn"
                            disabled={candidateActionKey !== null || c.willingness !== 'willing'}
                            title={c.willingness === 'willing' ? '建立正式單月嫂方案' : '僅目前願意承接的候選人可建立正式方案'}
                            onClick={() => void createFormalPlanFromWillingCandidate(c.candidateId)}
                          >
                            {candidateActionKey === `formal-plan:${c.candidateId}` ? '建立並回讀正式方案中…' : '建立正式單月嫂配對方案'}
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                  {visibleMatchingCandidates.length === 0 && (
                    <div role="status" style={{ color: '#74593f' }}>目前篩選條件下沒有候選聯繫紀錄。</div>
                  )}
                </div>
              ) : matchingDetail ? (
                <div role="status" style={{ color: '#74593f' }}>目前尚無候選聯繫紀錄。</div>
              ) : null}
            </div>

            {/* 📝 步驟四：推薦產婦、定金狀態與雙邊線上簽約 */}
            {activePlanQueryError ? (
              <div
                role="alert"
                data-surface-id="orders.matching.active-plan-query-error"
                style={{ color: '#b42318', backgroundColor: '#fff1f0', border: '1px solid #f3b8b2', borderRadius: '12px', padding: '14px 16px' }}
              >
                {activePlanQueryError}
              </div>
            ) : matchingDetail && (
              <div className="matching-step-card">
                <div className="matching-step-header">
                  <div>
                    <h3 className="matching-step-title">
                      <span className="matching-step-badge">4</span>
                      📝 推薦產婦、定金確認與雙邊線上簽約
                    </h3>
                    <div className="matching-step-subtext">
                      產婦確認配對方案、繳納定金並完成雙邊不可變線上契約簽署。
                    </div>
                  </div>
                </div>

                <div className="matching-contract-grid">
                  <div className="matching-contract-box">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: '0.95rem', fontWeight: 700, color: '#1e1b19' }}>👥 推薦月嫂給產婦 (Customer Decision)</span>
                      <span style={{
                        padding: '3px 10px',
                        borderRadius: '9999px',
                        fontWeight: 700,
                        fontSize: '0.8rem',
                        backgroundColor: '#f8fafc',
                        color: '#57423b',
                      }}>
                        {matchingDetail.status}
                      </span>
                    </div>
                    <div style={{ fontSize: '0.82rem', color: '#74593f' }}>方案識別：{matchingDetail.planId}</div>
                    <div style={{ fontSize: '0.82rem', color: '#57423b', lineHeight: '1.5' }}>
                      🔒 {matchingDetail.waitingLockText}
                    </div>
                    <div role="status" style={{ fontSize: '0.78rem', color: '#74593f' }}>
                      履歷發送依進行中方案的 communication version 與 segment identity 建立可靠任務。
                    </div>
                  </div>

                  <div className="matching-contract-box">
                    <div style={{ fontWeight: 700, fontSize: '0.95rem', color: '#1e1b19' }}>
                      📑 雙邊線上契約簽署進度 (Contract Signing SSOT)
                    </div>
                    {matchingContractQueryError && (
                      <div role="alert" style={{ color: '#991b1b' }}>{matchingContractQueryError}</div>
                    )}
                    {contractDetail && <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '0.84rem' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span>👩‍🍼 月嫂服務契約：</span>
                        <span style={{ color: contractDetail?.staffContractSigned ? '#16a34a' : '#c2410c', fontWeight: 700 }}>
                          {contractDetail.staffContractSignedText}
                        </span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span>👥 產婦服務契約：</span>
                        <span style={{ color: contractDetail?.clientContractSigned ? '#16a34a' : '#c2410c', fontWeight: 700 }}>
                          {contractDetail.clientContractSignedText}
                        </span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span>💰 客戶定金核銷：</span>
                        <span style={{ color: contractDetail.depositSettled ? '#16a34a' : '#c2410c', fontWeight: 700 }}>
                          {contractDetail.depositSettledText}
                        </span>
                      </div>
                    </div>}
                    <div role="status" style={{ fontSize: '0.78rem', color: '#74593f' }}>
                      契約寄送需由文件版本與收件人 binding 共同建立可靠任務。
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* 📋 步驟五：正式執行排班（生效成果） */}
            <div className="matching-step-card">
              <div className="matching-step-header">
                <div>
                  <h3 className="matching-step-title">
                    <span className="matching-step-badge">5</span>
                    📋 正式執行排班（生效成果）
                  </h3>
                  <div className="matching-step-subtext">
                    只顯示後端 assignment-plan 已確認的正式服務分段與排程日曆。
                  </div>
                </div>
              </div>

              {matchingDetail?.assignmentSegments.length ? (
                <div data-surface-id="orders.matching.assignment-plan" style={{ display: 'grid', gap: '12px' }}>
                  <h4 style={{ margin: 0, fontSize: '0.95rem', color: '#1e1b19' }}>正式執行排班（非候選推薦）</h4>
                  {matchingDetail.assignmentSegments.map((segment) => (
                    <article
                      key={segment.key}
                      style={{
                        border: '1px solid #dec0b6',
                        borderRadius: '12px',
                        padding: '16px 18px',
                        backgroundColor: '#fffdfc',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '6px',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <strong style={{ fontSize: '1rem', color: '#1e1b19' }}>
                          第 {segment.sequence} 段 ｜ Staff #{segment.staffId}
                        </strong>
                        <span style={{
                          padding: '3px 10px',
                          borderRadius: '9999px',
                          backgroundColor: '#dcfce7',
                          color: '#166534',
                          fontSize: '0.78rem',
                          fontWeight: 700,
                        }}>
                          🟢 正式指派生效中
                        </span>
                      </div>
                      <div style={{ fontSize: '0.85rem', color: '#57423b' }}>📅 服務區間：{segment.serviceRange}</div>
                      <div style={{ fontSize: '0.85rem', color: '#57423b' }}>
                        正式服務日：{segment.officialServiceDates.length ? segment.officialServiceDates.join('、') : '無'}
                      </div>
                      <div style={{ fontSize: '0.85rem', color: '#74593f', fontWeight: 600 }}>{segment.actualHoursText}</div>
                    </article>
                  ))}
                </div>
              ) : (
                <div data-surface-id="orders.matching.assignment-plan-unavailable" role="status" style={{ color: '#74593f', fontSize: '0.88rem' }}>
                  {matchingDetailError
                    ? '正式排班資料載入失敗，請關閉後重試。'
                    : matchingAssignmentPlanCorrection
                      ? '完整正式排班 projection 待補正；請以上方案件投影中的 Scheduling 指派來源為準，不視為無排班。'
                      : matchingDetail ? '目前尚無正式執行排班分段' : '正在確認正式排班資料…'}
                </div>
              )}
            </div>
          </div>
        )}
      </Drawer>

      {/* 3. Unified 1280px Workbench: Terms, Service Dates & Contract Progress (size="xl") */}
      <Drawer
        isOpen={Boolean(contractOrder || dateConfirmOrder)}
        onClose={() => {
          if (!serviceDatesLocked) {
            serviceDatesPreviewControllerRef.current?.abort();
            serviceDatesPreviewControllerRef.current = null;
            invalidateDrawerRequest();
            setContractOrder(null);
            setDateConfirmOrder(null);
          }
        }}
        size="xl"
        title={`📑 訂單條款、服務日曆與契約簽署工作台 — ${(contractOrder || dateConfirmOrder)?.id || ''}`}
        footer={
          <button
            style={{
              padding: '10px 24px',
              border: '1px solid #dec0b6',
              borderRadius: '8px',
              background: '#fff',
              fontWeight: 700,
              cursor: 'pointer',
            }}
            onClick={() => {
              if (!serviceDatesLocked) {
                serviceDatesPreviewControllerRef.current?.abort();
                serviceDatesPreviewControllerRef.current = null;
                invalidateDrawerRequest();
                setContractOrder(null);
                setDateConfirmOrder(null);
              }
            }}
            disabled={serviceDatesLocked}
          >
            關閉
          </button>
        }
      >
        {(contractOrder || dateConfirmOrder) && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
            {renderCardProjection()}

            {/* Top 4-Column Fact Strip */}
            <div className="matching-facts-bar">
              <div className="matching-fact-item">
                <div className="matching-fact-label">產婦與地點</div>
                <div className="matching-fact-value">
                  {contractDetail?.clientName || (contractOrder || dateConfirmOrder)?.clientName}
                </div>
                <div style={{ fontSize: '0.78rem', color: '#8b7169' }}>
                  📍 {cardProjection?.rows.find((row) => row.key === 'contact_address')?.valueText
                    || (contractOrder || dateConfirmOrder)?.serviceRange
                    || '地址待確認'}
                </div>
              </div>
              <div className="matching-fact-item">
                <div className="matching-fact-label">約定服務起訖與天數</div>
                <div className="matching-fact-value">
                  {contractDetail?.serviceDays ? `${contractDetail.serviceDays} 天` : '天數待確認'}
                </div>
                <div style={{ fontSize: '0.78rem', color: '#8b7169' }}>
                  📅 {contractDetail?.serviceRange || (contractOrder || dateConfirmOrder)?.serviceRange}
                </div>
              </div>
              <div className="matching-fact-item">
                <div className="matching-fact-label">每日時段與料理</div>
                <div className="matching-fact-value">
                  {contractDetail?.serviceTimeText || '09:00～17:00'}
                </div>
                <div style={{ fontSize: '0.78rem', color: '#8b7169' }}>
                  🍳 {contractDetail?.requiresCookingText || '料理需求待確認'}
                </div>
              </div>
              <div className="matching-fact-item">
                <div className="matching-fact-label">合約總額與定金</div>
                <div className="matching-fact-value">
                  {contractDetail?.contractAmountText || (contractOrder || dateConfirmOrder)?.contractAmountFormatted}
                </div>
                <div style={{ fontSize: '0.78rem', color: contractDetail?.depositSettled ? '#166534' : '#c2410c', fontWeight: 700 }}>
                  {contractDetail?.depositSettled ? '🟢 定金已全額核銷 (檔期鎖定)' : '🟡 定金待核銷'}
                </div>
              </div>
            </div>

            {/* 3-Tab Navigation */}
            <div className="contract-tabs-nav">
              <button
                type="button"
                className={`contract-tab-btn ${activeContractTab === 'contract' ? 'active' : ''}`}
                onClick={() => switchContractTab('contract')}
              >
                📑 雙邊線上契約與定金 (SSOT)
              </button>
              <button
                type="button"
                className={`contract-tab-btn ${activeContractTab === 'terms' ? 'active' : ''}`}
                onClick={() => switchContractTab('terms')}
              >
                ⚙️ 約定服務條款管理 (Order Terms)
              </button>
              <button
                type="button"
                className={`contract-tab-btn ${activeContractTab === 'calendar' ? 'active' : ''}`}
                onClick={() => switchContractTab('calendar')}
              >
                📅 實質服務日曆與天數精算 (Service Calendar)
              </button>
            </div>

            {drawerLoading && (
              <div style={{ textAlign: 'center', padding: '16px', color: '#ff7f50' }}>
                ⏳ 正在載入訂單條款與服務日曆數據...
              </div>
            )}
            {contractQueryError && !drawerLoading && (
              <div role="alert" data-surface-id="orders.contract.query-error" style={{ padding: '12px 14px', borderRadius: '10px', backgroundColor: '#fef2f2', border: '1px solid #fecaca', color: '#991b1b' }}>
                {contractQueryError}
              </div>
            )}
            {contractCorrectionNotice && !drawerLoading && (
              <div role="status" data-surface-id="orders.contract.historical-correction" style={{ padding: '12px 14px', borderRadius: '10px', backgroundColor: '#fffbeb', border: '1px solid #fbbf24', color: '#92400e' }}>
                <strong>歷史資料待補正</strong>
                <div>{contractCorrectionNotice}</div>
              </div>
            )}

            {/* Tab 1: 雙邊線上契約與定金 (SSOT) */}
            {activeContractTab === 'contract' && contractDetail && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div className="matching-contract-grid">
                  <div className="matching-contract-box">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <strong style={{ fontSize: '1rem', color: '#1e1b19' }}>👩‍🍼 月嫂服務契約 (Staff Contract)</strong>
                      <span style={{ padding: '3px 10px', borderRadius: '9999px', backgroundColor: contractDetail.staffContractSigned ? '#dcfce7' : '#fef3c7', color: contractDetail.staffContractSigned ? '#166534' : '#92400e', fontSize: '0.78rem', fontWeight: 700 }}>
                        {contractDetail.staffContractSigned ? '🟢 已線上簽回' : '🟡 待簽署'}
                      </span>
                    </div>
                    <div style={{ fontSize: '0.85rem', color: '#57423b' }}>
                      服務人員：{(contractOrder || dateConfirmOrder)?.assignedDoulaDisplay || '—'}
                    </div>
                    <div style={{ fontSize: '0.85rem', color: '#57423b' }}>
                      簽署進度：<span>{contractDetail.staffContractSignedText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（月嫂契約簽回）`}</span>
                    </div>
                  </div>

                  <div className="matching-contract-box">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <strong style={{ fontSize: '1rem', color: '#1e1b19' }}>👥 產婦服務契約 (Client Contract)</strong>
                      <span style={{ padding: '3px 10px', borderRadius: '9999px', backgroundColor: contractDetail.clientContractSigned ? '#dcfce7' : '#fef3c7', color: contractDetail.clientContractSigned ? '#166534' : '#92400e', fontSize: '0.78rem', fontWeight: 700 }}>
                        {contractDetail.clientContractSigned ? '🟢 已線上簽回' : '🟡 待簽署'}
                      </span>
                    </div>
                    <div style={{ fontSize: '0.85rem', color: '#57423b' }}>
                      立約產婦：{contractDetail.clientName}
                    </div>
                    <div style={{ fontSize: '0.85rem', color: '#57423b' }}>
                      簽署進度：<span>{contractDetail.clientContractSignedText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（客戶契約簽回）`}</span>
                    </div>
                  </div>

                  <div className="matching-contract-box" style={{ gridColumn: '1 / -1' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <strong style={{ fontSize: '1rem', color: '#1e1b19' }}>💰 客戶定金核銷存證 (Deposit Settlement)</strong>
                      <span style={{ padding: '3px 10px', borderRadius: '9999px', backgroundColor: contractDetail.depositSettled ? '#dcfce7' : '#fef3c7', color: contractDetail.depositSettled ? '#166534' : '#92400e', fontSize: '0.78rem', fontWeight: 700 }}>
                        {contractDetail.depositSettled ? '🟢 已全額核銷' : '🟡 待核銷'}
                      </span>
                    </div>
                    <div style={{ fontSize: '0.85rem', color: '#57423b' }}>
                      核銷狀態：<span>{contractDetail.depositSettledText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（客戶定金核銷）`}</span>
                    </div>
                  </div>
                </div>

                {contractDetail.domainBlockers && contractDetail.domainBlockers.length > 0 ? (
                  <div style={{ backgroundColor: '#fef2f2', border: '1px solid #fecaca', padding: '14px', borderRadius: '10px' }}>
                    <div style={{ fontWeight: 700, color: '#991b1b', marginBottom: '6px' }}>🛑 完工阻擋檢核項目：</div>
                    <ul style={{ margin: 0, paddingLeft: '20px', color: '#b91c1c', fontSize: '0.85rem' }}>
                      {contractDetail.domainBlockers.map((b, idx) => (
                        <li key={idx}>{b}</li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <div style={{ backgroundColor: '#f0fdf4', border: '1px solid #bbf7d0', padding: '14px', borderRadius: '10px', color: '#166534', fontWeight: 600, fontSize: '0.88rem' }}>
                    ✅ 雙邊契約簽署齊備且定金已全額核銷，本訂單無任何履約阻擋。
                  </div>
                )}

                {/* Terms Summary & Mutation Form directly accessible in Tab 1 */}
                <div style={{ backgroundColor: '#fff8f6', padding: '16px', borderRadius: '12px', border: '1px solid #f2e2dc' }}>
                  <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#ff7f50', marginBottom: '8px' }}>正式 Order Terms (不可原地修改)</h3>
                  <p><strong>客戶姓名：</strong>{contractDetail?.clientName || (contractOrder || dateConfirmOrder)?.clientName}</p>
                  <p><strong>服務起訖：</strong>{contractDetail?.serviceRange || (contractOrder || dateConfirmOrder)?.serviceRange}（{contractDetail?.serviceDays === null || contractDetail?.serviceDays === undefined ? ORDERS_TYPED_PROJECTION_UNAVAILABLE : `${contractDetail.serviceDays} 天`}）</p>
                  <p><strong>每日時段 Tuple：</strong>{contractDetail?.serviceTimeText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（服務時段）`}</p>
                  <p><strong>下廚料理條款：</strong>{contractDetail?.requiresCookingText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（下廚料理條款）`}</p>
                  <p><strong>樓層加給費：</strong>{contractDetail?.floorFeeText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（樓層加給）`}</p>
                  <p><strong>雇主自付應付額：</strong>{contractDetail?.contractAmountText || (contractOrder || dateConfirmOrder)?.contractAmountFormatted}</p>
                </div>

                <section data-surface-id="orders.terms.mutation" style={{ border: '1px solid #fed9b8', padding: '16px', borderRadius: '12px', backgroundColor: '#ffffff' }}>
                  <h3 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '6px', color: '#ff7f50' }}>編修訂單服務條款（Preview → Apply）</h3>
                  <p style={{ marginTop: 0, color: '#74593f', fontSize: '0.85rem' }}>
                    每次 Apply 都會重查四個 domain version；Preview 本身不寫入。
                  </p>
                  {termsQuery?.service_data_locked && (
                    <div role="status" style={{ marginBottom: '10px', color: '#9a3412' }}>
                      此案件的服務根事實已鎖定，依既有規則不可再變更條款。
                    </div>
                  )}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '10px 14px' }}>
                    <label>計畫服務開始日
                      <input aria-label="計畫服務開始日" type="date" value={termsDraft.plannedStartDate} disabled={termsMutationLocked} onChange={(event) => updateTermsDraft('plannedStartDate', event.target.value)} />
                    </label>
                    <label>服務天數
                      <input aria-label="服務天數" type="number" min="1" value={termsDraft.serviceDays} disabled={termsMutationLocked} onChange={(event) => updateTermsDraft('serviceDays', event.target.value)} />
                    </label>
                    <label>每日服務時數
                      <input aria-label="每日服務時數" type="number" min="1" value={termsDraft.serviceHoursPerDay} disabled={termsMutationLocked} onChange={(event) => updateTermsDraft('serviceHoursPerDay', event.target.value)} />
                    </label>
                    <label>下廚料理需求
                      <select aria-label="下廚料理需求" value={termsDraft.requiresCooking} disabled={termsMutationLocked} onChange={(event) => updateTermsDraft('requiresCooking', event.target.value as OrderTermsDraft['requiresCooking'])}>
                        <option value="">請明確選擇</option>
                        <option value="yes">需要下廚</option>
                        <option value="no">不需下廚</option>
                      </select>
                    </label>
                    <label>樓層加給（NTD）
                      <input aria-label="樓層加給" type="number" min="0" value={termsDraft.floorFeeNtd} disabled={termsMutationLocked} onChange={(event) => updateTermsDraft('floorFeeNtd', event.target.value)} />
                    </label>
                    <label>每日開始時間
                      <input aria-label="每日開始時間" type="time" value={termsDraft.startTime} disabled={termsMutationLocked} onChange={(event) => updateTermsDraft('startTime', event.target.value)} />
                    </label>
                    <label>每日結束時間
                      <input aria-label="每日結束時間" type="time" value={termsDraft.endTime} disabled={termsMutationLocked} onChange={(event) => updateTermsDraft('endTime', event.target.value)} />
                    </label>
                    <label>結束日偏移
                      <select aria-label="結束日偏移" value={termsDraft.endDayOffset} disabled={termsMutationLocked} onChange={(event) => updateTermsDraft('endDayOffset', event.target.value as OrderTermsDraft['endDayOffset'])}>
                        <option value="0">同日</option>
                        <option value="1">隔日</option>
                      </select>
                    </label>
                  </div>
                  <button
                    type="button"
                    disabled={termsMutationLocked || !termsDraftReady}
                    onClick={() => void previewOrderTerms()}
                    style={{ marginTop: '12px' }}
                  >
                    {termsMutationStatus === 'previewing' ? '條款 Preview 處理中…' : '預覽訂單條款變更'}
                  </button>
                  {termsPreview && (
                    <div style={{ marginTop: '12px', background: '#fff8f6', borderRadius: '10px', padding: '12px' }}>
                      <strong>Preview 已產生</strong>
                      <div>服務日期：{termsPreview.after.planned_start_date}｜{termsPreview.after.service_days} 天</div>
                      <div>每日時段：{termsPreview.after.service_time.start_time} ～ {termsPreview.after.service_time.end_time}</div>
                      <div>Fingerprint：{termsPreview.preview_fingerprint.slice(0, 12)}…</div>
                      <label style={{ display: 'block', marginTop: '8px' }}>變更原因
                        <textarea aria-label="訂單條款變更原因" rows={2} maxLength={500} value={termsReason} disabled={termsMutationLocked} onChange={(event) => setTermsReason(event.target.value)} />
                      </label>
                      <button type="button" disabled={termsMutationLocked || termsReason.trim().length === 0} onClick={() => void applyOrderTerms()}>
                        {termsMutationStatus === 'applying' ? '條款套用中…' : '確認套用訂單條款'}
                      </button>
                    </div>
                  )}
                  {termsReceipt && (
                    <div role="status" style={{ marginTop: '10px', color: '#166534', fontWeight: 700 }}>
                      條款已套用（Order v{termsReceipt.order_version}；正式服務日 {termsReceipt.official_service_day_count} 天）
                    </div>
                  )}
                  {termsMutationError && <div role="alert" style={{ marginTop: '10px', color: '#b91c1c' }}>{termsMutationError}</div>}
                </section>
              </div>
            )}

            {/* Tab 2: 約定服務條款管理 (Order Terms) */}
            {activeContractTab === 'terms' && contractDetail && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div style={{ backgroundColor: '#fff8f6', padding: '16px', borderRadius: '12px', border: '1px solid #f2e2dc' }}>
                  <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#ff7f50', marginBottom: '8px' }}>正式 Order Terms (不可原地修改)</h3>
                  <p><strong>客戶姓名：</strong>{contractDetail?.clientName || (contractOrder || dateConfirmOrder)?.clientName}</p>
                  <p><strong>服務起訖：</strong>{contractDetail?.serviceRange || (contractOrder || dateConfirmOrder)?.serviceRange}（{contractDetail?.serviceDays === null || contractDetail?.serviceDays === undefined ? ORDERS_TYPED_PROJECTION_UNAVAILABLE : `${contractDetail.serviceDays} 天`}）</p>
                  <p><strong>每日時段 Tuple：</strong>{contractDetail?.serviceTimeText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（服務時段）`}</p>
                  <p><strong>下廚料理條款：</strong>{contractDetail?.requiresCookingText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（下廚料理條款）`}</p>
                  <p><strong>樓層加給費：</strong>{contractDetail?.floorFeeText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（樓層加給）`}</p>
                  <p><strong>雇主自付應付額：</strong>{contractDetail?.contractAmountText || (contractOrder || dateConfirmOrder)?.contractAmountFormatted}</p>
                </div>

                <section data-surface-id="orders.terms.mutation" style={{ border: '1px solid #fed9b8', padding: '16px', borderRadius: '12px', backgroundColor: '#ffffff' }}>
                  <h3 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '6px', color: '#ff7f50' }}>編修訂單服務條款（Preview → Apply）</h3>
                  <p style={{ marginTop: 0, color: '#74593f', fontSize: '0.85rem' }}>
                    每次 Apply 都會重查四個 domain version；Preview 本身不寫入。
                  </p>
                  {termsQuery?.service_data_locked && (
                    <div role="status" style={{ marginBottom: '10px', color: '#9a3412' }}>
                      此案件的服務根事實已鎖定，依既有規則不可再變更條款。
                    </div>
                  )}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '10px 14px' }}>
                    <label>計畫服務開始日
                      <input aria-label="計畫服務開始日" type="date" value={termsDraft.plannedStartDate} disabled={termsMutationLocked} onChange={(event) => updateTermsDraft('plannedStartDate', event.target.value)} />
                    </label>
                    <label>服務天數
                      <input aria-label="服務天數" type="number" min="1" value={termsDraft.serviceDays} disabled={termsMutationLocked} onChange={(event) => updateTermsDraft('serviceDays', event.target.value)} />
                    </label>
                    <label>每日服務時數
                      <input aria-label="每日服務時數" type="number" min="1" value={termsDraft.serviceHoursPerDay} disabled={termsMutationLocked} onChange={(event) => updateTermsDraft('serviceHoursPerDay', event.target.value)} />
                    </label>
                    <label>下廚料理需求
                      <select aria-label="下廚料理需求" value={termsDraft.requiresCooking} disabled={termsMutationLocked} onChange={(event) => updateTermsDraft('requiresCooking', event.target.value as OrderTermsDraft['requiresCooking'])}>
                        <option value="">請明確選擇</option>
                        <option value="yes">需要下廚</option>
                        <option value="no">不需下廚</option>
                      </select>
                    </label>
                    <label>樓層加給（NTD）
                      <input aria-label="樓層加給" type="number" min="0" value={termsDraft.floorFeeNtd} disabled={termsMutationLocked} onChange={(event) => updateTermsDraft('floorFeeNtd', event.target.value)} />
                    </label>
                    <label>每日開始時間
                      <input aria-label="每日開始時間" type="time" value={termsDraft.startTime} disabled={termsMutationLocked} onChange={(event) => updateTermsDraft('startTime', event.target.value)} />
                    </label>
                    <label>每日結束時間
                      <input aria-label="每日結束時間" type="time" value={termsDraft.endTime} disabled={termsMutationLocked} onChange={(event) => updateTermsDraft('endTime', event.target.value)} />
                    </label>
                    <label>結束日偏移
                      <select aria-label="結束日偏移" value={termsDraft.endDayOffset} disabled={termsMutationLocked} onChange={(event) => updateTermsDraft('endDayOffset', event.target.value as OrderTermsDraft['endDayOffset'])}>
                        <option value="0">同日</option>
                        <option value="1">隔日</option>
                      </select>
                    </label>
                  </div>
                  <button
                    type="button"
                    disabled={termsMutationLocked || !termsDraftReady}
                    onClick={() => void previewOrderTerms()}
                    style={{ marginTop: '12px' }}
                  >
                    {termsMutationStatus === 'previewing' ? '條款 Preview 處理中…' : '預覽訂單條款變更'}
                  </button>
                  {termsPreview && (
                    <div style={{ marginTop: '12px', background: '#fff8f6', borderRadius: '10px', padding: '12px' }}>
                      <strong>Preview 已產生</strong>
                      <div>服務日期：{termsPreview.after.planned_start_date}｜{termsPreview.after.service_days} 天</div>
                      <div>每日時段：{termsPreview.after.service_time.start_time} ～ {termsPreview.after.service_time.end_time}</div>
                      <div>Fingerprint：{termsPreview.preview_fingerprint.slice(0, 12)}…</div>
                      <label style={{ display: 'block', marginTop: '8px' }}>變更原因
                        <textarea aria-label="訂單條款變更原因" rows={2} maxLength={500} value={termsReason} disabled={termsMutationLocked} onChange={(event) => setTermsReason(event.target.value)} />
                      </label>
                      <button type="button" disabled={termsMutationLocked || termsReason.trim().length === 0} onClick={() => void applyOrderTerms()}>
                        {termsMutationStatus === 'applying' ? '條款套用中…' : '確認套用訂單條款'}
                      </button>
                    </div>
                  )}
                  {termsReceipt && (
                    <div role="status" style={{ marginTop: '10px', color: '#166534', fontWeight: 700 }}>
                      條款已套用（Order v{termsReceipt.order_version}；正式服務日 {termsReceipt.official_service_day_count} 天）
                    </div>
                  )}
                  {termsMutationError && <div role="alert" style={{ marginTop: '10px', color: '#b91c1c' }}>{termsMutationError}</div>}
                </section>
              </div>
            )}

            {/* Tab 3: 實質服務日曆與天數精算 (Service Calendar & Precision) */}
            {activeContractTab === 'calendar' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <section
                  data-surface-id="orders.drawer.service-dates"
                  style={{ backgroundColor: '#ffffff', border: '1px solid #cbd5e1', padding: '20px', borderRadius: '14px' }}
                >
                  <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#0f766e', marginBottom: '12px' }}>
                    正式服務日期確認
                  </h3>

                  {serviceDatesDraft?.queryView && (
                    <>
                      <div className="service-dates-meta-row" style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', marginBottom: '14px', fontSize: '0.85rem' }}>
                        <span>合約服務天數：{serviceDatesDraft.queryView.contracted_service_days} 天</span>
                        <span>目前確認版本：{serviceDatesDraft.queryView.current_version === null ? '尚未確認' : `v${serviceDatesDraft.queryView.current_version}`}</span>
                        <span>已確認日期：{serviceDatesDraft.queryView.current_dates.length > 0 ? serviceDatesDraft.queryView.current_dates.join(', ') : '無'}</span>
                      </div>

                      {/* Schedule Precision Controls Bar */}
                      <div style={{ backgroundColor: '#fffdfc', border: '1px solid #fed9b8', borderRadius: '12px', padding: '16px', marginBottom: '16px' }}>
                        <div style={{ fontWeight: 700, fontSize: '0.92rem', color: '#ff7f50', marginBottom: '10px' }}>
                          🧮 出勤天數精算與排休順延控制
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: '12px', alignItems: 'flex-end' }}>
                          <div>
                            <div style={{ fontSize: '0.82rem', fontWeight: 700, color: '#57423b', marginBottom: '6px' }}>
                              實際開工基準：
                            </div>
                            <div style={{ padding: '7px 10px', borderRadius: '8px', backgroundColor: '#f1f5f9', border: '1px solid #dec0b6', fontSize: '0.9rem', fontWeight: 600, color: '#334155' }}>
                              📅 {actualStartDraft || termsDraft.plannedStartDate || '2026-09-01'}
                            </div>
                          </div>
                          <div>
                            <label htmlFor="precision-service-mode" style={{ display: 'block', fontSize: '0.82rem', fontWeight: 700, color: '#57423b', marginBottom: '4px' }}>
                              排班服務模式：
                            </label>
                            <select
                              id="precision-service-mode"
                              value={precisionMode}
                              disabled={serviceDatesLocked}
                              onChange={(event) => setPrecisionMode(event.target.value as '週休1日' | '週休2日' | '連續服務')}
                              style={{ width: '100%', padding: '7px 10px', borderRadius: '8px', border: '1px solid #dec0b6' }}
                            >
                              <option value="週休1日">週休 1 日</option>
                              <option value="週休2日">週休 2 日</option>
                              <option value="連續服務">連續服務 (無排休)</option>
                            </select>
                          </div>
                          <button
                            type="button"
                            disabled={serviceDatesLocked || precisionCalculating}
                            onClick={() => void runSchedulePrecision((contractOrder || dateConfirmOrder)!.id)}
                            style={{
                              padding: '8px 18px',
                              backgroundColor: '#ff7f50',
                              color: '#fff',
                              border: 'none',
                              borderRadius: '8px',
                              fontWeight: 700,
                              cursor: 'pointer',
                            }}
                          >
                            {precisionCalculating ? '精算中…' : '🧮 執行出勤天數精算'}
                          </button>
                        </div>

                        {precisionResult && (
                          <div className="precision-stat-grid" style={{ marginTop: '14px' }}>
                            <div className="precision-stat-box">
                              <span className="precision-stat-label">合約目標天數</span>
                              <span className="precision-stat-val">{precisionResult.target_service_days} 天</span>
                            </div>
                            <div className="precision-stat-box">
                              <span className="precision-stat-label">實質出勤天數</span>
                              <span className="precision-stat-val" style={{ color: '#0f766e' }}>{precisionResult.actual_work_days_count} 天</span>
                            </div>
                            <div className="precision-stat-box">
                              <span className="precision-stat-label">排休/假日記數</span>
                              <span className="precision-stat-val" style={{ color: '#9a3412' }}>{precisionResult.rest_days_count} 天</span>
                            </div>
                            <div className="precision-stat-box">
                              <span className="precision-stat-label">總日曆跨越天</span>
                              <span className="precision-stat-val">{precisionResult.total_calendar_days} 天</span>
                            </div>
                            <div className="precision-stat-box">
                              <span className="precision-stat-label">🎯 自動順延完工日</span>
                              <span className="precision-stat-val" style={{ color: '#ff7f50' }}>{precisionResult.actual_end_date}</span>
                            </div>
                          </div>
                        )}
                        {precisionError && (
                          <div role="alert" style={{ color: '#b91c1c', fontSize: '0.85rem', marginTop: '8px' }}>
                            {precisionError}
                          </div>
                        )}
                      </div>

                      {/* Selectable Date Matrix */}
                      <div data-surface-id="orders.date.service-date-selection" style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '12px' }}>
                        {serviceDatesDraft.queryView.selectable_dates.map((date) => {
                          const selected = serviceDatesDraft.selectedDates.includes(date);
                          return (
                            <button
                              key={date}
                              data-control-id="orders.date.service-date-select"
                              type="button"
                              aria-pressed={selected}
                              disabled={serviceDatesLocked}
                              onClick={() =>
                                changeServiceDateSelection(
                                  (contractOrder || dateConfirmOrder)!.id,
                                  selected
                                    ? serviceDatesDraft.selectedDates.filter((value) => value !== date)
                                    : [...serviceDatesDraft.selectedDates, date]
                                )
                              }
                              style={{
                                padding: '7px 10px',
                                borderRadius: '8px',
                                border: selected ? '1px solid #0d9488' : '1px solid #cbd5e1',
                                background: selected ? '#ccfbf1' : '#fff',
                                color: '#0f766e',
                                cursor: serviceDatesLocked ? 'not-allowed' : 'pointer',
                              }}
                            >
                              {date}
                            </button>
                          );
                        })}
                      </div>

                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', marginBottom: '12px' }}>
                        <button
                          type="button"
                          disabled={serviceDatesLocked}
                          onClick={() => changeServiceDateSelection((contractOrder || dateConfirmOrder)!.id, serviceDatesDraft.queryView!.suggested_dates)}
                        >
                          帶入建議日期
                        </button>
                        <button
                          type="button"
                          data-control-id="orders.date.service-date-preview"
                          disabled={
                            serviceDatesLocked ||
                            serviceDatesDraft.status === 'preview_loading' ||
                            serviceDatesDraft.selectedDates.length !== serviceDatesDraft.queryView.contracted_service_days
                          }
                          onClick={() => previewServiceDates((contractOrder || dateConfirmOrder)!.id)}
                        >
                          {serviceDatesDraft.status === 'preview_loading' ? '預覽處理中…' : '預覽正式服務日期'}
                        </button>
                      </div>
                    </>
                  )}

                  {serviceDatesDraft?.previewView && (
                    <div style={{ background: '#fff', border: '1px solid #99f6e4', borderRadius: '10px', padding: '14px' }}>
                      <h4 style={{ color: '#0f766e', marginBottom: '8px' }}>服務週次精算預覽</h4>
                      {serviceDatesDraft.previewView.weeks.map((week) => (
                        <div key={week.week_number} style={{ marginBottom: '6px', fontSize: '0.85rem' }}>
                          第 {week.week_number} 週：{week.period_start} ～ {week.period_end}（{week.service_dates.join(', ')}）
                        </div>
                      ))}
                      <label style={{ display: 'block', marginTop: '10px', fontWeight: 700 }}>
                        確認原因
                        <textarea
                          className="mutation-reason-input"
                          rows={3}
                          maxLength={500}
                          value={serviceDatesDraft.reason}
                          disabled={serviceDatesLocked}
                          onChange={(event) => updateServiceDatesReason((contractOrder || dateConfirmOrder)!.id, event.target.value)}
                          style={{ display: 'block', width: '100%', marginTop: '6px' }}
                        />
                      </label>
                      <button
                        type="button"
                        data-control-id="orders.date.service-date-apply"
                        disabled={serviceDatesLocked || serviceDatesDraft.reason.trim().length === 0}
                        onClick={() => void applyServiceDatesFlow((contractOrder || dateConfirmOrder)!.id).catch(() => undefined)}
                        style={{ marginTop: '10px' }}
                      >
                        確認套用服務日期
                      </button>
                    </div>
                  )}

                  {serviceDatesDraft?.status === 'outcome_unknown' && (
                    <div role="alert" style={{ marginTop: '12px', color: '#9a3412' }}>
                      服務日期確認回應逾時或未明；只可用原 Payload 與原 Key 重試。
                      <button type="button" onClick={() => void retryServiceDatesApplyFlow((contractOrder || dateConfirmOrder)!.id).catch(() => undefined)}>
                        重試提交
                      </button>
                    </div>
                  )}
                  {(serviceDatesDraft?.status === 'observed' || serviceDatesDraft?.status === 'receipt_received' || serviceDatesDraft?.status === 'requery_loading') && serviceDatesDraft.receiptView && (
                    <div role="status" style={{ marginTop: '12px', color: '#166534', fontWeight: 700 }}>
                      服務日期已確認成功（Confirmed v{serviceDatesDraft.receiptView.confirmed_version}）
                    </div>
                  )}
                  {serviceDatesDraft?.status === 'observation_failed' && (
                    <div role="alert" style={{ marginTop: '12px', color: '#9a3412' }}>
                      套用 receipt 已收到，但重新查詢失敗：{serviceDatesDraft.error?.message}
                      <button type="button" onClick={() => void retryServiceDatesObservationFlow((contractOrder || dateConfirmOrder)!.id).catch(() => undefined)}>
                        重試觀察
                      </button>
                    </div>
                  )}
                  {(serviceDatesDraft?.status === 'typed_error' || serviceDatesDraft?.status === 'stale') && (
                    <div role="alert" style={{ marginTop: '12px', color: '#b91c1c' }}>
                      {serviceDatesDraft.error?.message ?? '服務日期操作失敗，請重新查詢。'}
                    </div>
                  )}
                </section>

                {/* 實際服務開始日 */}
                <div style={{ backgroundColor: '#ffffff', border: '1px solid #fed9b8', padding: '20px', borderRadius: '14px' }}>
                  <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#ff7f50', marginBottom: '12px' }}>
                    實際服務開始日
                  </h3>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '14px' }}>
                    <div>
                      <label htmlFor="edit-actual-start-date" style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#57423b', marginBottom: '6px' }}>
                        實際服務開始日：
                      </label>
                      <input
                        id="edit-actual-start-date"
                        type="date"
                        value={actualStartDraft}
                        disabled={actualStartLocked || actualStartQuery === null}
                        onChange={(event) => {
                          setActualStartDraft(event.target.value);
                          setActualStartPreview(null);
                          setActualStartReceipt(null);
                        }}
                        style={{ width: '100%', padding: '8px 12px', borderRadius: '8px', border: '1px solid #dec0b6', fontSize: '0.95rem', fontWeight: 600, backgroundColor: '#f8fafc' }}
                      />
                      <button
                        type="button"
                        disabled={actualStartLocked || actualStartQuery === null || actualStartDraft.length === 0}
                        onClick={() => void previewActualStart()}
                        style={{ marginTop: '8px' }}
                      >
                        {actualStartStatus === 'previewing' ? '實際開工日 Preview 處理中…' : '預覽實際開工日變更'}
                      </button>
                    </div>
                    <div style={{ backgroundColor: '#fff8f6', border: '1px solid #fed9b8', borderRadius: '10px', padding: '12px' }}>
                      <strong>最新根事實版本</strong>
                      <div>計畫開始日：{actualStartQuery?.planned_start_date ?? '查詢中'}</div>
                      <div>目前實際開始日：{actualStartQuery?.current_actual_start_date ?? '尚未登錄'}</div>
                      <div>Order v{actualStartQuery?.order_version ?? '—'}｜Scheduling v{actualStartQuery?.scheduling_version ?? '—'}</div>
                    </div>
                  </div>

                  {actualStartQuery?.service_data_locked && (
                    <div role="status" style={{ color: '#92400e', marginBottom: '10px' }}>
                      本案服務資料已鎖定；目前只能查詢，需先依既有解鎖流程處理後才能更正。
                    </div>
                  )}
                  {actualStartPreview && (
                    <div style={{ backgroundColor: '#fff8f6', border: '1px solid #fed9b8', borderRadius: '10px', padding: '14px', marginBottom: '12px' }}>
                      <strong>實際開工日 Preview 已產生</strong>
                      <div>日期：{actualStartPreview.before_actual_start_date ?? '尚未登錄'} → {actualStartPreview.after_actual_start_date}</div>
                      <div>預計結束日：{actualStartPreview.actual_end_date}</div>
                      <div>正式服務日：{actualStartPreview.actual_start.official_service_dates.length} 天</div>
                      <div>重建指派：{actualStartPreview.scheduling.assignments.length} 段</div>
                      <label style={{ display: 'block', marginTop: '8px' }}>
                        套用原因
                        <textarea
                          aria-label="實際開工日變更原因"
                          rows={2}
                          maxLength={500}
                          value={actualStartReason}
                          disabled={actualStartLocked}
                          onChange={(event) => setActualStartReason(event.target.value)}
                        />
                      </label>
                      <button
                        type="button"
                        disabled={actualStartLocked || actualStartReason.trim().length === 0}
                        onClick={() => void applyActualStart()}
                      >
                        {actualStartStatus === 'applying' ? '實際開工日套用中…' : '確認套用實際開工日'}
                      </button>
                    </div>
                  )}
                  {actualStartReceipt && (
                    <div role="status" style={{ color: '#166534', fontWeight: 700, marginBottom: '10px' }}>
                      實際開工日已套用（Order v{actualStartReceipt.order_version}；{actualStartReceipt.official_service_day_count} 個正式服務日）
                    </div>
                  )}
                  {actualStartError && <div role="alert" style={{ color: '#b91c1c', marginBottom: '10px' }}>{actualStartError}</div>}
                </div>
              </div>
            )}
          </div>
        )}
      </Drawer>

      {/* 4. Cancellation & Refund Preview Drawer */}
      <Drawer
        isOpen={cancelOrder !== null}
        onClose={() => { invalidateDrawerRequest(); setCancelOrder(null); }}
        size="wide"
        title={`🛑 訂單取消與退款試算 (Preview) - ${cancelOrder?.id || ''}`}
        footer={
          <button
            style={{ padding: '8px 16px', border: '1px solid #dec0b6', borderRadius: '8px', background: '#fff', cursor: 'pointer' }}
            onClick={() => { invalidateDrawerRequest(); setCancelOrder(null); }}
          >
            關閉
          </button>
        }
      >
        {cancelOrder && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {renderCardProjection()}
            {cancellationStatus === 'querying' && <div role="status">正在載入取消根事實…</div>}
            {cancellationError && <div role="alert">{cancellationError}</div>}
            {cancellationQuery && (
              <section style={{ backgroundColor: '#fff1f2', padding: '16px', borderRadius: '12px', border: '1px solid #fecdd3' }}>
                <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#9f1239', marginBottom: '8px' }}>取消前根事實</h3>
                <div>生命週期：{cancellationQuery.lifecycle_status}</div>
                <div>實際開始日：{cancellationQuery.actual_start_date ?? '尚未開始'}</div>
                <div>契約服務天數：{cancellationQuery.contracted_service_days} 天</div>
                <div>已確認服務日：{cancellationQuery.confirmed_service_days.length} 天</div>
                <button
                  type="button"
                  data-control-id="orders.cancellation.preview"
                  disabled={cancellationStatus === 'previewing'}
                  onClick={() => void previewCancellation()}
                  style={{ marginTop: '12px' }}
                >
                  {cancellationStatus === 'previewing' ? '正在產生取消預覽…' : '產生取消預覽'}
                </button>
              </section>
            )}
            {cancellationPreview && (
              <section style={{ backgroundColor: '#fff', padding: '16px', borderRadius: '12px', border: '1px solid #dec0b6' }}>
                <h4 style={{ fontWeight: 700, marginBottom: '8px' }}>取消影響預覽（零寫入）</h4>
                <div>取消日期：{cancellationPreview.cancellation_date}</div>
                <div>服務結束日：{cancellationPreview.actual_end_date ?? '無'}</div>
                <div>正式服務天數：{cancellationPreview.official_service_day_count} 天</div>
                <div>正式服務時數：{cancellationPreview.official_service_hours} 小時</div>
                <div>排班版本：v{cancellationPreview.scheduling_version}</div>
                <div>財務版本：v{cancellationPreview.client_finance_version}</div>
              </section>
            )}
          </div>
        )}
      </Drawer>

      <Drawer
        isOpen={reopenOrder !== null}
        onClose={handleCloseReopen}
        size="wide"
        title={`🔄 訂單受控重開 — ${reopenOrder?.id || ''}`}
        footer={
          <button
            type="button"
            onClick={handleCloseReopen}
            disabled={reopenLocked}
            style={{ padding: '8px 16px' }}
          >
            關閉
          </button>
        }
      >
        {reopenOrder && (
          <div data-surface-id="orders.modal.reopen" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {reopenDraft?.status === 'preview_loading' && (
              <div role="status">正在向伺服器取得重開預覽…</div>
            )}

            {reopenDraft?.previewView && (
              <>
                <div style={{ background: '#fff7ed', border: '1px solid #fed7aa', borderRadius: '12px', padding: '16px' }}>
                  <h3 style={{ marginBottom: '8px', color: '#9a3412' }}>伺服器重開候選</h3>
                  <div>{reopenDraft.previewView.before_status} → <strong>{reopenDraft.previewView.after_status}</strong></div>
                  <div>Order v{reopenDraft.previewView.order_version}</div>
                  <div>Client Finance v{reopenDraft.previewView.client_finance_version}</div>
                  <div>Payroll v{reopenDraft.previewView.payroll_version}</div>
                  <div>Cancellation Event #{reopenDraft.previewView.cancellation_event_id}</div>
                  <div>
                    requires_fresh_scheduling_preview：
                    {reopenDraft.previewView.requires_fresh_scheduling_preview ? '是，必須重新產生排程預覽' : '否'}
                  </div>
                  <div>恢復 Assignment／Schedule／Lock：0／0／0</div>
                </div>

                <label style={{ fontWeight: 700 }}>
                  重開原因
                  <textarea
                    data-control-id="orders.reopen.reason"
                    rows={4}
                    maxLength={500}
                    value={reopenDraft.reason}
                    disabled={reopenLocked}
                    onChange={(event) => updateReopenReason(reopenOrder.id, event.target.value)}
                    style={{ display: 'block', width: '100%', marginTop: '6px' }}
                  />
                </label>
                <button
                  type="button"
                  data-control-id="orders.reopen.apply"
                  disabled={reopenLocked || reopenDraft.reason.trim().length === 0}
                  onClick={() => void applyReopenFlow(reopenOrder.id, fetchOrderSummaries).catch(() => undefined)}
                >
                  確認受控重開
                </button>
              </>
            )}

            {reopenDraft?.status === 'outcome_unknown' && (
              <div role="alert" style={{ color: '#9a3412' }}>
                訂單重開回應逾時或未明；只可使用相同 Payload 與相同 Key 重試。
                <button
                  type="button"
                  onClick={() => void retryReopenApplyFlow(reopenOrder.id, fetchOrderSummaries).catch(() => undefined)}
                >
                  重試重開
                </button>
              </div>
            )}

            {reopenDraft?.receiptView && (
              <div role="status" style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '12px', padding: '14px', color: '#166534' }}>
                <strong>訂單已成功重開</strong>
                <div>伺服器狀態：{reopenDraft.receiptView.lifecycle_status}</div>
                <div>Order v{reopenDraft.receiptView.order_version}</div>
                <div>仍需 fresh scheduling preview：{reopenDraft.receiptView.requires_fresh_scheduling_preview ? '是' : '否'}</div>
              </div>
            )}

            {reopenDraft?.status === 'observation_failed' && (
              <div role="alert" style={{ color: '#9a3412' }}>
                重開 receipt 已收到，但重新查詢失敗：{reopenDraft.error?.message}
                <button
                  type="button"
                  onClick={() => void retryReopenObservationFlow(reopenOrder.id, fetchOrderSummaries).catch(() => undefined)}
                >
                  重試觀察
                </button>
              </div>
            )}

            {(reopenDraft?.status === 'typed_error' || reopenDraft?.status === 'stale') && (
              <div role="alert" style={{ background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '12px', padding: '14px', color: '#991b1b' }}>
                <div>{reopenDraft.error?.message ?? '訂單受控重開失敗。'}</div>
                {reopenTypedError?.correlationId && <div>ID: {reopenTypedError.correlationId}</div>}
                {reopenTypedError?.domainBlockers.map((blocker) => (
                  <div key={blocker}>{blocker}</div>
                ))}
              </div>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default OrdersPage;

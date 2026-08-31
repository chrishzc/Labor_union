/**
 * File: OrdersPage.tsx
 * Description: 顯示 Orders 摘要與可操作 Drawer，整合外部簽約、服務前換人與 typed 媒合操作。
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import './OrdersPage.css';
import { loadAllOrderSummaries, ordersQueryClient } from '../api/orders/order_query_client';
import { contractSigningClient } from '../api/orders/contract_signing_client';
import {
  orderCancellationClient,
  type OrderCancellationApplyPayload,
  type OrderCancellationPreview,
  type OrderCancellationQuery,
  type OrderCancellationReceipt,
  type ServiceDay,
} from '../api/orders/order_cancellation_client';
import { orderCardProjectionClient } from '../api/orders/order_card_projection_client';
import { loadAllOrderOperationalTimelines, orderStageProjectionClient } from '../api/orders/order_stage_projection_client';
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
import type { ActualStart, FormManagementContext, OrderDetail } from '../api/orders/order_query_schemas';
import { candidateContactPoolClient } from '../api/scheduling/candidate_contact_pool_client';
import {
  matchingCandidateWorkflowClient,
  defaultMatchingFilterPolicy,
  type MatchingAvailability,
} from '../api/scheduling/matching_candidate_workflow_client';
import {
  waitingDepositLockClient,
  type WaitingDepositPreview,
  type WaitingDepositReceipt,
} from '../api/scheduling/waiting_deposit_lock_client';
import {
  matchingPlanCommunicationClient,
  type CustomerProfilesNotificationReceipt,
} from '../api/scheduling/matching_plan_communication_client';
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
} from '../adapters/orders/order_stage_projection_adapter';
import type {
  OrderOperationalTimeline,
  OrderOperationalTimelinePage,
} from '../api/orders/order_stage_projection_schemas';
import { Drawer } from '../components/Drawer';
import { ContractExternalSigningActions } from '../components/ContractExternalSigningActions';
import { ServiceBeforeReplacementActions } from '../components/ServiceBeforeReplacementActions';
import { MatchingScheduleAndAssignmentActions } from '../components/MatchingScheduleAndAssignmentActions';
import { OrderServiceCompletionActions } from '../components/OrderServiceCompletionActions';
import {
  CandidateManualInformationActions,
  CustomerProfilesManualActions,
} from '../components/MatchingManualCommunicationActions';
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
  retryServiceDatesApplyFlow,
  selectServiceDates,
  updateReopenReason,
  updateServiceDatesReason,
} from '../adapters/orders/order_mutation_adapter';

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

function matchingAvailabilityErrorMessage(caught: unknown, fallback: string): string {
  if (caught instanceof ApiHttpError && caught.code === 'matching_preference_source_not_ready') {
    return '下廚料理需求尚未就緒；請先從資料匯入中心匯入並唯一配對 Client BeClass，再重新查詢月嫂。';
  }
  if (caught instanceof ApiHttpError && caught.code === 'official_service_dates_incomplete') {
    return '尚未確認精確服務日期；請先完成日期精算與休假調整，再重新查詢月嫂。';
  }
  if (caught instanceof ApiHttpError && caught.code === 'caregiver_availability_stage_conflict') {
    return '此案已不在洽談階段，不能重新查詢候選月嫂；請依既有正式方案、定金與簽約流程繼續。';
  }
  return caught instanceof Error ? caught.message : fallback;
}

function cancellationPreviewErrorMessage(caught: unknown): string {
  if (caught instanceof ApiHttpError) {
    return caught.message;
  }
  return caught instanceof Error
    ? caught.message
    : '取消預覽未通過，請確認案件狀態與服務日資料。';
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

interface CancellationServiceDayDraft {
  service_date: string;
  staff_id: number;
  reason: string;
}

type ClientFinanceDirection =
  | 'refund_due'
  | 'additional_charge_due'
  | 'no_finance_change';

function clientFinanceDirectionLabel(direction: ClientFinanceDirection): string {
  switch (direction) {
    case 'refund_due':
      return '應退款';
    case 'additional_charge_due':
      return '應補收';
    case 'no_finance_change':
      return '無帳務變動';
    default:
      return direction;
  }
}

const cancellationDayDrafts = (days: ServiceDay[]): CancellationServiceDayDraft[] => days.map((day) => ({
  service_date: day.service_date,
  staff_id: day.staff_id,
  reason: day.reason ?? '',
}));

const validCancellationDays = (days: CancellationServiceDayDraft[]): ServiceDay[] | null => {
  if (days.some((day) => !/^\d{4}-\d{2}-\d{2}$/.test(day.service_date) || !Number.isInteger(day.staff_id) || day.staff_id <= 0)) return null;
  const typed = days.map((day) => ({
    service_date: day.service_date,
    staff_id: day.staff_id,
    reason: day.reason.trim() || null,
  }));
  const dates = typed.map((day) => day.service_date);
  return new Set(dates).size === dates.length ? typed : null;
};

interface CancellationApplyAttempt {
  caseNo: string;
  idempotencyKey: string;
  payload: OrderCancellationApplyPayload;
}

const sameCancellationApplyPayload = (
  left: OrderCancellationApplyPayload,
  right: OrderCancellationApplyPayload,
): boolean => JSON.stringify(left) === JSON.stringify(right);

export const OrdersPage: React.FC = () => {
  const [pageData, setPageData] = useState<OrderSummaryPageViewModel | null>(null);
  const [stagePage, setStagePage] = useState<OrderOperationalTimelinePage | null>(null);
  const [stageIndex, setStageIndex] = useState<ReadonlyMap<string, OrderOperationalTimeline>>(new Map());
  const [stageProjectionError, setStageProjectionError] = useState<string | null>(null);
  const [selectedStage, setSelectedStage] = useState<WorkflowStage | '全部'>('全部');
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

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
  const [matchingFormContext, setMatchingFormContext] = useState<FormManagementContext | null>(null);
  const [matchingFormContextError, setMatchingFormContextError] = useState(false);
  const [matchingAvailability, setMatchingAvailability] = useState<MatchingAvailability | null>(null);
  const [multiCaregiverSegmentCount, setMultiCaregiverSegmentCount] = useState<2 | 3 | 4>(2);
  const [selectedCandidateStaffIds, setSelectedCandidateStaffIds] = useState<number[]>([]);
  const [candidateWillingnessDrafts, setCandidateWillingnessDrafts] = useState<Record<number, {
    willingness: 'willing' | 'unwilling';
    reason: string;
  }>>({});
  const [customerDecisionReason, setCustomerDecisionReason] = useState('');
  const [resumeNote, setResumeNote] = useState('');
  const [resumeReceipt, setResumeReceipt] = useState<CustomerProfilesNotificationReceipt | null>(null);
  const [waitingLockPreview, setWaitingLockPreview] = useState<WaitingDepositPreview | null>(null);
  const [waitingLockReceipt, setWaitingLockReceipt] = useState<WaitingDepositReceipt | null>(null);
  const [contractDetail, setContractDetail] = useState<OrderTermsContractDrawerViewModel | null>(null);
  const [contractQueryError, setContractQueryError] = useState<string | null>(null);
  const [contractCorrectionNotice, setContractCorrectionNotice] = useState<string | null>(null);
  type ContractWorkbenchTab = 'contract_terms' | 'calendar' | 'cancellation' | 'reopen';
  const [activeContractTab, setActiveContractTab] = useState<ContractWorkbenchTab>('contract_terms');
  const [contractDocView, setContractDocView] = useState<'contract' | 'spec'>('contract');
  const [contractDocFullscreen, setContractDocFullscreen] = useState(false);
  const [precisionMode, setPrecisionMode] = useState<'週休1日' | '週休2日' | '連續服務'>('週休1日');
  const [precisionCalculating, setPrecisionCalculating] = useState(false);
  const [precisionResult, setPrecisionResult] = useState<SchedulePrecisionResult | null>(null);
  const [precisionError, setPrecisionError] = useState<string | null>(null);
  const [holidayRestDates, setHolidayRestDates] = useState<string[]>([]);
  const [leaveDates, setLeaveDates] = useState<string[]>([]);
  const [customWorkDates, setCustomWorkDates] = useState<string[]>([]);
  const [leaveDateDraft, setLeaveDateDraft] = useState('');
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
  const [cancellationDays, setCancellationDays] = useState<CancellationServiceDayDraft[]>([]);
  const [cancellationPreview, setCancellationPreview] = useState<OrderCancellationPreview | null>(null);
  const [cancellationReceipt, setCancellationReceipt] = useState<OrderCancellationReceipt | null>(null);
  const [cancellationReason, setCancellationReason] = useState('');
  const [cancellationConfirmed, setCancellationConfirmed] = useState(false);
  const [cancellationStatus, setCancellationStatus] = useState<'idle' | 'querying' | 'previewing' | 'applying'>('idle');
  const [cancellationError, setCancellationError] = useState<string | null>(null);
  const [cancellationRetryMode, setCancellationRetryMode] = useState(false);
  const [cardProjection, setCardProjection] = useState<OrdersCardProjectionViewModel | null>(null);
  const [cardProjectionLoading, setCardProjectionLoading] = useState<boolean>(false);
  const [cardProjectionError, setCardProjectionError] = useState<string | null>(null);

  // Generation guard refs to prevent race conditions on fast switching
  const currentSummaryRequestRef = useRef<number>(0);
  const currentDrawerRequestRef = useRef<number>(0);
  const summaryControllerRef = useRef<AbortController | null>(null);
  const drawerControllerRef = useRef<AbortController | null>(null);
  const serviceDatesPreviewControllerRef = useRef<AbortController | null>(null);
  const reopenPreviewControllerRef = useRef<AbortController | null>(null);
  const cardProjectionControllerRef = useRef<AbortController | null>(null);
  const currentCardProjectionRequestRef = useRef<number>(0);
  const precisionRequestRef = useRef<number>(0);
  const cancellationApplyAttemptRef = useRef<CancellationApplyAttempt | null>(null);
  const cancellationApplyInFlightRef = useRef(false);

  useEffect(
    () => orderMutationFlowStore.subscribe(() => setMutationRevision((value) => value + 1)),
    []
  );

  useEffect(() => () => {
    currentSummaryRequestRef.current += 1;
    currentDrawerRequestRef.current += 1;
    summaryControllerRef.current?.abort();
    drawerControllerRef.current?.abort();
    serviceDatesPreviewControllerRef.current?.abort();
    reopenPreviewControllerRef.current?.abort();
    cardProjectionControllerRef.current?.abort();
    precisionRequestRef.current += 1;
  }, []);

  // Load summaries from live API
  const fetchOrderSummaries = useCallback(async () => {
    summaryControllerRef.current?.abort();
    const controller = new AbortController();
    summaryControllerRef.current = controller;
    const requestId = ++currentSummaryRequestRef.current;
    setLoading(true);
    setError(null);
    setStageProjectionError(null);

    try {
      const queryText = searchQuery.trim();
      if (queryText) {
        setSelectedStage('全部');
        setStagePage(null);
        setStageIndex(new Map());
      }
      const [summaryResult, stageResult] = await Promise.allSettled([
        loadAllOrderSummaries(
          ordersQueryClient.getOrderSummaries.bind(ordersQueryClient),
          { page_size: 200, lifecycle_scope: queryText ? 'all' : 'unfinished', ...(queryText ? { query_text: queryText } : {}) },
          { signal: controller.signal },
        ),
        queryText
          ? Promise.resolve(null)
          : loadAllOrderOperationalTimelines(
            orderStageProjectionClient.getOperationalTimelines.bind(orderStageProjectionClient),
            { page_size: 200, lifecycle_scope: 'unfinished' },
            { signal: controller.signal },
          ),
      ]);
      if (summaryResult.status === 'rejected') throw summaryResult.reason;
      if (requestId === currentSummaryRequestRef.current) {
        const rawPage = summaryResult.value;
        const adapted = adaptOrderSummaryPage(rawPage);
        setPageData(adapted);
        if (queryText) {
          // The stage endpoint has no query_text contract. A searched card stays operable,
          // while stage filters remain disabled instead of treating unrelated rows as an error.
          setSelectedStage('全部');
          setStagePage(null);
          setStageIndex(new Map());
        } else if (stageResult.status === 'fulfilled' && stageResult.value !== null) {
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
          const stageReason = stageResult.status === 'rejected' ? stageResult.reason : null;
          setStageProjectionError(stageReason instanceof Error ? stageReason.message : ORDER_STAGE_PROJECTION_UNAVAILABLE);
        }
      }
    } catch (err) {
      if (requestId === currentSummaryRequestRef.current) {
        const message = err instanceof Error ? err.message : '載入訂單列表失敗';
        setError(`訂單清單載入未完成：${message}`);
      }
    } finally {
      if (requestId === currentSummaryRequestRef.current) {
        setLoading(false);
      }
    }
  }, [searchQuery]);

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
    <section
      data-surface-id="orders.card-projection"
      className="orders-card-projection-container"
    >
      <div className="card-projection-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <h3 className="card-projection-title">📋 案件聯絡、條款與指派資料</h3>
          {cardProjection && (
            <span className="card-projection-badge">正式案件資料</span>
          )}
        </div>
        <span className="card-projection-subtitle">
          跨領域核心資料投影（Client 聯絡、Orders 條款、Finance 定金與 Scheduling 指派）
        </span>
      </div>

      {cardProjectionLoading && (
        <div role="status" style={{ padding: '14px 0', color: '#ff7f50', fontWeight: 600, fontSize: '0.9rem' }}>
          ⏳ 正在載入案件資料…
        </div>
      )}

      {cardProjectionError && !cardProjectionLoading && (
        <div
          role="alert"
          style={{
            marginTop: '12px',
            padding: '10px 14px',
            borderRadius: '8px',
            backgroundColor: '#fef2f2',
            border: '1px solid #fecaca',
            color: '#991b1b',
            fontSize: '0.88rem',
            fontWeight: 600,
          }}
        >
          {ORDERS_CARD_PROJECTION_UNAVAILABLE}：{cardProjectionError}
        </div>
      )}

      {cardProjection && (
        <>
          <div className="card-projection-grid">
            {cardProjection.rows.map((item) => (
              <div key={item.key} className="card-projection-item">
                <div className="card-projection-item-header">
                  <strong className="card-projection-item-label">{item.label}</strong>
                  {item.availability !== 'available' && (
                    <span className={`card-projection-item-status ${item.availability}`}>
                      {item.availability === 'blocked' ? '受阻' : '待補正'}
                    </span>
                  )}
                </div>
                <div className="card-projection-item-value">{item.valueText}</div>
              </div>
            ))}
          </div>

          <div className="card-projection-assignments">
            <strong className="card-projection-assignments-title">👩‍🍼 正式指派分段</strong>
            {cardProjection.assignmentSegments.length === 0 ? (
              <p className="card-projection-empty-assignments" style={{ margin: 0 }}>
                {cardProjection.assignmentSegmentsAvailability === 'available'
                  ? '目前尚無正式指派分段。'
                  : cardProjection.assignmentSegmentsMessage}
              </p>
            ) : (
              <div className="card-projection-segments-grid">
                {cardProjection.assignmentSegments.map((segment, sIdx) => (
                  <div key={segment.key} className="card-projection-segment-card">
                    <div className="card-projection-segment-header">
                      <span>正式分段 #{sIdx + 1}</span>
                    </div>
                    <div className="card-projection-segment-fields">
                      <div className="card-projection-segment-row">
                        <span className="card-projection-segment-label">服務人員：</span>
                        <span className="card-projection-segment-val">
                          {segment.rows.find((item) => item.key.endsWith('.staff_name'))?.valueText ?? '尚未登錄（服務人員）'}
                        </span>
                      </div>
                      <div className="card-projection-segment-row">
                        <span className="card-projection-segment-label">正式服務期間：</span>
                        <span className="card-projection-segment-val">
                          {segment.rows.find((item) => item.key.endsWith('.assigned_start_date'))?.valueText ?? '尚未登錄（開始日）'}
                          {' ～ '}
                          {segment.rows.find((item) => item.key.endsWith('.assigned_end_date'))?.valueText ?? '尚未登錄（結束日）'}
                        </span>
                      </div>
                      <div className="card-projection-segment-row">
                        <span className="card-projection-segment-label">指派狀態：</span>
                        <span className="card-projection-segment-val">
                          {segment.rows.find((item) => item.key.endsWith('.status'))?.valueText ?? '尚未登錄（指派狀態）'}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <details className="card-projection-technical-details">
            <summary>技術詳情與資料來源</summary>
            <div className="card-projection-technical-content">
              {cardProjection.rows.map((item) => (
                <div key={`technical.${item.key}`}>
                  <strong>{item.label}</strong>
                  <span>{item.metadataText}</span>
                </div>
              ))}
              {cardProjection.assignmentSegments.map((segment, segmentIndex) => (
                <section key={`technical.${segment.key}`} aria-label={`正式分段 ${segmentIndex + 1} 技術詳情`}>
                  <strong>正式分段 #{segmentIndex + 1}</strong>
                  {segment.rows.map((item) => (
                    <div key={`technical.${item.key}`}>
                      <span>{item.label}：{item.valueText}</span>
                      <span>{item.metadataText}</span>
                    </div>
                  ))}
                </section>
              ))}
            </div>
          </details>
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
  const serviceDatesSelectionReady = precisionResult !== null
    && serviceDatesDraft?.queryView !== null
    && serviceDatesDraft?.queryView !== undefined
    && serviceDatesDraft.selectedDates.length === serviceDatesDraft.queryView.contracted_service_days;
  const reopenLocked =
    reopenDraft?.status === 'apply_pending' ||
    reopenDraft?.status === 'outcome_unknown' ||
    reopenDraft?.status === 'receipt_received' ||
    reopenDraft?.status === 'requery_loading';
  const closeContractDrawer = () => {
    if (cancellationApplyInFlightRef.current) {
      setCancellationError('取消套用仍在進行中，請等待結果確認後再關閉工作台。');
      return;
    }
    if (serviceDatesLocked || reopenLocked) return;
    serviceDatesPreviewControllerRef.current?.abort();
    serviceDatesPreviewControllerRef.current = null;
    reopenPreviewControllerRef.current?.abort();
    reopenPreviewControllerRef.current = null;
    const activeId = (contractOrder || dateConfirmOrder || reopenOrder || cancelOrder)?.id;
    if (activeId) {
      orderMutationFlowStore.closeReopenDialog(activeId);
    }
    precisionRequestRef.current += 1;
    invalidateDrawerRequest();
    setContractOrder(null);
    setDateConfirmOrder(null);
    setReopenOrder(null);
    setCancelOrder(null);
  };
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
      setActualStartError(previewError instanceof Error ? previewError.message : '無法檢查實際開工日影響。');
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
      setActualStartError(applyError instanceof Error ? applyError.message : '無法確認實際開工日。');
    } finally {
      setActualStartStatus('idle');
    }
  };

  // Handle opening Drawer 2: Matching Workbench
  const handleOpenMatchingDrawer = async (
    order: OrderSummaryCardViewModel,
    options?: { preserveCandidateAction?: boolean },
  ) => {
    if (cancellationApplyInFlightRef.current) {
      setCancellationError('取消套用仍在進行中，請等待結果確認後再切換案件。');
      return;
    }
    setContractOrder(null);
    setDateConfirmOrder(null);
    setCancelOrder(null);
    setReopenOrder(null);
    setMatchingOrder(order);
    if (!options?.preserveCandidateAction) {
      setMatchingDetail(null);
    }
    setMatchingDetailError(null);
    setMatchingFormContext(null);
    setMatchingFormContextError(false);
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
      setCustomerDecisionReason('');
      setResumeNote('');
      setResumeReceipt(null);
      setWaitingLockPreview(null);
      setWaitingLockReceipt(null);
    }
    loadCardProjection(order.id);
    setDrawerLoading(true);
    const { controller, requestId } = beginDrawerRequest();

    try {
      const [detailRes, assignmentPlanRes, termsRes, candidatePoolRes, activePlanRes, formContextRes] = await Promise.allSettled([
        ordersQueryClient.getOrderDetail(order.id, { signal: controller.signal }),
        ordersQueryClient.getAssignmentPlan(order.id, { signal: controller.signal }),
        ordersQueryClient.getOrderTerms(order.id, { signal: controller.signal }),
        candidateContactPoolClient.query(order.id, { signal: controller.signal }),
        waitingDepositLockClient.queryPlan(order.id, controller.signal),
        ordersQueryClient.getFormManagementContext(order.id, { signal: controller.signal }),
      ]);

      if (requestId !== currentDrawerRequestRef.current) return;

      const assignmentPlan = assignmentPlanRes.status === 'fulfilled' ? assignmentPlanRes.value : null;
      const terms = termsRes.status === 'fulfilled' ? termsRes.value : null;
      const candidateContactPool = candidatePoolRes.status === 'fulfilled' ? candidatePoolRes.value : null;
      const activePlan = activePlanRes.status === 'fulfilled' ? activePlanRes.value : null;
      const contactStateRes = activePlan === null
        ? null
        : await Promise.allSettled([
          matchingPlanCommunicationClient.queryContactState(order.id, activePlan.planId),
        ]);
      if (requestId !== currentDrawerRequestRef.current) return;
      const contactState = contactStateRes?.[0]?.status === 'fulfilled'
        ? contactStateRes[0].value
        : null;
      const activePlanMissing = activePlanRes.status === 'rejected'
        && activePlanRes.reason instanceof ApiHttpError
        && activePlanRes.reason.status === 404;
      const activePlanFailed = (activePlanRes.status === 'rejected' && !activePlanMissing)
        || (contactStateRes !== null && contactState === null);

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
        const formContextReady = formContextRes.status === 'fulfilled'
          && formContextRes.value.case_no === order.id;
        setMatchingFormContext(formContextReady ? formContextRes.value : null);
        setMatchingFormContextError(!formContextReady);
        setMatchingDetail(matchingQueriesReady ? adaptMatchingWorkbenchDrawer({
          caseNo: order.id,
          assignmentPlan,
          terms,
          candidateContactPool,
          // A failed customer-decision read must not erase the independently
          // authoritative active plan or its waiting-deposit lock.  Keeping it
          // visible prevents a stale UI from offering a second formal plan.
          activePlan: activePlanRes.status === 'fulfilled' ? activePlan : null,
          customerDecision: contactState?.customer_decision,
          customerProfilesStatus: contactState?.customer_profiles_manual_confirmation
            ? 'manually_confirmed'
            : contactState?.customer_profiles_status,
        }) : null);
        setMatchingDetailError(matchingQueriesReady ? null : '正式排班資料載入失敗，請關閉後重試。');
        setMatchingCorrectionNotice((termsHistoricalGap || assignmentHistoricalGap) && matchingQueriesReady
          ? '此歷史案件缺少客戶帳務資料；既有排班指派仍可檢視，料理、服務時段與完整排班保持待補正。'
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
    const blocker = candidatePoolMutationBlocker();
    if (blocker) {
      setCandidateActionError(blocker);
      return;
    }
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
          ? `訂單資訊-${infoType} 已排入發送；尚未代表 LINE 已送達。`
          : `訂單資訊-${infoType} 已由既有發送工作受理。`,
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
        defaultMatchingFilterPolicy,
      );
      setMatchingAvailability(availability);
      setSelectedCandidateStaffIds([]);
      const eligibleCount = availability.candidate_options.filter(
        (candidate) => candidate.segment_index === 0 && candidate.full_case_coverage
          && ['region', 'cooking', 'preferred_service_days', 'daily_service_hours']
            .every((key) => candidate.filter_results[key] === true),
      ).length;
      setCandidateActionNotice(
        eligibleCount > 0
          ? `已依最新檔期查得 ${eligibleCount} 位可完整承接候選月嫂。`
          : '目前沒有月嫂能完整承接本案服務日期。',
      );
    } catch (caught) {
      setMatchingAvailability(null);
      setCandidateActionError(matchingAvailabilityErrorMessage(caught, '候選月嫂查詢失敗。'));
    } finally {
      setCandidateActionKey(null);
    }
  };

  const searchMultiCaregiverFallback = async () => {
    if (!matchingOrder) return;
    setCandidateActionError(null);
    setCandidateActionNotice(null);
    setCandidateActionKey('multi-availability-search');
    try {
      const availability = await matchingCandidateWorkflowClient.searchSegmentedCaregivers(
        matchingOrder.id,
        multiCaregiverSegmentCount,
        [],
        defaultMatchingFilterPolicy,
      );
      setMatchingAvailability(availability);
      setSelectedCandidateStaffIds([]);
      const combinationCount = availability.complete_combinations.filter(
        (combination) => combination.length === multiCaregiverSegmentCount,
      ).length;
      setCandidateActionNotice(
        combinationCount > 0
          ? `伺服器已找出 ${combinationCount} 組 ${multiCaregiverSegmentCount} 段連續承接備案。`
          : `目前沒有可完整承接的 ${multiCaregiverSegmentCount} 段備案；請依衝突與可用檔期調整。`,
      );
    } catch (caught) {
      setMatchingAvailability(null);
      setCandidateActionError(matchingAvailabilityErrorMessage(caught, '多月嫂備案查詢失敗。'));
    } finally {
      setCandidateActionKey(null);
    }
  };

  const addSelectedMatchingCandidates = async () => {
    if (!matchingOrder || !matchingAvailability) return;
    const blocker = candidatePoolMutationBlocker();
    if (blocker) {
      setCandidateActionError(blocker);
      return;
    }
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
    const blocker = candidatePoolMutationBlocker();
    if (blocker) {
      setCandidateActionError(blocker);
      return;
    }
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
    const formalPlanBlocker = formalPlanCreationBlocker();
    if (formalPlanBlocker) {
      setCandidateActionError(formalPlanBlocker);
      return;
    }
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
      setCandidateActionNotice('正式單月嫂方案已建立並完成回讀。');
    } catch (caught) {
      setCandidateActionError(caught instanceof Error ? caught.message : '建立正式單月嫂方案失敗。');
    } finally {
      setCandidateActionKey(null);
    }
  };

  const createFormalMultiCaregiverPlan = async (combination: MatchingAvailability['complete_combinations'][number]) => {
    if (!matchingOrder) return;
    const formalPlanBlocker = formalPlanCreationBlocker();
    if (formalPlanBlocker) {
      setCandidateActionError(formalPlanBlocker);
      return;
    }
    if (combination.length < 2 || combination.length > 4) {
      setCandidateActionError('正式多月嫂方案必須由伺服器回傳的 2 至 4 段完整組合建立。');
      return;
    }
    setCandidateActionKey('multi-formal-plan');
    setCandidateActionError(null);
    setCandidateActionNotice(null);
    try {
      const plan = await matchingCandidateWorkflowClient.createMatchingPlan(
        matchingOrder.id,
        combination.map((segment) => ({
          staff_id: segment.staff_id,
          start_date: segment.start_date,
          end_date: segment.end_date,
        })),
      );
      const observed = await waitingDepositLockClient.queryPlan(matchingOrder.id);
      if (observed.planId !== plan.plan_id) {
        throw new Error('正式多月嫂方案建立後 active plan 回讀不一致，請重新查詢。');
      }
      await handleOpenMatchingDrawer(matchingOrder, { preserveCandidateAction: true });
      setCandidateActionNotice(`正式 ${plan.segments.length} 段多月嫂方案已建立並完成回讀。`);
    } catch (caught) {
      setCandidateActionError(caught instanceof Error ? caught.message : '建立正式多月嫂方案失敗。');
    } finally {
      setCandidateActionKey(null);
    }
  };

  const formalPlanCreationBlocker = (): string | null => {
    if (!matchingOrder || !matchingDetail) return '媒合資料尚未載入，無法建立正式方案。';
    if (matchingDetail.waitingLockAcquired) return '目前方案已取得等待訂金鎖，不能重新建立媒合方案。';
    if (matchingDetail.status === '已接受') return '目前方案已由客戶接受，不能重新建立媒合方案。';
    if (matchingOrder.orderStatus !== '洽談中') {
      return `目前訂單狀態為「${matchingOrder.orderStatus}」，僅洽談中案件可建立正式媒合方案。`;
    }
    return null;
  };

  const candidatePoolMutationBlocker = (): string | null => {
    if (!matchingOrder || !matchingDetail) return '媒合資料尚未載入，候選聯繫紀錄暫時不可修改。';
    if (matchingDetail.waitingLockAcquired) {
      return '目前方案已取得等待訂金鎖；候選聯繫紀錄已鎖定，請依定金與簽約流程繼續。';
    }
    if (matchingDetail.status === '已接受') {
      return '客戶已接受正式媒合方案；候選聯繫紀錄改為唯讀，請依定金與簽約流程繼續。';
    }
    if (matchingOrder.orderStatus !== '洽談中') {
      return `目前訂單狀態為「${matchingOrder.orderStatus}」；候選聯繫紀錄已改為唯讀。`;
    }
    return null;
  };

  const sendCustomerProfiles = async () => {
    if (!matchingOrder) return;
    setCandidateActionKey('customer-profiles');
    setCandidateActionError(null);
    setCandidateActionNotice(null);
    setResumeReceipt(null);
    try {
      const activePlan = await waitingDepositLockClient.queryPlan(matchingOrder.id);
      const contactState = await matchingPlanCommunicationClient.queryContactState(matchingOrder.id, activePlan.planId);
      if (
        contactState.plan.status !== 'proposed'
        || contactState.customer_decision !== 'pending'
        || contactState.plan.communication_version !== activePlan.communicationVersion
      ) {
        throw new Error('目前方案不是可寄送履歷的提案，請重新載入。');
      }
      if (!contactState.all_willing) {
        throw new Error('正式方案尚缺月嫂意願確認，不能寄送履歷給客戶。');
      }
      if (contactState.customer_profiles_status !== null) {
        throw new Error('客戶履歷已建立可靠發送任務，請等待或補登客戶決策。');
      }
      const receipt = await matchingPlanCommunicationClient.sendCustomerProfiles(
        matchingOrder.id,
        activePlan.planId,
        contactState.plan.communication_version,
        resumeNote,
      );
      const observed = await matchingPlanCommunicationClient.queryContactState(matchingOrder.id, activePlan.planId);
      if (observed.customer_profiles_status === null) {
        throw new Error('履歷發送任務回讀未出現在正式方案聯繫狀態。');
      }
      await handleOpenMatchingDrawer(matchingOrder, { preserveCandidateAction: true });
      setResumeReceipt(receipt);
      setCandidateActionNotice('客戶履歷已排入發送；尚未代表 LINE 已送達，請等待客戶確認。');
    } catch (caught) {
      setCandidateActionError(
        caught instanceof ApiHttpError && caught.status === 409
          ? '無法建立履歷可靠發送任務；請先確認客戶 LINE 綁定與月嫂目前檔期，或改用下方人工確認補登，系統不會偽造 LINE 發送。'
          : caught instanceof Error ? caught.message : '寄送月嫂履歷給客戶失敗。',
      );
    } finally {
      setCandidateActionKey(null);
    }
  };

  const recordMatchingCustomerAcceptance = async () => {
    if (!matchingOrder) return;
    setCandidateActionKey('customer-decision');
    setCandidateActionError(null);
    setCandidateActionNotice(null);
    try {
      const activePlan = await waitingDepositLockClient.queryPlan(matchingOrder.id);
      const contactState = await matchingPlanCommunicationClient.queryContactState(matchingOrder.id, activePlan.planId);
      if (
        contactState.plan.status !== 'proposed'
        || contactState.customer_decision !== 'pending'
        || contactState.plan.communication_version !== activePlan.communicationVersion
      ) {
        throw new Error('目前方案不是可補登客戶決策的提案，請重新載入。');
      }
      if (!contactState.all_willing) {
        throw new Error('正式方案尚缺月嫂意願確認；請先補登正式方案月嫂願意承接。');
      }
      await matchingPlanCommunicationClient.recordCustomerDecision(
        matchingOrder.id,
        activePlan.planId,
        contactState.plan.communication_version,
        'accepted',
        customerDecisionReason,
      );
      const observed = await matchingPlanCommunicationClient.queryContactState(matchingOrder.id, activePlan.planId);
      if (observed.plan.id !== activePlan.planId || observed.customer_decision !== 'accepted') {
        throw new Error('客戶決策回讀未取得已接受方案，請重新載入。');
      }
      await handleOpenMatchingDrawer(matchingOrder, { preserveCandidateAction: true });
      setCandidateActionNotice('客戶接受正式媒合方案的紀錄已完成回讀。');
    } catch (caught) {
      setCandidateActionError(caught instanceof Error ? caught.message : '補登客戶配對決策失敗。');
    } finally {
      setCandidateActionKey(null);
    }
  };

  const recordFormalPlanWillingness = async () => {
    if (!matchingOrder) return;
    setCandidateActionKey('formal-plan-willingness');
    setCandidateActionError(null);
    setCandidateActionNotice(null);
    try {
      const activePlan = await waitingDepositLockClient.queryPlan(matchingOrder.id);
      const contactState = await matchingPlanCommunicationClient.queryContactState(matchingOrder.id, activePlan.planId);
      const pendingSegment = contactState.segments.find((segment) => segment.willingness === 'pending');
      if (activePlan.status !== 'proposed' || !pendingSegment) {
        throw new Error('目前沒有可補登願意承接的正式方案月嫂區段。');
      }
      await matchingPlanCommunicationClient.recordFormalPlanWillingness(
        matchingOrder.id,
        activePlan.planId,
        pendingSegment.segment_id,
        contactState.plan.communication_version,
        customerDecisionReason,
      );
      const observed = await matchingPlanCommunicationClient.queryContactState(matchingOrder.id, activePlan.planId);
      if (!observed.all_willing) throw new Error('月嫂意願回讀未完成，請重新載入。');
      await handleOpenMatchingDrawer(matchingOrder, { preserveCandidateAction: true });
      setCandidateActionNotice('已回讀確認正式方案月嫂願意承接。');
    } catch (caught) {
      setCandidateActionError(caught instanceof Error ? caught.message : '補登正式方案月嫂意願失敗。');
    } finally {
      setCandidateActionKey(null);
    }
  };

  const previewWaitingDepositLock = async () => {
    if (!matchingOrder) return;
    setCandidateActionKey('waiting-lock-preview');
    setCandidateActionError(null);
    setCandidateActionNotice(null);
    setWaitingLockPreview(null);
    setWaitingLockReceipt(null);
    try {
      const activePlan = await waitingDepositLockClient.queryPlan(matchingOrder.id);
      const contactState = await matchingPlanCommunicationClient.queryContactState(matchingOrder.id, activePlan.planId);
      if (contactState.customer_decision !== 'accepted' || activePlan.activeLockId !== null) {
        throw new Error('僅已接受且尚未鎖定的正式方案可建立等待訂金鎖。');
      }
      const preview = await waitingDepositLockClient.preview(matchingOrder.id, activePlan.planId);
      setWaitingLockPreview(preview);
      setCandidateActionNotice(preview.apply_allowed
        ? `等待訂金鎖影響檢查已完成：${preview.service_day_count} 個服務日、${preview.buffer_day_count} 個防撞期日。`
        : '等待訂金鎖影響檢查未通過，請先處理衝突。');
    } catch (caught) {
      setCandidateActionError(caught instanceof Error ? caught.message : '無法檢查等待訂金鎖影響。');
    } finally {
      setCandidateActionKey(null);
    }
  };

  const applyWaitingDepositLock = async () => {
    if (!matchingOrder || !waitingLockPreview || !waitingLockPreview.apply_allowed) return;
    setCandidateActionKey('waiting-lock-apply');
    setCandidateActionError(null);
    setCandidateActionNotice(null);
    try {
      const receipt = await waitingDepositLockClient.apply(
        matchingOrder.id,
        waitingLockPreview.plan_id,
        waitingLockPreview.preview_fingerprint,
      );
      const observed = await waitingDepositLockClient.queryPlan(matchingOrder.id);
      if (observed.planId !== receipt.plan_id || observed.activeLockId !== receipt.lock_id) {
        throw new Error('等待訂金鎖套用後回讀不一致，請重新載入。');
      }
      setWaitingLockReceipt(receipt);
      await handleOpenMatchingDrawer(matchingOrder, { preserveCandidateAction: true });
      setCandidateActionNotice('等待訂金檔期鎖已套用並完成回讀。');
    } catch (caught) {
      setCandidateActionError(caught instanceof Error ? caught.message : '等待訂金鎖套用失敗。');
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
          '此案件缺少客戶帳務的契約與定金資料，已隔離為歷史資料待補正；目前可檢視已有資料，但不可預覽或套用條款。'
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

  async function calculateAndSelectServiceDates(input: {
    caseNo: string;
    startDate: string;
    targetDays: number;
    serviceMode: '週休1日' | '週休2日' | '連續服務';
    selectableDates: string[];
    holidayRestDates?: string[];
    leaveDates: string[];
    customWorkDates: string[];
  }) {
    const requestId = ++precisionRequestRef.current;
    setPrecisionCalculating(true);
    setPrecisionError(null);
    try {
      const result = await schedulePrecisionClient.calculate({
        actual_start_date: input.startDate,
        target_service_days: input.targetDays,
        service_mode: input.serviceMode,
        ...(input.holidayRestDates === undefined
          ? {}
          : { custom_holiday_rest_dates: input.holidayRestDates }),
        custom_leave_dates: input.leaveDates,
        ...(input.customWorkDates.length === 0
          ? {}
          : { custom_work_dates: input.customWorkDates }),
      });
      if (requestId !== precisionRequestRef.current) return;
      const workDates = result.day_by_day
        .filter((day) => day.is_work_day)
        .map((day) => day.date);
      const selectableDates = new Set(input.selectableDates);
      const preservesContractedDays = result.target_service_days === input.targetDays
        && result.actual_work_days_count === input.targetDays
        && workDates.length === input.targetDays
        && new Set(workDates).size === input.targetDays;
      if (!preservesContractedDays || workDates.some((date) => !selectableDates.has(date))) {
        setPrecisionResult(null);
        changeServiceDateSelection(input.caseNo, []);
        setPrecisionError('伺服器精算結果未維持合約服務天數，或日期超出正式可選範圍，已停止帶入。');
        return;
      }
      setPrecisionResult(result);
      setHolidayRestDates(
        result.national_holidays_found
          .filter((holiday) => !holiday.is_worked)
          .map((holiday) => holiday.date),
      );
      changeServiceDateSelection(input.caseNo, workDates);
    } catch (err) {
      if (requestId !== precisionRequestRef.current) return;
      setPrecisionResult(null);
      changeServiceDateSelection(input.caseNo, []);
      setPrecisionError(err instanceof Error ? err.message : '出勤天數精算失敗');
    } finally {
      if (requestId === precisionRequestRef.current) setPrecisionCalculating(false);
    }
  }

  const runSchedulePrecision = (
    nextHolidayRestDates = holidayRestDates,
    nextLeaveDates = leaveDates,
    caseNo = (contractOrder || dateConfirmOrder)?.id,
    nextCustomWorkDates = customWorkDates,
  ) => {
    if (!caseNo) return;
    const serviceDateQuery = orderMutationFlowStore.getServiceDatesDraft(caseNo)?.queryView;
    const startDate = actualStartQuery?.case_no === caseNo
      ? actualStartQuery.current_actual_start_date ?? actualStartQuery.planned_start_date
      : null;
    if (!serviceDateQuery || serviceDateQuery.case_no !== caseNo || startDate === null) {
      setPrecisionResult(null);
      setPrecisionError('正式服務日精算所需的開始日、合約天數或排休類型尚未載入，請關閉後重試。');
      return;
    }
    void calculateAndSelectServiceDates({
      caseNo,
      startDate,
      targetDays: serviceDateQuery.contracted_service_days,
      serviceMode: precisionMode,
      selectableDates: serviceDateQuery.selectable_dates,
      holidayRestDates: nextHolidayRestDates,
      leaveDates: nextLeaveDates,
      customWorkDates: nextCustomWorkDates,
    });
  };

  const rerunSchedulePrecision = runSchedulePrecision;

  // Lazy loader for Service Dates & Actual Start queries
  const loadCalendarTabQueries = async (order: OrderSummaryCardViewModel) => {
    const { controller, requestId } = beginDrawerRequest();
    setDrawerLoading(true);
    setPrecisionResult(null);
    setPrecisionError(null);
    setHolidayRestDates([]);
    setLeaveDates([]);
    setCustomWorkDates([]);
    setLeaveDateDraft('');
    try {
      const [actualStartRes, serviceDatesRes, calendarDetailRes] = await Promise.allSettled([
        ordersQueryClient.getActualStart(order.id, { signal: controller.signal }),
        fetchServiceDatesQuery(order.id, { signal: controller.signal }),
        ordersQueryClient.getOrderCalendarDetail(order.id, { signal: controller.signal }),
      ]);
      if (requestId !== currentDrawerRequestRef.current) return;
      const actualStart = actualStartRes.status === 'fulfilled' ? actualStartRes.value : null;
      setActualStartQuery(actualStart);
      setActualStartDraft(actualStart?.current_actual_start_date ?? actualStart?.planned_start_date ?? '');
      if (actualStartRes.status === 'rejected') {
        setActualStartError('實際開工日查詢失敗，請關閉後重試。');
      }
      const serviceDates = serviceDatesRes.status === 'fulfilled' ? serviceDatesRes.value : null;
      const calendarDetail = calendarDetailRes.status === 'fulfilled' ? calendarDetailRes.value : null;
      const startDate = actualStart?.current_actual_start_date ?? actualStart?.planned_start_date ?? null;
      const inputsReady = actualStart?.case_no === order.id
        && serviceDates?.case_no === order.id
        && calendarDetail?.case_no === order.id
        && startDate !== null;
      if (!inputsReady) {
        selectServiceDates(order.id, []);
        setPrecisionError('正式服務日精算所需的開始日、合約天數或排休類型尚未載入，請關閉後重試。');
        return;
      }
      setPrecisionMode(calendarDetail.service_mode);
      await calculateAndSelectServiceDates({
        caseNo: order.id,
        startDate,
        targetDays: serviceDates.contracted_service_days,
        serviceMode: calendarDetail.service_mode,
        selectableDates: serviceDates.selectable_dates,
        leaveDates: [],
        customWorkDates: [],
      });
    } finally {
      if (requestId === currentDrawerRequestRef.current) {
        setDrawerLoading(false);
      }
    }
  };

  // Lazy loader for Cancellation queries
  const loadCancellationTabQueries = async (order: OrderSummaryCardViewModel) => {
    const { controller, requestId } = beginDrawerRequest();
    setDrawerLoading(true);
    setCancellationQuery(null);
    setCancellationDays([]);
    setCancellationPreview(null);
    setCancellationReceipt(null);
    setCancellationReason('');
    setCancellationConfirmed(false);
    setCancellationError(null);
    setCancellationStatus('querying');
    setCancellationRetryMode(cancellationApplyAttemptRef.current?.caseNo === order.id);
    try {
      const query = await orderCancellationClient.query(order.id, controller.signal);
      if (requestId !== currentDrawerRequestRef.current) return;
      setCancellationQuery(query);
      setCancellationDays(cancellationDayDrafts(query.service_started ? query.confirmed_service_days : []));
      setCancellationStatus('idle');
    } catch {
      if (requestId !== currentDrawerRequestRef.current) return;
      setCancellationError('取消資料暫時無法取得，請關閉後重試。');
      setCancellationStatus('idle');
    } finally {
      if (requestId === currentDrawerRequestRef.current) {
        setDrawerLoading(false);
      }
    }
  };

  // Lazy loader for Reopen preview queries
  const loadReopenTabQueries = async (order: OrderSummaryCardViewModel) => {
    reopenPreviewControllerRef.current?.abort();
    const controller = new AbortController();
    reopenPreviewControllerRef.current = controller;
    setReopenOrder(order);
    void previewReopenFlow(order.id, { signal: controller.signal }).catch(() => undefined);
  };

  // Handle opening Unified Drawer: Terms, Service Dates, Contract Progress, Cancellation & Reopen
  const handleOpenContractDrawer = async (
    order: OrderSummaryCardViewModel,
    initialTab: ContractWorkbenchTab = 'contract_terms',
  ) => {
    if (cancellationApplyInFlightRef.current) {
      setCancellationError('取消套用仍在進行中，請等待結果確認後再關閉或切換案件。');
      return;
    }
    serviceDatesPreviewControllerRef.current?.abort();
    reopenPreviewControllerRef.current?.abort();
    setContractOrder(order);
    setDateConfirmOrder(order);
    setCancelOrder(order);
    setReopenOrder(order);
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
    setCancellationDays([]);
    setCancellationPreview(null);
    setCancellationReceipt(null);
    setCancellationReason('');
    setCancellationConfirmed(false);
    setCancellationError(null);
    setCancellationStatus('idle');
    setCancellationRetryMode(cancellationApplyAttemptRef.current?.caseNo === order.id);
    precisionRequestRef.current += 1;
    setPrecisionResult(null);
    setPrecisionError(null);
    setHolidayRestDates([]);
    setLeaveDates([]);
    setCustomWorkDates([]);
    setLeaveDateDraft('');
    loadCardProjection(order.id);

    if (initialTab === 'calendar') {
      await loadCalendarTabQueries(order);
    } else if (initialTab === 'cancellation') {
      await loadCancellationTabQueries(order);
    } else if (initialTab === 'reopen') {
      await loadReopenTabQueries(order);
    } else {
      await loadContractTabQueries(order);
    }
  };

  const switchContractTab = (tab: ContractWorkbenchTab) => {
    if (cancellationApplyInFlightRef.current) {
      setCancellationError('取消套用仍在進行中，請等待結果確認後再切換工作台。');
      return;
    }
    setActiveContractTab(tab);
    const activeOrder = contractOrder || dateConfirmOrder || reopenOrder || cancelOrder;
    if (!activeOrder) return;
    if (tab === 'contract_terms' && contractDetail === null && !contractQueryError) {
      void loadContractTabQueries(activeOrder);
    } else if (tab === 'calendar' && actualStartQuery === null) {
      void loadCalendarTabQueries(activeOrder);
    } else if (tab === 'cancellation') {
      if (cancellationQuery === null) {
        void loadCancellationTabQueries(activeOrder);
      }
    } else if (tab === 'reopen') {
      if (!reopenDraft?.previewView) {
        void loadReopenTabQueries(activeOrder);
      }
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
      setTermsMutationError(caught instanceof Error ? caught.message : '無法檢查訂單條款變更影響。');
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
      setTermsMutationError(caught instanceof Error ? caught.message : '無法確認套用訂單條款。');
    } finally {
      setTermsMutationStatus('idle');
    }
  };

  const previewCancellation = async () => {
    if (!cancelOrder || !cancellationQuery) return;
    const typedDays = validCancellationDays(cancellationDays);
    if (typedDays === null) {
      setCancellationError('請輸入有效且不重複的實際服務日期、月嫂。');
      return;
    }
    if (!cancellationQuery.service_started && typedDays.length > 0) {
      setCancellationError('服務尚未開始，實際服務日必須維持為 0 天。');
      return;
    }
    if (cancellationQuery.service_started && typedDays.length === 0) {
      setCancellationError('服務已開始時，至少要保留一日實際服務事實。');
      return;
    }
    const baseline = new Set(cancellationQuery.confirmed_service_days.map((day) => `${day.service_date}:${day.staff_id}`));
    if (typedDays.some((day) => !baseline.has(`${day.service_date}:${day.staff_id}`) && day.reason === null)) {
      setCancellationError('新增或變更實際服務日／月嫂時，必須填寫該日的人工原因。');
      return;
    }
    const orderedDays = [...typedDays].sort((left, right) => left.service_date.localeCompare(right.service_date));
    setCancellationDays(cancellationDayDrafts(orderedDays));
    const { controller, requestId } = beginDrawerRequest();
    setCancellationStatus('previewing');
    setCancellationError(null);
    try {
      const preview = await orderCancellationClient.preview(cancelOrder.id, orderedDays, controller.signal);
      if (controller.signal.aborted || requestId !== currentDrawerRequestRef.current) return;
      setCancellationPreview(preview);
      setCancellationReceipt(null);
      setCancellationConfirmed(false);
      setCancellationStatus('idle');
    } catch (caught) {
      if (controller.signal.aborted || requestId !== currentDrawerRequestRef.current) return;
      setCancellationError(cancellationPreviewErrorMessage(caught));
      setCancellationStatus('idle');
    }
  };

  const applyCancellation = async () => {
    if (!cancelOrder || !cancellationPreview || !cancellationReason.trim() || !cancellationConfirmed) return;
    const caseNo = cancelOrder.id;
    const payload: OrderCancellationApplyPayload = {
      confirmed_service_days: cancellationPreview.confirmed_service_days,
      expected_order_version: cancellationPreview.order_version,
      expected_scheduling_version: cancellationPreview.scheduling_version,
      expected_client_finance_version: cancellationPreview.client_finance_version,
      expected_payroll_version: cancellationPreview.payroll_version,
      preview_fingerprint: cancellationPreview.preview_fingerprint,
      reason: cancellationReason.trim(),
    };
    const existingAttempt = cancellationApplyAttemptRef.current;
    if (existingAttempt && (
      existingAttempt.caseNo !== caseNo
      || !sameCancellationApplyPayload(existingAttempt.payload, payload)
    )) {
      setCancellationRetryMode(true);
      setCancellationError('上一次取消結果尚未確認，且目前內容已不同；請先使用原內容重新確認，系統不會送出新的取消操作。');
      return;
    }
    const attempt = existingAttempt ?? {
      caseNo,
      payload,
      idempotencyKey: `orders-cancellation-ui-${caseNo}-${crypto.randomUUID()}`,
    };
    cancellationApplyAttemptRef.current = attempt;
    cancellationApplyInFlightRef.current = true;
    const drawerRequestId = currentDrawerRequestRef.current;
    const isCurrentDrawer = () => (
      drawerRequestId === currentDrawerRequestRef.current
      && cancelOrder?.id === caseNo
    );
    setCancellationStatus('applying');
    setCancellationError(null);
    setCancellationRetryMode(false);
    try {
      let receipt: OrderCancellationReceipt;
      if (existingAttempt) {
        try {
          receipt = await orderCancellationClient.receipt(
            caseNo,
            attempt.idempotencyKey,
            drawerControllerRef.current?.signal,
          );
        } catch (caught) {
          if (!(caught instanceof ApiHttpError) || caught.status !== 404) {
            if (!isCurrentDrawer()) return;
            setCancellationRetryMode(true);
            setCancellationError('取消結果未明；尚無法確認原操作結果，系統不會重送取消。');
            return;
          }
          receipt = await orderCancellationClient.apply(
            caseNo,
            payload,
            { idempotencyKey: attempt.idempotencyKey },
          );
        }
      } else {
        receipt = await orderCancellationClient.apply(
          caseNo,
          payload,
          { idempotencyKey: attempt.idempotencyKey },
        );
      }
      if (!isCurrentDrawer()) return;
      setCancellationReceipt(receipt);
      setCancellationPreview(null);
      setCancellationConfirmed(false);
      cancellationApplyAttemptRef.current = null;
      setCancellationRetryMode(false);
      try {
        const readback = await orderCancellationClient.query(caseNo);
        if (!isCurrentDrawer()) return;
        setCancellationQuery(readback);
        setCancellationDays(cancellationDayDrafts(readback.service_started ? readback.confirmed_service_days : []));
        await fetchOrderSummaries();
        if (isCurrentDrawer()) loadCardProjection(caseNo);
      } catch {
        if (!isCurrentDrawer()) return;
        setCancellationError('取消已套用，但最新案件狀態讀取失敗；請重新整理後確認。');
      }
    } catch (caught) {
      if (!isCurrentDrawer()) return;
      const isKnownRejection = caught instanceof ApiHttpError && caught.status >= 400 && caught.status < 500;
      if (isKnownRejection) {
        cancellationApplyAttemptRef.current = null;
        setCancellationRetryMode(false);
        setCancellationPreview(null);
        setCancellationConfirmed(false);
        setCancellationError(caught.status === 409
          ? '訂單或後續資料已變更，請重新查詢後再檢查取消影響。'
          : '這筆取消未通過檢查，請重新查詢案件狀態。');
      } else {
        setCancellationRetryMode(true);
        setCancellationError('取消結果未明；系統保留原操作，只能用相同內容重新確認，結果確認前不視為成功。');
      }
    } finally {
      cancellationApplyInFlightRef.current = false;
      if (isCurrentDrawer()) setCancellationStatus('idle');
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
  const passesDefaultMatchingSafetyGate = (candidate: MatchingAvailability['candidate_options'][number]) => (
    ['region', 'cooking', 'preferred_service_days', 'daily_service_hours']
      .every((key) => candidate.filter_results[key] === true)
  );
  const eligibleMatchingCandidates = matchingAvailability?.candidate_options.filter(
    (candidate) => candidate.segment_index === 0 && candidate.full_case_coverage
      && passesDefaultMatchingSafetyGate(candidate),
  ) ?? [];
  const diagnosticMatchingCandidates = matchingAvailability?.candidate_options.filter(
    (candidate) => candidate.segment_index === 0 && candidate.full_case_coverage
      && !passesDefaultMatchingSafetyGate(candidate),
  ) ?? [];
  const completeMultiCaregiverCombinations = matchingAvailability?.complete_combinations.filter(
    (combination) => combination.length >= 2 && combination.length <= 4,
  ) ?? [];

  return (
    <div>
      <div className="page-header-banner orders-page-header">
        <div>
          <h1 className="page-title">📦 訂單與客戶管理</h1>
          <p className="page-subtitle">查詢訂單階段、契約簽署、媒合進度與正式排班。</p>
        </div>
        <div className="orders-search-wrapper">
          <label className="orders-search-input-box" htmlFor="orders-query-search-input">
            <span className="orders-search-icon" aria-hidden="true">🔍</span>
            <input
              id="orders-query-search-input"
              aria-label="搜尋案件"
              data-control-id="orders.query.search"
              value={searchQuery}
              maxLength={100}
              placeholder="案件編號或客戶名稱"
              onChange={(event) => setSearchQuery(event.target.value)}
            />
            {searchQuery && (
              <button
                type="button"
                className="orders-search-clear-btn"
                onClick={() => setSearchQuery('')}
                aria-label="清除搜尋"
                title="清除搜尋"
              >
                ✕
              </button>
            )}
          </label>
        </div>
      </div>

      {/* Status Filter Chips */}
      <div className="orders-filter-bar">
        {ORDER_FILTER_OPTIONS.map((filter) => {
          const projectionReady = stagePage !== null;
          const count = filter.stage === '全部'
            ? pageData?.loadedCount
            : stagePage
              ? [...stageIndex.values()].filter((timeline) => timeline.current_stage_code === filter.stage).length
              : null;
          return (
            <button
              key={filter.stage}
              type="button"
              data-control-id={`orders.filter.${filter.stage}`}
              className={`filter-chip ${selectedStage === filter.stage ? 'active' : ''}`}
              disabled={filter.stage !== '全部' && !projectionReady}
              aria-disabled={filter.stage !== '全部' && !projectionReady}
              title={filter.stage === '全部' ? '目前已載入的訂單摘要' : '依案件進度階段篩選'}
              onClick={() => setSelectedStage(filter.stage)}
            >
              {filter.label} {pageData ? `(${count ?? '—'})` : ''}
            </button>
          );
        })}
      </div>
      {stageProjectionError && !loading && (
        <div role="alert" data-surface-id="orders.stage-projection-error" style={{ padding: '12px 14px', marginBottom: '16px', borderRadius: '10px', backgroundColor: '#fff7ed', border: '1px solid #fdba74', color: '#9a3412' }}>
          <span>{ORDER_STAGE_PROJECTION_UNAVAILABLE}：{stageProjectionError}</span>
          <button
            type="button"
            style={{ marginLeft: '12px', padding: '6px 14px', backgroundColor: '#c2410c', color: '#fff', border: 'none', borderRadius: '6px', fontWeight: 700, cursor: 'pointer' }}
            onClick={fetchOrderSummaries}
          >
            重試
          </button>
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
                <div>🪪 身分資格：{order.identityStatus}</div>
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
                  data-control-id="orders.card.contract-workbench"
                  onClick={() => handleOpenContractDrawer(order, 'contract_terms')}
                >
                  📑 條款與契約
                </button>

                <button
                  className="btn-primary-action"
                  data-control-id="orders.card.matching-workbench"
                  onClick={() => handleOpenMatchingDrawer(order)}
                >
                  👩‍🍼 媒合與正式排班
                </button>
              </div>
              )}
            </div>
          ))}
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

            <section className="matching-step-card" data-surface-id="orders.matching.client-context" aria-label="客戶服務資料">
              <div className="matching-step-header">
                <div>
                  <h3 className="matching-step-title">📋 客戶服務資料</h3>
                  <div className="matching-step-subtext">僅顯示目前已確認的案件資料；尚未匯入或配對的欄位會標示尚未登錄。</div>
                </div>
              </div>
              <div className="matching-criteria-grid" role="list" aria-label="客戶服務資料欄位">
                {([
                  ['身分資格', matchingOrder.identityStatus],
                  ['服務縣市', matchingFormContext?.city],
                  ['服務類型', matchingFormContext?.service_type],
                  ['每日服務時段', matchingFormContext?.service_time],
                  ['生產方式', matchingFormContext?.delivery_type],
                  ['住宅類型', matchingFormContext?.residence_type],
                ] as const).map(([label, value]) => (
                  <div className="matching-criteria-item" role="listitem" key={label}>
                    {label}：{matchingFormContextError ? '資料載入失敗' : value?.trim() || (matchingFormContext ? '尚未登錄' : '載入中…')}
                  </div>
                ))}
              </div>
            </section>

            {/* 👥 步驟一：以既定規則查詢候選月嫂 */}
            <div className="matching-step-card">
              <div className="matching-step-header">
                <div>
                  <h3 className="matching-step-title">
                    <span className="matching-step-badge">1</span>
                    👥 查詢符合條件的月嫂
                  </h3>
                  <div className="matching-step-subtext">
                    系統依本案已確認的服務日與工會媒合規則，直接取得可完整承接的月嫂名單。
                  </div>
                </div>
                <button
                  type="button"
                  className="orders-load-more-btn"
                  style={{ padding: '6px 20px', fontSize: '0.82rem' }}
                  disabled={drawerLoading || candidateActionKey !== null || matchingOrderFacts === null || candidatePoolMutationBlocker() !== null}
                  title={candidatePoolMutationBlocker() ?? '依案件既定規則與最新檔期查詢可完整承接的月嫂'}
                  onClick={() => void searchMatchingCandidates()}
                >
                  {candidateActionKey === 'availability-search' ? '正在查詢最新檔期…' : '🔍 重新查詢符合條件月嫂'}
                </button>
              </div>

              <div className="matching-criteria-grid" role="list" aria-label="目前媒合查詢條件">
                <div className="matching-criteria-item" role="listitem">📍 服務地點：{cardProjection?.rows.find((row) => row.key === 'contact_address')?.valueText ?? '正在確認…'}</div>
                <div className="matching-criteria-item" role="listitem">⏰ 每日時段：{matchingDetail?.serviceTimeText ?? '正在確認…'}</div>
                <div className="matching-criteria-item" role="listitem">📅 承接天數：{matchingOrder.serviceDaysLabel}</div>
                <div className="matching-criteria-item" role="listitem">🍳 料理需求：以上方正式案件條件為準</div>
              </div>
              <div role="note" style={{ border: '1px solid #ead8d1', borderRadius: '10px', marginTop: '12px', padding: '10px 12px', color: '#57423b', fontSize: '0.82rem' }}>
                固定套用：服務區域、下廚需求、完整服務日、每日工時與目前檔期。若案件條款或服務日不正確，請回「條款與契約」修正，再重新查詢。
              </div>
            </div>

            {/* 👥 步驟二：選擇合格月嫂並加入候選池 */}
            <div className="matching-step-card">
              <div className="matching-step-header">
                <div>
                  <h3 className="matching-step-title">
                    <span className="matching-step-badge">2</span>
                    👥 符合條件的月嫂清單 ➜ 加入候選池
                  </h3>
                  <div className="matching-step-subtext">
                    勾選可完整承接本案的月嫂，再加入候選池，進入後續聯繫與意願確認。
                  </div>
                </div>
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
                    <div role="status" style={{ display: 'grid', gap: '10px', color: '#74593f' }}>
                      <span>目前沒有月嫂能完整承接本案服務日。</span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                        <label style={{ fontSize: '0.82rem' }}>
                          改查多月嫂備案
                          <select
                            aria-label="多月嫂備案分段數"
                            value={multiCaregiverSegmentCount}
                            disabled={candidateActionKey !== null}
                            onChange={(event) => setMultiCaregiverSegmentCount(Number(event.target.value) as 2 | 3 | 4)}
                            style={{ marginLeft: '6px' }}
                          >
                            <option value={2}>2 段</option>
                            <option value={3}>3 段</option>
                            <option value={4}>4 段</option>
                          </select>
                        </label>
                        <button
                          type="button"
                          className="orders-load-more-btn"
                          disabled={drawerLoading || candidateActionKey !== null || matchingOrderFacts === null}
                          onClick={() => void searchMultiCaregiverFallback()}
                        >
                          {candidateActionKey === 'multi-availability-search' ? '正在產生多月嫂備案…' : '查詢多月嫂連續分段備案'}
                        </button>
                      </div>
                    </div>
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
                  {diagnosticMatchingCandidates.length > 0 && (
                    <div style={{ display: 'grid', gap: '8px', borderTop: '1px solid #ead8d1', paddingTop: '12px' }}>
                      <strong style={{ color: '#74593f', fontSize: '0.86rem' }}>僅供檢視的放寬條件結果（{diagnosticMatchingCandidates.length} 位）</strong>
                      {diagnosticMatchingCandidates.map((candidate) => {
                        const omitted = ['region', 'cooking', 'preferred_service_days', 'daily_service_hours']
                          .filter((key) => candidate.filter_results[key] !== true)
                          .map((key) => ({ region: '服務區域', cooking: '料理需求', preferred_service_days: '承接天數', daily_service_hours: '每日工時' }[key] ?? key))
                          .join('、');
                        return (
                          <div key={candidate.staff_id} style={{ padding: '10px 12px', border: '1px dashed #d6a999', borderRadius: '10px', color: '#74593f' }}>
                            <strong>{candidate.staff_name}</strong>（Staff #{candidate.staff_id}）｜未符合：{omitted}｜僅供檢視，不能加入候選聯繫池。
                          </div>
                        );
                      })}
                    </div>
                  )}
                  {completeMultiCaregiverCombinations.length > 0 && (
                    <div style={{ display: 'grid', gap: '10px', borderTop: '1px solid #ead8d1', paddingTop: '14px' }}>
                      <strong style={{ color: '#1e1b19' }}>已核對的多月嫂連續備案（{completeMultiCaregiverCombinations.length} 組）</strong>
                      <span style={{ color: '#74593f', fontSize: '0.82rem' }}>
                        以下每組日期與可用性均由伺服器計算；建立後會再次驗證，不會透過候選聯繫池轉換。
                      </span>
                      {completeMultiCaregiverCombinations.map((combination, index) => (
                        <div key={combination.map((segment) => `${segment.segment_index}-${segment.staff_id}-${segment.start_date}`).join('|')} style={{ border: '1px solid #ead8d1', borderRadius: '10px', padding: '10px 12px' }}>
                          <strong>備案 {index + 1}</strong>
                          {combination.map((segment) => (
                            <div key={`${segment.segment_index}-${segment.staff_id}`} style={{ color: '#74593f', fontSize: '0.82rem', marginTop: '4px' }}>
                              第 {segment.segment_index + 1} 段｜Staff #{segment.staff_id}｜{segment.start_date} ~ {segment.end_date}
                            </div>
                          ))}
                          <button
                            type="button"
                            className="orders-load-more-btn"
                            style={{ marginTop: '10px' }}
                            disabled={candidateActionKey !== null || formalPlanCreationBlocker() !== null}
                            title={formalPlanCreationBlocker() ?? '建立已核對的正式多月嫂方案'}
                            onClick={() => void createFormalMultiCaregiverPlan(combination)}
                          >
                            {candidateActionKey === 'multi-formal-plan' ? '建立並回讀正式方案中…' : `建立此 ${combination.length} 段正式多月嫂方案`}
                          </button>
                        </div>
                      ))}
                    </div>
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
              {candidatePoolMutationBlocker() && (
                <div role="status" style={{ color: '#74593f', marginBottom: '10px' }}>
                  {candidatePoolMutationBlocker()}
                </div>
              )}

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
                              {c.info1StatusLabel}
                            </span>
                          </div>
                          <div style={{ fontSize: '0.78rem', color: '#888' }}>
                            推播服務天數、時段與地區，保護產婦個資並徵詢初步接案意願。
                          </div>
                          <button
                            type="button"
                            className="matching-action-btn-sm"
                            disabled={candidateActionKey !== null || c.contactStatus === 'withdrawn' || candidatePoolMutationBlocker() !== null}
                            title={c.contactStatus === 'withdrawn'
                              ? '已退出候選池，不建立新的發送任務。'
                              : candidatePoolMutationBlocker() ?? '建立可靠發送任務'}
                            onClick={() => void sendCandidateInformation(c.candidateId, 1)}
                          >
                            {candidateActionKey === `${c.candidateId}:1` ? '正在建立資訊-1 發送任務…' : '🔄 重新寄送資訊-1'}
                          </button>
                          <CandidateManualInformationActions
                            caseNo={matchingOrder.id}
                            candidateId={c.candidateId}
                            infoType={1}
                            disabledReason={c.contactStatus === 'withdrawn' ? '候選人已退出。' : candidatePoolMutationBlocker()}
                            onCommitted={() => handleOpenMatchingDrawer(matchingOrder, { preserveCandidateAction: true })}
                          />
                        </div>

                        <div className="matching-subcard">
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ fontWeight: 700, fontSize: '0.88rem', color: '#1e1b19' }}>📄 訂單資訊-2（精篩條款與地址）</span>
                            <span style={{ fontSize: '0.78rem', color: c.info2Status === 'sent' ? '#16a34a' : '#888', fontWeight: 600 }}>
                              {c.info2StatusLabel}
                            </span>
                          </div>
                          <div style={{ fontSize: '0.78rem', color: '#888' }}>
                            推播詳細合約條款、地址與特殊膳食需求，供月嫂二次確認。
                          </div>
                          <button
                            type="button"
                            className="matching-action-btn-sm"
                            disabled={candidateActionKey !== null || c.contactStatus === 'withdrawn' || candidatePoolMutationBlocker() !== null}
                            title={c.contactStatus === 'withdrawn'
                              ? '已退出候選池，不建立新的發送任務。'
                              : candidatePoolMutationBlocker() ?? '建立可靠發送任務'}
                            onClick={() => void sendCandidateInformation(c.candidateId, 2)}
                          >
                            {candidateActionKey === `${c.candidateId}:2` ? '正在建立資訊-2 發送任務…' : '🔄 重新寄送資訊-2'}
                          </button>
                          <CandidateManualInformationActions
                            caseNo={matchingOrder.id}
                            candidateId={c.candidateId}
                            infoType={2}
                            disabledReason={c.contactStatus === 'withdrawn' ? '候選人已退出。' : candidatePoolMutationBlocker()}
                            onCommitted={() => handleOpenMatchingDrawer(matchingOrder, { preserveCandidateAction: true })}
                          />
                        </div>
                      </div>

                      {c.contactStatus !== 'withdrawn' && (
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', alignItems: 'end', marginTop: '12px', paddingTop: '12px', borderTop: '1px solid #ead8d1' }}>
                          <label style={{ display: 'grid', gap: '4px', fontSize: '0.82rem', color: '#57423b' }}>
                            人工補登意願
                            <select
                              value={candidateWillingnessDrafts[c.candidateId]?.willingness ?? 'willing'}
                              disabled={candidateActionKey !== null || candidatePoolMutationBlocker() !== null}
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
                              disabled={candidateActionKey !== null || candidatePoolMutationBlocker() !== null}
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
                            disabled={candidateActionKey !== null || candidatePoolMutationBlocker() !== null}
                            title={candidatePoolMutationBlocker() ?? '更新候選意願'}
                            onClick={() => void recordMatchingCandidateWillingness(c.candidateId)}
                          >
                            {candidateActionKey === `willingness:${c.candidateId}` ? '更新並回讀中…' : '更新候選意願'}
                          </button>
                          <button
                            type="button"
                            className="orders-load-more-btn"
                            disabled={candidateActionKey !== null || c.willingness !== 'willing' || formalPlanCreationBlocker() !== null}
                            title={c.willingness !== 'willing'
                              ? '僅目前願意且仍在候選池的月嫂可建立正式方案'
                              : formalPlanCreationBlocker() ?? '建立正式單月嫂方案'}
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

            {/* 📝 步驟四：推薦產婦、定金狀態與雙邊契約簽署 */}
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
                      📝 推薦產婦、定金確認與雙邊契約簽署
                    </h3>
                    <div className="matching-step-subtext">
                      產婦確認配對方案、繳納定金並完成雙邊不可變契約簽署（LINE 或受控人工證據）。
                    </div>
                  </div>
                </div>

                <div className="matching-contract-grid">
                  <div className="matching-contract-box">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: '0.95rem', fontWeight: 700, color: '#1e1b19' }}>👥 推薦月嫂並記錄客戶決定</span>
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
                      履歷會依目前正式方案與分段內容排入發送；畫面只表示已排入，不代表 LINE 已送達。
                    </div>
                    {matchingDetail.status === '提案中' && (
                      <div style={{ display: 'grid', gap: '8px', marginTop: '12px', padding: '12px', border: '1px solid #ead8d1', borderRadius: '10px' }}>
                        <strong style={{ fontSize: '0.88rem', color: '#1e1b19' }}>📨 Step 5：寄送月嫂履歷給客戶</strong>
                        <label style={{ display: 'grid', gap: '4px', fontSize: '0.82rem', color: '#57423b' }}>
                          履歷訊息備註
                          <textarea
                            rows={2}
                            maxLength={1000}
                            value={resumeNote}
                            disabled={candidateActionKey !== null || matchingDetail.customerProfilesStatus !== null}
                            onChange={(event) => setResumeNote(event.target.value)}
                            placeholder="說明推薦原因與服務安排，將隨月嫂履歷送交客戶。"
                          />
                        </label>
                        <button
                          type="button"
                          className="matching-action-btn-sm"
                          disabled={candidateActionKey !== null || resumeNote.trim().length === 0 || matchingDetail.customerProfilesStatus !== null}
                          onClick={() => void sendCustomerProfiles()}
                        >
                          {candidateActionKey === 'customer-profiles'
                            ? '正在排入履歷發送並確認結果…'
                            : matchingDetail.customerProfilesStatus === 'manually_confirmed'
                              ? '已留存人工履歷送達證據'
                              : matchingDetail.customerProfilesStatus !== null ? '履歷已排入發送' : '排入履歷發送'}
                        </button>
                        {matchingDetail.customerProfilesStatusLabel !== null && <span style={{ fontSize: '0.8rem', color: '#166534' }}>履歷傳達狀態：{matchingDetail.customerProfilesStatusLabel}</span>}
                        {resumeReceipt && <span style={{ fontSize: '0.8rem', color: '#166534' }}>客戶履歷已排入發送，尚未代表 LINE 已送達。</span>}
                        <CustomerProfilesManualActions
                          caseNo={matchingOrder.id}
                          planId={Number(matchingDetail.planId)}
                          currentStatus={matchingDetail.customerProfilesStatus}
                          onCommitted={() => handleOpenMatchingDrawer(matchingOrder, { preserveCandidateAction: true })}
                        />
                      </div>
                    )}
                    {matchingDetail.status === '提案中' && (
                      <div style={{ display: 'grid', gap: '8px', marginTop: '12px' }}>
                        <label style={{ display: 'grid', gap: '4px', fontSize: '0.82rem', color: '#57423b' }}>
                          人工確認依據（LINE 未綁定、未送達或電話確認時補登）
                          <input
                            type="text"
                            maxLength={500}
                            value={customerDecisionReason}
                            disabled={candidateActionKey !== null}
                            onChange={(event) => setCustomerDecisionReason(event.target.value)}
                          />
                        </label>
                        <button
                          type="button"
                          className="matching-action-btn-sm"
                          disabled={candidateActionKey !== null || customerDecisionReason.trim().length === 0}
                          onClick={() => void recordFormalPlanWillingness()}
                        >
                          {candidateActionKey === 'formal-plan-willingness' ? '補登並回讀月嫂意願中…' : '補登正式方案月嫂願意承接'}
                        </button>
                        <button
                          type="button"
                          className="orders-load-more-btn"
                          disabled={candidateActionKey !== null || customerDecisionReason.trim().length === 0}
                          title="補登客戶接受配對方案"
                          onClick={() => void recordMatchingCustomerAcceptance()}
                        >
                          {candidateActionKey === 'customer-decision' ? '補登並回讀客戶決策中…' : '補登客戶接受配對方案'}
                        </button>
                      </div>
                    )}
                    {matchingDetail.status === '已接受' && !matchingDetail.waitingLockAcquired && matchingDetail.assignmentSegments.length === 0 && (
                      <div style={{ display: 'grid', gap: '8px', marginTop: '12px' }}>
                        <button
                          type="button"
                          className="matching-action-btn-sm"
                          disabled={candidateActionKey !== null}
                          onClick={() => void previewWaitingDepositLock()}
                        >
                          {candidateActionKey === 'waiting-lock-preview' ? '正在檢查等待訂金鎖…' : '檢查等待訂金檔期鎖影響'}
                        </button>
                        {waitingLockPreview && (
                          <div role="status" style={{ fontSize: '0.8rem', color: waitingLockPreview.apply_allowed ? '#166534' : '#991b1b' }}>
                            影響檢查：服務日 {waitingLockPreview.service_day_count}、防撞期 {waitingLockPreview.buffer_day_count}；
                            {waitingLockPreview.apply_allowed ? '可套用。' : `不可套用（${waitingLockPreview.conflicts.length} 項衝突）。`}
                          </div>
                        )}
                        <button
                          type="button"
                          className="orders-load-more-btn"
                          disabled={candidateActionKey !== null || !waitingLockPreview?.apply_allowed}
                          onClick={() => void applyWaitingDepositLock()}
                        >
                          {candidateActionKey === 'waiting-lock-apply' ? '套用並回讀等待訂金鎖中…' : '確認套用等待訂金檔期鎖'}
                        </button>
                        {waitingLockReceipt && <div role="status" style={{ fontSize: '0.8rem', color: '#166534' }}>等待訂金檔期鎖已建立。</div>}
                      </div>
                    )}
                  </div>

                  <div className="matching-contract-box">
                    <div style={{ fontWeight: 700, fontSize: '0.95rem', color: '#1e1b19' }}>
                      📑 雙邊契約簽署進度
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
                      契約寄送需核對文件版本與收件人身分後才能排入發送。
                    </div>
                  </div>
                </div>
                {matchingOrder && matchingDetail.planSegments.length > 0 && Number.isInteger(Number(matchingDetail.planId)) && (
                  <MatchingScheduleAndAssignmentActions
                    caseNo={matchingOrder.id}
                    planId={Number(matchingDetail.planId)}
                    planSegments={matchingDetail.planSegments}
                    waitingLockAcquired={matchingDetail.waitingLockAcquired}
                    assignmentExists={matchingDetail.assignmentSegments.length > 0}
                    onAssignmentCompleted={async () => {
                      await handleOpenMatchingDrawer(matchingOrder, { preserveCandidateAction: true });
                      await fetchOrderSummaries();
                    }}
                  />
                )}
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
                    只顯示系統已確認的正式服務分段與排程日曆。
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
        isOpen={Boolean(contractOrder || dateConfirmOrder || reopenOrder || cancelOrder)}
        onClose={closeContractDrawer}
        closeDisabled={cancellationStatus === 'applying'}
        size="xl"
        title={`📑 訂單條款、服務日曆與契約簽署工作台 — ${(contractOrder || dateConfirmOrder || reopenOrder || cancelOrder)?.id || ''}`}
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
            onClick={closeContractDrawer}
            disabled={serviceDatesLocked || reopenLocked || cancellationStatus === 'applying'}
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
                  {contractDetail?.serviceTimeText || '服務時段待確認'}
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

            {/* 4-Tab Clean Navigation */}
            <div className="contract-tabs-nav">
              <button
                type="button"
                className={`contract-tab-btn ${activeContractTab === 'contract_terms' ? 'active' : ''}`}
                onClick={() => switchContractTab('contract_terms')}
              >
                📑 契約簽署與約定條款
              </button>
              <button
                type="button"
                className={`contract-tab-btn ${activeContractTab === 'calendar' ? 'active' : ''}`}
                onClick={() => switchContractTab('calendar')}
              >
                📅 實質服務日曆與天數精算
              </button>
              <button
                type="button"
                className={`contract-tab-btn ${activeContractTab === 'cancellation' ? 'active' : ''}`}
                onClick={() => switchContractTab('cancellation')}
              >
                🛑 訂單取消、退款與受控重開
              </button>
              <button
                type="button"
                className={`contract-tab-btn ${activeContractTab === 'reopen' ? 'active' : ''}`}
                onClick={() => switchContractTab('reopen')}
              >
                🔄 受控重開訂單
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

            {/* Tab 1: 契約簽署與約定條款 (Contract & Terms Consolidated) */}
            {activeContractTab === 'contract_terms' && contractDetail && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
                {/* SSOT 3-Card Status Strip */}
                <div className="contract-ssot-grid">
                  <div className="contract-ssot-card">
                    <div className="contract-ssot-header">
                      <strong className="contract-ssot-title">👩‍🍼 月嫂服務契約</strong>
                      <span className={`contract-status-pill ${contractDetail.staffContractSigned ? 'success' : 'pending'}`}>
                        {contractDetail.staffContractSigned ? '🟢 已簽回' : '🟡 待簽署'}
                      </span>
                    </div>
                    <div className="contract-ssot-body">
                      <div>服務人員：{(contractOrder || dateConfirmOrder)?.assignedDoulaDisplay || '—'}</div>
                      <div>簽署進度：<span>{contractDetail.staffContractSignedText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（月嫂契約簽回）`}</span></div>
                    </div>
                    <button type="button" className="contract-evidence-btn" disabled={!contractDetail.staffContractSigned}>
                      👁️ 檢視月嫂契約簽署存證
                    </button>
                  </div>

                  <div className="contract-ssot-card">
                    <div className="contract-ssot-header">
                      <strong className="contract-ssot-title">👥 產婦服務契約</strong>
                      <span className={`contract-status-pill ${contractDetail.clientContractSigned ? 'success' : 'pending'}`}>
                        {contractDetail.clientContractSigned ? '🟢 已簽回' : '🟡 待簽署'}
                      </span>
                    </div>
                    <div className="contract-ssot-body">
                      <div>立約產婦：{contractDetail.clientName}</div>
                      <div>簽署進度：<span>{contractDetail.clientContractSignedText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（客戶契約簽回）`}</span></div>
                    </div>
                    <button type="button" className="contract-evidence-btn" disabled={!contractDetail.clientContractSigned}>
                      👁️ 檢視產婦契約簽署存證
                    </button>
                  </div>

                  <div className="contract-ssot-card">
                    <div className="contract-ssot-header">
                      <strong className="contract-ssot-title">💰 客戶定金核銷</strong>
                      <span className={`contract-status-pill ${contractDetail.depositSettled ? 'success' : 'pending'}`}>
                        {contractDetail.depositSettled ? '🟢 已全額核銷' : '🟡 待核銷'}
                      </span>
                    </div>
                    <div className="contract-ssot-body">
                      <div>核銷狀態：<span>{contractDetail.depositSettledText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（客戶定金核銷）`}</span></div>
                      <div style={{ fontWeight: 700, color: contractDetail.depositSettled ? '#166534' : '#c2410c' }}>
                        {contractDetail.depositSettled ? '🔒 檔期已鎖定 (定金已入帳)' : '🟡 待收到定金後鎖定檔期'}
                      </div>
                    </div>
                    <button type="button" className="contract-evidence-btn">
                      🧾 檢視定金收據明細
                    </button>
                  </div>
                </div>

                {(contractOrder || dateConfirmOrder) && (
                  <ContractExternalSigningActions
                    caseNo={(contractOrder || dateConfirmOrder)!.id}
                    onCommitted={() => loadContractTabQueries((contractOrder || dateConfirmOrder)!)}
                  />
                )}

                {(contractOrder || dateConfirmOrder) && (
                  <ServiceBeforeReplacementActions
                    caseNo={(contractOrder || dateConfirmOrder)!.id}
                    onCommitted={() => loadContractTabQueries((contractOrder || dateConfirmOrder)!)}
                    onSubstitutionReferral={() => {
                      window.location.hash = `#scheduling?tab=leave_sub&case_no=${encodeURIComponent((contractOrder || dateConfirmOrder)!.id)}`;
                    }}
                  />
                )}

                {contractDetail.domainBlockers && contractDetail.domainBlockers.length > 0 ? (
                  <div style={{ backgroundColor: '#fef2f2', border: '1px solid #fecaca', padding: '14px 18px', borderRadius: '12px' }}>
                    <div style={{ fontWeight: 700, color: '#991b1b', marginBottom: '6px' }}>🛑 完工阻擋檢核項目：</div>
                    <ul style={{ margin: 0, paddingLeft: '20px', color: '#b91c1c', fontSize: '0.85rem' }}>
                      {contractDetail.domainBlockers.map((b, idx) => (
                        <li key={idx}>{b}</li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <div style={{ backgroundColor: '#f0fdf4', border: '1px solid #bbf7d0', padding: '14px 18px', borderRadius: '12px', color: '#166534', fontWeight: 600, fontSize: '0.88rem' }}>
                    ✅ 雙邊契約簽署齊備且定金已全額核銷，本訂單無任何履約阻擋。
                  </div>
                )}

                {/* 5:5 Split Workbench: Left Terms Form + Diff | Right Document Live Preview */}
                <div style={{ display: 'grid', gridTemplateColumns: '1.1fr 0.9fr', gap: '20px', alignItems: 'start' }}>
                  {/* Left Column: 編輯約定服務條款 */}
                  <div className="terms-edit-card">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                      <h3 style={{ fontSize: '1.05rem', fontWeight: 750, color: '#ff7f50', margin: 0 }}>📝 編輯約定服務條款</h3>
                    </div>
                    <p style={{ marginTop: '2px', marginBottom: '12px', color: '#74593f', fontSize: '0.82rem' }}>
                      預覽不會寫入；確認套用時會重新核對訂單、排班與帳務的最新狀態。
                    </p>
                    {termsQuery?.service_data_locked && (
                      <div role="status" style={{ marginBottom: '10px', color: '#9a3412', fontSize: '0.84rem' }}>
                        此案件的服務條件已鎖定，依既有規則不可再變更條款。
                      </div>
                    )}
                    <section data-surface-id="orders.terms.mutation">
                      <div className="terms-form-grid">
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
                        className="btn-secondary-action"
                        style={{ marginTop: '16px', width: '100%', padding: '10px' }}
                        disabled={termsMutationLocked || !termsDraftReady}
                        onClick={() => void previewOrderTerms()}
                      >
                        {termsMutationStatus === 'previewing' ? '正在檢查條款變更…' : '檢查訂單條款變更'}
                      </button>

                      {termsPreview && (
                        <div style={{ marginTop: '14px', padding: '14px', backgroundColor: '#fffdfb', border: '1px solid #fed9b8', borderRadius: '10px' }}>
                          <div style={{ fontWeight: 700, color: '#ff7f50', fontSize: '0.9rem', marginBottom: '8px' }}>✨ 條款變更前後</div>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '0.84rem', color: '#57423b' }}>
                            <div>服務天數：{termsPreview.before.service_days} 天 ➔ <strong>{termsPreview.after.service_days} 天</strong></div>
                            <div>時段：{termsPreview.before.service_time.start_time}～{termsPreview.before.service_time.end_time} ➔ <strong>{termsPreview.after.service_time.start_time}～{termsPreview.after.service_time.end_time}</strong></div>
                            <div>下廚需求：{termsPreview.before.requires_cooking ? '需要' : '不需'} ➔ <strong>{termsPreview.after.requires_cooking ? '需要' : '不需'}</strong></div>
                          </div>
                          <label style={{ display: 'block', marginTop: '10px', fontWeight: 700, fontSize: '0.82rem' }}>
                            變更原因（稽核必填）
                            <textarea
                              rows={2}
                              maxLength={500}
                              value={termsReason}
                              disabled={termsMutationLocked}
                              onChange={(e) => setTermsReason(e.target.value)}
                              placeholder="請輸入變更條款原因…"
                              style={{ width: '100%', marginTop: '4px', padding: '6px 8px', borderRadius: '6px', border: '1px solid #dec0b6' }}
                            />
                          </label>
                          <button
                            type="button"
                            className="btn-primary-action"
                            style={{ marginTop: '8px', width: '100%', padding: '10px', background: '#c2410c' }}
                            disabled={termsMutationLocked || termsReason.trim().length === 0}
                            onClick={() => void applyOrderTerms()}
                          >
                            {termsMutationStatus === 'applying' ? '條款套用中…' : '確認套用訂單條款'}
                          </button>
                        </div>
                      )}
                      {termsReceipt && (
                        <div role="status" style={{ marginTop: '10px', color: '#166534', fontWeight: 700, fontSize: '0.86rem' }}>
                          ✅ 條款已套用（正式服務日 {termsReceipt.official_service_day_count} 天）
                        </div>
                      )}
                      {termsMutationError && <div role="alert" style={{ color: '#b91c1c', marginTop: '10px', fontSize: '0.84rem' }}>{termsMutationError}</div>}
                    </section>
                  </div>

                  {/* Right Column: 📜 正式雙邊契約與訂單資訊即時文件預覽 */}
                  <div className={`contract-doc-preview-card ${contractDocFullscreen ? 'fullscreen' : ''}`}>
                    <div className="contract-doc-toolbar">
                      <div className="contract-doc-view-toggle">
                        <button
                          type="button"
                          className={`contract-doc-toggle-btn ${contractDocView === 'contract' ? 'active' : ''}`}
                          onClick={() => setContractDocView('contract')}
                        >
                          📜 契約草稿預覽（非正式）
                        </button>
                        <button
                          type="button"
                          className={`contract-doc-toggle-btn ${contractDocView === 'spec' ? 'active' : ''}`}
                          onClick={() => setContractDocView('spec')}
                        >
                          📋 訂單規格摘要
                        </button>
                      </div>
                      <div className="contract-doc-actions">
                        <button
                          type="button"
                          className="contract-doc-tool-btn"
                          title="列印草稿預覽（非正式 PDF）"
                          onClick={() => window.print()}
                        >
                          🖨️ 列印草稿
                        </button>
                        <button
                          type="button"
                          className="contract-doc-tool-btn"
                          title={contractDocFullscreen ? '離開全螢幕' : '全螢幕檢視'}
                          onClick={() => setContractDocFullscreen(!contractDocFullscreen)}
                        >
                          {contractDocFullscreen ? '🗗 縮小' : '⛶ 全螢幕'}
                        </button>
                      </div>
                    </div>

                    {contractDocView === 'contract' ? (
                      <div className="contract-doc-sheet">
                        <div className="contract-doc-watermark">
                          {contractDetail.staffContractSigned && contractDetail.clientContractSigned ? 'OFFICIAL CONTRACT' : 'DRAFT PREVIEW'}
                        </div>
                        <div className="contract-doc-header">
                          <h4 className="contract-doc-title">中華民國月子照護勞動工會</h4>
                          <div style={{ fontSize: '0.95rem', fontWeight: 700, color: '#ff7f50' }}>產婦月子照護服務定型化契約書</div>
                          <div className="contract-doc-meta-row">
                            <span>契約字號：CT-{(contractOrder || dateConfirmOrder)?.id.slice(4)}</span>
                            <span>訂單編號：{(contractOrder || dateConfirmOrder)?.id}</span>
                            <span>條款來源：正式訂單資料</span>
                          </div>
                        </div>

                        <div className="contract-doc-parties">
                          <div><strong>甲方（委託人／產婦）：</strong>{contractDetail.clientName}</div>
                          <div><strong>乙方（媒合服務單位）：</strong>中華民國月子照護勞動工會</div>
                          <div><strong>丙方（服務承接月嫂）：</strong>{(contractOrder || dateConfirmOrder)?.assignedDoulaDisplay || '（正式媒合指派中）'}</div>
                        </div>

                        <div className="contract-doc-clauses">
                          <div className="contract-doc-clause-item">
                            <div className="contract-doc-clause-title">第一條【服務期間與地點】</div>
                            <div className="contract-doc-clause-body">
                              自民國 <span className="contract-doc-clause-highlight">{termsDraft.plannedStartDate || contractDetail.serviceRange.split(' ~ ')[0] || '約定日'}</span> 起，
                              共計實質服務 <span className="contract-doc-clause-highlight">{termsDraft.serviceDays || contractDetail.serviceDays} 日整</span>。
                              服務地點為甲方指定之居所。
                            </div>
                          </div>

                          <div className="contract-doc-clause-item">
                            <div className="contract-doc-clause-title">第二條【服務時段與膳食料理】</div>
                            <div className="contract-doc-clause-body">
                              每日服務時段為 <span className="contract-doc-clause-highlight">{termsDraft.startTime && termsDraft.endTime ? `${termsDraft.startTime} 至 ${termsDraft.endTime}` : '待確認'}</span>（每日 {termsDraft.serviceHoursPerDay || '待確認'} 小時）。
                              膳食料理需求：<span className="contract-doc-clause-highlight">{termsDraft.requiresCooking === 'yes' ? '需要下廚料理月子餐' : termsDraft.requiresCooking === 'no' ? '不需下廚' : contractDetail.requiresCookingText}</span>。
                            </div>
                          </div>

                          <div className="contract-doc-clause-item">
                            <div className="contract-doc-clause-title">第三條【服務報酬與定金核銷】</div>
                            <div className="contract-doc-clause-body">
                              合約總報酬為新臺幣 <span className="contract-doc-clause-highlight">{contractDetail.contractAmountText}</span>。
                              定金約定收取 20%（{contractDetail.depositSettled ? '🟢 定金已全額入帳核銷，服務檔期已正式鎖定' : '🟡 定金待收取核銷'}）。
                            </div>
                          </div>
                        </div>

                        <div className="contract-doc-stamps-grid">
                          <div className="contract-doc-stamp-card">
                            <div className="contract-doc-stamp-title">
                              <span>甲方（產婦）簽章存證</span>
                              <span className={`contract-doc-seal ${contractDetail.clientContractSigned ? '' : 'pending'}`}>
                                {contractDetail.clientContractSigned ? '已簽署' : '待簽署'}
                              </span>
                            </div>
                            <div style={{ color: '#74593f', marginTop: '4px' }}>簽署人：{contractDetail.clientName}</div>
                            <div style={{ fontSize: '0.72rem', color: '#8b7169' }}>{contractDetail.clientContractSigned ? '簽署文件已由正式回讀確認' : '尚未完成簽署存證'}</div>
                          </div>

                          <div className="contract-doc-stamp-card">
                            <div className="contract-doc-stamp-title">
                              <span>丙方（月嫂）簽章存證</span>
                              <span className={`contract-doc-seal ${contractDetail.staffContractSigned ? '' : 'pending'}`}>
                                {contractDetail.staffContractSigned ? '已簽署' : '待簽署'}
                              </span>
                            </div>
                            <div style={{ color: '#74593f', marginTop: '4px' }}>簽署人：{(contractOrder || dateConfirmOrder)?.assignedDoulaDisplay || '—'}</div>
                            <div style={{ fontSize: '0.72rem', color: '#8b7169' }}>{contractDetail.staffContractSigned ? '簽署文件已由正式回讀確認' : '尚未完成簽署存證'}</div>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="contract-doc-sheet">
                        <div style={{ fontWeight: 800, fontSize: '1rem', color: '#ff7f50', marginBottom: '12px' }}>📋 訂單完整條件規格摘要 (Order Spec)</div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', fontSize: '0.84rem' }}>
                          <div style={{ padding: '8px 12px', background: '#fff8f6', borderRadius: '6px' }}><strong>訂單編號：</strong>{(contractOrder || dateConfirmOrder)?.id}</div>
                          <div style={{ padding: '8px 12px', background: '#fff8f6', borderRadius: '6px' }}><strong>產婦姓名：</strong>{contractDetail.clientName}</div>
                          <div style={{ padding: '8px 12px', background: '#fff8f6', borderRadius: '6px' }}><strong>預定服務起訖：</strong>{termsDraft.plannedStartDate || contractDetail.serviceRange}</div>
                          <div style={{ padding: '8px 12px', background: '#fff8f6', borderRadius: '6px' }}><strong>約定服務天數：</strong>{termsDraft.serviceDays || contractDetail.serviceDays} 天</div>
                          <div style={{ padding: '8px 12px', background: '#fff8f6', borderRadius: '6px' }}><strong>每日時數時段：</strong>{termsDraft.startTime && termsDraft.endTime ? `${termsDraft.startTime} ~ ${termsDraft.endTime}` : '待確認'} ({termsDraft.serviceHoursPerDay ? `${termsDraft.serviceHoursPerDay} hr` : '時數待確認'})</div>
                          <div style={{ padding: '8px 12px', background: '#fff8f6', borderRadius: '6px' }}><strong>下廚需求：</strong>{termsDraft.requiresCooking === 'yes' ? '需要' : termsDraft.requiresCooking === 'no' ? '不需' : '待確認'}</div>
                          <div style={{ padding: '8px 12px', background: '#fff8f6', borderRadius: '6px' }}><strong>樓層費加給：</strong>NT$ {termsDraft.floorFeeNtd || '0'}</div>
                          <div style={{ padding: '8px 12px', background: '#fff8f6', borderRadius: '6px' }}><strong>合約總應付額：</strong>{contractDetail.contractAmountText}</div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Tab 2: 實質服務日曆與天數精算 (Service Calendar & Precision) */}
            {activeContractTab === 'calendar' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
                <section data-surface-id="orders.drawer.service-dates">
                  {precisionError && (
                    <div role="alert" className="mutation-error-banner">
                      {precisionError}
                    </div>
                  )}
                  {serviceDatesDraft?.queryView && (
                    <>
                      {/* Precision Controls & Metric Bar */}
                      <div style={{ backgroundColor: '#ffffff', border: '1px solid #fed9b8', borderRadius: '14px', padding: '18px 22px', marginBottom: '18px', boxShadow: '0 4px 16px rgba(255, 127, 80, 0.05)' }}>
                        <div className="service-dates-meta-row" style={{ display: 'flex', flexWrap: 'wrap', gap: '14px', marginBottom: '14px', fontSize: '0.85rem', color: '#57423b' }}>
                          <span>合約服務天數：{serviceDatesDraft.queryView.contracted_service_days} 天</span>
                          <span>日期確認狀態：{serviceDatesDraft.queryView.current_version === null ? '尚未確認' : '已確認'}</span>
                          <span>已確認日期：{serviceDatesDraft.queryView.current_dates.length > 0 ? serviceDatesDraft.queryView.current_dates.join(', ') : '無'}</span>
                        </div>

                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: '14px', alignItems: 'flex-end', marginBottom: '14px' }}>
                          <div>
                            <div style={{ fontSize: '0.82rem', fontWeight: 700, color: '#57423b', marginBottom: '4px' }}>
                              實際開工基準：
                            </div>
                            <div style={{ padding: '8px 12px', borderRadius: '8px', backgroundColor: '#f1f5f9', border: '1px solid #dec0b6', fontSize: '0.9rem', fontWeight: 600, color: '#334155' }}>
                              📅 {actualStartQuery?.current_actual_start_date ?? actualStartQuery?.planned_start_date ?? '尚未載入'}
                            </div>
                          </div>
                          <div>
                            <div style={{ fontSize: '0.82rem', fontWeight: 700, color: '#57423b', marginBottom: '4px' }}>
                              工會排休類型：
                            </div>
                            <div aria-label="工會排休類型" style={{ padding: '8px 12px', borderRadius: '8px', backgroundColor: '#f1f5f9', border: '1px solid #dec0b6', fontSize: '0.9rem', fontWeight: 600, color: '#334155' }}>
                              {precisionMode}
                            </div>
                          </div>
                          <button
                            type="button"
                            className="btn-primary-action"
                            disabled={serviceDatesLocked || precisionCalculating}
                            onClick={() => rerunSchedulePrecision()}
                            style={{ padding: '9px 20px', fontSize: '0.88rem' }}
                          >
                            {precisionCalculating ? '精算中…' : '🧮 重新依工會規則精算'}
                          </button>
                        </div>

                        {precisionResult && (
                          <div className="precision-stat-grid" style={{ marginBottom: 0 }}>
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
                      </div>

                      {/* Precision Rule Explanations Banner */}
                      {precisionResult && (
                        <div style={{ backgroundColor: '#fff8f6', border: '1px solid #fed9b8', borderRadius: '12px', padding: '14px 18px', marginBottom: '18px' }}>
                          <div style={{ fontWeight: 700, fontSize: '0.88rem', color: '#9a3412', marginBottom: '6px' }}>
                            工會排休與出勤精算依據：
                          </div>
                          <ul style={{ margin: 0, paddingLeft: '20px', color: '#57423b', fontSize: '0.82rem', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                            <li><strong>排休服務模式</strong>：依「{precisionMode}」規則自動計算出勤與休假（排休共計 {precisionResult.rest_days_count} 天）。</li>
                            <li><strong>國定假日／補假</strong>：系統自動比對行政院人事行政總處行事曆（偵測到 {precisionResult.national_holidays_found.length} 天國定假日）。</li>
                            <li><strong>事前請假日</strong>：依月嫂與產婦雙方約定排除（已設定 {leaveDates.length} 天）。</li>
                            <li><strong>目標達成保證</strong>：系統自動順延至滿足合約 {precisionResult.target_service_days} 天實質出勤為止。</li>
                          </ul>
                          {precisionResult.national_holidays_found.map((holiday) => {
                            const restsOnHoliday = holidayRestDates.includes(holiday.date);
                            return (
                              <label key={holiday.date} style={{ display: 'flex', gap: '6px', marginTop: '8px', fontSize: '0.8rem', color: '#57423b' }}>
                                <input
                                  type="checkbox"
                                  checked={restsOnHoliday}
                                  disabled={serviceDatesLocked || precisionCalculating}
                                  onChange={() => {
                                    const nextHolidayRestDates = restsOnHoliday
                                      ? holidayRestDates.filter((date) => date !== holiday.date)
                                      : [...holidayRestDates, holiday.date].sort();
                                    setHolidayRestDates(nextHolidayRestDates);
                                    rerunSchedulePrecision(nextHolidayRestDates, leaveDates, undefined, customWorkDates);
                                  }}
                                />
                                {holiday.name}（{holiday.date}）列為休假日
                              </label>
                            );
                          })}
                        </div>
                      )}

                      <div className="service-calendar-workbench-layout">
                        <div className="calendar-matrix-card">
                          <div className="calendar-month-header">
                            <h3 style={{ fontSize: '1.05rem', fontWeight: 750, color: '#0f766e', margin: 0 }}>
                              📅 正式服務日期確認（日曆排盤）
                            </h3>
                          </div>

                          <div className="calendar-days-grid" data-surface-id="orders.date.service-date-selection">
                            {serviceDatesDraft.queryView.selectable_dates.length > 0 && Array.from({
                              length: new Date(`${serviceDatesDraft.queryView.selectable_dates[0]}T00:00:00`).getDay(),
                            }).map((_, index) => <div key={`calendar-leading-${index}`} aria-hidden="true" />)}
                            {serviceDatesDraft.queryView.selectable_dates.map((date) => {
                              const precisionDay = precisionResult?.day_by_day.find((day) => day.date === date);
                              const selected = precisionDay?.is_work_day === true;
                              const holiday = precisionResult?.national_holidays_found.find((h) => h.date === date);
                              const isLeave = leaveDates.includes(date);
                              const isCustomWork = customWorkDates.includes(date);
                              const calendarActionLabel = isLeave
                                ? `${date} 人工調整休假，點擊取消`
                                : isCustomWork
                                  ? `${date} 人工覆寫服務日，點擊恢復固定排休`
                                  : selected
                                    ? `${date} 服務日，點擊改為人工排休`
                                    : `${date} 固定排休，點擊改為正式服務日`;
                              return (
                                <button
                                  key={date}
                                  data-control-id="orders.date.service-date-select"
                                  type="button"
                                  aria-label={calendarActionLabel}
                                  aria-pressed={selected}
                                  className={`calendar-date-cell ${selected ? 'selected' : isLeave ? 'manual-rest' : holiday ? 'holiday' : ''}`}
                                  disabled={serviceDatesLocked}
                                  onClick={() => {
                                    if (isLeave) {
                                      const nextLeaveDates = leaveDates.filter((value) => value !== date);
                                      setLeaveDates(nextLeaveDates);
                                      rerunSchedulePrecision(holidayRestDates, nextLeaveDates, undefined, customWorkDates);
                                      return;
                                    }
                                    if (isCustomWork) {
                                      const nextCustomWorkDates = customWorkDates.filter((value) => value !== date);
                                      setCustomWorkDates(nextCustomWorkDates);
                                      rerunSchedulePrecision(holidayRestDates, leaveDates, undefined, nextCustomWorkDates);
                                      return;
                                    }
                                    if (selected) {
                                      const nextLeaveDates = [...leaveDates, date].sort();
                                      setLeaveDates(nextLeaveDates);
                                      rerunSchedulePrecision(holidayRestDates, nextLeaveDates, undefined, customWorkDates);
                                      return;
                                    }
                                    const nextCustomWorkDates = [...customWorkDates, date].sort();
                                    setCustomWorkDates(nextCustomWorkDates);
                                    rerunSchedulePrecision(holidayRestDates, leaveDates, undefined, nextCustomWorkDates);
                                  }}
                                >
                                  <span>{date}</span>
                                  {selected && <span className="calendar-date-cell-badge">8hr / 服務</span>}
                                  {holiday && !selected && <span className="calendar-date-cell-badge" style={{ backgroundColor: '#fed7aa', color: '#9a3412' }}>{holiday.name}</span>}
                                  {isLeave && !selected && <span className="calendar-date-cell-badge" style={{ backgroundColor: '#fecaca', color: '#991b1b' }}>請假</span>}
                                </button>
                              );
                            })}
                          </div>
                        </div>

                      </div>

                      <div className="leave-planning-box" style={{ marginTop: '12px' }}>
                        <strong style={{ fontSize: '0.82rem', color: '#9a3412' }}>➕ 設定事前約定請假日：</strong>
                        <div style={{ display: 'flex', gap: '6px', marginTop: '6px' }}>
                          <input
                            type="date"
                            aria-label="事前請假日期"
                            value={leaveDateDraft}
                            disabled={serviceDatesLocked || precisionCalculating}
                            onChange={(e) => setLeaveDateDraft(e.target.value)}
                            style={{ padding: '4px 8px', borderRadius: '6px', border: '1px solid #dec0b6', fontSize: '0.82rem', flex: 1 }}
                          />
                          <button
                            type="button"
                            className="btn-secondary-action"
                            disabled={serviceDatesLocked || precisionCalculating || !leaveDateDraft}
                            onClick={() => {
                              if (!leaveDateDraft || leaveDates.includes(leaveDateDraft)) return;
                              const nextLeaveDates = [...leaveDates, leaveDateDraft].sort();
                              setLeaveDates(nextLeaveDates);
                              setLeaveDateDraft('');
                              rerunSchedulePrecision(holidayRestDates, nextLeaveDates, undefined, customWorkDates);
                            }}
                            style={{ padding: '4px 10px', fontSize: '0.78rem' }}
                          >
                            新增事前請假
                          </button>
                        </div>
                      </div>

                      {/* Full-width Preview / Apply workflow below the calendar */}
                      <div className="service-date-confirmation-panel">
                        <div className="service-date-confirmation-actions">
                          <button
                            type="button"
                            data-control-id="orders.date.service-date-preview"
                            className="btn-secondary-action"
                            style={{ width: '100%', padding: '9px', marginBottom: '10px' }}
                            disabled={serviceDatesLocked || precisionCalculating || !serviceDatesSelectionReady}
                            onClick={() => (contractOrder || dateConfirmOrder) && previewServiceDates((contractOrder || dateConfirmOrder)!.id)}
                          >
                            {serviceDatesDraft?.status === 'preview_loading' ? '正在精算服務週次…' : '🔍 檢查服務週次影響'}
                          </button>

                          {serviceDatesDraft?.previewView && (
                            <div style={{ marginBottom: '10px', padding: '10px', background: '#fffdfb', border: '1px solid #fed9b8', borderRadius: '8px' }}>
                              <strong style={{ fontSize: '0.86rem', color: '#ff7f50' }}>服務週次精算預覽</strong>
                              <div style={{ fontSize: '0.82rem', color: '#57423b', marginTop: '4px' }}>
                                正式服務日數：{serviceDatesDraft.previewView.service_dates.length} 天
                              </div>
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '6px' }}>
                                {serviceDatesDraft.previewView.weeks.map((week) => (
                                  <div key={week.week_number} style={{ fontSize: '0.78rem', color: '#57423b', background: '#ffffff', padding: '4px 8px', borderRadius: '4px', border: '1px solid #fed9b8' }}>
                                    {`第 ${week.week_number} 週：${week.period_start} ~ ${week.period_end}（${week.service_day_count} 天）`}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          <label style={{ display: 'block', fontWeight: 700, fontSize: '0.84rem' }}>
                            服務日期確認原因（稽核必填）
                            <input
                              type="text"
                              className="mutation-reason-input"
                              aria-label="確認服務日期原因"
                              maxLength={500}
                              value={serviceDatesDraft?.reason ?? ''}
                              disabled={serviceDatesLocked}
                              placeholder="請輸入確認服務日期之具體原因"
                              onChange={(e) => (contractOrder || dateConfirmOrder) && updateServiceDatesReason((contractOrder || dateConfirmOrder)!.id, e.target.value)}
                              style={{ width: '100%', marginTop: '4px', padding: '8px 10px', borderRadius: '8px', border: '1px solid #dec0b6', fontSize: '0.85rem' }}
                            />
                          </label>

                          {serviceDatesDraft?.previewView && (
                            <button
                              type="button"
                              data-control-id="orders.date.service-date-apply"
                              className="btn-primary-action"
                              style={{ marginTop: '10px', width: '100%', padding: '11px', background: '#c2410c' }}
                              disabled={serviceDatesLocked || precisionCalculating || !serviceDatesSelectionReady || (serviceDatesDraft?.reason.trim().length ?? 0) === 0}
                              onClick={() => {
                                const caseNo = (contractOrder || dateConfirmOrder)?.id;
                                if (!caseNo) return;
                                void applyServiceDatesFlow(caseNo)
                                  .then(() => fetchOrderSummaries())
                                  .catch(() => undefined);
                              }}
                            >
                              {serviceDatesDraft?.status === 'apply_pending' ? '服務日期套用中…' : '確認套用服務日期'}
                            </button>
                          )}

                          {serviceDatesDraft?.status === 'outcome_unknown' && (
                            <div role="alert" style={{ marginTop: '10px', padding: '10px', background: '#fff7ed', border: '1px solid #fdba74', borderRadius: '8px', color: '#9a3412', fontSize: '0.84rem' }}>
                              服務日期確認回應逾時或未明；只可使用相同 Payload 與相同 Key 重試。
                              <button
                                type="button"
                                className="btn-secondary-action"
                                style={{ marginTop: '6px', width: '100%' }}
                                onClick={() => {
                                  const caseNo = (contractOrder || dateConfirmOrder)?.id;
                                  if (!caseNo) return;
                                  void retryServiceDatesApplyFlow(caseNo)
                                    .then(() => fetchOrderSummaries())
                                    .catch(() => undefined);
                                }}
                              >
                                重試提交
                              </button>
                            </div>
                          )}

                          {serviceDatesDraft?.receiptView && (
                            <div role="status" style={{ marginTop: '10px', padding: '10px', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '8px', color: '#166534', fontWeight: 700, fontSize: '0.82rem' }}>
                              ✅ 服務日期已確認成功
                            </div>
                          )}

                          {(serviceDatesDraft?.status === 'stale' || serviceDatesDraft?.status === 'typed_error') && (
                            <div role="alert" style={{ marginTop: '10px', padding: '10px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '8px', color: '#991b1b', fontSize: '0.84rem' }}>
                              {serviceDatesDraft.error?.message ?? '服務日期確認失敗，請重新查詢。'}
                            </div>
                          )}
                        </div>
                      </div>

                      <div className="leave-substitution-entry">
                        <div>
                          <strong>已有正式排班：處理請假／代班</strong>
                          <p>
                            未正式指派時只做上方事前排休；正式指派後請在代班工作台選同日指定代班，或讓原月嫂後續順延。
                          </p>
                        </div>
                        <button
                          type="button"
                          className="btn-secondary-action"
                          onClick={() => {
                            const caseNo = (contractOrder || dateConfirmOrder)?.id;
                            if (caseNo) {
                              window.location.hash = `#scheduling?tab=leave_sub&case_no=${encodeURIComponent(caseNo)}`;
                            }
                          }}
                        >
                          前往請假／代班工作台
                        </button>
                      </div>
                    </>
                  )}
                  {!serviceDatesDraft?.queryView && (
                    <div style={{ padding: '20px', backgroundColor: '#ffffff', border: '1px solid #fed9b8', borderRadius: '14px' }}>
                      {precisionError ? (
                        <div role="alert" style={{ color: '#b91c1c', fontSize: '0.85rem' }}>
                          {precisionError}
                        </div>
                      ) : (
                        <div role="status" style={{ color: '#64748b', fontSize: '0.85rem' }}>
                          正在載入服務日期與出勤精算數據…
                        </div>
                      )}
                    </div>
                  )}
                </section>

                {/* Actual Start Date Precision Card */}
                <div className="calendar-workbench-card" style={{ marginTop: '16px' }}>
                  <div className="calendar-card-header">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span className="calendar-badge actual">實際開工</span>
                      <h4 className="calendar-card-title">實際開工日更正與動態排盤</h4>
                    </div>
                  </div>

                  <div>
                    <div>
                      <label style={{ display: 'block', fontWeight: 700, fontSize: '0.85rem' }}>
                        更正實際服務開始日
                        <input
                          type="date"
                          value={actualStartDraft}
                          disabled={actualStartLocked}
                          onChange={(e) => setActualStartDraft(e.target.value)}
                          style={{ width: '100%', marginTop: '6px', padding: '8px 10px', borderRadius: '8px', border: '1px solid #dec0b6' }}
                        />
                      </label>
                      <button
                        type="button"
                        className="btn-secondary-action"
                        style={{ marginTop: '10px', width: '100%', padding: '9px' }}
                        disabled={actualStartLocked || actualStartDraft.trim().length === 0}
                        onClick={() => void previewActualStart()}
                      >
                        {actualStartStatus === 'previewing' ? '正在產生預覽…' : '預覽實際開工日變更'}
                      </button>
                    </div>
                  </div>

                  {actualStartQuery?.service_data_locked && (
                    <div role="status" style={{ color: '#92400e', margin: '10px 0', fontSize: '0.84rem' }}>
                      本案服務資料已鎖定；目前只能查詢，需先依既有解鎖流程處理後才能更正。
                    </div>
                  )}
                  {actualStartPreview && (
                    <div style={{ backgroundColor: '#fffdfb', border: '1px solid #fed9b8', borderRadius: '12px', padding: '16px', marginTop: '14px' }}>
                      <strong style={{ color: '#ff7f50', fontSize: '0.92rem' }}>實際開工日影響已確認</strong>
                      <div style={{ fontSize: '0.86rem', color: '#57423b', marginTop: '6px' }}>日期：{actualStartPreview.before_actual_start_date ?? '尚未登錄'} → {actualStartPreview.after_actual_start_date}</div>
                      <div style={{ fontSize: '0.86rem', color: '#57423b' }}>預計結束日：{actualStartPreview.actual_end_date}</div>
                      <div style={{ fontSize: '0.86rem', color: '#57423b' }}>正式服務日：{actualStartPreview.actual_start.official_service_dates.length} 天</div>
                      <div style={{ fontSize: '0.86rem', color: '#57423b' }}>重建指派：{actualStartPreview.scheduling.assignments.length} 段</div>
                      <label style={{ display: 'block', marginTop: '10px', fontWeight: 700, fontSize: '0.84rem' }}>
                        套用原因（稽核必填）
                        <textarea
                          rows={2}
                          maxLength={500}
                          value={actualStartReason}
                          disabled={actualStartLocked}
                          onChange={(e) => setActualStartReason(e.target.value)}
                          style={{ width: '100%', marginTop: '6px', padding: '8px 10px', borderRadius: '8px', border: '1px solid #dec0b6' }}
                        />
                      </label>
                      <button
                        type="button"
                        className="btn-primary-action"
                        style={{ marginTop: '10px', width: '100%', padding: '11px', background: '#c2410c' }}
                        disabled={actualStartLocked || actualStartReason.trim().length === 0}
                        onClick={() => void applyActualStart()}
                      >
                        {actualStartStatus === 'applying' ? '實際開工日套用中…' : '確認套用實際開工日'}
                      </button>
                    </div>
                  )}
                  {actualStartReceipt && (
                    <div role="status" style={{ color: '#166534', fontWeight: 700, marginTop: '10px', fontSize: '0.86rem' }}>
                      實際開工日已套用（{actualStartReceipt.official_service_day_count} 個正式服務日）
                    </div>
                  )}
                  {actualStartError && <div role="alert" style={{ color: '#b91c1c', marginTop: '10px', fontSize: '0.85rem' }}>{actualStartError}</div>}
                </div>

                {(contractOrder || dateConfirmOrder) && (
                  <OrderServiceCompletionActions
                    caseNo={(contractOrder || dateConfirmOrder)!.id}
                    orderStatus={(contractOrder || dateConfirmOrder)!.orderStatus}
                    onCompleted={fetchOrderSummaries}
                  />
                )}
              </div>
            )}

            {/* Tab 3: 訂單取消、退款與受控重開 (Cancellation, Refund & Reopen) */}
            {/* Tab 3: 訂單取消與退款試算 (Cancellation & Refund) */}
            {activeContractTab === 'cancellation' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
                <div style={{ backgroundColor: '#fffdfc', border: '1px solid #fed9b8', borderRadius: '12px', padding: '14px 18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span style={{ fontSize: '0.92rem', fontWeight: 700, color: '#57423b' }}>當前案件狀態：</span>
                    <strong style={{ fontSize: '1rem', color: '#ff7f50' }}>{(contractOrder || dateConfirmOrder || cancelOrder || reopenOrder)?.orderStatus ?? '洽談中'}</strong>
                  </div>
                  <span style={{ padding: '3px 10px', borderRadius: '9999px', fontSize: '0.78rem', fontWeight: 750, backgroundColor: '#fef2f2', color: '#991b1b', border: '1px solid #fecaca' }}>
                    🟢 允許取消試算
                  </span>
                </div>

                <div className="cancellation-reopen-card" style={{ maxWidth: '720px' }}>
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                      <h3 style={{ fontSize: '1.05rem', fontWeight: 750, color: '#9f1239', margin: 0 }}>🛑 訂單取消與退款處理</h3>
                      {cancellationQuery && <span className="contract-status-pill pending">{cancellationQuery.lifecycle_status}</span>}
                    </div>
                    <p style={{ margin: '0 0 12px 0', fontSize: '0.82rem', color: '#74593f' }}>
                      系統會依目前訂單、正式排班、客戶帳務與月嫂薪資根事實計算取消影響。
                    </p>

                    {cancellationError && (
                      <div role="alert" style={{ color: '#b91c1c', fontSize: '0.82rem', marginBottom: '8px' }}>
                        {cancellationError}
                      </div>
                    )}
                    {cancellationRetryMode && !cancellationError && (
                      <div role="status" style={{ color: '#9a3412', fontSize: '0.82rem', marginBottom: '8px' }}>
                        上一次取消結果尚未確認；重試會沿用同一命令內容與識別，不會建立新的送出命令。
                      </div>
                    )}

                    {cancellationQuery ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '0.85rem', color: '#57423b', marginBottom: '12px' }}>
                        <div>實際開始日：{cancellationQuery.actual_start_date ?? '尚未開始'}</div>
                        <div>契約服務天數：{cancellationQuery.contracted_service_days} 天</div>
                        <div>目前實際服務日：{cancellationDays.length} 天</div>
                        <div style={{ color: '#74593f' }}>
                          {cancellationQuery.service_started
                            ? '服務進行中：請逐日核對實際服務日期與月嫂；未服務的未來日期請移除。'
                            : '服務尚未開始：實際服務日固定為 0 天，不得把未來排班當作已服務事實。'}
                        </div>
                        {cancellationQuery.service_started && cancellationDays.length >= cancellationQuery.contracted_service_days && (
                          <div role="alert" style={{ color: '#991b1b' }}>已達完整服務天數；依正式規則不可執行取消，系統不會寫入變更。</div>
                        )}
                        {cancellationQuery.service_started && (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', borderTop: '1px solid #f3d8c8', paddingTop: '10px' }}>
                            <strong>逐日實際服務事實</strong>
                            {cancellationDays.length === 0 && <span style={{ color: '#8b7169' }}>尚未填入實際服務日；服務已開始時必須至少保留一日。</span>}
                            {cancellationDays.map((day, index) => {
                              const original = cancellationQuery.confirmed_service_days.some((candidate) => candidate.service_date === day.service_date && candidate.staff_id === day.staff_id);
                              return (
                                <div key={`${index}-${day.service_date}`} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', alignItems: 'center' }}>
                                  <label>
                                    <span className="sr-only">第 {index + 1} 日日期</span>
                                    <input
                                      type="date"
                                      value={day.service_date}
                                      disabled={cancellationStatus === 'applying'}
                                      onChange={(event) => {
                                        setCancellationDays((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, service_date: event.target.value } : item));
                                        setCancellationPreview(null);
                                      }}
                                    />
                                  </label>
                                  <label>
                                    <span className="sr-only">第 {index + 1} 日月嫂</span>
                                    <select
                                      value={day.staff_id}
                                      disabled={cancellationStatus === 'applying'}
                                      onChange={(event) => {
                                        setCancellationDays((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, staff_id: Number(event.target.value) } : item));
                                        setCancellationPreview(null);
                                      }}
                                    >
                                      <option value={0}>請選擇月嫂</option>
                                      {cancellationQuery.caregiver_options.map((option) => <option key={option.staff_id} value={option.staff_id}>{option.display_name}</option>)}
                                    </select>
                                  </label>
                                  <input
                                    aria-label={`第 ${index + 1} 日人工原因`}
                                    value={day.reason}
                                    maxLength={500}
                                    placeholder={original ? '若更換日期／月嫂請填原因' : '新增／變更必填原因'}
                                    disabled={cancellationStatus === 'applying'}
                                    onChange={(event) => {
                                      setCancellationDays((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, reason: event.target.value } : item));
                                      setCancellationPreview(null);
                                    }}
                                  />
                                  <button type="button" className="btn-secondary-action" disabled={cancellationStatus === 'applying'} onClick={() => { setCancellationDays((current) => current.filter((_, itemIndex) => itemIndex !== index)); setCancellationPreview(null); }}>移除本日</button>
                                </div>
                              );
                            })}
                            <button
                              type="button"
                              className="btn-secondary-action"
                              disabled={cancellationStatus === 'applying' || cancellationQuery.caregiver_options.length === 0}
                              onClick={() => {
                                const staffId = cancellationQuery.caregiver_options[0]?.staff_id ?? 0;
                                setCancellationDays((current) => [...current, { service_date: '', staff_id: staffId, reason: '' }]);
                                setCancellationPreview(null);
                              }}
                            >新增實際服務日</button>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div style={{ fontSize: '0.82rem', color: '#8b7169', marginBottom: '12px' }}>
                        {cancellationStatus === 'querying' ? '⏳ 載入取消事實中…' : '點擊下方預覽按鈕以試算退款與服務影響。'}
                      </div>
                    )}

                    {cancellationPreview && (
                      <div className="cancellation-calc-box">
                        <strong style={{ color: '#9f1239', fontSize: '0.88rem' }}>📊 取消影響預覽</strong>
                        <div className="cancellation-calc-row">
                          <span>取消基準日</span>
                          <strong>{cancellationPreview.cancellation_date}</strong>
                        </div>
                        <div className="cancellation-calc-row">
                          <span>實際服務終止日</span>
                          <span>{cancellationPreview.actual_end_date ?? '尚未開始服務'}</span>
                        </div>
                        <div className="cancellation-calc-row">
                          <span>正式服務量</span>
                          <span>{cancellationPreview.official_service_day_count} 天／{cancellationPreview.official_service_hours} 小時</span>
                        </div>
                        <div style={{ marginTop: '8px', fontSize: '0.78rem', color: '#74593f' }}>
                          不另加收額外費用；客戶帳務與月嫂薪資只依正式根事實產生影響。
                        </div>
                        <div style={{ marginTop: '8px', fontSize: '0.78rem', color: '#57423b' }}>
                          客戶帳務：{cancellationPreview.client_finance_impact.actions?.length ?? 0} 筆調整，待處理阻擋 {cancellationPreview.client_finance_impact.blockers?.length ?? 0} 項。
                        </div>
                        <div style={{ fontSize: '0.78rem', color: '#57423b' }}>
                          服務人員薪資：{cancellationPreview.payroll_impact.actions?.length ?? 0} 筆調整，待處理阻擋 {cancellationPreview.payroll_impact.blockers?.length ?? 0} 項。
                        </div>
                        {cancellationPreview.client_finance_impact.actions?.slice(0, 3).map((action) => (
                          <div key={`client-${action.obligation_identity}`} style={{ fontSize: '0.76rem', color: '#57423b' }}>
                            客戶帳務：{clientFinanceDirectionLabel(action.direction)} NT$ {action.direction_amount_ntd.toLocaleString()}
                          </div>
                        ))}
                        {cancellationPreview.payroll_impact.actions?.slice(0, 3).map((action) => (
                          <div key={`payroll-${action.obligation_identity}`} style={{ fontSize: '0.76rem', color: '#57423b' }}>
                            服務人員薪資調整：NT$ {action.amount.amount.toLocaleString()}
                          </div>
                        ))}
                        <details style={{ marginTop: '8px', fontSize: '0.76rem', color: '#74593f' }}>
                          <summary>技術詳情與資料來源</summary>
                          <div>
                            訂單版本 {cancellationPreview.order_version}｜排班版本 {cancellationPreview.scheduling_version}｜
                            客戶帳務版本 {cancellationPreview.client_finance_version}｜薪資版本 {cancellationPreview.payroll_version}
                          </div>
                          {cancellationPreview.client_finance_impact.actions?.slice(0, 3).map((action) => (
                            <div key={`client-technical-${action.obligation_identity}`}>客戶帳務／{action.action}：{action.obligation_identity}（{action.direction}）</div>
                          ))}
                          {cancellationPreview.payroll_impact.actions?.slice(0, 3).map((action) => (
                            <div key={`payroll-technical-${action.obligation_identity}`}>薪資／{action.action}：{action.obligation_identity}（{action.direction}）</div>
                          ))}
                        </details>
                      </div>
                    )}

                    {cancellationPreview && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '12px' }}>
                        <label htmlFor="cancellation-reason" style={{ fontSize: '0.82rem', fontWeight: 700, color: '#57423b' }}>
                          人工取消原因
                        </label>
                        <textarea
                          id="cancellation-reason"
                          value={cancellationReason}
                          maxLength={500}
                          rows={3}
                          disabled={cancellationStatus === 'applying'}
                          onChange={(event) => setCancellationReason(event.target.value)}
                          placeholder="請記錄客戶決定或人工介入原因"
                        />
                        <label style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', fontSize: '0.8rem', color: '#57423b' }}>
                          <input
                            type="checkbox"
                            checked={cancellationConfirmed}
                            disabled={cancellationStatus === 'applying'}
                            onChange={(event) => setCancellationConfirmed(event.target.checked)}
                          />
                          我已核對本次取消日期、正式服務量及後續帳務／薪資影響，確認套用取消。
                        </label>
                      </div>
                    )}

                    {cancellationReceipt && (
                      <div role="status" style={{ marginTop: '12px', color: '#166534', fontSize: '0.84rem', fontWeight: 700 }}>
                        訂單取消已完成；最新狀態：{cancellationReceipt.lifecycle_status}，正式服務量為 {cancellationReceipt.official_service_day_count} 天／{cancellationReceipt.official_service_hours} 小時。
                        <details style={{ marginTop: '4px', color: '#74593f', fontWeight: 400 }}>
                          <summary>技術詳情與資料來源</summary>
                          <div>訂單、客戶帳務、薪資版本已回讀為 {cancellationReceipt.order_version}／{cancellationReceipt.client_finance_version}／{cancellationReceipt.payroll_version}。</div>
                        </details>
                      </div>
                    )}
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <button
                      type="button"
                      data-control-id="orders.cancellation.preview"
                      className="btn-secondary-action"
                      style={{ width: '100%', padding: '10px' }}
                      disabled={!cancellationQuery || cancellationStatus !== 'idle' || (cancellationQuery.service_started && cancellationDays.length >= cancellationQuery.contracted_service_days)}
                      onClick={() => void previewCancellation()}
                    >
                      {cancellationStatus === 'previewing' ? '正在試算取消影響…' : '🔍 預覽取消與退款試算（檢查取消影響）'}
                    </button>
                    <button
                      type="button"
                      data-control-id="orders.cancellation.apply"
                      className="btn-primary-action"
                      style={{ backgroundColor: '#9f1239', borderColor: '#9f1239', width: '100%', padding: '10px' }}
                      disabled={!cancellationPreview || !cancellationReason.trim() || !cancellationConfirmed || cancellationStatus !== 'idle' || (cancellationQuery?.service_started === true && cancellationDays.length >= cancellationQuery.contracted_service_days)}
                      onClick={() => void applyCancellation()}
                    >
                      {cancellationStatus === 'applying'
                        ? '正在套用取消…'
                        : cancellationRetryMode ? '以相同內容重新確認取消' : '確認執行取消'}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Tab 4: 🔄 訂單受控重開 (Controlled Reopen) */}
            {activeContractTab === 'reopen' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
                <div style={{ backgroundColor: '#fffdfc', border: '1px solid #fed9b8', borderRadius: '12px', padding: '14px 18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span style={{ fontSize: '0.92rem', fontWeight: 700, color: '#57423b' }}>當前案件狀態：</span>
                    <strong style={{ fontSize: '1rem', color: '#ff7f50' }}>{(contractOrder || dateConfirmOrder || cancelOrder || reopenOrder)?.orderStatus ?? '洽談中'}</strong>
                  </div>
                  <span style={{ padding: '3px 10px', borderRadius: '9999px', fontSize: '0.78rem', fontWeight: 750, backgroundColor: '#f0fdf4', color: '#166534', border: '1px solid #bbf7d0' }}>
                    🔄 允許受控重啟
                  </span>
                </div>

                <div className="cancellation-reopen-card" style={{ maxWidth: '720px' }}>
                  <div data-surface-id="orders.modal.reopen">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                      <h3 style={{ fontSize: '1.05rem', fontWeight: 750, color: '#ea580c', margin: 0 }}>🔄 訂單受控重開</h3>
                      <span className="contract-status-pill pending">受控安全重啟</span>
                    </div>
                    <p style={{ margin: '0 0 12px 0', fontSize: '0.82rem', color: '#74593f' }}>
                      已終止或封閉案件會先核對訂單、帳務與月嫂款項，再恢復至「洽談中」進件階段。
                    </p>

                    {reopenDraft?.previewView && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '0.84rem', color: '#57423b', marginBottom: '12px' }}>
                        <div>狀態轉移：<span>{reopenDraft.previewView.before_status}</span> ➔ <strong style={{ color: '#166534' }}>{reopenDraft.previewView.after_status}</strong></div>
                        <div className="reopen-version-grid">
                          <div><strong>訂單狀態</strong>已核對</div>
                          <div><strong>客戶帳務</strong>已完成雙向核對</div>
                          <div><strong>月嫂款項</strong>無待處理欠款</div>
                        </div>
                        {reopenDraft.previewView.requires_fresh_scheduling_preview && (
                          <div style={{ fontSize: '0.8rem', color: '#9a3412' }}>
                            套用重開前必須重新檢查排班。
                          </div>
                        )}
                      </div>
                    )}
                    {!reopenDraft?.previewView && !reopenDraft?.error && (
                      <div style={{ fontSize: '0.82rem', color: '#8b7169', marginBottom: '12px' }}>
                        {reopenDraft?.status === 'preview_loading' ? '⏳ 正在取得受控重開預覽…' : '正在載入重開候選事實…'}
                      </div>
                    )}
                    {reopenDraft?.error && (
                      <div role="alert" style={{ color: '#b91c1c', fontSize: '0.82rem', marginBottom: '8px' }}>
                        <div>{reopenDraft.error.message}</div>
                        {'domainBlockers' in reopenDraft.error && Array.isArray(reopenDraft.error.domainBlockers) && reopenDraft.error.domainBlockers.length > 0 && (
                          <div>此案件目前有業務阻擋，處理完成後才能重開。</div>
                        )}
                      </div>
                    )}

                    <label style={{ display: 'block', fontWeight: 700, fontSize: '0.84rem' }}>
                      重開原因說明（稽核必填，1～500 字）
                      <textarea
                        data-control-id="orders.reopen.reason"
                        rows={3}
                        maxLength={500}
                        placeholder="請具體說明重開訂單之業務原因（至少 1 字）"
                        value={reopenDraft?.reason ?? ''}
                        disabled={reopenLocked}
                        onChange={(event) => (contractOrder || dateConfirmOrder || reopenOrder || cancelOrder) && updateReopenReason((contractOrder || dateConfirmOrder || reopenOrder || cancelOrder)!.id, event.target.value)}
                        style={{ width: '100%', marginTop: '6px', padding: '8px 10px', borderRadius: '8px', border: '1px solid #dec0b6', fontSize: '0.85rem' }}
                      />
                    </label>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {reopenDraft?.status === 'outcome_unknown' && (
                      <div>
                        <div role="alert" style={{ color: '#9a3412', fontSize: '0.8rem', backgroundColor: '#fff7ed', padding: '6px 10px', borderRadius: '6px', border: '1px solid #fdba74', marginBottom: '8px' }}>
                          重開結果尚未確認；請使用下方重試功能繼續，系統會安全沿用同一次操作。
                        </div>
                        <button
                          type="button"
                          data-control-id="orders.reopen.retry"
                          className="btn-primary-action"
                          style={{ width: '100%', padding: '11px', background: '#c2410c' }}
                          onClick={() => {
                            const caseNo = (contractOrder || dateConfirmOrder || reopenOrder || cancelOrder)?.id;
                            if (!caseNo) return;
                            void retryReopenApplyFlow(caseNo, () => fetchOrderSummaries());
                          }}
                        >
                          重試提交受控重開
                        </button>
                      </div>
                    )}
                    {(reopenDraft?.status === 'observed' || reopenDraft?.status === 'receipt_received') && (
                      <div role="status" style={{ color: '#166534', fontWeight: 700, fontSize: '0.84rem', backgroundColor: '#f0fdf4', padding: '6px 10px', borderRadius: '6px', border: '1px solid #bbf7d0' }}>
                        ✅ 訂單已受控重開成功
                      </div>
                    )}
                    {reopenDraft?.previewView && (
                      <button
                        type="button"
                        data-control-id="orders.reopen.apply"
                        className="btn-primary-action"
                        style={{ width: '100%', padding: '11px', background: '#c2410c' }}
                        disabled={reopenLocked || (reopenDraft?.reason.trim().length ?? 0) === 0}
                        onClick={() => {
                          const caseNo = (contractOrder || dateConfirmOrder || reopenOrder || cancelOrder)?.id;
                          if (!caseNo) return;
                          void applyReopenFlow(caseNo)
                            .then(() => fetchOrderSummaries())
                            .catch(() => undefined);
                        }}
                      >
                        {reopenDraft?.status === 'apply_pending' ? '重開套用中…' : '確認受控重開訂單'}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default OrdersPage;

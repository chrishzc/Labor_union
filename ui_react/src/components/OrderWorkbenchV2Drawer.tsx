import { useUnsavedNavigation } from './UnsavedChanges';
import { useStaffIdentityLabels } from './StaffIdentityProvider';
import type { OrderWorkbenchScope } from '../api/orders/order_core_stage_projection_client';
import { useCallback, useEffect, useRef, useState, useSyncExternalStore, type FC } from 'react';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';
import { serviceDatesNeedCompletion } from '../adapters/orders/service_date_start_flow';
import './OrderWorkbenchV2Drawer.css';
import '../pages/OrdersPage.css';
import { historicalAdoptionEvidenceClient } from '../api/orders/historical_adoption_evidence_client';
import type { HistoricalOrderAdoptionEvidence } from '../api/orders/historical_adoption_evidence_schemas';
import {
  historicalServiceAccountingClient,
  type HistoricalServiceAccountingQuery,
} from '../api/orders/historical_service_accounting_client';
import { orderCoreStageProjectionClient } from '../api/orders/order_core_stage_projection_client';
import type {
  CoreStageBranchType,
  CoreStageCode,
  CoreStageProjection,
  OrderCoreStageTimeline,
} from '../api/orders/order_core_stage_projection_schemas';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { OrderConflictError } from '../api/orders/order_query_errors';
import type { AssignmentPlan, OrderDetail, OrderTerms } from '../api/orders/order_query_schemas';
import { coreStageSubstatusLabel } from '../adapters/orders/order_core_stage_projection_adapter';
import type { OrderSummaryCardViewModel } from '../adapters/orders/order_summary_adapter';
import { ContractExternalSigningActions } from './ContractExternalSigningActions';
import { OrderAssignmentPlanPanel } from './OrderAssignmentPlanPanel';
import { OrderCandidateContactStatusPanel } from './OrderCandidateContactStatusPanel';
import { OrderCandidateQueryPanel } from './OrderCandidateQueryPanel';
import { OrderMultiCaregiverPlanPanel } from './OrderMultiCaregiverPlanPanel';
import { defaultMatchingFilterPolicy, type MatchingFilterPolicy } from '../api/scheduling/matching_candidate_workflow_client';
import { OrderFormalRecommendationPanel } from './OrderFormalRecommendationPanel';
import { OrderIntakeRepairPanel } from './OrderIntakeRepairPanel';
import { OrderAutomaticCompletionStatus } from './OrderAutomaticCompletionStatus';
import { ServiceArrangementDepositGate } from './ServiceArrangementDepositGate';
import { OrderServiceDatesPanel } from './OrderServiceDatesPanel';
import { OrderWorkbenchV2OwnerContext } from './OrderWorkbenchV2OwnerContext';
import { OrderCancellationPanel } from './OrderCancellationPanel';
import { OrderControlledReopenPanel } from './OrderControlledReopenPanel';
import { OrderActualStartPanel } from './OrderActualStartPanel';
import { CandidateInquiryDialog } from './CandidateInquiryDialog';

interface OrderWorkbenchV2DrawerProps {
  caseNo: string;
  branchType: CoreStageBranchType;
  summary?: OrderSummaryCardViewModel;
  workbenchScope?: OrderWorkbenchScope;
  homeNavigationRequest?: number;
  onClose: () => void;
  onObserved?: () => void;
}

type ReadState<T> =
  | { status: 'loading' }
  | { status: 'ready'; data: T }
  | { status: 'error'; message: string }
  | { status: 'skipped' };

type HistoricalRestartState =
  | { status: 'idle'; message: null }
  | { status: 'applying'; message: null }
  | { status: 'completed'; message: string }
  | { status: 'error'; message: string };

const WORK_GROUPS = [
  { id: 'intake', title: '確認客戶與服務需求', description: '確認基本服務需求；待補資料與可先辦事項分開處理。', stages: ['intake_validation'] },
  { id: 'matching', title: '尋找月嫂與詢問意願', description: '新增人選、分開寄送訂單資訊，再記錄初步接案意願。', stages: ['matching_pool', 'caregiver_line_delivery', 'caregiver_willingness_reply'] },
  { id: 'recommendation', title: '推薦月嫂給客戶確認', description: '工會選定推薦人選，核對月嫂正式方案意願，再送交客戶確認接受或拒絕。', stages: ['formal_recommendation'] },
  { id: 'contracts', title: '辦理契約與簽署', description: '下載未簽署的客戶與月嫂契約，送交外部平台簽署後，分別回收簽署文件。', stages: ['external_signing_dispatch', 'external_signing_completion'] },
  { id: 'service', title: '確認服務日期與排班', description: '先儲存服務日期，再確認雙方安排；條件齊備後自動排班。', stages: ['confirmed_service_dates', 'formal_service', 'service_completion'] },
] as const;
type WorkGroup = typeof WORK_GROUPS[number]['id'];

const SERVICE_WORK_VIEWS = [
  { id: 'dates', label: '設定服務日期' },
  { id: 'assignment', label: '確認排班' },
] as const;
type ServiceWorkView = typeof SERVICE_WORK_VIEWS[number]['id'];

function workGroupStatus(
  stages: readonly { status: string }[],
): '已完成' | '可辦理' | '需要處理' | '等待資料' {
  if (stages.length > 0 && stages.every((stage) => stage.status === 'completed')) return '已完成';
  if (stages.some((stage) => stage.status === 'blocked')) return '需要處理';
  if (stages.some((stage) => stage.status === 'not_started' || stage.status === 'in_progress')) return '可辦理';
  if (stages.some((stage) => stage.status === 'completed')) return '可辦理';
  return '等待資料';
}


const loading = <T,>(): ReadState<T> => ({ status: 'loading' });

function errorMessage(error: unknown): string {
  if (error instanceof OrderConflictError) {
    const missingField: Record<string, string> = {
      order_terms_start_date_required: '約定服務開始日',
      order_terms_service_days_required: '服務天數',
      order_terms_service_hours_per_day_required: '每日服務時數',
      order_terms_floor_fee_required: '樓層加給總額',
    };
    if (missingField[error.code]) return `尚未填寫${missingField[error.code]}，目前無法開啟完整服務條件。`;
  }
  return error instanceof Error && error.message.trim()
    ? error.message.trim()
    : '正式唯讀資料查詢失敗';
}

function timelineForCase(
  page: Awaited<ReturnType<typeof orderCoreStageProjectionClient.getCoreStageTimelines>>,
  caseNo: string,
): OrderCoreStageTimeline {
  const exact = page.items.filter((item) => item.case_no === caseNo);
  if (exact.length !== 1) throw new Error(`正式十三階段查詢未唯一命中案件 ${caseNo}`);
  return exact[0]!;
}

function historicalCurrentOwnerStage(timeline: OrderCoreStageTimeline): CoreStageProjection | null {
  const code = timeline.historical_current_owner_stage_code ?? null;
  if (code === null) return null;
  const stage = timeline.core_stages.find((item) => item.code === code);
  if (!stage) throw new Error('historical current owner stage 不存在於正式十三階段投影。');
  if (stage.source.owner === 'Historical Orders') {
    throw new Error('immutable historical baseline 不得冒充目前正式 owner stage。');
  }
  return stage;
}

function evidencePeriod(evidence: HistoricalOrderAdoptionEvidence): string {
  if (evidence.source_period_availability === 'unavailable') return '來源服務期間未保留';
  return `${evidence.source_start_date ?? '開始日未保留'} → ${evidence.source_end_date ?? '結束日未保留'}`;
}

export const OrderWorkbenchV2Drawer: FC<OrderWorkbenchV2DrawerProps> = ({
  caseNo,
  branchType,
  summary,
  workbenchScope = 'in_progress',
  homeNavigationRequest = 0,
  onClose,
  onObserved,
}) => {
  const requestSequence = useRef(0);
  const staffIdentity = useStaffIdentityLabels();
  const [refreshRevision, setRefreshRevision] = useState(0);
  const [serviceDatesCalculationRevision, setServiceDatesCalculationRevision] = useState(() => new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('recalculate') === '1' ? 1 : 0);
  const [factsRefreshing, setFactsRefreshing] = useState(true);
  const [timeline, setTimeline] = useState<ReadState<OrderCoreStageTimeline>>(loading);
  const [detail, setDetail] = useState<ReadState<OrderDetail>>(loading);
  const [terms, setTerms] = useState<ReadState<OrderTerms>>(loading);
  const [assignmentPlan, setAssignmentPlan] = useState<ReadState<AssignmentPlan>>(loading);
  const [historicalEvidence, setHistoricalEvidence] = useState<ReadState<HistoricalOrderAdoptionEvidence>>(
    () => branchType === 'historical' ? loading<HistoricalOrderAdoptionEvidence>() : { status: 'skipped' },
  );
  const [historicalAccounting, setHistoricalAccounting] = useState<ReadState<HistoricalServiceAccountingQuery>>(
    () => branchType === 'historical' ? loading<HistoricalServiceAccountingQuery>() : { status: 'skipped' },
  );
  const [historicalRestart, setHistoricalRestart] = useState<HistoricalRestartState>({ status: 'idle', message: null });
  const [selectedGroup, setSelectedGroup] = useState<WorkGroup | null>(() => new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('work') === 'service' ? 'service' : null);
  const [visitedGroups, setVisitedGroups] = useState<WorkGroup[]>([]);
  const [addingCandidates, setAddingCandidates] = useState(false);
  const [candidateAddState, setCandidateAddState] = useState({ dirty: false, busy: false });
  const [candidateContactState, setCandidateContactState] = useState({ dirty: false, busy: false });
  const [matchingView, setMatchingView] = useState<'candidates' | 'multi'>('candidates');
  const [multiOpened, setMultiOpened] = useState(false);
  const [multiBusy, setMultiBusy] = useState(false);
  const [multiFilters, setMultiFilters] = useState<MatchingFilterPolicy>(() => ({ ...defaultMatchingFilterPolicy }));
  const [recommendationState, setRecommendationState] = useState({ dirty: false, busy: false });
  const [recommendedCandidateId, setRecommendedCandidateId] = useState<number | undefined>();
  const [focusedCandidateId, setFocusedCandidateId] = useState<number | undefined>();
  const [selectedServiceView, setServiceView] = useState<ServiceWorkView | null>(null);
  const [historicalArrangementPending, setHistoricalArrangementPending] = useState(false);
  const pageHeadingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => { pageHeadingRef.current?.focus(); }, [caseNo]);
  const [replacementRequest, setReplacementRequest] = useState(0);
  const [serviceConfirmationState, setServiceConfirmationState] = useState({ dirty: false, busy: false });
  const [depositBusy, setDepositBusy] = useState(false);
  const [operation, setOperation] = useState<'cancellation' | 'reopen' | 'actual-start' | null>(null);
  const [operationBusy, setOperationBusy] = useState(false);
  const [editingCompletedDates, setEditingCompletedDates] = useState(false);
  useEffect(() => { setEditingCompletedDates(false); }, [caseNo]);
  const operationDialogRef = useRef<HTMLDialogElement>(null);
  const headerActionRef = useRef<HTMLButtonElement>(null);
  const caseOperation = operation === 'cancellation';
  useEffect(() => {
    if (!caseOperation) return;
    const dialog = operationDialogRef.current!;
    dialog.showModal();
    return () => {
      dialog.close();
      headerActionRef.current?.focus();
    };
  }, [caseOperation]);
  const datesPending = useSyncExternalStore(
    (listener) => orderMutationFlowStore.subscribe(listener),
    () => serviceDatesNeedCompletion(caseNo),
  );
  const operationBusyRef = useRef(false);
  const onOperationBusyChange = useCallback((busy: boolean) => {
    operationBusyRef.current = busy;
    setOperationBusy(busy);
  }, []);
  const refreshFacts = useCallback(() => {
    setRefreshRevision((revision) => revision + 1);
    onObserved?.();
  }, [onObserved]);
  const { requestLeave, pending: leavePending } = useUnsavedNavigation();
  const guardedClose = useCallback(() => {
    if (!operationBusyRef.current) requestLeave(onClose);
  }, [onClose, requestLeave]);

  useEffect(() => {
    const requestId = requestSequence.current + 1;
    requestSequence.current = requestId;
    const controller = new AbortController();
    const current = () => !controller.signal.aborted && requestSequence.current === requestId;
    setFactsRefreshing(true);
    let pendingReads = branchType === 'historical' ? 6 : 4;
    const finished = () => {
      pendingReads -= 1;
      if (pendingReads === 0 && current()) setFactsRefreshing(false);
    };

    if (refreshRevision === 0) {
      setTimeline(loading());
      setDetail(loading());
      setTerms(loading());
      setAssignmentPlan(loading());
      setHistoricalEvidence(branchType === 'historical' ? loading() : { status: 'skipped' });
      setHistoricalAccounting(branchType === 'historical' ? loading() : { status: 'skipped' });
      setHistoricalRestart({ status: 'idle', message: null });

    }

    void orderCoreStageProjectionClient.getCoreStageTimelines({
      page_size: 20,
      lifecycle_scope: 'all',
      case_no_search: caseNo,
    }, { signal: controller.signal })
      .then((page) => { if (current()) setTimeline({ status: 'ready', data: timelineForCase(page, caseNo) }); })
      .catch((error) => { if (current()) setTimeline({ status: 'error', message: errorMessage(error) }); })
      .finally(finished);

    void ordersQueryClient.getOrderDetail(caseNo, { signal: controller.signal })
      .then((data) => { if (current()) setDetail({ status: 'ready', data }); })
      .catch((error) => { if (current()) setDetail({ status: 'error', message: errorMessage(error) }); })
      .finally(finished);

    void ordersQueryClient.getOrderTerms(caseNo, { signal: controller.signal })
      .then((data) => { if (current()) setTerms({ status: 'ready', data }); })
      .catch((error) => { if (current()) setTerms({ status: 'error', message: errorMessage(error) }); })
      .finally(finished);

    void ordersQueryClient.getAssignmentPlan(caseNo, { signal: controller.signal })
      .then((data) => { if (current()) setAssignmentPlan({ status: 'ready', data }); })
      .catch((error) => { if (current()) setAssignmentPlan({ status: 'error', message: errorMessage(error) }); })
      .finally(finished);

    if (branchType === 'historical') {
      void historicalServiceAccountingClient.query(caseNo)
        .then((data) => { if (current()) setHistoricalAccounting({ status: 'ready', data }); })
        .catch((error) => { if (current()) setHistoricalAccounting({ status: 'error', message: errorMessage(error) }); })
        .finally(finished);
      void historicalAdoptionEvidenceClient.queryByCase(caseNo, { signal: controller.signal })
        .then((data) => { if (current()) setHistoricalEvidence({ status: 'ready', data }); })
        .catch((error) => { if (current()) setHistoricalEvidence({ status: 'error', message: errorMessage(error) }); })
        .finally(finished);
    }

    return () => {
      controller.abort();
      if (requestSequence.current === requestId) requestSequence.current += 1;
    };
  }, [branchType, caseNo, refreshRevision]);

  const restartHistoricalOrderIntoNormalFlow = async () => {
    if (branchType !== 'historical' || historicalRestart.status === 'applying') return;
    setHistoricalRestart({ status: 'applying', message: null });
    try {
      const query = await historicalServiceAccountingClient.queryPrecisionRestart(caseNo);
      if (query.blockers.length > 0) {
        throw new Error(`目前不可重啟正常流程：${query.blockers.join('、')}`);
      }
      const preview = await historicalServiceAccountingClient.previewPrecisionRestart(caseNo);
      const receipt = await historicalServiceAccountingClient.applyPrecisionRestart(
        preview,
        '工會人員從案件處理頁 選擇重啟正常流程',
      );
      if (receipt.lifecycle_status !== '訂單成立') {
        throw new Error('重啟後狀態不是正常「訂單成立」，已停止後續操作。');
      }
      const observed = await ordersQueryClient.getOrderDetail(caseNo);
      if (observed.order_status !== '訂單成立') {
        throw new Error('重啟收據已回傳，但正式案件回讀尚未觀察到「訂單成立」。');
      }
      setDetail({ status: 'ready', data: observed });
      setHistoricalRestart({
        status: 'completed',
        message: receipt.replayed
          ? '此案件先前已重啟正常流程；已接續到服務日期精算。'
          : '已重啟正常流程並正式回讀；已接續到服務日期精算。',
      });
      setServiceView('dates');
      openGroup('service');
      setServiceDatesCalculationRevision((revision) => revision + 1);
      refreshFacts();
    } catch (error) {
      setHistoricalRestart({ status: 'error', message: errorMessage(error) });
    }
  };

  const blockers = timeline.status === 'ready'
    ? timeline.data.core_stages.flatMap((stage) => stage.blockers.map((notice) => ({
      key: `${stage.code}:${notice.code}`,
      stageCode: stage.code,
      stage: stage.label,
      message: notice.message,
    })))
    : [];
  const warnings = timeline.status === 'ready'
    ? timeline.data.core_stages.flatMap((stage) => stage.warnings.map((notice) => ({
      key: `${stage.code}:${notice.code}`,
      stageCode: stage.code,
      stage: stage.label,
      message: notice.message,
    })))
    : [];
  const currentHistoricalOwner = timeline.status === 'ready' && branchType === 'historical'
    ? historicalCurrentOwnerStage(timeline.data)
    : null;
  const terminalStatus = timeline.status === 'ready' && ['訂單完成', '訂單取消', '歷史訂單－服務完成', '歷史訂單－帳務完成'].includes(timeline.data.lifecycle_status);
  const completedService = timeline.status === 'ready' && timeline.data.lifecycle_status === '訂單完成';
  const showCompletion = timeline.status === 'ready' && ['訂單完成', '歷史訂單－服務完成', '歷史訂單－帳務完成'].includes(timeline.data.lifecycle_status);
  const completionStage = timeline.status === 'ready' ? timeline.data.core_stages.find(stage => stage.code === 'service_completion') : undefined;
  const contractStage = timeline.status === 'ready' ? timeline.data.core_stages.find(stage => stage.code === 'external_signing_completion') : undefined;
  const depositStage = timeline.status === 'ready' ? timeline.data.core_stages.find(stage => stage.code === 'deposit_settlement') : undefined;
  const actualStartActionLabel = assignmentPlan.status === 'ready' && assignmentPlan.data.assignments.some((assignment) => assignment.assignment_id !== null)
    ? '更正開始日並重排' : '確認／更正實際開始日';
  const currentBranch = timeline.status === 'ready' ? timeline.data.branch_type : branchType;
  const intakeOrderStatus = timeline.status === 'ready'
    ? timeline.data.lifecycle_status
    : detail.status === 'ready' ? detail.data.order_status : null;
  const currentStageCode: CoreStageCode | null = timeline.status === 'ready'
    ? timeline.data.current_core_stage_code
    : null;
  const suggestedServiceView: ServiceWorkView = currentStageCode === 'formal_service'
    ? 'assignment' : currentStageCode === 'service_completion' ? 'assignment' : 'dates';
  const serviceView = selectedServiceView ?? suggestedServiceView;
  useEffect(() => {
    if (timeline.status === 'ready') setServiceView((previous) => previous === suggestedServiceView ? null : previous);
  }, [timeline.status, suggestedServiceView]);
  const suggestedGroup = showCompletion || ['deposit_settlement', 'client_settlement', 'staff_payout'].includes(currentStageCode ?? '')
    ? 'service' : terminalStatus ? 'intake' : WORK_GROUPS.find((group) => (group.stages as readonly string[]).includes(currentStageCode ?? ''))?.id ?? 'intake';
  const activeGroup = selectedGroup ?? suggestedGroup;
  useEffect(() => {
    if (timeline.status === 'ready') setSelectedGroup((previous) => previous === suggestedGroup ? null : previous);
  }, [timeline.status, suggestedGroup]);
  useEffect(() => {
    if (timeline.status === 'ready') setVisitedGroups((previous) => previous.includes(activeGroup) ? previous : [...previous, activeGroup]);
  }, [timeline.status, activeGroup]);
  const groupDefinition = WORK_GROUPS.find((group) => group.id === activeGroup)!;
  const groupTitle = showCompletion && activeGroup === 'service' && !editingCompletedDates ? '服務完工' : groupDefinition.title;
  const openGroup = (group: WorkGroup) => {
    setVisitedGroups((previous) => Array.from(new Set([...previous, activeGroup, group])));
    setSelectedGroup(group === suggestedGroup ? null : group);
  };
  const navigationLocked = operationBusy || historicalRestart.status === 'applying' || caseOperation || addingCandidates
    || candidateAddState.busy || candidateContactState.busy || recommendationState.busy || multiBusy
    || serviceConfirmationState.busy || depositBusy;
  const previousHomeRequest = useRef(homeNavigationRequest);
  useEffect(() => {
    if (previousHomeRequest.current === homeNavigationRequest) return;
    previousHomeRequest.current = homeNavigationRequest;
    if (!navigationLocked) guardedClose();
  }, [homeNavigationRequest, navigationLocked, guardedClose]);
  const currentSummary = summary?.id === caseNo ? summary : undefined;
  const summaryReadError = detail.status === 'error' ? '讀取失敗' : '讀取中';
  const clientName = detail.status === 'ready' ? detail.data.client_name || '未登錄姓名'
    : currentSummary ? currentSummary.clientName || '未登錄姓名' : summaryReadError;
  const plannedStart = detail.status === 'ready' ? detail.data.start_date ?? '尚未設定'
    : currentSummary ? currentSummary.startDate ?? '尚未設定' : summaryReadError;
  const actualStart = detail.status === 'ready' ? detail.data.actual_start_date ?? '尚未確認'
    : currentSummary ? currentSummary.actualStartDate ?? '尚未確認' : summaryReadError;
  const serviceVolume = detail.status === 'ready'
    ? `${detail.data.service_days} 日 · 每日 ${detail.data.service_hours_per_day} 小時`
    : currentSummary ? currentSummary.serviceDays === null ? '待補服務天數' : `${currentSummary.serviceDays} 日` : summaryReadError;
  const assignedStaff = assignmentPlan.status === 'ready'
    ? assignmentPlan.data.assignments.length === 0 ? '尚未正式指派'
      : assignmentPlan.data.assignments.map(segment => staffIdentity.label(segment.staff_id, detail.status === 'ready' && (detail.data.staff_id === segment.staff_id || assignmentPlan.data.assignments.length === 1) ? detail.data.staff_name : undefined)).join('、')
    : assignmentPlan.status === 'loading' ? '讀取服務指派中…' : '正式指派暫時無法取得';

  const serviceDateWorkspace = <>
                <nav className="service-arrangement-steps" aria-label="服務安排步驟">
                  {SERVICE_WORK_VIEWS.map((view, index) => <button type="button" key={view.id} aria-current={serviceView === view.id ? 'step' : undefined} disabled={navigationLocked || factsRefreshing} onClick={() => setServiceView(view.id)}><span>{index + 1}</span>{view.label}</button>)}
                </nav>
                <h3 className="order-case-service-title">{completedService ? (serviceView === 'dates' ? '設定服務日期' : '確認排班') : serviceView === 'dates' && assignmentPlan.status === 'ready' && assignmentPlan.data.assignments.length > 0 ? '現行服務日期' : serviceView === 'assignment' ? '客戶與月嫂確認排班' : SERVICE_WORK_VIEWS.find(view => view.id === serviceView)!.label}</h3>
                <div hidden={serviceView !== 'dates' && serviceView !== 'assignment'}>
                <OrderServiceDatesPanel
                  caseNo={caseNo}
                  completedCorrection={completedService}
                  view={serviceView === 'assignment' ? 'arrangement' : 'dates'}
                  onOpenArrangement={() => setServiceView('assignment')}
                  onOpenDates={() => setServiceView('dates')}
                  onArrangementPendingChange={setHistoricalArrangementPending}
                  calculationRevision={serviceDatesCalculationRevision}
                  projectionRevision={refreshRevision}
                  currentAssignmentPlan={assignmentPlan.status === 'ready' ? assignmentPlan.data : null}
                  onBusyChange={onOperationBusyChange}
                  onObserved={refreshFacts}
                  onOpenActualStart={() => {
                    setOperation('actual-start');
                  }}
                />
                </div>
  </>;

  return (
    <div className="order-case-page" role="region" aria-label={`案件 ${caseNo}`}>
      <header className="order-case-header">
        <button type="button" className="order-case-back" disabled={navigationLocked} onClick={guardedClose}>← 返回待辦看板</button>
        <div className="order-case-heading-row">
          <div><p className="order-case-eyebrow">案件 {caseNo}</p><h1 ref={pageHeadingRef} tabIndex={-1}>案件處理</h1></div>
          <div className="order-case-header-actions">
            <span className="order-case-lifecycle">{intakeOrderStatus ?? '讀取案件中'}</span>
            {timeline.status === 'ready' && currentBranch === 'cancelled'
              ? <OrderControlledReopenPanel key={caseNo} caseNo={caseNo} onObserved={refreshFacts} onBusyChange={onOperationBusyChange} />
              : timeline.status === 'ready' && !terminalStatus && <button ref={headerActionRef} type="button" className="order-v2-danger" disabled={navigationLocked || factsRefreshing} onClick={() => setOperation('cancellation')}>取消訂單</button>}
          </div>
        </div>
        <p className="order-case-purpose">依目前進度接續工作；需要的訂單與服務資料會顯示在各辦理事項中。</p>
        <div className="order-case-summary-row">
        <div className="order-case-context">
          <span><small>客戶</small>{clientName}</span>
          <span><small>約定服務開始日</small>{plannedStart}</span>
          <span><small>實際開始</small>{actualStart}</span>
          <span><small>服務量</small>{serviceVolume}</span>
          <span><small>服務月嫂</small>{assignedStaff}</span>
          {branchType === 'historical' && historicalEvidence.status === 'ready' && <span><small>歷史匯入期間</small>{evidencePeriod(historicalEvidence.data)}</span>}
        </div>
        <OrderWorkbenchV2OwnerContext caseNo={caseNo} revision={refreshRevision} placement="header" disabled={navigationLocked} completedService={completedService} />
        {!showCompletion && <a aria-disabled={navigationLocked || undefined} onClick={(event) => { if (navigationLocked) event.preventDefault(); }} href={`#finance?tab=client-receipts&case_no=${encodeURIComponent(caseNo)}&from=workbench`}>查看本案帳務 →</a>}
        <a className="order-case-profile-link" aria-disabled={navigationLocked || undefined} onClick={(event) => { if (navigationLocked) event.preventDefault(); }} href={`#clients?case=${encodeURIComponent(caseNo)}&from=workbench`}>編輯客戶與訂單資料 →</a>
        </div>
      </header>
      {factsRefreshing && <p role="status" className="order-case-read-status">正在更新案件資料…</p>}
      {timeline.status === 'error' && <div role="alert" className="order-v2-drawer-error">案件進度暫時無法取得，請稍後重新整理。</div>}
      <div className="order-case-workspace">
        <aside className="order-case-stepper" aria-label="案件辦理事項">
          <h2>辦理事項</h2><p>依目前進度開啟工作，也可切換其他事項。</p>
          <ol>
            {WORK_GROUPS.map((group, index) => (
              <li key={group.id}>
                <button type="button" disabled={navigationLocked} className={group.id === activeGroup ? 'selected' : ''} aria-current={group.id === activeGroup ? 'page' : undefined} onClick={() => openGroup(group.id)}>
                  <span className="order-case-step-number">{index + 1}</span>
                  <span><strong>{showCompletion && group.id === 'service' ? '服務完工' : group.title}</strong>{timeline.status === 'ready' && <small>{workGroupStatus(timeline.data.core_stages.filter((stage) => (group.stages as readonly string[]).includes(stage.code)))}</small>}</span>
                </button>
              </li>
            ))}
          </ol>
          {timeline.status === 'ready' && !terminalStatus && workbenchScope === 'in_progress' && <details className="order-case-progress"><summary>查看十三階段紀錄</summary><ol>{timeline.data.core_stages.map((stage) => <li key={stage.code}><span>{stage.ordinal}. {stage.label}</span><small>{stage.status === 'completed' ? '已完成' : stage.status === 'blocked' ? '需要處理' : stage.status === 'unavailable' ? '暫無資料' : '可繼續辦理'}</small></li>)}</ol></details>}
        </aside>
        <div className="order-case-task-body">
          <div className="order-case-work-heading"><div><p className="order-case-eyebrow">{terminalStatus ? '案件紀錄' : activeGroup === suggestedGroup ? '目前待辦' : '其他辦理事項'}</p><h2>{groupTitle}</h2>{activeGroup !== 'intake' && !showCompletion && <p>{groupDefinition.description}</p>}</div>
            {activeGroup !== suggestedGroup && <button type="button" disabled={navigationLocked} onClick={() => openGroup(suggestedGroup)}>{showCompletion ? '返回服務完工' : '回到目前待辦'}</button>}
          </div>
          {showCompletion && activeGroup !== 'service' && <section className="order-case-review-note" aria-label="完工案件操作說明">
            <p role="status">本案服務已完成，「{groupDefinition.title}」已結束，不能從此重新辦理。</p>
            <p>請使用上方「查看相關資料與通知紀錄」查閱既有紀錄。</p>
          </section>}
          {!terminalStatus && (activeGroup === 'service' || visitedGroups.includes('service')) && <div hidden={activeGroup !== 'service'} className="service-arrangement-deposit-slot"><fieldset disabled={operationBusy || factsRefreshing}>
            <ServiceArrangementDepositGate caseNo={caseNo} revision={refreshRevision} onCommitted={refreshFacts} onBusyChange={setDepositBusy} />
          </fieldset></div>}
          {activeGroup === 'intake' && <>
            {branchType === 'historical' && currentBranch !== 'cancelled' && intakeOrderStatus !== null && <OrderIntakeRepairPanel caseNo={caseNo} orderStatus={intakeOrderStatus} onChanged={refreshFacts} summaryHref={`#clients?case=${encodeURIComponent(caseNo)}&field=intake&from=workbench`} />}
          </>}
        {currentBranch === 'normal' && workbenchScope === 'in_progress' && !terminalStatus && (
          <section className={`order-v2-drawer-current-task${activeGroup === 'contracts' ? ' contract-workspace' : ''}`} aria-label="案件工作內容">
            {[...blockers, ...warnings].filter((notice) => (groupDefinition.stages as readonly string[]).includes(notice.stageCode)).map((notice) => <p className="order-case-review-note" key={notice.key} role="status">{notice.key !== 'intake_validation:orders_terms_missing' && <><strong>{notice.stage}</strong>：</>}{notice.message}</p>)}
            <fieldset disabled={operationBusy || factsRefreshing}>
              {(activeGroup === 'intake' || visitedGroups.includes('intake')) && <div hidden={activeGroup !== 'intake'}>
              {intakeOrderStatus !== null && (
                <OrderIntakeRepairPanel
                  caseNo={caseNo}
                  orderStatus={intakeOrderStatus}
                  onChanged={refreshFacts}
                  remainingServiceIssues={blockers.filter((notice) => notice.stageCode === 'intake_validation').map((notice) => notice.message)}
                  repairServiceTime={terms.status !== 'loading'}
                  summaryHref={`#clients?case=${encodeURIComponent(caseNo)}&field=intake&from=workbench`}
                />
              )}
              </div>}
              {(activeGroup === 'matching' || visitedGroups.includes('matching')) && <div hidden={activeGroup !== 'matching'}>
                <nav className="order-case-subnav" aria-label="尋找月嫂方式">
                  <button type="button" aria-pressed={matchingView === 'candidates'} disabled={navigationLocked} onClick={() => setMatchingView('candidates')}>候選月嫂</button>
                  <button type="button" aria-pressed={matchingView === 'multi'} disabled={navigationLocked} onClick={() => { setMultiOpened(true); setMatchingView('multi'); }}>多月嫂分段</button>
                </nav>
                <div hidden={matchingView !== 'candidates'}>
                <OrderCandidateContactStatusPanel caseNo={caseNo} revision={refreshRevision} onObserved={() => { setSelectedGroup('matching'); refreshFacts(); }}
                  presentation="workbench" focusedCandidateId={focusedCandidateId} onEditStateChange={setCandidateContactState} onAddCandidates={() => setAddingCandidates(true)}
                  onOpenCustomerConfirmation={id => { setRecommendedCandidateId(id); openGroup('recommendation'); }} />
                {addingCandidates && <CandidateInquiryDialog title="新增候選月嫂" wide busy={candidateAddState.busy}
                  onClose={() => { requestLeave(() => setAddingCandidates(false)); }}>
                  <div className="candidate-inquiry-dialog-content"><p>查詢後，點選人選旁的「加入候選池」。已加入的人選會標示「已加入」；加入候選池尚未形成排班。</p>
                    <OrderCandidateQueryPanel caseNo={caseNo} presentation="workbench" includeMultiCaregiver={false} onEditStateChange={setCandidateAddState}
                      onPoolReadback={ids => { setFocusedCandidateId(ids?.[0]); refreshFacts(); }} />
                  </div>
                </CandidateInquiryDialog>}
                </div>
                {multiOpened && <div hidden={matchingView !== 'multi'}>
                  <h3>多月嫂分段</h3>
                  <p>指定 2–4 位月嫂，查詢可銜接的服務日期。採用組合後會建立正式推薦方案，再接續各段意願與客戶確認。</p>
                  {datesPending && <p role="status">開始日與服務日期尚未完成接續確認，請先到「服務安排 → 設定服務日期」完成，再規劃分段。</p>}
                  <fieldset disabled={multiBusy || datesPending} aria-label="分段媒合篩選條件"><legend>媒合篩選條件</legend>
                    {([
                      ['region', '服務地區'], ['cooking', '下廚料理'],
                      ['preferred_service_days', '服務方式'], ['daily_service_hours', '每日服務時數'],
                    ] as const).map(([key, label]) => <label key={key}><input type="checkbox" checked={multiFilters[key]}
                      onChange={() => setMultiFilters(value => ({ ...value, [key]: !value[key] }))} />{label}</label>)}
                  </fieldset>
                  <fieldset disabled={datesPending}>
                    <OrderMultiCaregiverPlanPanel caseNo={caseNo} filters={multiFilters} onBusyChange={setMultiBusy}
                      onObserved={() => { refreshFacts(); openGroup('recommendation'); }} />
                  </fieldset>
                </div>}
              </div>}
              {(activeGroup === 'recommendation' || visitedGroups.includes('recommendation')) && <div hidden={activeGroup !== 'recommendation'}>
                {datesPending && <p role="status">開始日與服務日期尚未完成接續確認，請先到「服務安排 → 設定服務日期」完成；目前不能以舊日期繼續推薦確認。</p>}
                <fieldset disabled={datesPending}>
                <OrderFormalRecommendationPanel
                  caseNo={caseNo}
                  revision={refreshRevision}
                  assignmentExists={assignmentPlan.status === 'ready' && assignmentPlan.data.assignments.length > 0}
                  initialCandidateId={recommendedCandidateId}
                  openReplacementRequest={replacementRequest}
                  onOpenCandidates={() => openGroup('matching')}
                  onEditStateChange={setRecommendationState}
                  onObserved={refreshFacts}
                  onOpenServiceDates={() => {
                    setServiceView('dates');
                    openGroup('service');
                  }}
                />
                </fieldset>
              </div>}
              {(activeGroup === 'contracts' || visitedGroups.includes('contracts')) && <div hidden={activeGroup !== 'contracts'}>
                <ContractExternalSigningActions caseNo={caseNo} revision={refreshRevision} onCommitted={() => { setSelectedGroup('contracts'); refreshFacts(); }} onOpenServiceDates={() => { setServiceView('dates'); openGroup('service'); }} onOpenRecommendation={() => { setReplacementRequest(value => value + 1); openGroup('recommendation'); }} />
              </div>}
              {(activeGroup === 'service' || visitedGroups.includes('service')) && <div hidden={activeGroup !== 'service'}>
                {serviceDateWorkspace}
                <div hidden={serviceView !== 'assignment'}>
                {datesPending && <p role="status">服務日期尚未完成保存或回讀，請先到「設定服務日期」接續；目前不能以舊日期辦理自動排班。</p>}
                <fieldset disabled={datesPending}>
                <OrderAssignmentPlanPanel caseNo={caseNo} revision={refreshRevision} historicalArrangementPending={historicalArrangementPending} onObserved={refreshFacts} onEditStateChange={setServiceConfirmationState}
                  contractReady={contractStage && contractStage.status !== 'unavailable' ? contractStage.status === 'completed' : undefined}
                  depositReady={depositStage && depositStage.status !== 'unavailable' ? depositStage.status === 'completed' : undefined}
                  onOpenDates={() => setServiceView('dates')} onOpenRecommendation={() => openGroup('recommendation')} />
                </fieldset>
                </div>

              </div>}
            </fieldset>
          </section>
        )}
        {showCompletion && timeline.status === 'ready' && <section hidden={activeGroup !== 'service'} className="order-v2-drawer-section order-case-completion" aria-label="服務完工摘要">
          <div className="service-arrangement-status-notice ready"><h3>服務已完成</h3><p>服務履約已完成，收付款與結算可至帳務中心查閱。</p></div>
          {editingCompletedDates ? serviceDateWorkspace : <>
          <dl className="order-case-completion-facts">
            <div><dt>服務期間</dt><dd>{detail.status === 'ready' ? `${detail.data.actual_start_date ?? '尚未記錄開始日'} ～ ${detail.data.actual_end_date ?? '尚未記錄結束日'}` : summaryReadError}</dd></div>
            <div><dt>服務月嫂</dt><dd>{assignedStaff}</dd></div>
            <div><dt>實際完成時間</dt><dd>{completionStage?.occurred_at ? new Intl.DateTimeFormat('zh-TW', { timeZone: 'Asia/Taipei', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(completionStage.occurred_at)) : '未保留完工時間'}</dd></div>
            <div><dt>完工狀態</dt><dd>服務已完成</dd></div>
          </dl>
          <div className="order-case-completion-finance" aria-label="結算摘要">
            {(['client_settlement', 'staff_payout'] as const).map(code => {
              const stage = timeline.data.core_stages.find(item => item.code === code);
              return <p key={code}><span>{code === 'client_settlement' ? '客戶款項' : '月嫂款項'}</span><strong>{stage ? coreStageSubstatusLabel(stage.substatus_code) : '結算狀態暫時無法取得'}</strong></p>;
            })}
          </div>
          </>}
          <div className="order-case-action-row"><a aria-disabled={navigationLocked || undefined} onClick={(event) => { if (navigationLocked) event.preventDefault(); }} href={`#finance?tab=client-receipts&case_no=${encodeURIComponent(caseNo)}&from=workbench`}>查看本案帳務 →</a>{completedService && <button type="button" disabled={navigationLocked || factsRefreshing} onClick={() => {
            setServiceView('dates');
            setEditingCompletedDates(current => !current);
          }}>{editingCompletedDates ? '返回完工摘要' : '更正完工服務日期'}</button>}</div>
        </section>}
        {currentBranch === 'historical' && (intakeOrderStatus === '歷史訂單－未服務' || intakeOrderStatus === '歷史訂單－服務中') && (
          <section  className={`order-v2-drawer-current-task${activeGroup === 'contracts' ? ' contract-workspace' : ''}`} aria-label="歷史訂單精算天數重啟">
            <header>
              <span>歷史案件操作</span>
              <div>
                <h3>重啟精算天數</h3>
                <p>先退出歷史分支並回到「訂單成立」；成功後即可沿用正式日期精算、媒合與排班流程。</p>
              </div>
            </header>
            <fieldset disabled={operationBusy || factsRefreshing}>
              <button
                type="button"
                className="btn-secondary-action"
                data-control-id="orders.intake-repair.historical-restart"
                onClick={() => void restartHistoricalOrderIntoNormalFlow()}
              >
                前往重啟正常流程
              </button>
            </fieldset>
          </section>
        )}

          {(activeGroup === 'service' || visitedGroups.includes('service')) && <div hidden={activeGroup !== 'service'}>
        {branchType === 'historical' && <section className="order-v2-drawer-section order-case-wide"><h2>歷史服務資料</h2><p>以下為匯入時保留的資料，不代表目前已確認的服務安排。</p>
          {historicalEvidence.status === 'error' && <p role="alert">歷史服務資料暫時無法取得：{historicalEvidence.message}</p>}
          {historicalAccounting.status === 'error' && <p role="alert">歷史帳務資料暫時無法取得：{historicalAccounting.message}</p>}
          {historicalEvidence.status === 'ready' && <p>歷史服務期間：{evidencePeriod(historicalEvidence.data)}</p>}
          {historicalEvidence.status === 'ready' && <p>歷史記載月嫂：{historicalEvidence.data.paired_staff.map((staff) => staffIdentity.label(staff.staff_id, staff.staff_name)).join('、') || '未登錄'}</p>}
          {historicalAccounting.status === 'ready' && <p>歷史約定天數：{historicalAccounting.data.contracted_service_days} 日；月嫂：{historicalAccounting.data.assignments.map((item) => staffIdentity.label(item.staff_id, item.staff_name)).join('、') || '未登錄'}</p>}
        </section>}
            {!completedService && <section className="order-v2-drawer-section service-arrangement-related-actions" aria-label="服務安排相關操作">
              {!terminalStatus && currentBranch !== 'cancelled' && (currentBranch === 'historical' || (assignmentPlan.status === 'ready' && assignmentPlan.data.assignments.length > 0)) && <p>開始日有變動時，請先核對各段排班的調整結果。</p>}
              <div className="order-case-action-row">
                {!terminalStatus && currentBranch !== 'cancelled' && operation !== 'actual-start' && (currentBranch === 'historical' || (assignmentPlan.status === 'ready' && assignmentPlan.data.assignments.length > 0 && serviceView !== 'dates')) && <button type="button" disabled={navigationLocked || factsRefreshing} onClick={() => setOperation('actual-start')}>{actualStartActionLabel}</button>}
                {currentBranch === 'cancelled' && <button type="button" disabled={navigationLocked || factsRefreshing} onClick={() => setOperation('cancellation')}>補登取消服務事實</button>}
              </div>
              {operationBusy && <p role="status">操作結果或正式回讀尚未確認，暫時不能關閉或切換操作。</p>}
              {!terminalStatus && operation === 'actual-start' && (currentBranch === 'historical' || (assignmentPlan.status === 'ready' && assignmentPlan.data.assignments.length > 0)) && <OrderActualStartPanel key={caseNo} caseNo={caseNo} autoLoad onObserved={(actualStartOperation) => {
                setServiceView(actualStartOperation === 'reschedule' ? 'assignment' : 'dates');
                openGroup('service');
                if (actualStartOperation === 'date_only') setServiceDatesCalculationRevision((revision) => revision + 1);
                refreshFacts();
              }} onBusyChange={onOperationBusyChange} onOpenServiceDates={() => { setServiceView('dates'); openGroup('service'); }} />}
              {!showCompletion && <OrderAutomaticCompletionStatus caseNo={caseNo} revision={refreshRevision} onObserved={refreshFacts} />}
              {currentBranch === 'normal' && !terminalStatus && <button type="button" disabled={navigationLocked || factsRefreshing} onClick={() => { setReplacementRequest(value => value + 1); openGroup('recommendation'); }}>服務前更換月嫂 →</button>}

            </section>}
          </div>}
          {terminalStatus && !showCompletion && <section className="order-v2-drawer-section"><h2>案件處理紀錄</h2><p>此案件目前為「{intakeOrderStatus}」，可切換辦理事項查閱既有資料與紀錄。</p></section>}
          {currentBranch === 'historical' && currentHistoricalOwner && <section className="order-v2-drawer-section"><h2>歷史案件目前進度</h2><p>{currentHistoricalOwner.label}：{coreStageSubstatusLabel(currentHistoricalOwner.substatus_code)}</p></section>}
          {historicalRestart.message && <p role={historicalRestart.status === 'error' ? 'alert' : 'status'}>{historicalRestart.message}</p>}
        </div>
      </div>
      <dialog ref={operationDialogRef} className="order-case-operation-dialog" aria-labelledby="order-case-operation-title" onCancel={(event) => {
        event.preventDefault();
        if (!operationBusyRef.current && !leavePending) requestLeave(() => setOperation(null));
      }}>
        <header className="order-case-dialog-heading"><h2 id="order-case-operation-title">{currentBranch === 'cancelled' ? '補登取消服務事實' : '取消訂單'}</h2>
          <button type="button" disabled={operationBusy} onClick={() => requestLeave(() => setOperation(null))}>返回案件處理</button>
        </header>
        {operationBusy && <p role="status">操作結果或正式回讀尚未確認，請先完成確認再返回案件。</p>}
        {operation === 'cancellation' && <OrderCancellationPanel key={caseNo} caseNo={caseNo} onObserved={refreshFacts} onBusyChange={onOperationBusyChange} />}
      </dialog>
    </div>
  );
};

export default OrderWorkbenchV2Drawer;

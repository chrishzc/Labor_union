import type { OrderWorkbenchScope } from '../api/orders/order_core_stage_projection_client';
import { useCallback, useEffect, useRef, useState, type FC } from 'react';
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
import type { AssignmentPlan, OrderDetail, OrderTerms } from '../api/orders/order_query_schemas';
import { coreStageDefinition, coreStageSubstatusLabel } from '../adapters/orders/order_core_stage_projection_adapter';
import { ContractExternalSigningActions } from './ContractExternalSigningActions';
import { OrderAssignmentPlanPanel } from './OrderAssignmentPlanPanel';
import { OrderCandidateContactStatusPanel } from './OrderCandidateContactStatusPanel';
import { OrderCandidateQueryPanel } from './OrderCandidateQueryPanel';
import { OrderFormalRecommendationPanel } from './OrderFormalRecommendationPanel';
import { OrderIntakeRepairPanel } from './OrderIntakeRepairPanel';
import { OrderServiceCompletionActions } from './OrderServiceCompletionActions';
import { OrderServiceDatesPanel } from './OrderServiceDatesPanel';
import { OrderTermsMutationPanel } from './OrderTermsMutationPanel';
import { OrderWorkbenchV2OwnerContext } from './OrderWorkbenchV2OwnerContext';
import { ServiceBeforeReplacementActions } from './ServiceBeforeReplacementActions';
import { OrderCancellationPanel } from './OrderCancellationPanel';
import { OrderControlledReopenPanel } from './OrderControlledReopenPanel';
import { OrderActualStartPanel } from './OrderActualStartPanel';
import { OrderInformationSheets } from './OrderInformationSheets';
import { OrderContractPreview } from './OrderContractPreview';

interface OrderWorkbenchV2DrawerProps {
  caseNo: string;
  branchType: CoreStageBranchType;
  workbenchScope?: OrderWorkbenchScope;
  onClose: () => void;
  onObserved?: () => void;
  initialView?: 'work' | 'data';
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

type DrawerTab = 'work' | 'data' | 'changes';

const WORK_GROUPS = [
  { id: 'intake', title: '進件資料', description: '確認基本服務需求；待補資料與可先辦事項分開處理。', stages: ['intake_validation'] },
  { id: 'matching', title: '候選與詢問', description: '選擇月嫂、分開提供訂單資訊，再記錄接案意願。', stages: ['matching_pool', 'caregiver_line_delivery', 'caregiver_willingness_reply'] },
  { id: 'recommendation', title: '推薦確認', description: '將願意承接的人選推薦給客戶，確認服務方案。', stages: ['formal_recommendation'] },
  { id: 'contracts', title: '契約與文件', description: '核對客戶與月嫂契約，辦理送簽與簽回文件。', stages: ['external_signing_dispatch', 'external_signing_completion'] },
  { id: 'service', title: '服務安排', description: '確認實際服務日期、排班與完工；換人及日期異動另由案件異動辦理。', stages: ['confirmed_service_dates', 'formal_service', 'service_completion'] },
  { id: 'finance', title: '收款與結算', description: '查看訂金、客戶收款及月嫂付款；核銷統一由帳務中心處理。', stages: ['deposit_settlement', 'client_settlement', 'staff_payout'] },
] as const;
type WorkGroup = typeof WORK_GROUPS[number]['id'];


const loading = <T,>(): ReadState<T> => ({ status: 'loading' });

function errorMessage(error: unknown): string {
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
  workbenchScope = 'in_progress',
  onClose,
  onObserved,
  initialView = 'work',
}) => {
  const requestSequence = useRef(0);
  const [refreshRevision, setRefreshRevision] = useState(0);
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
  const [drawerTab, setDrawerTab] = useState<DrawerTab>(initialView);
  const [selectedGroup, setSelectedGroup] = useState<WorkGroup | null>(null);
  const [visitedGroups, setVisitedGroups] = useState<WorkGroup[]>([]);
  const [matchingView, setMatchingView] = useState<'list' | 'search' | 'information'>('list');
  const [informationKind, setInformationKind] = useState<1 | 2>(1);
  const [serviceView, setServiceView] = useState<'dates' | 'assignment' | 'completion'>('dates');
  const [contractView, setContractView] = useState<'overview' | 'signing'>('signing');
  const [signingOpened, setSigningOpened] = useState(true);
  const pageHeadingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => { pageHeadingRef.current?.focus(); }, [caseNo]);
  const [replacementExpanded, setReplacementExpanded] = useState(false);
  const [operation, setOperation] = useState<'cancellation' | 'reopen' | 'actual-start' | null>(null);
  const [operationBusy, setOperationBusy] = useState(false);
  const operationBusyRef = useRef(false);
  const onOperationBusyChange = useCallback((busy: boolean) => {
    operationBusyRef.current = busy;
    setOperationBusy(busy);
  }, []);
  const refreshFacts = useCallback(() => {
    setRefreshRevision((revision) => revision + 1);
    onObserved?.();
  }, [onObserved]);
  const guardedClose = useCallback(() => {
    if (!operationBusyRef.current) onClose();
  }, [onClose]);

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
      setReplacementExpanded(false);
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
          ? '此案件先前已重啟正常流程；正式回讀已確認為「訂單成立」。請返回待辦看板後繼續。'
          : '已重啟正常流程並回讀確認為「訂單成立」。請返回待辦看板後繼續日期／媒合／排班。',
      });
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
  const currentBranch = timeline.status === 'ready' ? timeline.data.branch_type : branchType;
  const intakeOrderStatus = timeline.status === 'ready'
    ? timeline.data.lifecycle_status
    : detail.status === 'ready' ? detail.data.order_status : null;
  const currentStageCode: CoreStageCode | null = timeline.status === 'ready'
    ? timeline.data.current_core_stage_code
    : null;
  const currentStage = currentStageCode === null ? null : coreStageDefinition(currentStageCode);
  const currentGroup = terminalStatus ? 'finance' : WORK_GROUPS.find((group) => (group.stages as readonly string[]).includes(currentStageCode ?? ''))?.id ?? 'intake';
  const activeGroup = selectedGroup ?? currentGroup;
  useEffect(() => {
    if (timeline.status === 'ready') setSelectedGroup((previous) => previous ?? currentGroup);
  }, [timeline.status, currentGroup]);
  const groupDefinition = WORK_GROUPS.find((group) => group.id === activeGroup)!;
  const openGroup = (group: WorkGroup) => {
    setVisitedGroups((previous) => Array.from(new Set([...previous, activeGroup, group])));
    setSelectedGroup(group);
  };
  const navigationLocked = operationBusy || historicalRestart.status === 'applying';
  const selectedTitle = drawerTab === 'data' ? '訂單與服務資料' : drawerTab === 'changes' ? '案件異動' : '案件處理';

  return (
    <div className="order-case-page" role="region" aria-label={`案件 ${caseNo}`}>
      <header className="order-case-header">
        <button type="button" className="order-case-back" disabled={navigationLocked} onClick={guardedClose}>← 返回待辦看板</button>
        <div className="order-case-heading-row">
          <div><p className="order-case-eyebrow">案件 {caseNo}</p><h1 ref={pageHeadingRef} tabIndex={-1}>{selectedTitle}</h1></div>
          <span className="order-case-lifecycle">{intakeOrderStatus ?? '讀取案件中'}</span>
        </div>
        <p className="order-case-purpose">{drawerTab === 'data' ? '查閱客戶、約定條款與服務安排，不在此頁執行案件流程。' : drawerTab === 'changes' ? '選擇需要辦理的異動，核對影響後再確認。' : '選擇要辦理的工作；目前進度提供指引，不限制可獨立處理的事項。'}</p>
        <div className="order-case-context">
          <span><small>客戶</small>{detail.status === 'ready' ? detail.data.client_name || '未登錄' : '讀取中'}</span>
          <span><small>約定服務</small>{terms.status === 'ready' ? terms.data.terms.planned_start_date : '讀取中'}</span>
          <span><small>服務量</small>{terms.status === 'ready' ? `${terms.data.terms.service_days} 日 · 每日 ${terms.data.terms.service_hours_per_day} 小時` : '讀取中'}</span>
        </div>
        <nav className="order-case-view-nav" aria-label="案件頁面">
          {([['work', '案件處理'], ['data', '訂單與服務資料'], ['changes', '案件異動']] as const).map(([id, label]) => (
            <button type="button" key={id} aria-current={drawerTab === id ? 'page' : undefined} disabled={navigationLocked} onClick={() => setDrawerTab(id)}>{label}</button>
          ))}
        </nav>
      </header>
      {factsRefreshing && <p role="status" className="order-case-read-status">正在更新案件資料…</p>}
      {timeline.status === 'error' && <div role="alert" className="order-v2-drawer-error">案件進度暫時無法取得，請稍後重新整理。</div>}
      <div hidden={drawerTab !== 'work'} className="order-case-workspace">
        <aside className="order-case-stepper" aria-label="案件分步流程">
          <h2>辦理事項</h2><p>依工作切換，不會變更案件進度。</p>
          <ol>
            {WORK_GROUPS.map((group, index) => (
              <li key={group.id}>
                <button type="button" disabled={navigationLocked} className={group.id === activeGroup ? 'selected' : ''} aria-current={group.id === activeGroup ? 'page' : undefined} onClick={() => openGroup(group.id)}>
                  <span className="order-case-step-number">{index + 1}</span>
                  <span><strong>{group.title}</strong>{timeline.status === 'ready' && group.id === currentGroup && <small>目前待辦</small>}</span>
                </button>
              </li>
            ))}
          </ol>
          {timeline.status === 'ready' && !terminalStatus && workbenchScope === 'in_progress' && <details className="order-case-progress"><summary>查看十三階段進度</summary><ol>{timeline.data.core_stages.map((stage) => <li key={stage.code}><span>{stage.ordinal}. {stage.label}</span><small>{stage.status === 'completed' ? '已完成' : stage.code === currentStageCode ? '目前待辦' : stage.status === 'unavailable' ? '暫無資料' : '尚未完成'}</small></li>)}</ol></details>}
        </aside>
        <div className="order-case-task-body">
          <div className="order-case-work-heading"><div><p className="order-case-eyebrow">{currentStage ? `目前進度：${currentStage.label}` : '案件工作區'}</p><h2>{groupDefinition.title}</h2><p>{groupDefinition.description}</p></div></div>
        {currentBranch === 'normal' && workbenchScope === 'in_progress' && !terminalStatus && (
          <section className="order-v2-drawer-current-task" aria-label="案件工作內容">
            {[...blockers, ...warnings].filter((notice) => (groupDefinition.stages as readonly string[]).includes(notice.stageCode)).map((notice) => <p className="order-case-review-note" key={notice.key} role="status"><strong>{notice.stage}</strong>：{notice.message}</p>)}
            <fieldset disabled={operationBusy || factsRefreshing}>
              {(activeGroup === 'intake' || visitedGroups.includes('intake')) && <div hidden={activeGroup !== 'intake'}>
              {intakeOrderStatus !== null && (
                <OrderIntakeRepairPanel
                  caseNo={caseNo}
                  orderStatus={intakeOrderStatus}
                  onChanged={refreshFacts}
                />
              )}
              {terms.status === 'ready' && (
                <OrderTermsMutationPanel caseNo={caseNo} query={terms.data} onObserved={refreshFacts} />
              )}
              </div>}
              {(activeGroup === 'matching' || visitedGroups.includes('matching')) && <div hidden={activeGroup !== 'matching'}>
                <nav className="order-case-subnav" aria-label="候選與詢問工作"><button type="button" aria-pressed={matchingView === 'list'} onClick={() => setMatchingView('list')}>候選月嫂</button><button type="button" aria-pressed={matchingView === 'search'} onClick={() => setMatchingView('search')}>新增候選月嫂</button><button type="button" aria-pressed={matchingView === 'information'} onClick={() => setMatchingView('information')}>訂單資訊預覽</button></nav>
                <div hidden={matchingView !== 'list'}><OrderCandidateContactStatusPanel caseNo={caseNo} revision={refreshRevision} onObserved={refreshFacts} onPreviewInformation={(kind) => { setInformationKind(kind); setMatchingView('information'); }} /></div>
                <div hidden={matchingView !== 'search'}><h3>尋找合適的月嫂</h3><p>查詢後勾選人選，加入同一份候選清單。</p><OrderCandidateQueryPanel caseNo={caseNo} onPoolReadback={refreshFacts} /></div>
                {matchingView === 'information' && <OrderInformationSheets caseNo={caseNo} initialKind={informationKind} assignments={assignmentPlan.status === 'ready' ? assignmentPlan.data.assignments : []} onOpenCandidates={() => setMatchingView('list')} />}
              </div>}
              {(activeGroup === 'recommendation' || visitedGroups.includes('recommendation')) && <div hidden={activeGroup !== 'recommendation'}>
                <OrderFormalRecommendationPanel caseNo={caseNo} onObserved={refreshFacts} />
              </div>}
              {(activeGroup === 'contracts' || visitedGroups.includes('contracts')) && <div hidden={activeGroup !== 'contracts'}>
                <nav className="order-case-subnav" aria-label="契約工作"><button type="button" aria-pressed={contractView === 'overview'} onClick={() => setContractView('overview')}>契約欄位預覽</button><button type="button" aria-pressed={contractView === 'signing'} onClick={() => { setSigningOpened(true); setContractView('signing'); }}>下載與簽回</button></nav>
                <div hidden={contractView !== 'overview'}><OrderContractPreview caseNo={caseNo} /></div>
                {signingOpened && <div hidden={contractView !== 'signing'}><ContractExternalSigningActions caseNo={caseNo} onCommitted={refreshFacts} /></div>}
              </div>}
              {(activeGroup === 'service' || visitedGroups.includes('service')) && <div hidden={activeGroup !== 'service'}>
                <nav className="order-case-subnav" aria-label="服務工作"><button type="button" aria-pressed={serviceView === 'dates'} onClick={() => setServiceView('dates')}>確認日期</button><button type="button" aria-pressed={serviceView === 'assignment'} onClick={() => setServiceView('assignment')}>正式排班</button><button type="button" aria-pressed={serviceView === 'completion'} onClick={() => setServiceView('completion')}>完工確認</button></nav>
                <div hidden={serviceView !== 'dates'}>
                <OrderServiceDatesPanel caseNo={caseNo} onObserved={refreshFacts} />
                </div><div hidden={serviceView !== 'assignment'}>
                <OrderAssignmentPlanPanel caseNo={caseNo} onObserved={refreshFacts} onOpenReplacement={() => { setDrawerTab('changes'); setReplacementExpanded(true); }} />
                </div><div hidden={serviceView !== 'completion'}>{detail.status === 'ready' && (
                <OrderServiceCompletionActions caseNo={caseNo} orderStatus={detail.data.order_status} onCompleted={refreshFacts} />
              )}</div></div>}
              {activeGroup === 'finance' && <div className="order-case-document-grid"><article><h3>訂金與客戶收款</h3><p>核對訂金、各期款與退款。正常收款依銀行流水核銷。</p><a href={`#finance?tab=client-receipts&case_no=${encodeURIComponent(caseNo)}`}>查看本案客戶收款 →</a></article><article><h3>月嫂付款與結案</h3><p>前往帳務頁選擇月嫂，再核對應付與付款紀錄。</p><a href="#finance?tab=staff-payables">前往月嫂付款 →</a></article><p className="order-case-review-note">銀行流水如需人工核對，請在帳務頁預覽更正內容後確認核銷。</p></div>}
            </fieldset>
          </section>
        )}
        {terminalStatus && timeline.status === 'ready' && <section className="order-v2-drawer-section" aria-label="結算狀態">
          <h3>結算狀態</h3>
          {timeline.data.core_stages.filter((stage) => stage.code === 'client_settlement' || stage.code === 'staff_payout').map((stage) => <p key={stage.code}>{stage.label}：{coreStageSubstatusLabel(stage.substatus_code)}</p>)}
        </section>}
        {currentBranch === 'historical' && (intakeOrderStatus === '歷史訂單－未服務' || intakeOrderStatus === '歷史訂單－服務中') && (
          <section  className="order-v2-drawer-current-task" aria-label="歷史訂單精算天數重啟">
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

          {terminalStatus && <section className="order-v2-drawer-section"><h2>案件處理紀錄</h2><p>此案件目前為「{intakeOrderStatus}」，請由左側流程查閱各步驟狀態，或前往訂單與服務資料。</p></section>}
          {currentBranch === 'historical' && currentHistoricalOwner && <section className="order-v2-drawer-section"><h2>歷史案件目前進度</h2><p>{currentHistoricalOwner.label}：{coreStageSubstatusLabel(currentHistoricalOwner.substatus_code)}</p></section>}
          {historicalRestart.message && <p role={historicalRestart.status === 'error' ? 'alert' : 'status'}>{historicalRestart.message}</p>}
        </div>
      </div>
      <div hidden={drawerTab !== 'data'} className="order-case-data-grid">
        <section className="order-v2-drawer-section"><h2>客戶與訂單</h2>
          {detail.status === 'error' && <p role="alert">客戶與訂單資料暫時無法取得。</p>}
          {detail.status === 'ready' && <dl className="order-case-facts">
            <div><dt>客戶</dt><dd>{detail.data.client_name || '未登錄'}</dd></div>
            <div><dt>訂單狀態</dt><dd>{detail.data.order_status}</dd></div>
            <div><dt>身分類別</dt><dd>{detail.data.identity_status ?? '未登錄'}</dd></div>
            <div><dt>實際開始</dt><dd>{detail.data.actual_start_date ?? '尚未確認'}</dd></div>
          </dl>}
        </section>
        <section className="order-v2-drawer-section"><h2>約定服務</h2>
          {terms.status === 'error' && <p role="alert">約定服務資料暫時無法取得。</p>}
          {terms.status === 'ready' && <dl className="order-case-facts">
            <div><dt>計畫開始</dt><dd>{terms.data.terms.planned_start_date}</dd></div>
            <div><dt>約定天數</dt><dd>{terms.data.terms.service_days} 日</dd></div>
            <div><dt>每日時數</dt><dd>{terms.data.terms.service_hours_per_day} 小時</dd></div>
          </dl>}
        </section>
        <section className="order-v2-drawer-section order-case-wide"><h2>已安排的月嫂與服務日期</h2>
          {assignmentPlan.status === 'loading' && <p>讀取服務安排中…</p>}
          {assignmentPlan.status === 'error' && <p role="alert">服務安排暫時無法取得。</p>}
          {assignmentPlan.status === 'ready' && assignmentPlan.data.assignments.length === 0 && <p>尚未正式安排月嫂。</p>}
          {assignmentPlan.status === 'ready' && assignmentPlan.data.assignments.map((segment) => <article className="order-case-assignment" key={`${segment.sequence}:${segment.staff_id}`}>
            <strong>第 {segment.sequence} 段 · 月嫂編號 {segment.staff_id}</strong>
            <span>{segment.assigned_start_date} ～ {segment.assigned_end_date}</span><span>{segment.official_service_dates.length} 個正式服務日</span>
          </article>)}
        </section>
        <div className="order-case-wide"><OrderWorkbenchV2OwnerContext caseNo={caseNo} revision={refreshRevision} /></div>
        {branchType === 'historical' && <section className="order-v2-drawer-section order-case-wide"><h2>歷史服務資料</h2><p>以下為匯入時保留的資料，不代表目前已確認的服務安排。</p>
          {historicalEvidence.status === 'error' && <p role="alert">歷史服務資料暫時無法取得：{historicalEvidence.message}</p>}
          {historicalAccounting.status === 'error' && <p role="alert">歷史帳務資料暫時無法取得：{historicalAccounting.message}</p>}
          {historicalEvidence.status === 'ready' && <p>歷史服務期間：{evidencePeriod(historicalEvidence.data)}</p>}
          {historicalEvidence.status === 'ready' && <p>歷史記載月嫂：{historicalEvidence.data.paired_staff.map((staff) => staff.staff_name).join('、') || '未登錄'}</p>}
          {historicalAccounting.status === 'ready' && <p>歷史約定天數：{historicalAccounting.data.contracted_service_days} 日；月嫂：{historicalAccounting.data.assignments.map((item) => item.staff_name).join('、') || '未登錄'}</p>}
        </section>}
      </div>
      <section hidden={drawerTab !== 'changes'} className="order-v2-drawer-section order-case-changes">
        <h2>選擇要辦理的異動</h2><p>異動會影響案件或服務安排；請先確認對象，再檢查變更內容。</p>
        {(!terminalStatus || currentBranch === 'cancelled') ? <>
            <div className="order-v2-drawer-actions">
              <button type="button" disabled={operationBusy || factsRefreshing} onClick={() => setOperation('cancellation')}>取消／補登取消服務事實</button>
              {currentBranch === 'cancelled' && (
                <button type="button" disabled={operationBusy || factsRefreshing} onClick={() => setOperation('reopen')}>受控重開取消案件</button>
              )}
              {currentBranch !== 'cancelled' && (
                <button type="button" disabled={operationBusy || factsRefreshing} onClick={() => setOperation('actual-start')}>確認／更正實際開始日</button>
              )}
            </div>
            {operationBusy && <p role="status">操作結果或正式回讀尚未確認，暫時不能關閉或切換操作。</p>}
            {operation === 'cancellation' && <OrderCancellationPanel key={caseNo} caseNo={caseNo} onObserved={refreshFacts} onBusyChange={onOperationBusyChange} />}
            {operation === 'reopen' && <OrderControlledReopenPanel key={caseNo} caseNo={caseNo} onObserved={refreshFacts} onBusyChange={onOperationBusyChange} />}
            {operation === 'actual-start' && <OrderActualStartPanel key={caseNo} caseNo={caseNo} onObserved={refreshFacts} onBusyChange={onOperationBusyChange} />}
            {currentBranch === 'normal' && !terminalStatus && detail.status === 'ready' && (
              <div className="order-v2-more-action-workflow" data-surface-id="orders.service-before-replacement.entry">
                {!replacementExpanded ? (
                  <button
                    type="button"
                    className="btn-secondary-action"
                    data-control-id="orders.service-before-replacement.open"
                    onClick={() => setReplacementExpanded(true)}
                  >
                    服務前更換月嫂
                  </button>
                ) : (
                  <ServiceBeforeReplacementActions
                    caseNo={caseNo}
                    onCommitted={refreshFacts}
                    onSubstitutionReferral={() => {
                      window.location.hash = `#scheduling?tab=leave_sub&case_no=${encodeURIComponent(caseNo)}`;
                    }}
                  />
                )}
              </div>
            )}

        </> : <p>此案件目前沒有可在這裡辦理的異動。</p>}
        {branchType === 'historical' && currentBranch !== 'cancelled' && intakeOrderStatus !== null && <OrderIntakeRepairPanel caseNo={caseNo} orderStatus={intakeOrderStatus} onChanged={refreshFacts} />}
      </section>
    </div>
  );
};

export default OrderWorkbenchV2Drawer;

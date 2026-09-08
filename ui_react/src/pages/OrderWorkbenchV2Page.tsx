import { loadAllCoreStageTimelines } from '../api/orders/load_all_core_stage_timelines';
/**
 * File: OrderWorkbenchV2Page.tsx
 * Description: 待辦看板 Beta。唯讀使用正式十三核心階段 query contract，不以前端推導階段或計數。
 */
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FC,
} from 'react';
import './OrdersPage.css';
import './OrderTrackerPage.css';
import './OrderWorkbenchV2Page.css';
import { OrderAssignmentPlanPanel } from '../components/OrderAssignmentPlanPanel';
import { OrderCandidateContactStatusPanel } from '../components/OrderCandidateContactStatusPanel';
import { OrderCandidateQueryPanel } from '../components/OrderCandidateQueryPanel';
import { ContractExternalSigningActions } from '../components/ContractExternalSigningActions';
import { OrderFormalRecommendationPanel } from '../components/OrderFormalRecommendationPanel';
import { OrderServiceDatesPanel } from '../components/OrderServiceDatesPanel';
import { OrderWorkbenchV2Drawer } from '../components/OrderWorkbenchV2Drawer';
import {
  type OrderWorkbenchScope,
  type OrderCoreStageProjectionQueryParams,
} from '../api/orders/order_core_stage_projection_client';
import type {
  CoreStageBranchType,
  CoreStageCode,
  CoreStageSubstatusCode,
} from '../api/orders/order_core_stage_projection_schemas';
import {
  loadAllOrderSummaries,
  ordersQueryClient,
} from '../api/orders/order_query_client';
import {
  adaptOrderCoreStageTimelinePage,
  CORE_STAGE_DEFINITIONS,
  coreStageDefinition,
  ORDER_CORE_STAGE_PROJECTION_UNAVAILABLE,
  type OrderCoreStageWorkbenchViewModel,
} from '../adapters/orders/order_core_stage_projection_adapter';
import {
  adaptOrderSummaryPage,
  type OrderSummaryCardViewModel,
} from '../adapters/orders/order_summary_adapter';

const WORKBENCH_SCOPES: readonly OrderWorkbenchScope[] = ['in_progress', 'completed', 'cancelled'];
const SCOPE_LABELS: Record<OrderWorkbenchScope, string> = {
  in_progress: '進行中訂單', completed: '完成訂單', cancelled: '取消訂單',
};

function summaryUnavailableMessage(summaryLoading: boolean, summaryQueryFailed: boolean): string {
  if (summaryLoading) return '正式案件摘要載入中。';
  if (summaryQueryFailed) return '正式案件摘要查詢失敗；目前只顯示十三階段投影。';
  return '未取得與此案件編號相符的正式摘要。';
}

function coreQueryErrorMessage(error: unknown): string {
  const detail = error instanceof Error && error.message.trim()
    ? error.message.trim()
    : '無法取得訂單資料';
  return `${ORDER_CORE_STAGE_PROJECTION_UNAVAILABLE} 原因：${detail}`;
}

export const OrderWorkbenchV2Page: FC = () => {
  const [view, setView] = useState<OrderCoreStageWorkbenchViewModel | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summaryIndex, setSummaryIndex] = useState<ReadonlyMap<string, OrderSummaryCardViewModel>>(
    () => new Map(),
  );
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [summaryQueryFailed, setSummaryQueryFailed] = useState(false);
  const [selectedStage, setSelectedStage] = useState<CoreStageCode | null>(null);
  const [selectedSubstatus, setSelectedSubstatus] = useState<CoreStageSubstatusCode | null>(null);
  const [workbenchScope, setWorkbenchScope] = useState<OrderWorkbenchScope>('in_progress');
  const [search, setSearch] = useState('');
  const [onlyBlocked, setOnlyBlocked] = useState(false);
  const [onlyWarning, setOnlyWarning] = useState(false);
  const [projectionRefreshKey, setProjectionRefreshKey] = useState(0);
  const [selectedDrawer, setSelectedDrawer] = useState<{
    caseNo: string;
    branchType: CoreStageBranchType;
  } | null>(null);
  const requestSequence = useRef(0);
  const lastResolvedQuery = useRef<string | null>(null);
  const refreshProjection = useCallback(() => setProjectionRefreshKey((current) => current + 1), []);
  const closeDrawer = useCallback(() => {
    setSelectedDrawer(null);
    refreshProjection();
  }, [refreshProjection]);

  const normalizedSearch = search.trim();

  useEffect(() => {
    const requestId = requestSequence.current + 1;
    requestSequence.current = requestId;
    const controller = new AbortController();
    const query: OrderCoreStageProjectionQueryParams = {
      page_size: 200,
      lifecycle_scope: 'all',
      workbench_scope: workbenchScope,
      case_no_search: normalizedSearch || undefined,
      blocker_only: onlyBlocked || undefined,
      warning_only: onlyWarning || undefined,
      stage: workbenchScope === 'in_progress' ? selectedStage ?? undefined : undefined,
      substatus_code:
        workbenchScope === 'in_progress' && selectedSubstatus !== null
          ? selectedSubstatus
          : undefined,
    };

    const queryKey = JSON.stringify(query);
    const readbackRefresh = lastResolvedQuery.current === queryKey;
    setError(null);
    setRefreshing(readbackRefresh);
    if (!readbackRefresh) {
      setLoading(true);
      setView(null);
    }

    void loadAllCoreStageTimelines(query, {
      signal: controller.signal,
    })
      .then((page) => {
        if (controller.signal.aborted || requestSequence.current !== requestId) return;
        const nextView = adaptOrderCoreStageTimelinePage(page, query);
        lastResolvedQuery.current = queryKey;
        setView(nextView);
      })
      .catch((caught) => {
        if (controller.signal.aborted || requestSequence.current !== requestId) return;
        setError(coreQueryErrorMessage(caught));
      })
      .finally(() => {
        if (!controller.signal.aborted && requestSequence.current === requestId) {
          setLoading(false);
          setRefreshing(false);
        }
      });

    return () => controller.abort();
  }, [
    workbenchScope,
    normalizedSearch,
    onlyBlocked,
    onlyWarning,
    projectionRefreshKey,
    selectedStage,
    selectedSubstatus,
  ]);

  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    setSummaryIndex(new Map());
    setSummaryLoading(true);
    setSummaryQueryFailed(false);

    void loadAllOrderSummaries(
      ordersQueryClient.getOrderSummaries.bind(ordersQueryClient),
      { lifecycle_scope: 'all', page_size: 200 },
      { signal: controller.signal },
    )
      .then((data) => {
        if (!alive) return;
        const summaries = adaptOrderSummaryPage(data).items;
        setSummaryIndex(new Map(summaries.map((item) => [item.id, item])));
      })
      .catch(() => {
        if (!alive) return;
        setSummaryIndex(new Map());
        setSummaryQueryFailed(true);
      })
      .finally(() => {
        if (alive) setSummaryLoading(false);
      });

    return () => {
      alive = false;
      controller.abort();
    };
  }, [projectionRefreshKey]);

  const selectedDefinition = selectedStage === null ? null : coreStageDefinition(selectedStage);
  const selectedStageCount = selectedStage === null ? view?.items.length ?? 0 : view?.stageCounts[selectedStage] ?? 0;
  const displayedCount = view?.items.length ?? 0;

  const selectScope = (scope: OrderWorkbenchScope) => {
    setWorkbenchScope(scope);
    setSelectedStage(null);
    setSelectedSubstatus(null);
    setOnlyBlocked(false);
    setOnlyWarning(false);
    setSelectedDrawer(null);
  };

  const selectStage = (stage: CoreStageCode | null) => {
    setSelectedStage(stage);
    setSelectedSubstatus(null);
  };

  return (
    <div className="order-v2-page">
      <header className="page-header-banner orders-page-header">
        <div>
          <h1 className="page-title">📌 待辦看板 <span className="order-v2-beta">Beta</span></h1>
          <p className="page-subtitle">依案件階段查看待辦、追蹤進度與處理工作。</p>
        </div>
        <div className="orders-search-wrapper">
          <label className="orders-search-input-box">
            <span className="orders-search-icon" aria-hidden="true">🔍</span>
            <input
              aria-label="搜尋案件編號"
              value={search}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setSearch(event.target.value)}
              placeholder="搜尋案件編號"
            />
          </label>
          <button className="tracker-reload-button" type="button" disabled={loading || refreshing} onClick={refreshProjection}>
            重新整理
          </button>
        </div>
      </header>

      <nav className="tracker-tabs-stitch order-v2-branch-filters" aria-label="訂單狀態分類">
        {WORKBENCH_SCOPES.map((scope) => (
          <button type="button" key={scope}
            className={`tracker-tab-btn ${workbenchScope === scope ? 'active' : ''}`}
            aria-pressed={workbenchScope === scope} onClick={() => selectScope(scope)}>
            {SCOPE_LABELS[scope]}
          </button>
        ))}
      </nav>

      {workbenchScope === 'in_progress' && (
        <section className="pipeline-stepper-nav order-v2-stage-strip" aria-label="13 個核心訂單階段">
          <button type="button" className={`pipeline-step-pill ${selectedStage === null ? 'active' : ''}`}
            aria-pressed={selectedStage === null} onClick={() => selectStage(null)}>全部進行中</button>
          {CORE_STAGE_DEFINITIONS.map((definition) => (
            <button key={definition.code} type="button"
              className={`pipeline-step-pill ${selectedStage === definition.code ? 'active' : ''}`}
              aria-pressed={selectedStage === definition.code} onClick={() => selectStage(definition.code)}>
              <span className="order-v2-stage-number">{definition.ordinal}</span>
              <span className="order-v2-stage-label">{definition.shortLabel}</span>
              <span className="pipeline-step-badge">{view?.stageCounts[definition.code] ?? 0}</span>
            </button>
          ))}
        </section>
      )}

      <section className="pipeline-stage-section order-v2-results" aria-label="案件工作清單">
      <div className="pipeline-stage-header">
        <div>
          <h2 className="pipeline-stage-title">
            {selectedDefinition ? `${selectedDefinition.ordinal}. ${selectedDefinition.label}` : SCOPE_LABELS[workbenchScope]}
          </h2>
          <p className="pipeline-stage-desc">
            {workbenchScope === 'in_progress'
              ? '查看所有進行中案件，或依作業階段篩選待辦。'
              : workbenchScope === 'completed'
                ? '服務已完成；可查閱案件紀錄，並追蹤客戶與月嫂的結算狀態。'
                : '查閱取消訂單的案件紀錄與後續處理。'}
          </p>
        </div>
{workbenchScope === 'in_progress' && <div className="order-v2-result-filters">
        <label className="tracker-completed-toggle">
          <input type="checkbox" checked={onlyBlocked} onChange={(event: ChangeEvent<HTMLInputElement>) => setOnlyBlocked(event.target.checked)} />
          只看阻塞
        </label>
        <label className="tracker-completed-toggle">
          <input type="checkbox" checked={onlyWarning} onChange={(event: ChangeEvent<HTMLInputElement>) => setOnlyWarning(event.target.checked)} />
          只看提醒
        </label>
      </div>}
        <div className="order-v2-result-count" aria-live="polite">
          顯示 <strong>{displayedCount}</strong>
          <span>／ {selectedStage === null ? displayedCount : selectedStageCount} 筆</span>
        </div>
      </div>
      {workbenchScope === 'in_progress' && selectedStage !== null && (
        <div className="order-v2-subfilters" aria-label="階段子狀態篩選">
          <button
            type="button"
            className={selectedSubstatus === null ? 'active' : ''}
            aria-pressed={selectedSubstatus === null}
            onClick={() => setSelectedSubstatus(null)}
          >
            全部 <strong>{selectedStageCount}</strong>
          </button>
          {(view?.substatusOptions ?? []).map((option) => (
            <button
              type="button"
              key={option.code}
              className={selectedSubstatus === option.code ? 'active' : ''}
              aria-pressed={selectedSubstatus === option.code}
              onClick={() => setSelectedSubstatus(option.code)}
            >
              {option.label} <strong>{option.count}</strong>
            </button>
          ))}
        </div>
      )}

      {summaryQueryFailed && !loading && !error && (
        <div className="order-v2-summary-warning" role="status">
          案件摘要查詢失敗；案件分類仍可查閱，但客戶、日期與月嫂摘要暫時不可用。
        </div>
      )}

      {loading && <div className="order-v2-empty">正在查詢訂單資料…</div>}
      {error && <div className="order-v2-error" role="alert">{error}</div>}
      {!loading && view !== null && (refreshing || error !== null) && (
        <div className="order-v2-summary-warning" role="status">清單更新尚未完成；目前顯示上次內容，案件操作暫停。</div>
      )}
      {!loading && !error && displayedCount === 0 && (
        <div className="stage-empty-state">
          <span className="stage-empty-icon" aria-hidden="true">☕</span>
          <strong className="stage-empty-text">目前沒有符合條件的案件。</strong>
          <span className="stage-empty-hint">{workbenchScope === 'in_progress' ? '可切換作業階段，或調整搜尋與篩選條件。' : '可調整搜尋條件，或切換訂單分類。'}</span>
        </div>
      )}
      {!loading && displayedCount > 0 && (
        <fieldset disabled={refreshing || error !== null} style={{ border: 0, padding: 0, margin: 0 }}>
        <div className="orders-grid order-v2-orders-grid">
          {view?.items.map((item) => {
            const summary = summaryIndex.get(item.id) ?? null;
            const stage = item.currentStage;
            const actionStage = selectedStage ?? stage?.code;
            return (
              <article className="order-card" key={item.id}>
                <div className="order-card-top">
                  <strong className="order-id-badge">{item.id}</strong>
                  <span className={`order-status-pill order-v2-status status-${stage?.status ?? item.branchType}`}>
                    {item.statusLabel}
                  </span>
                </div>

                {summary ? (
                  <div className="order-card-body">
                    <div className="order-client-title"><span aria-hidden="true">👤 </span><span>{summary.clientName.trim() || '客戶姓名未登錄'}</span></div>
                    <div>🪪 身分資格：<span>{summary.identityStatus}</span></div>
                    <div>📅 約定服務：<span>{summary.serviceRange}</span>（{summary.serviceDaysLabel}）</div>
                    {summary.contractAmount !== null && (
                      <div>💰 雇主自付應付額：<strong className="order-id-badge">{summary.contractAmountFormatted}</strong></div>
                    )}
                    <div className="order-doula-box">👩‍🍼 指派月嫂：<strong>{summary.assignedDoulaDisplay}</strong></div>
                  </div>
                ) : (
                  <div className="order-v2-business-summary unavailable" role="note">
                    <strong>案件摘要不可用</strong>
                    <span>{summaryUnavailableMessage(summaryLoading, summaryQueryFailed)}</span>
                  </div>
                )}

                {workbenchScope === 'completed' && (
                  <div className="order-v2-settlement-summary" aria-label="結算狀態">
                    <span>客戶端：{item.clientSettlementLabel}</span>
                    <span>月嫂端：{item.staffSettlementLabel}</span>
                  </div>
                )}
                <details className="order-v2-case-details">
                  <summary>案件狀態與來源</summary>
                  <div className="order-v2-case-meta">
                  <span>Lifecycle：{item.lifecycleStatus}</span>
                  <span>支線：{item.branchLabel}</span>
                  <span>Revision：{item.baseRevision}</span>
                  {stage && <span>目前階段：{stage.label}</span>}
                  {stage && <span>Owner：{stage.owner}</span>}
                  {item.historicalCurrentOwnerStage && (
                    <span>目前正式 owner progression：{item.historicalCurrentOwnerStage.label}</span>
                  )}
                  {stage?.occurred_at && (
                    <span>更新：{new Date(stage.occurred_at).toLocaleString('zh-TW')}</span>
                  )}
                  </div>
                </details>

                {item.blockers.length > 0 && (
                  <div className="order-v2-notice blocked">
                    <strong>阻塞</strong>
                    {item.blockers.map((notice, index) => (
                      <span key={`${notice.id}:${index}`}>{notice.stageLabel}：{notice.message}</span>
                    ))}
                  </div>
                )}
                {item.warnings.length > 0 && (
                  <div className="order-v2-notice warning">
                    <strong>提醒</strong>
                    {item.warnings.map((notice, index) => (
                      <span key={`${notice.id}:${index}`}>{notice.stageLabel}：{notice.message}</span>
                    ))}
                  </div>
                )}
                {stage?.availability_reason && (
                  <div className="order-v2-technical">projection：{stage.availability_reason}</div>
                )}
                <div className="order-card-actions order-v2-card-actions">
                {workbenchScope === 'in_progress' && item.branchType === 'normal' && actionStage === 'matching_pool' && (
                  <OrderCandidateQueryPanel
                    key={item.id}
                    caseNo={item.id}
                    onPoolReadback={refreshProjection}
                  />
                )}
                {workbenchScope === 'in_progress' && item.branchType === 'normal' && (
                  actionStage === 'caregiver_line_delivery'
                  || actionStage === 'caregiver_willingness_reply'
                ) && (
                  <OrderCandidateContactStatusPanel key={item.id} caseNo={item.id} onObserved={refreshProjection} />
                )}
                {workbenchScope === 'in_progress' && item.branchType === 'normal' && actionStage === 'formal_recommendation' && (
                  <OrderFormalRecommendationPanel key={item.id} caseNo={item.id} onObserved={refreshProjection} />
                )}
                {workbenchScope === 'in_progress' && item.branchType === 'normal'
                  && (actionStage === 'caregiver_contract'
                    || actionStage === 'client_contract'
                    || actionStage === 'confirmed_service_dates') && (
                  <ContractExternalSigningActions key={`${item.id}:external-signing`} caseNo={item.id} onCommitted={refreshProjection} />
                )}
                {workbenchScope === 'in_progress' && item.branchType === 'normal' && actionStage === 'confirmed_service_dates' && (
                  <OrderServiceDatesPanel
                    key={`${item.id}:service-dates`}
                    caseNo={item.id}
                    onObserved={refreshProjection}
                  />
                )}
                {workbenchScope === 'in_progress' && item.branchType === 'normal' && actionStage === 'formal_service' && (
                  <OrderAssignmentPlanPanel key={item.id} caseNo={item.id} onObserved={refreshProjection} />
                )}
                <button
                  type="button"
                  className="btn-secondary-action"
                  onClick={() => setSelectedDrawer({ caseNo: item.id, branchType: item.branchType })}
                >
                  {workbenchScope === 'in_progress' ? '開啟案件工作' : '查看案件紀錄'}
                </button>
                </div>
              </article>
            );
          })}
        </div>
        </fieldset>
      )}

      </section>

      {selectedDrawer !== null && (
        <OrderWorkbenchV2Drawer
          key={selectedDrawer.caseNo}
          caseNo={selectedDrawer.caseNo}
          branchType={selectedDrawer.branchType}
          workbenchScope={workbenchScope}
          onClose={closeDrawer}
          onObserved={refreshProjection}
        />
      )}
    </div>
  );
};

export default OrderWorkbenchV2Page;

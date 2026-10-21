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
import { ArrowRight, Search } from 'lucide-react';
import './OrdersPage.css';
import './OrderTrackerPage.css';
import './OrderWorkbenchV2Page.css';
import { OrderWorkbenchV2Drawer } from '../components/OrderWorkbenchV2Drawer';
import { WorkbenchCaseStatistics } from '../components/WorkbenchCaseStatistics';
import { loadCurrentHcmReviewsForCases, type HcmCurrentReview } from '../api/case_import/hcm_resubmission_client';
import {
  orderCoreStageProjectionClient,
  type OrderCoreStageProjectionQueryParams,
} from '../api/orders/order_core_stage_projection_client';
import type {
  CoreStageBranchType,
  CoreStageCode,
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
  formatServiceRange,
  type OrderSummaryCardViewModel,
} from '../adapters/orders/order_summary_adapter';

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

export const OrderWorkbenchV2Page: FC<{ homeNavigationRequest?: number }> = ({ homeNavigationRequest = 0 }) => {
  const [view, setView] = useState<OrderCoreStageWorkbenchViewModel | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summaryIndex, setSummaryIndex] = useState<ReadonlyMap<string, OrderSummaryCardViewModel>>(
    () => new Map(),
  );
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [summaryQueryFailed, setSummaryQueryFailed] = useState(false);
  const [intakeReviews, setIntakeReviews] = useState<ReadonlyMap<string, HcmCurrentReview>>(new Map());
  const [intakeReviewsError, setIntakeReviewsError] = useState(false);
  const [selectedStage, setSelectedStage] = useState<CoreStageCode | null>(null);
  const [search, setSearch] = useState('');
  const [projectionRefreshKey, setProjectionRefreshKey] = useState(0);
  const [selectedDrawer, setSelectedDrawer] = useState<{
    caseNo: string;
    branchType: CoreStageBranchType;
  } | null>(null);
  const requestSequence = useRef(0);
  const [requestedCase, setRequestedCase] = useState(() => new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('case') ?? '');
  const [caseLinkError, setCaseLinkError] = useState<string | null>(null);
  const lastResolvedQuery = useRef<string | null>(null);
  const refreshProjection = useCallback(() => setProjectionRefreshKey((current) => current + 1), []);
  const closeDrawer = useCallback(() => {
    setSelectedDrawer(null);
    setRequestedCase('');
    setCaseLinkError(null);
    if (new URLSearchParams(window.location.hash.split('?')[1] ?? '').has('case')) window.history.replaceState(null, '', '#order-workbench-v2');
    refreshProjection();
  }, [refreshProjection]);
  const previousHomeRequest = useRef(homeNavigationRequest);
  useEffect(() => {
    if (previousHomeRequest.current === homeNavigationRequest) return;
    previousHomeRequest.current = homeNavigationRequest;
    if (selectedDrawer === null) closeDrawer();
  }, [homeNavigationRequest, selectedDrawer, closeDrawer]);

  const normalizedSearch = search.trim().toLocaleLowerCase();

  useEffect(() => {
    if (!requestedCase) return;
    const controller = new AbortController();
    setCaseLinkError(null);
    void orderCoreStageProjectionClient.getCoreStageTimelines({ lifecycle_scope: 'all', case_no_search: requestedCase, page_size: 20 }, { signal: controller.signal })
      .then((page) => {
        if (controller.signal.aborted) return;
        const exact = page.items.filter((item) => item.case_no === requestedCase);
        if (exact.length !== 1) throw new Error('找不到可唯一確認的案件，請重新查詢。');
        setSelectedDrawer({ caseNo: exact[0]!.case_no, branchType: exact[0]!.branch_type });
      })
      .catch((error) => { if (!controller.signal.aborted) setCaseLinkError(error instanceof Error ? error.message : '案件讀取失敗。'); });
    return () => controller.abort();
  }, [requestedCase]);

  useEffect(() => {
    const requestId = requestSequence.current + 1;
    requestSequence.current = requestId;
    const controller = new AbortController();
    const query: OrderCoreStageProjectionQueryParams = {
      page_size: 200,
      lifecycle_scope: 'all',
      workbench_scope: 'in_progress',
      stage: selectedStage ?? undefined,
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
    projectionRefreshKey,
    selectedStage,
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

  useEffect(() => {
    const controller = new AbortController();
    setIntakeReviews(new Map());
    setIntakeReviewsError(false);
    const caseNos = (view?.items ?? []).filter((item) => item.lifecycleStatus === '待補件').map((item) => item.id);
    void loadCurrentHcmReviewsForCases(caseNos, { signal: controller.signal })
      .then((reviews) => {
        if (!controller.signal.aborted) setIntakeReviews(new Map(reviews.map((review) => [review.case_no, review])));
      })
      .catch(() => {
        if (!controller.signal.aborted) setIntakeReviewsError(true);
      });
    return () => controller.abort();
  }, [view]);

  const displayedItems = (view?.items ?? []).filter((item) => {
    if (!normalizedSearch) return true;
    if (item.id.toLocaleLowerCase().includes(normalizedSearch)) return true;
    const clientName = summaryIndex.get(item.id)?.clientName ?? '';
    return clientName.toLocaleLowerCase().includes(normalizedSearch);
  });

  const selectedDefinition = selectedStage === null ? null : coreStageDefinition(selectedStage);
  const selectedStageCount = selectedStage === null ? view?.items.length ?? 0 : view?.stageCounts[selectedStage] ?? 0;
  const displayedCount = displayedItems.length;
  const clearFilters = () => { setSearch(''); setSelectedStage(null); };

  const selectStage = (stage: CoreStageCode | null) => {
    setSelectedStage(stage);
  };

  if (selectedDrawer !== null) return (
    <>
      {error !== null && <div role="alert"><p>案件清單更新失敗，請重新整理後繼續。</p><button type="button" onClick={refreshProjection}>重新整理</button></div>}
      <fieldset disabled={refreshing || error !== null} style={{ border: 0, padding: 0, margin: 0, minWidth: 0, width: '100%' }}>
        <OrderWorkbenchV2Drawer
          key={selectedDrawer.caseNo}
          homeNavigationRequest={homeNavigationRequest}
          caseNo={selectedDrawer.caseNo}
          branchType={selectedDrawer.branchType}
          summary={summaryIndex.get(selectedDrawer.caseNo)}
          workbenchScope="in_progress"
          onClose={closeDrawer}
          onObserved={refreshProjection}
        />
      </fieldset>
    </>
  );

  return (
    <div className="order-v2-page">
      {caseLinkError && <p role="alert">{caseLinkError}</p>}
      <header className="page-header-banner orders-page-header">
        <div>
          <h1 className="page-title">待辦看板</h1>
          <p className="page-subtitle">找到需要處理的案件，從目前步驟接著完成。</p>
        </div>
      </header>

      <details className="order-v2-overview-details">
        <summary>案件受理統計</summary>
        <WorkbenchCaseStatistics refreshKey={projectionRefreshKey} />
      </details>

      <div className="order-v2-overview-details order-v2-stage-overview">
        <h2>查看全部階段與件數</h2>
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
      </div>

        <form className="orders-search-wrapper order-v2-search" onSubmit={(event) => event.preventDefault()} role="search" aria-label="搜尋待辦案件">
          <label className="orders-search-input-box">
            <Search className="orders-search-icon" size={18} aria-hidden="true" />
            <input
              aria-label="搜尋案件編號或姓名"
              value={search}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setSearch(event.target.value)}
              placeholder="搜尋案件編號或姓名"
            />
          </label>
          <button type="submit" className="tracker-reload-button">搜尋</button>
          <button type="button" className="tracker-reload-button order-v2-secondary-button" onClick={clearFilters}>清除篩選</button>
          <button className="tracker-reload-button order-v2-secondary-button" type="button" disabled={loading || refreshing} onClick={refreshProjection}>
            重新整理
          </button>
        </form>

      <section className="pipeline-stage-section order-v2-results" aria-label="案件工作清單">
      <div className="pipeline-stage-header">
        <div>
          <h2 className="pipeline-stage-title">
            {selectedDefinition ? `${selectedDefinition.ordinal}. ${selectedDefinition.label}` : '進行中案件'}
          </h2>
          <p className="pipeline-stage-desc">
            點選案件列，進入案件處理。
          </p>
        </div>
        <div className="order-v2-result-count" aria-live="polite">
          顯示 <strong>{displayedCount}</strong>
          <span>／ {selectedStageCount} 筆</span>
        </div>
      </div>

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
          {(search || selectedStage) && <button type="button" className="tracker-reload-button" onClick={clearFilters}>清除搜尋與篩選</button>}
          <span className="stage-empty-hint">可切換作業階段，或調整搜尋與篩選條件。</span>
        </div>
      )}
      {!loading && displayedCount > 0 && (
        <fieldset disabled={refreshing || error !== null} style={{ border: 0, padding: 0, margin: 0 }}>
        <div className="order-v2-table-wrap" tabIndex={0} role="region" aria-label="待辦案件清單，可橫向捲動">
        <table className="order-v2-table" aria-label="待辦案件清單">
          <thead><tr>
            <th scope="col">案件編號</th>
            <th scope="col">客戶姓名</th>
            <th scope="col">約定服務期間</th>
            <th scope="col">指派月嫂</th>
            <th scope="col">目前待辦</th>
            <th scope="col">提醒</th>
            <th scope="col">操作</th>
          </tr></thead>
          <tbody>
          {displayedItems.map((item) => {
            const summary = summaryIndex.get(item.id) ?? null;
            const stage = item.currentStage;
            const primaryNotice = item.blockers[0] ?? item.warnings[0] ?? null;
            const entryDisabled = refreshing || error !== null;
            const openWork = () => {
              if (!entryDisabled) setSelectedDrawer({ caseNo: item.id, branchType: item.branchType });
            };
            return (
              <tr
                className="order-v2-case-entry"
                key={item.id}
                tabIndex={entryDisabled ? -1 : 0}
                aria-label={`開啟案件 ${item.id} 案件處理`}
                aria-disabled={entryDisabled}
                onClick={openWork}
                onKeyDown={(event) => {
                  if (event.target !== event.currentTarget) return;
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    openWork();
                  }
                }}
              >
                <td className="order-v2-case-number">{item.id}</td>
                <td>{summary ? summary.clientName.trim() || '客戶姓名未登錄' : <span title={summaryUnavailableMessage(summaryLoading, summaryQueryFailed)}>案件摘要不可用</span>}</td>
                <td className="order-v2-service-dates">
                  {summary ? <>
                    <span>{summary.serviceRange}</span>
                    <small>{summary.serviceDaysLabel}</small>
                    {(summary.actualStartDate !== null || summary.actualEndDate !== null) && (
                      <small>實際服務：<span>{formatServiceRange(summary.actualStartDate, summary.actualEndDate)}</span></small>
                    )}
                  </> : '—'}
                </td>
                <td>{summary?.assignedDoulaDisplay ?? '—'}</td>
                <td title={stage?.label ?? item.statusLabel}>
                  <span>{stage ? coreStageDefinition(stage.code).shortLabel : item.statusLabel}</span>
                  {stage && <small className="order-v2-row-meta">{item.statusLabel}</small>}
                </td>
                <td className="order-v2-reminders">
                  {intakeReviews.get(item.id) && (
                    <div className="order-v2-notice warning">
                      <strong>進件欄位待修正</strong>
                      <span>{intakeReviews.get(item.id)!.fields.join('、')}</span>
                      <small>可至客戶名冊修正資料。</small>
                    </div>
                  )}
                  {intakeReviewsError && item.lifecycleStatus === '待補件' && (
                    <div className="order-v2-notice warning" role="status">原始進件欄位問題讀取失敗，請重新讀取案件。</div>
                  )}
                  {primaryNotice && (
                    <div className={`order-v2-notice ${item.blockers.length > 0 ? 'blocked' : 'warning'}`}>
                      {primaryNotice.id !== 'intake_validation:orders_terms_missing' && <strong>{item.blockers.length > 0 ? '阻塞' : '提醒'} · {primaryNotice.stageLabel}</strong>}
                      <span>{primaryNotice.message}</span>
                      {item.blockers.length + item.warnings.length > 1 && <small>另有 {item.blockers.length + item.warnings.length - 1} 項，請在案件工作中查看。</small>}
                    </div>
                  )}
                  {!intakeReviews.get(item.id) && !(intakeReviewsError && item.lifecycleStatus === '待補件') && !primaryNotice && <span className="order-v2-row-meta">—</span>}
                </td>
                <td>
                  <button type="button" className="order-v2-open-case" disabled={entryDisabled}
                    aria-label={`開啟案件 ${item.id} 案件處理`}
                    onClick={(event) => { event.stopPropagation(); openWork(); }}>
                    處理 <ArrowRight size={15} aria-hidden="true" />
                  </button>
                </td>
              </tr>
            );
          })}
          </tbody>
        </table>
        </div>
        </fieldset>
      )}

      </section>


    </div>
  );
};

export default OrderWorkbenchV2Page;

import { ManagementPageHeader } from '../components/ManagementPageHeader';
import { loadAllCoreStageTimelines } from '../api/orders/load_all_core_stage_timelines';
import { serviceStartClient } from '../api/scheduling/service_start_client';
import { sessionClient } from '../api/auth/session_client';
/**
 * File: OrderWorkbenchV2Page.tsx
 * Description: 待辦看板 Beta。唯讀使用正式十三核心階段 query contract，不以前端推導階段或計數。
 */
import {
  useCallback,
  useEffect,
  useLayoutEffect,
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
import { isViewAccessDenied, useAdminOperationsViews, useOperationsQuery, useOperationsScroll, viewTimestamp } from './admin_operations_view_cache';
import { WorkbenchCaseStatistics } from '../components/WorkbenchCaseStatistics';
import { loadCurrentImportFieldIssuesForCases, importFieldIssueHref, type ImportFieldIssueCase } from '../api/case_import/import_field_issues';
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
} from '../adapters/orders/order_core_stage_projection_adapter';
import {
  adaptOrderSummaryPage,
  formatServiceRange,
  type OrderSummaryCardViewModel,
} from '../adapters/orders/order_summary_adapter';

const EMPTY_SUMMARIES: ReadonlyMap<string, OrderSummaryCardViewModel> = new Map();
const EMPTY_INTAKE: ReadonlyMap<string, ImportFieldIssueCase> = new Map();

function summaryUnavailableMessage(summaryLoading: boolean, summaryQueryFailed: boolean): string {
  if (summaryLoading) return '正式案件摘要載入中。';
  if (summaryQueryFailed) return '案件摘要暫時無法載入，仍可查看辦理階段。';
  return '未取得與此案件編號相符的正式摘要。';
}

export const OrderWorkbenchV2Page: FC<{ homeNavigationRequest?: number }> = ({ homeNavigationRequest = 0 }) => {
  const views = useAdminOperationsViews();
  const cache = views.workbench;
  const [selectedStage, setSelectedStage] = useState<CoreStageCode | null>(() => cache.selection.stage);
  const [search, setSearch] = useState(() => cache.selection.search);
  const [projectionRefreshKey, setProjectionRefreshKey] = useState(0);
  const [selectedDrawer, setSelectedDrawer] = useState<{
    caseNo: string;
    branchType: CoreStageBranchType;
    openUpcomingStaffing?: boolean;
  } | null>(null);
  const [caseLink, setCaseLink] = useState(() => window.location.hash);
  const caseLinkParams = new URLSearchParams(
    caseLink.startsWith('#order-workbench-v2?') ? caseLink.split('?')[1] : '',
  );
  const requestedCase = caseLinkParams.get('case') ?? '';
  const requestedSubstitute = caseLinkParams.get('substitute');
  const openUpcomingStaffing = caseLinkParams.get('staffing') === 'upcoming';
  const [caseLinkError, setCaseLinkError] = useState<string | null>(null);
  useOperationsScroll(views, 'order-workbench-v2', selectedDrawer === null && !requestedCase);
  useLayoutEffect(() => {
    cache.selection = { stage: selectedStage, search };
  }, [cache, selectedStage, search]);

  const refreshProjection = useCallback(() => {
    views.invalidateWorkbench();
    setProjectionRefreshKey(current => current + 1);
  }, [views]);
  const observeChanged = useCallback((scope?: 'calendar') => {
    if (scope === 'calendar') views.invalidateSchedulingMonths();
    else views.scheduling.options.invalidate();
    refreshProjection();
  }, [views, refreshProjection]);
  const clearDrawer = useCallback(() => {
    setSelectedDrawer(null);
    setCaseLink('');
    setCaseLinkError(null);
    if (new URLSearchParams(window.location.hash.split('?')[1] ?? '').has('case')) window.history.replaceState(null, '', '#order-workbench-v2');
  }, []);
  const closeDrawer = useCallback(() => {
    clearDrawer();
    refreshProjection();
  }, [clearDrawer, refreshProjection]);
  useEffect(() => {
    const readCaseLink = () => {
      const hash = window.location.hash;
      if (hash.startsWith('#order-workbench-v2?') && new URLSearchParams(hash.split('?')[1]).has('case')) {
        setCaseLink(hash);
      }
    };
    window.addEventListener('hashchange', readCaseLink);
    return () => window.removeEventListener('hashchange', readCaseLink);
  }, []);
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
    let legacyRequestId: number | undefined;
    if (requestedSubstitute !== null) {
      const candidate = Number(requestedSubstitute);
      if (!/^[1-9][0-9]*$/.test(requestedSubstitute) || !Number.isSafeInteger(candidate)
        || !sessionClient.getUser()?.capabilities.includes('system.administration')) {
        setSelectedDrawer(null);
        setCaseLinkError('無法確認案件，請從案件工作區開啟。');
        return;
      }
      legacyRequestId = candidate;
    }
    setCaseLinkError(null);
    void orderCoreStageProjectionClient.getCoreStageTimelines({ lifecycle_scope: 'all', case_no_search: requestedCase, page_size: 20 }, { signal: controller.signal })
      .then(async (page) => {
        if (controller.signal.aborted) return;
        const exact = page.items.filter((item) => item.case_no === requestedCase);
        if (exact.length !== 1) throw new Error('無法確認要開啟的案件，請重新查詢。');
        if (legacyRequestId !== undefined) {
          const request = await serviceStartClient.detail(legacyRequestId);
          if (controller.signal.aborted) return;
          if (request.request_id !== legacyRequestId || request.case_no !== requestedCase || request.workflow_kind !== 'leave') {
            throw new Error('無法確認案件，請從案件工作區開啟。');
          }
        }
        setSelectedDrawer({ caseNo: exact[0]!.case_no, branchType: exact[0]!.branch_type,
          openUpcomingStaffing: openUpcomingStaffing || legacyRequestId !== undefined });
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setSelectedDrawer(null);
        setCaseLinkError(error instanceof Error ? error.message : '案件讀取失敗。');
      });
    return () => controller.abort();
  }, [requestedCase, requestedSubstitute, openUpcomingStaffing]);

  const queryKey = selectedStage ?? 'all';
  const readCore = useCallback(async (signal: AbortSignal) => {
    const query: OrderCoreStageProjectionQueryParams = {
      page_size: 200,
      lifecycle_scope: 'all',
      workbench_scope: 'in_progress',
      stage: selectedStage ?? undefined,
    };
    return adaptOrderCoreStageTimelinePage(await loadAllCoreStageTimelines(query, { signal }), query);
  }, [selectedStage]);
  const core = useOperationsQuery({ cache: cache.core, queryKey, read: readCore, refreshKey: projectionRefreshKey });
  const view = core.snapshot?.data ?? null;
  const loading = view === null && core.status.kind === 'loading';
  const refreshing = view !== null && core.status.kind === 'loading';
  const coreAccessDenied = core.status.kind === 'failed' && isViewAccessDenied(core.status.error);
  const error = core.status.kind === 'failed'
    ? (coreAccessDenied ? '目前帳號無法查看案件清單。請聯絡系統管理員確認權限。' : '暫時無法讀取案件清單。請按「重試」。')
    : null;
  useLayoutEffect(() => {
    if (coreAccessDenied) clearDrawer();
  }, [coreAccessDenied, clearDrawer]);

  const readSummaries = useCallback(async (signal: AbortSignal) => {
    const data = await loadAllOrderSummaries(
      ordersQueryClient.getOrderSummaries.bind(ordersQueryClient),
      { lifecycle_scope: 'all', page_size: 200 },
      { signal },
    );
    const summaries = adaptOrderSummaryPage(data).items;
    return new Map(summaries.map(item => [item.id, item]));
  }, []);
  const summaries = useOperationsQuery({
    cache: cache.summaries, queryKey: 'all', read: readSummaries, refreshKey: projectionRefreshKey,
  });
  const summaryIndex = summaries.snapshot?.data ?? EMPTY_SUMMARIES;
  const summaryLoading = summaries.status.kind === 'loading';
  const summaryQueryFailed = summaries.status.kind === 'failed';

  const intakeKey = JSON.stringify([queryKey, ...(view?.items ?? []).map(item => item.id)]);
  const readIntake = useCallback(async (signal: AbortSignal) => {
    const reviews = await loadCurrentImportFieldIssuesForCases((view?.items ?? []).map(item => item.id), { signal });
    return new Map(reviews.map(review => [review.case_no, review]));
  }, [view]);
  const intake = useOperationsQuery({
    cache: cache.intake, queryKey: intakeKey, read: readIntake, refreshKey: projectionRefreshKey,
    enabled: view !== null && core.status.kind === 'ready',
  });
  const intakeReviews = intake.snapshot?.data ?? EMPTY_INTAKE;
  const intakeReviewsError = intake.status.kind === 'failed';

  const displayedItems = (view?.items ?? []).filter((item) => {
    if (!normalizedSearch) return true;
    if (item.id.toLocaleLowerCase().includes(normalizedSearch)) return true;
    const clientName = summaryIndex.get(item.id)?.clientName ?? '';
    return clientName.toLocaleLowerCase().includes(normalizedSearch);
  });

  const selectedDefinition = selectedStage === null ? null : coreStageDefinition(selectedStage);
  const selectedStageCount = selectedStage === null ? view?.items.length ?? 0 : view?.stageCounts[selectedStage] ?? 0;
  const displayedCount = displayedItems.length;
  const previewOnly = refreshing || error !== null;
  const nameSearchIncomplete = normalizedSearch !== '' && view !== null && view.items.length > 0
    && (summaryLoading || summaryQueryFailed);
  const showEmpty = view !== null && !previewOnly && !nameSearchIncomplete && displayedCount === 0;
  const tableDescriptions = [
    refreshing ? 'workbench-refresh-status' : null,
    view !== null && error !== null ? 'workbench-list-error' : null,
    view !== null && (summaryLoading || summaryQueryFailed) ? 'workbench-summary-status' : null,
  ].filter(Boolean).join(' ');
  const clearFilters = () => { setSearch(''); setSelectedStage(null); };

  const selectStage = (stage: CoreStageCode | null) => {
    setSelectedStage(stage);
  };

  if (selectedDrawer !== null && !coreAccessDenied) return (
    <>
      {error !== null && <div role="alert"><p>案件清單更新失敗，請重新整理後繼續。</p><button type="button" onClick={refreshProjection}>重新整理</button></div>}
      {caseLinkError && <p role="alert">{caseLinkError}</p>}
      <fieldset disabled={refreshing || error !== null} style={{ border: 0, padding: 0, margin: 0, minWidth: 0, width: '100%' }}>
        <OrderWorkbenchV2Drawer
          key={`${selectedDrawer.caseNo}:${selectedDrawer.openUpcomingStaffing ?? false}`}
          homeNavigationRequest={homeNavigationRequest}
          caseNo={selectedDrawer.caseNo}
          branchType={selectedDrawer.branchType}
          openUpcomingStaffing={selectedDrawer.openUpcomingStaffing}
          summary={summaryIndex.get(selectedDrawer.caseNo)}
          workbenchScope="in_progress"
          onClose={closeDrawer}
          onObserved={observeChanged}
        />
      </fieldset>
    </>
  );

  return (
    <div className="order-v2-page">
      <ManagementPageHeader className="orders-page-header" title="待辦看板" />
      {caseLinkError && <p role="alert">{caseLinkError}</p>}

      <details className="order-v2-overview-details">
        <summary>案件受理統計</summary>
        <WorkbenchCaseStatistics viewCache={cache} refreshKey={projectionRefreshKey} />
        <WorkbenchCaseStatistics viewCache={cache} refreshKey={projectionRefreshKey} caseCategory="non_citizen" />
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
              <span className="pipeline-step-badge">{view?.stageCounts[definition.code] ?? '—'}</span>
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
            {view !== null && previewOnly ? '可搜尋及查閱上次的案件編號、目前待辦與提醒。' : '點選案件列，進入案件處理。'}
          </p>
        </div>
        <div className="order-v2-result-count" aria-live="polite">
          顯示 <strong>{view === null || (nameSearchIncomplete && displayedCount === 0) ? '—' : displayedCount}</strong>
          <span>／ {view === null ? '—' : selectedStageCount} 筆</span>
        </div>
      </div>

      {view !== null && (summaryLoading || summaryQueryFailed) && (
        <div id="workbench-summary-status" className="order-v2-summary-warning" role="status">
          {summaryLoading
            ? (summaries.snapshot ? '案件摘要更新中，顯示上次的客戶、日期與月嫂資料。' : '正在載入客戶、日期與月嫂資料。可先查看案件編號和辦理階段。')
            : (summaries.snapshot ? `案件摘要更新失敗，顯示 ${viewTimestamp(summaries.snapshot.updatedAt)} 的資料。` : '客戶、日期與月嫂資料暫時無法載入。可先查看案件分類。')}
          {nameSearchIncomplete && (summaries.snapshot
            ? ' 姓名搜尋暫以更新前的摘要比對。'
            : ' 姓名搜尋尚無法比對，目前只比對案件編號。')}
          {summaryQueryFailed && !previewOnly && <> <button type="button" onClick={refreshProjection}>重試</button></>}
        </div>
      )}

      {loading && <div className="order-v2-empty">正在查詢訂單資料…</div>}
      {error && <div id="workbench-list-error" className="order-v2-error" role="alert">
        {error}
        {core.snapshot && <> 顯示 {viewTimestamp(core.snapshot.updatedAt)} 的資料，重新讀取成功後可處理案件。</>}
        {' '}<button type="button" onClick={refreshProjection}>重試</button>
      </div>}
      {refreshing && (
        <div id="workbench-refresh-status" className="order-v2-summary-warning" role="status">
          清單更新中，顯示上次資料。重新讀取完成後可處理案件。
        </div>
      )}
      {view !== null && previewOnly && !nameSearchIncomplete && displayedCount === 0 && (
        <p className="order-v2-empty">上次清單沒有符合目前條件的案件。</p>
      )}
      {showEmpty && (
        <div className="stage-empty-state">
          <span className="stage-empty-icon" aria-hidden="true">☕</span>
          <strong className="stage-empty-text">目前沒有符合條件的案件。</strong>
          {(search || selectedStage) && <button type="button" className="tracker-reload-button" onClick={clearFilters}>清除搜尋與篩選</button>}
          <span className="stage-empty-hint">可切換作業階段，或調整搜尋與篩選條件。</span>
        </div>
      )}
      {displayedCount > 0 && (
        <div className="order-v2-table-wrap" tabIndex={0} role="region" aria-label="待辦案件清單，可橫向捲動">
        <table className="order-v2-table" aria-label="待辦案件清單" aria-describedby={tableDescriptions || undefined}>
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
            const entryDisabled = previewOnly;
            const openWork = () => {
              if (entryDisabled) return;
              if (stage?.code === 'intake_validation') window.location.hash = importFieldIssueHref(item.id, intakeReviews.get(item.id)?.issues[0]);
              else setSelectedDrawer({ caseNo: item.id, branchType: item.branchType });
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
                <td>{summary ? summary.clientName.trim() || '客戶姓名未登錄' : <span title={summaryUnavailableMessage(summaryLoading, summaryQueryFailed)}>{summaryLoading ? '摘要載入中' : '案件摘要不可用'}</span>}</td>
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
                      <span>{intakeReviews.get(item.id)!.issues.map((issue) => issue.source_field).join('、')}</span>
                      {!entryDisabled && <a href={importFieldIssueHref(item.id, intakeReviews.get(item.id)?.issues[0])} onClick={(event) => event.stopPropagation()}>修正資料</a>}
                    </div>
                  )}
                  {intakeReviewsError && (
                    <div className="order-v2-notice warning" role="status">原始進件欄位問題讀取失敗，請重新讀取案件。</div>
                  )}
                  {primaryNotice && (
                    <div className={`order-v2-notice ${item.blockers.length > 0 ? 'blocked' : 'warning'}`}>
                      {primaryNotice.id !== 'intake_validation:orders_terms_missing' && <strong>{item.blockers.length > 0 ? '阻塞' : '提醒'} · {primaryNotice.stageLabel}</strong>}
                      <span>{primaryNotice.message}</span>
                      {item.blockers.length + item.warnings.length > 1 && <small>另有 {item.blockers.length + item.warnings.length - 1} 項，請在案件工作中查看。</small>}
                    </div>
                  )}
                  {!intakeReviews.get(item.id) && !intakeReviewsError && !primaryNotice && <span className="order-v2-row-meta">—</span>}
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
      )}

      </section>


    </div>
  );
};

export default OrderWorkbenchV2Page;

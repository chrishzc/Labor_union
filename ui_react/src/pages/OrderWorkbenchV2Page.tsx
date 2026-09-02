/**
 * File: OrderWorkbenchV2Page.tsx
 * Description: 待辦看板 Beta。唯讀使用正式十三核心階段 query contract，不以前端推導階段或計數。
 */
import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FC,
} from 'react';
import './OrderWorkbenchV2Page.css';
import { OrderWorkbenchV2Drawer } from '../components/OrderWorkbenchV2Drawer';
import {
  orderCoreStageProjectionClient,
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
  coreStageBranchLabel,
  coreStageDefinition,
  ORDER_CORE_STAGE_PROJECTION_UNAVAILABLE,
  type OrderCoreStageWorkbenchViewModel,
} from '../adapters/orders/order_core_stage_projection_adapter';
import {
  adaptOrderSummaryPage,
  type OrderSummaryCardViewModel,
} from '../adapters/orders/order_summary_adapter';

const BRANCH_TYPES: readonly CoreStageBranchType[] = ['normal', 'historical', 'cancelled'];

function summaryUnavailableMessage(summaryLoading: boolean, summaryQueryFailed: boolean): string {
  if (summaryLoading) return '正式案件摘要載入中。';
  if (summaryQueryFailed) return '正式案件摘要查詢失敗；目前只顯示十三階段投影。';
  return '未取得與此案件編號相符的正式摘要。';
}

function coreQueryErrorMessage(error: unknown): string {
  const detail = error instanceof Error && error.message.trim()
    ? error.message.trim()
    : '無法取得正式十三階段資料';
  return `${ORDER_CORE_STAGE_PROJECTION_UNAVAILABLE} 原因：${detail}`;
}

export const OrderWorkbenchV2Page: FC = () => {
  const [view, setView] = useState<OrderCoreStageWorkbenchViewModel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [summaryIndex, setSummaryIndex] = useState<ReadonlyMap<string, OrderSummaryCardViewModel>>(
    () => new Map(),
  );
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [summaryQueryFailed, setSummaryQueryFailed] = useState(false);
  const [selectedStage, setSelectedStage] = useState<CoreStageCode>('intake_validation');
  const [selectedSubstatus, setSelectedSubstatus] = useState<CoreStageSubstatusCode | null>(null);
  const [branchType, setBranchType] = useState<CoreStageBranchType>('normal');
  const [search, setSearch] = useState('');
  const [onlyBlocked, setOnlyBlocked] = useState(false);
  const [onlyWarning, setOnlyWarning] = useState(false);
  const [selectedDrawer, setSelectedDrawer] = useState<{
    caseNo: string;
    branchType: CoreStageBranchType;
  } | null>(null);
  const requestSequence = useRef(0);

  const normalizedSearch = search.trim();

  useEffect(() => {
    const requestId = requestSequence.current + 1;
    requestSequence.current = requestId;
    const controller = new AbortController();
    const query: OrderCoreStageProjectionQueryParams = {
      page_size: 200,
      lifecycle_scope: 'all',
      branch_type: branchType,
      case_no_search: normalizedSearch || undefined,
      blocker_only: onlyBlocked || undefined,
      warning_only: onlyWarning || undefined,
      stage: branchType === 'normal' ? selectedStage : undefined,
      substatus_code:
        branchType === 'normal' && selectedSubstatus !== null
          ? selectedSubstatus
          : undefined,
    };

    setLoading(true);
    setError(null);
    setView(null);

    void orderCoreStageProjectionClient.getCoreStageTimelines(query, {
      signal: controller.signal,
    })
      .then((page) => {
        if (controller.signal.aborted || requestSequence.current !== requestId) return;
        setView(adaptOrderCoreStageTimelinePage(page, query));
      })
      .catch((caught) => {
        if (controller.signal.aborted || requestSequence.current !== requestId) return;
        setError(coreQueryErrorMessage(caught));
      })
      .finally(() => {
        if (!controller.signal.aborted && requestSequence.current === requestId) {
          setLoading(false);
        }
      });

    return () => controller.abort();
  }, [branchType, normalizedSearch, onlyBlocked, onlyWarning, selectedStage, selectedSubstatus]);

  useEffect(() => {
    let alive = true;
    setSummaryIndex(new Map());
    setSummaryLoading(true);
    setSummaryQueryFailed(false);

    void loadAllOrderSummaries(
      ordersQueryClient.getOrderSummaries.bind(ordersQueryClient),
      { lifecycle_scope: 'all', page_size: 200 },
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

    return () => { alive = false; };
  }, []);

  const selectedDefinition = coreStageDefinition(selectedStage);
  const selectedStageCount = view?.stageCounts[selectedStage] ?? 0;
  const displayedCount = view?.items.length ?? 0;

  const selectBranch = (branch: CoreStageBranchType) => {
    setBranchType(branch);
    setSelectedSubstatus(null);
  };

  const selectStage = (stage: CoreStageCode) => {
    setBranchType('normal');
    setSelectedStage(stage);
    setSelectedSubstatus(null);
  };

  return (
    <div className="order-v2-page">
      <header className="order-v2-header">
        <div>
          <div className="order-v2-eyebrow">BETA · 正式唯讀查詢</div>
          <h1>📌 待辦看板 Beta</h1>
          <p>案件、十三階段計數與子狀態計數均由正式 server query 回傳；此頁不再載入舊七階資料後自行推導。</p>
        </div>
        <div className="order-v2-summary">
          <strong>{coreStageBranchLabel(branchType)}</strong><span>目前支線</span>
          <strong>{displayedCount}</strong><span>目前顯示</span>
          {branchType === 'normal' && (
            <><strong>{selectedStageCount}</strong><span>階段總數</span></>
          )}
        </div>
      </header>

      <nav className="order-v2-branch-filters" aria-label="訂單支線篩選">
        {BRANCH_TYPES.map((branch) => (
          <button
            type="button"
            key={branch}
            className={branchType === branch ? 'active' : ''}
            onClick={() => selectBranch(branch)}
          >
            {coreStageBranchLabel(branch)}
          </button>
        ))}
      </nav>

      <section className="order-v2-stage-strip" aria-label="13 個核心訂單階段">
        {CORE_STAGE_DEFINITIONS.map((definition) => (
          <button
            key={definition.code}
            type="button"
            className={`order-v2-stage ${
              branchType === 'normal' && selectedStage === definition.code ? 'active' : ''
            }`}
            onClick={() => selectStage(definition.code)}
          >
            <span className="order-v2-stage-number">{definition.ordinal}</span>
            <span className="order-v2-stage-label">{definition.shortLabel}</span>
            <span className="order-v2-stage-count">{view?.stageCounts[definition.code] ?? 0}</span>
          </button>
        ))}
      </section>

      <section className="order-v2-toolbar">
        <div>
          <h2>
            {branchType === 'normal'
              ? `${selectedDefinition.ordinal}. ${selectedDefinition.label}`
              : coreStageBranchLabel(branchType)}
          </h2>
          <p>
            {branchType === 'normal'
              ? selectedDefinition.ownerLabel
              : '由正式 branch_type query 讀取，不套用正常十三階段推導。'}
          </p>
        </div>
        <div className="order-v2-toolbar-actions">
          <input
            aria-label="搜尋案件編號"
            value={search}
            onChange={(event: ChangeEvent<HTMLInputElement>) => setSearch(event.target.value)}
            placeholder="搜尋案件編號"
          />
          <label>
            <input
              type="checkbox"
              checked={onlyBlocked}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setOnlyBlocked(event.target.checked)}
            /> 只看阻塞
          </label>
          <label>
            <input
              type="checkbox"
              checked={onlyWarning}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setOnlyWarning(event.target.checked)}
            /> 只看提醒
          </label>
        </div>
      </section>

      {branchType === 'normal' && (
        <div className="order-v2-subfilters" aria-label="階段子狀態篩選">
          <button
            type="button"
            className={selectedSubstatus === null ? 'active' : ''}
            onClick={() => setSelectedSubstatus(null)}
          >
            全部 <strong>{selectedStageCount}</strong>
          </button>
          {(view?.substatusOptions ?? []).map((option) => (
            <button
              type="button"
              key={option.code}
              className={selectedSubstatus === option.code ? 'active' : ''}
              onClick={() => setSelectedSubstatus(option.code)}
            >
              {option.label} <strong>{option.count}</strong>
            </button>
          ))}
        </div>
      )}

      {summaryQueryFailed && !loading && !error && (
        <div className="order-v2-summary-warning" role="status">
          案件摘要查詢失敗；案件仍依正式十三階段 response 顯示，但客戶、日期與月嫂摘要暫時不可用。
        </div>
      )}

      {loading && <div className="order-v2-empty">正在查詢正式十三階段資料…</div>}
      {error && <div className="order-v2-error" role="alert">{error}</div>}
      {!loading && !error && displayedCount === 0 && (
        <div className="order-v2-empty">目前沒有符合 server-side 條件的案件。</div>
      )}
      {!loading && !error && view?.nextCursor != null && (
        <div className="order-v2-summary-warning" role="status">
          結果超過單次查詢上限；目前顯示前 200 筆，請縮小搜尋或篩選條件。
        </div>
      )}

      {!loading && !error && displayedCount > 0 && (
        <div className="order-v2-case-grid">
          {view?.items.map((item) => {
            const summary = summaryIndex.get(item.id) ?? null;
            const stage = item.currentStage;
            return (
              <article className="order-v2-case-card" key={item.id}>
                <div className="order-v2-case-topline">
                  <strong>{item.id}</strong>
                  <span className={`order-v2-status status-${stage?.status ?? item.branchType}`}>
                    {item.statusLabel}
                  </span>
                </div>

                {summary ? (
                  <dl className="order-v2-business-summary">
                    <div><dt>客戶</dt><dd>{summary.clientName.trim() || '客戶姓名未登錄'}</dd></div>
                    <div><dt>服務日期</dt><dd>{summary.serviceRange}</dd></div>
                    <div><dt>指派月嫂</dt><dd>{summary.assignedDoulaDisplay}</dd></div>
                  </dl>
                ) : (
                  <div className="order-v2-business-summary unavailable" role="note">
                    <strong>案件摘要不可用</strong>
                    <span>{summaryUnavailableMessage(summaryLoading, summaryQueryFailed)}</span>
                  </div>
                )}

                <div className="order-v2-case-meta">
                  <span>Lifecycle：{item.lifecycleStatus}</span>
                  <span>支線：{item.branchLabel}</span>
                  <span>Revision：{item.baseRevision}</span>
                  {stage && <span>目前階段：{stage.label}</span>}
                  {stage && <span>Owner：{stage.owner}</span>}
                  {stage?.occurred_at && (
                    <span>更新：{new Date(stage.occurred_at).toLocaleString('zh-TW')}</span>
                  )}
                </div>

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
                <button
                  type="button"
                  className="order-v2-open-drawer"
                  onClick={() => setSelectedDrawer({ caseNo: item.id, branchType: item.branchType })}
                >
                  開啟唯讀工作 Drawer
                </button>
              </article>
            );
          })}
        </div>
      )}

      <section className="order-v2-side-lanes">
        <button
          type="button"
          className={`order-v2-lane ${branchType === 'historical' ? 'active' : ''}`}
          onClick={() => selectBranch('historical')}
        >
          <span><strong>歷史訂單支線</strong><small>使用正式 historical branch filter。</small></span>
          <b>{branchType === 'historical' ? '檢視中' : '開啟'}</b>
        </button>
        <div className="order-v2-lane pending">
          <span><strong>政府補助結算支線</strong><small>等待正式 Government Subsidy → Order projection。</small></span>
          <b>待接正式 projection</b>
        </div>
        <button
          type="button"
          className={`order-v2-lane ${branchType === 'cancelled' ? 'active' : ''}`}
          onClick={() => selectBranch('cancelled')}
        >
          <span><strong>取消訂單支線</strong><small>使用正式 cancelled branch filter。</small></span>
          <b>{branchType === 'cancelled' ? '檢視中' : '開啟'}</b>
        </button>
      </section>

      {selectedDrawer !== null && (
        <OrderWorkbenchV2Drawer
          caseNo={selectedDrawer.caseNo}
          branchType={selectedDrawer.branchType}
          onClose={() => setSelectedDrawer(null)}
        />
      )}
    </div>
  );
};

export default OrderWorkbenchV2Page;

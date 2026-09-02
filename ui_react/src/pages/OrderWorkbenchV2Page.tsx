/**
 * File: OrderWorkbenchV2Page.tsx
 * Description: Dry-run 版案件待辦工作台。以既有 server-owned operational timeline 投影 13 個核心階段，
 *              不修改現行待辦看板或訂單管理，也不自行創造補助 owner 狀態。
 */
import React, { useEffect, useMemo, useState } from 'react';
import './OrderWorkbenchV2Page.css';
import {
  loadAllOrderOperationalTimelines,
  orderStageProjectionClient,
} from '../api/orders/order_stage_projection_client';
import {
  loadAllOrderSummaries,
  ordersQueryClient,
} from '../api/orders/order_query_client';
import type {
  OrderOperationalTimeline,
  OrderOperationalTimelinePage,
  SopStepProjection,
  StageProjection,
} from '../api/orders/order_stage_projection_schemas';
import {
  adaptOrderSummaryPage,
  type OrderSummaryCardViewModel,
} from '../adapters/orders/order_summary_adapter';

type CoreStageOrdinal = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13;
type FilterStatus = 'all' | 'not_started' | 'in_progress' | 'blocked' | 'unavailable';
type StageStatus = SopStepProjection['status'];

interface StageDefinition {
  ordinal: CoreStageOrdinal;
  shortLabel: string;
  label: string;
  owner: string;
}

interface StageCase {
  timeline: OrderOperationalTimeline;
  status: StageStatus;
  occurredAt: string | null;
  blockers: readonly { code: string; message: string }[];
  warnings: readonly { code: string; message: string }[];
  availabilityReason: string | null;
}

const CORE_STAGES: readonly StageDefinition[] = [
  { ordinal: 1, shortLabel: '進件', label: '進件與資料完整性驗證', owner: 'Case Import / Orders' },
  { ordinal: 2, shortLabel: '候選池', label: '建立候選月嫂池', owner: 'Assignments / Scheduling' },
  { ordinal: 3, shortLabel: '詢問月嫂', label: '詢問月嫂接案意願', owner: 'Assignments / LINE Delivery' },
  { ordinal: 4, shortLabel: '等待回覆', label: '等待月嫂意願回覆', owner: 'Assignments / LINE' },
  { ordinal: 5, shortLabel: '客戶確認', label: '推薦月嫂給客戶確認', owner: 'Assignments / Customer Decision' },
  { ordinal: 6, shortLabel: '月嫂契約', label: '月嫂契約簽署', owner: 'Contract Signing' },
  { ordinal: 7, shortLabel: '定金', label: '客戶定金核銷', owner: 'Client Finance' },
  { ordinal: 8, shortLabel: '客戶契約', label: '客戶契約簽署', owner: 'Contract Signing / Orders' },
  { ordinal: 9, shortLabel: '日期確認', label: '正式服務日期確認', owner: 'Orders / Scheduling' },
  { ordinal: 10, shortLabel: '排班/服務', label: '正式排班與服務履約', owner: 'Scheduling / Orders' },
  { ordinal: 11, shortLabel: '完工', label: '完工／服務完成確認', owner: 'Orders' },
  { ordinal: 12, shortLabel: '客戶結算', label: '客戶端結算', owner: 'Client Finance' },
  { ordinal: 13, shortLabel: '月嫂結算', label: '月嫂端結算', owner: 'Staff Payables' },
] as const;

function isHistorical(timeline: OrderOperationalTimeline): boolean {
  return timeline.lifecycle_status.startsWith('歷史訂單－');
}

function settlementStage(timeline: OrderOperationalTimeline): StageProjection | null {
  return timeline.stages.find((stage) => stage.code === 'settlement_payout') ?? null;
}

function settlementPart(timeline: OrderOperationalTimeline, code: 'service_completion' | 'client_settlement' | 'staff_payout') {
  return settlementStage(timeline)?.settlement.find((part) => part.code === code) ?? null;
}

function activeCoreStage(timeline: OrderOperationalTimeline): CoreStageOrdinal | null {
  if (isHistorical(timeline) || timeline.lifecycle_status === '訂單取消') return null;
  const step = timeline.current_step_ordinal;
  if (step === null) return null;
  if (step <= 10) return step as CoreStageOrdinal;

  const service = settlementPart(timeline, 'service_completion');
  if (!service || service.status !== 'completed') return 11;
  const client = settlementPart(timeline, 'client_settlement');
  if (!client || client.status !== 'completed') return 12;
  const staff = settlementPart(timeline, 'staff_payout');
  if (!staff || staff.status !== 'completed') return 13;
  return null;
}

function caseForStage(timeline: OrderOperationalTimeline, ordinal: CoreStageOrdinal): StageCase | null {
  if (activeCoreStage(timeline) !== ordinal) return null;
  if (ordinal <= 10) {
    const step = timeline.sop_steps[ordinal - 1];
    if (!step) return null;
    return {
      timeline,
      status: step.status,
      occurredAt: step.occurred_at,
      blockers: step.blockers,
      warnings: step.warnings,
      availabilityReason: step.availability_reason,
    };
  }

  const code = ordinal === 11 ? 'service_completion' : ordinal === 12 ? 'client_settlement' : 'staff_payout';
  const part = settlementPart(timeline, code);
  return {
    timeline,
    status: part?.status ?? 'unavailable',
    occurredAt: part?.occurred_at ?? null,
    blockers: [],
    warnings: [],
    availabilityReason: part?.availability_reason ?? `${code}_projection_missing`,
  };
}

function stageSubstatusLabel(ordinal: CoreStageOrdinal, status: StageStatus): string {
  if (ordinal === 10) {
    if (status === 'not_started') return '待開工';
    if (status === 'in_progress') return '服務進行中';
  }
  if (ordinal === 11) {
    if (status === 'unavailable' || status === 'not_started') return '待完工確認';
    if (status === 'in_progress') return '完工處理中';
  }
  if (ordinal === 12) {
    if (status === 'blocked') return '待客戶端結清';
    if (status === 'in_progress') return '客戶結算處理中';
  }
  if (ordinal === 13) {
    if (status === 'blocked') return '待月嫂端結清';
    if (status === 'in_progress') return '月嫂結算處理中';
  }
  if (status === 'not_started') return '待處理';
  if (status === 'in_progress') return '處理中';
  if (status === 'blocked') return '阻塞';
  if (status === 'unavailable') return '資料不足';
  return '已完成';
}

function availableFilters(cases: readonly StageCase[]): FilterStatus[] {
  const statuses = new Set(cases.map((item) => item.status));
  const result: FilterStatus[] = ['all'];
  (['not_started', 'in_progress', 'blocked', 'unavailable'] as const).forEach((status) => {
    if (statuses.has(status)) result.push(status);
  });
  return result;
}

function summaryUnavailableMessage(summaryLoading: boolean, summaryQueryFailed: boolean): string {
  if (summaryLoading) return '正式案件摘要載入中。';
  if (summaryQueryFailed) return '正式案件摘要查詢失敗；目前只顯示階段投影。';
  return '未取得與此案件編號相符的正式摘要。';
}

export const OrderWorkbenchV2Page: React.FC = () => {
  const [page, setPage] = useState<OrderOperationalTimelinePage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [summaryIndex, setSummaryIndex] = useState<ReadonlyMap<string, OrderSummaryCardViewModel>>(() => new Map());
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [summaryQueryFailed, setSummaryQueryFailed] = useState(false);
  const [selectedStage, setSelectedStage] = useState<CoreStageOrdinal>(1);
  const [selectedStatus, setSelectedStatus] = useState<FilterStatus>('all');
  const [search, setSearch] = useState('');
  const [onlyBlocked, setOnlyBlocked] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    setSummaryIndex(new Map());
    setSummaryLoading(true);
    setSummaryQueryFailed(false);

    void loadAllOrderOperationalTimelines(
      orderStageProjectionClient.getOperationalTimelines.bind(orderStageProjectionClient),
      { lifecycle_scope: 'all', page_size: 200 },
    )
      .then((data) => {
        if (alive) setPage(data);
      })
      .catch((caught) => {
        if (alive) setError(caught instanceof Error ? caught.message : '無法載入案件階段投影。');
      })
      .finally(() => {
        if (alive) setLoading(false);
      });

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

  const normalTimelines = useMemo(
    () => (page?.items ?? []).filter((item) => !isHistorical(item) && item.lifecycle_status !== '訂單取消'),
    [page],
  );
  const historicalTimelines = useMemo(
    () => (page?.items ?? []).filter(isHistorical),
    [page],
  );
  const cancelledTimelines = useMemo(
    () => (page?.items ?? []).filter((item) => item.lifecycle_status === '訂單取消'),
    [page],
  );

  const stageCases = useMemo(() => {
    const map = new Map<CoreStageOrdinal, StageCase[]>();
    CORE_STAGES.forEach((definition) => map.set(definition.ordinal, []));
    normalTimelines.forEach((timeline) => {
      const ordinal = activeCoreStage(timeline);
      if (ordinal === null) return;
      const item = caseForStage(timeline, ordinal);
      if (item) map.get(ordinal)?.push(item);
    });
    return map;
  }, [normalTimelines]);

  const selectedCases = stageCases.get(selectedStage) ?? [];
  const filters = availableFilters(selectedCases);

  useEffect(() => {
    if (!filters.includes(selectedStatus)) setSelectedStatus('all');
  }, [filters, selectedStatus]);

  const visibleCases = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase('zh-TW');
    return selectedCases.filter((item) => {
      if (selectedStatus !== 'all' && item.status !== selectedStatus) return false;
      if (onlyBlocked && item.status !== 'blocked' && item.blockers.length === 0) return false;
      if (needle && !item.timeline.case_no.toLocaleLowerCase('zh-TW').includes(needle)) return false;
      return true;
    });
  }, [onlyBlocked, search, selectedCases, selectedStatus]);

  const selectedDefinition = CORE_STAGES.find((item) => item.ordinal === selectedStage)!;

  return (
    <div className="order-v2-page">
      <header className="order-v2-header">
        <div>
          <div className="order-v2-eyebrow">DRY RUN · 不取代現行頁面</div>
          <h1>📌 待辦看板 Beta</h1>
          <p>以目前 server-owned Orders operational timeline 試投影 13 個核心階段。此頁唯讀，不修改舊待辦看板、訂單管理或 backend lifecycle contract。</p>
        </div>
        <div className="order-v2-summary">
          <strong>{normalTimelines.length}</strong><span>正常訂單</span>
          <strong>{historicalTimelines.length}</strong><span>歷史訂單</span>
          <strong>{cancelledTimelines.length}</strong><span>取消訂單</span>
        </div>
      </header>

      <section className="order-v2-stage-strip" aria-label="13 個核心訂單階段">
        {CORE_STAGES.map((definition) => {
          const count = stageCases.get(definition.ordinal)?.length ?? 0;
          return (
            <button
              key={definition.ordinal}
              type="button"
              className={`order-v2-stage ${selectedStage === definition.ordinal ? 'active' : ''}`}
              onClick={() => { setSelectedStage(definition.ordinal); setSelectedStatus('all'); }}
            >
              <span className="order-v2-stage-number">{definition.ordinal}</span>
              <span className="order-v2-stage-label">{definition.shortLabel}</span>
              <span className="order-v2-stage-count">{count}</span>
            </button>
          );
        })}
      </section>

      <section className="order-v2-toolbar">
        <div>
          <h2>{selectedStage}. {selectedDefinition.label}</h2>
          <p>{selectedDefinition.owner}</p>
        </div>
        <div className="order-v2-toolbar-actions">
          <input
            aria-label="搜尋案件編號"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="搜尋案件編號"
          />
          <label><input type="checkbox" checked={onlyBlocked} onChange={(event) => setOnlyBlocked(event.target.checked)} /> 只看阻塞</label>
        </div>
      </section>

      <div className="order-v2-subfilters" aria-label="階段子狀態篩選">
        {filters.map((status) => {
          const count = status === 'all' ? selectedCases.length : selectedCases.filter((item) => item.status === status).length;
          const label = status === 'all' ? '全部' : stageSubstatusLabel(selectedStage, status);
          return (
            <button
              type="button"
              key={status}
              className={selectedStatus === status ? 'active' : ''}
              onClick={() => setSelectedStatus(status)}
            >
              {label} <strong>{count}</strong>
            </button>
          );
        })}
      </div>

      {summaryQueryFailed && !loading && !error && (
        <div className="order-v2-summary-warning" role="status">
          案件摘要查詢失敗；以下案件仍依正式 operational timeline 顯示，但客戶、日期與月嫂摘要暫時不可用。
        </div>
      )}

      {loading && <div className="order-v2-empty">正在載入 server-owned 案件投影…</div>}
      {error && <div className="order-v2-error" role="alert">{error}</div>}
      {!loading && !error && visibleCases.length === 0 && <div className="order-v2-empty">目前沒有符合條件的案件。</div>}

      {!loading && !error && visibleCases.length > 0 && (
        <div className="order-v2-case-grid">
          {visibleCases.map(({ timeline, status, occurredAt, blockers, warnings, availabilityReason }) => {
            const summary = summaryIndex.get(timeline.case_no) ?? null;
            return (
              <article className="order-v2-case-card" key={timeline.case_no}>
                <div className="order-v2-case-topline">
                  <strong>{timeline.case_no}</strong>
                  <span className={`order-v2-status status-${status}`}>{stageSubstatusLabel(selectedStage, status)}</span>
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
                  <span>Lifecycle：{timeline.lifecycle_status}</span>
                  <span>Revision：{timeline.base_revision}</span>
                  {occurredAt && <span>更新：{new Date(occurredAt).toLocaleString('zh-TW')}</span>}
                </div>
                {blockers.length > 0 && (
                  <div className="order-v2-notice blocked"><strong>阻塞</strong>{blockers.map((item) => <span key={item.code}>{item.message}</span>)}</div>
                )}
                {warnings.length > 0 && (
                  <div className="order-v2-notice warning"><strong>提醒</strong>{warnings.map((item) => <span key={item.code}>{item.message}</span>)}</div>
                )}
                {availabilityReason && <div className="order-v2-technical">projection：{availabilityReason}</div>}
              </article>
            );
          })}
        </div>
      )}

      <section className="order-v2-side-lanes">
        <div className="order-v2-lane">
          <div><h3>歷史訂單支線</h3><p>維持既有 Historical Orders baseline，不硬塞進 13 個正常階段。</p></div>
          <strong>{historicalTimelines.length}</strong>
        </div>
        <div className="order-v2-lane pending">
          <div><h3>政府補助結算支線</h3><p>所有正常訂單必經；dry-run 版不偽造狀態，等待正式 Government Subsidy → Order projection 後接入。</p></div>
          <span>待接正式 projection</span>
        </div>
        <div className="order-v2-lane terminal">
          <div><h3>完全結案</h3><p>13 階段與政府補助結算都完成後的 terminal state；目前不改既有 lifecycle 判定。</p></div>
          <span>設計驗證中</span>
        </div>
      </section>
    </div>
  );
};

export default OrderWorkbenchV2Page;

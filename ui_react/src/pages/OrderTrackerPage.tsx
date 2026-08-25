/**
 * File: OrderTrackerPage.tsx
 * Description: 顯示未完成訂單的七階段、聯絡資料、SOP、結清與 LINE 通知唯讀歷程。
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { adaptOrderTrackerPage, type OrderTrackerPageViewModel, type TrackerOrderCardViewModel } from '../adapters/orders/order_tracker_adapter';
import {
  ORDER_STAGE_PROJECTION_UNAVAILABLE,
  formatProjectionTimestamp,
  indexOperationalTimelines,
  stageByCode,
  stageAvailabilityLabel,
  stageStatusLabel,
} from '../adapters/orders/order_stage_projection_adapter';
import { loadAllOrderSummaries, ordersQueryClient } from '../api/orders/order_query_client';
import type { FormManagementContext } from '../api/orders/order_query_schemas';
import { orderCardProjectionClient } from '../api/orders/order_card_projection_client';
import type { OrdersCardProjection } from '../api/orders/order_card_projection_schemas';
import { loadAllOrderOperationalTimelines, orderStageProjectionClient } from '../api/orders/order_stage_projection_client';
import type { OrderOperationalTimelinePage } from '../api/orders/order_stage_projection_schemas';
import { lineNotificationTimelineClient, type LineNotificationTimeline } from '../api/line/notification_timeline_client';
import { Drawer } from '../components/Drawer';
import './OrderTrackerPage.css';

type TrackerQueryState =
  | { kind: 'loading' }
  | { kind: 'ready'; data: OrderTrackerPageViewModel }
  | { kind: 'empty'; data: OrderTrackerPageViewModel }
  | { kind: 'error'; message: string };

type StageProjectionQueryState =
  | { kind: 'loading' }
  | { kind: 'ready'; page: OrderOperationalTimelinePage; byCaseNo: ReadonlyMap<string, OrderOperationalTimelinePage['items'][number]> }
  | { kind: 'unavailable'; message: string };

type CardProjectionState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ready'; data: OrdersCardProjection }
  | { kind: 'error'; message: string };

type NotificationTimelineState =
  | { kind: 'idle' | 'loading' }
  | { kind: 'ready'; data: LineNotificationTimeline }
  | { kind: 'error'; message: string };

type FormManagementContextState =
  | { kind: 'idle' | 'loading' }
  | { kind: 'ready'; data: FormManagementContext }
  | { kind: 'error'; message: string };

function controlSafeCaseNo(caseNo: string): string {
  return encodeURIComponent(caseNo);
}

const OWNER_LABELS: Readonly<Record<string, string>> = {
  'Case Import': '資料匯入',
  Orders: '訂單管理',
  Assignments: '媒合與正式指派',
  Scheduling: '排班管理',
  'LINE Delivery': 'LINE 通知',
  LINE: 'LINE 意願回覆',
  'Customer Decision': '客戶決定',
  'Contract Signing': '契約簽署',
  'Client Finance': '客戶帳務',
  'Staff Payables': '月嫂薪資',
};

function businessOwnerLabel(owner: string): string {
  return owner
    .split('/')
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => OWNER_LABELS[part] ?? part)
    .join(' / ');
}

function currentStageLabel(timeline: OrderOperationalTimelinePage['items'][number]): string {
  if (!timeline.current_stage_code) return '待判定';
  return stageByCode(timeline, timeline.current_stage_code)?.label ?? '待判定';
}

function currentStageSummary(
  timeline: OrderOperationalTimelinePage['items'][number] | null,
  fallback: string,
): string {
  if (!timeline) return fallback;
  if (!timeline.current_stage_code) {
    const missingFacts = [...new Set(
      timeline.stages
        .filter((stage) => stage.status === 'unavailable')
        .map((stage) => stageAvailabilityLabel(stage.availability_reason))
        .filter((message): message is string => message !== null),
    )];
    if (missingFacts.length === 0) return '資料完整性異常，請開啟案件確認根事實。';
    const visibleFacts = missingFacts.slice(0, 2).join('、');
    return `資料待補正：${visibleFacts}${missingFacts.length > 2 ? `（另 ${missingFacts.length - 2} 項）` : ''}`;
  }
  const stage = stageByCode(timeline, timeline.current_stage_code);
  if (!stage) return fallback;
  return stage.blockers[0]?.message
    ?? stage.warnings[0]?.message
    ?? stageAvailabilityLabel(stage.availability_reason)
    ?? `${stage.label}：${stageStatusLabel(stage.status)}`;
}

function cardProjectionValue<T>(
  field: { value: T | null; owner: string; availability: 'available' | 'unavailable' | 'blocked'; availability_reason: string | null },
  renderValue: (value: T) => string,
  emptyText: string,
): string {
  if (field.availability !== 'available') {
    const state = field.availability === 'blocked' ? '資料受阻' : '資料待補正';
    const reason = stageAvailabilityLabel(field.availability_reason) ?? `${businessOwnerLabel(field.owner)} 尚無可用資料`;
    return `${state}：${reason}`;
  }
  return field.value === null ? emptyText : renderValue(field.value);
}

function cardProjectionContactValue(
  state: CardProjectionState,
  field: 'contact_phone' | 'contact_address',
): string {
  if (state.kind === 'loading') return '載入中…';
  if (state.kind === 'error') return '載入失敗';
  if (state.kind === 'idle') return '尚未載入';
  return cardProjectionValue(state.data[field], String, '尚未登錄');
}

function formatFriendlyTimestamp(value: string | null): string {
  if (!value) return '尚無事件時間';
  const date = new Date(value);
  if (!isNaN(date.getTime()) && value.includes('-')) {
    const yyyy = date.getFullYear();
    const mm = String(date.getMonth() + 1).padStart(2, '0');
    const dd = String(date.getDate()).padStart(2, '0');
    const hh = String(date.getHours()).padStart(2, '0');
    const min = String(date.getMinutes()).padStart(2, '0');
    return `${yyyy}/${mm}/${dd} ${hh}:${min}`;
  }
  return value.replace('T', ' ');
}

export const OrderTrackerPage: React.FC = () => {
  const [queryState, setQueryState] = useState<TrackerQueryState>({ kind: 'loading' });
  const [stageProjectionState, setStageProjectionState] = useState<StageProjectionQueryState>({ kind: 'loading' });
  const [selectedOrder, setSelectedOrder] = useState<TrackerOrderCardViewModel | null>(null);
  const [drawerTab, setDrawerTab] = useState<'sop' | 'notifications'>('sop');
  const [cardProjectionState, setCardProjectionState] = useState<CardProjectionState>({ kind: 'idle' });
  const [formContextState, setFormContextState] = useState<FormManagementContextState>({ kind: 'idle' });
  const [notificationTimelineState, setNotificationTimelineState] = useState<NotificationTimelineState>({ kind: 'idle' });
  const [searchQuery, setSearchQuery] = useState('');
  const generationRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const drawerAbortRef = useRef<AbortController | null>(null);

  const fetchTrackerData = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    setSelectedOrder(null);
    setQueryState({ kind: 'loading' });
    setStageProjectionState({ kind: 'loading' });

    try {
      const [summaryResult, stageResult] = await Promise.allSettled([
        loadAllOrderSummaries(
          ordersQueryClient.getOrderSummaries.bind(ordersQueryClient),
          { page_size: 200, lifecycle_scope: 'unfinished' },
          { signal: controller.signal },
        ),
        loadAllOrderOperationalTimelines(
          orderStageProjectionClient.getOperationalTimelines.bind(orderStageProjectionClient),
          { page_size: 200, lifecycle_scope: 'unfinished' },
          { signal: controller.signal },
        ),
      ]);
      if (controller.signal.aborted || generation !== generationRef.current) return;
      if (summaryResult.status === 'rejected') throw summaryResult.reason;
      const page = summaryResult.value;
      const data = adaptOrderTrackerPage(page);
      setQueryState(data.loadedCount === 0 ? { kind: 'empty', data } : { kind: 'ready', data });
      if (stageResult.status === 'fulfilled') {
        try {
          const byCaseNo = indexOperationalTimelines(stageResult.value, page);
          setStageProjectionState({ kind: 'ready', page: stageResult.value, byCaseNo });
        } catch (error) {
          setStageProjectionState({
            kind: 'unavailable',
            message: error instanceof Error ? error.message : ORDER_STAGE_PROJECTION_UNAVAILABLE,
          });
        }
      } else {
        setStageProjectionState({
          kind: 'unavailable',
          message: ORDER_STAGE_PROJECTION_UNAVAILABLE,
        });
      }
    } catch (error) {
      if (controller.signal.aborted || generation !== generationRef.current) return;
      setStageProjectionState({ kind: 'unavailable', message: ORDER_STAGE_PROJECTION_UNAVAILABLE });
      setQueryState({
        kind: 'error',
        message: `訂單清單載入未完成：${error instanceof Error ? error.message : '載入訂單摘要失敗'}`,
      });
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) void fetchTrackerData();
    });
    return () => {
      cancelled = true;
      abortRef.current?.abort();
      drawerAbortRef.current?.abort();
      generationRef.current += 1;
    };
  }, [fetchTrackerData]);

  const resolvedData = queryState.kind === 'ready' || queryState.kind === 'empty'
    ? queryState.data
    : null;
  const selectedTimeline = selectedOrder && stageProjectionState.kind === 'ready'
    ? stageProjectionState.byCaseNo.get(selectedOrder.id) ?? null
    : null;
  const selectedCurrentStepOrdinal = selectedTimeline?.sop_steps.find(
    (step) => step.status === 'in_progress',
  )?.ordinal;

  const scrollToStage = (stageId: string) => {
    document.getElementById(`order-tracker-stage-${stageId}`)?.scrollIntoView({
      behavior: 'smooth',
      block: 'start',
    });
  };

  const trimmedQuery = searchQuery.trim().toLowerCase();
  const matchesSearch = useCallback(
    (order: TrackerOrderCardViewModel) => {
      if (!trimmedQuery) return true;
      return (
        order.id.toLowerCase().includes(trimmedQuery) ||
        order.clientName.toLowerCase().includes(trimmedQuery) ||
        order.assignedStaffDisplay.toLowerCase().includes(trimmedQuery)
      );
    },
    [trimmedQuery]
  );
  const visibleTrackerOrders = resolvedData?.unclassifiedOrders.filter(matchesSearch) ?? [];
  const visibleStageCount = (stageId: string): number => visibleTrackerOrders.filter(
    (order) => stageProjectionState.kind === 'ready'
      && stageProjectionState.byCaseNo.get(order.id)?.current_stage_code === stageId,
  ).length;

  const openOrder = (order: TrackerOrderCardViewModel) => {
    drawerAbortRef.current?.abort();
    const controller = new AbortController();
    drawerAbortRef.current = controller;
    setDrawerTab('sop');
    setSelectedOrder(order);
    setCardProjectionState({ kind: 'loading' });
    setFormContextState({ kind: 'loading' });
    setNotificationTimelineState({ kind: 'loading' });
    void Promise.allSettled([
      orderCardProjectionClient.getCardProjection(order.id, { signal: controller.signal }),
      ordersQueryClient.getFormManagementContext(order.id, { signal: controller.signal }),
      lineNotificationTimelineClient.query(order.id, { signal: controller.signal }),
    ]).then(([cardResult, formContextResult, notificationResult]) => {
      if (controller.signal.aborted || drawerAbortRef.current !== controller) return;
      setCardProjectionState(cardResult.status === 'fulfilled'
        ? { kind: 'ready', data: cardResult.value }
        : { kind: 'error', message: '案件聯絡與指派資料載入失敗，請重新開啟案件。' });
      setFormContextState(formContextResult.status === 'fulfilled'
        ? { kind: 'ready', data: formContextResult.value }
        : { kind: 'error', message: '客戶服務資料載入失敗，請重新開啟案件。' });
      setNotificationTimelineState(notificationResult.status === 'fulfilled'
        ? { kind: 'ready', data: notificationResult.value }
        : { kind: 'error', message: 'LINE 通知歷程載入失敗，請重新開啟案件。' });
    });
  };

  const closeOrder = () => {
    drawerAbortRef.current?.abort();
    drawerAbortRef.current = null;
    setSelectedOrder(null);
    setCardProjectionState({ kind: 'idle' });
    setFormContextState({ kind: 'idle' });
    setNotificationTimelineState({ kind: 'idle' });
  };

  const formatCardRange = (val: string) => {
    return val.replace(/（約定服務日期）$/, '').replace(/（實際服務日期）$/, '');
  };

  const renderTrackerCard = (order: TrackerOrderCardViewModel) => {
    const timeline = stageProjectionState.kind === 'ready'
      ? stageProjectionState.byCaseNo.get(order.id) ?? null
      : null;
    const stageCardState = stageProjectionState.kind === 'loading'
      ? { title: '階段資料載入中', summary: '正在載入七階段投影，尚未判定案件階段。' }
      : stageProjectionState.kind === 'unavailable'
        ? { title: '階段資料載入失敗', summary: stageProjectionState.message }
        : !timeline
          ? { title: '階段資料缺失', summary: '此案件未包含於目前的七階段投影，請重新載入摘要。' }
          : timeline.current_stage_code
            ? { title: '目前卡點／待辦', summary: currentStageSummary(timeline, order.waitingText) }
            : { title: '資料完整性異常', summary: currentStageSummary(timeline, order.waitingText) };
    const isAmountPending = order.contractAmountFormatted.includes('尚未登錄');
    return (
      <button
        type="button"
        key={order.id}
        className="pipeline-order-card"
        data-control-id={`order-tracker.card.${controlSafeCaseNo(order.id)}`}
        onClick={() => openOrder(order)}
        aria-label={`查看訂單 ${order.id} 的摘要與作業歷程`}
      >
        <div className="card-top-row">
          <span className="card-id-tag">{order.id}</span>
          <span className="card-days-tag">{order.serviceDaysLabel}</span>
        </div>
        <div className="card-client-row">
          <strong className="card-client-name">👤 {order.clientName}</strong>
          <span className={`card-amount-tag ${isAmountPending ? 'amount-pending' : ''}`}>
            {isAmountPending ? 'NT$ 待登錄' : order.contractAmountFormatted}
          </span>
        </div>
        <dl className="tracker-card-facts">
          <div><dt>目前訂單狀態</dt><dd>{order.rawOrderStatus}</dd></div>
          <div><dt>約定服務日期</dt><dd>{formatCardRange(order.plannedServiceRange)}</dd></div>
          <div><dt>實際服務日期</dt><dd>{formatCardRange(order.actualServiceRange)}</dd></div>
          <div><dt>正式指派月嫂</dt><dd>{order.assignedStaffDisplay}</dd></div>
        </dl>
        <div className="card-waiting-alert">
          <strong>{stageCardState.title}</strong>
          <span>{stageCardState.summary}</span>
        </div>
        <span className="tracker-card-link">查看摘要與作業歷程 ➔</span>
      </button>
    );
  };

  return (
    <div data-surface-id="order-tracker.page">
      <header className="tracker-page-header">
        <div>
          <h1 className="page-title">📊 訂單進度儀表板</h1>
          <p className="page-subtitle">
            依案件階段呈現待辦、作業歷程與結清狀態。
          </p>
        </div>
        <div className="tracker-header-actions">
          <div className="tracker-search-wrapper">
            <label className="tracker-search-input-box" htmlFor="tracker-query-search-input">
              <span className="tracker-search-icon" aria-hidden="true">🔍</span>
              <input
                id="tracker-query-search-input"
                aria-label="搜尋案件"
                data-control-id="order-tracker.query.search"
                value={searchQuery}
                maxLength={100}
                placeholder="案件編號或客戶名稱"
                onChange={(event) => setSearchQuery(event.target.value)}
              />
              {searchQuery && (
                <button
                  type="button"
                  className="tracker-search-clear-btn"
                  onClick={() => setSearchQuery('')}
                  aria-label="清除搜尋"
                  title="清除搜尋"
                >
                  ✕
                </button>
              )}
            </label>
          </div>
          <button
            type="button"
            className="tracker-reload-button"
            data-control-id="order-tracker.query.retry"
            onClick={() => void fetchTrackerData()}
          >
            重新載入摘要
          </button>
        </div>
      </header>

      {queryState.kind === 'loading' && (
        <div className="tracker-query-state" data-surface-id="order-tracker.query.loading" role="status">
          ⏳ 正在載入訂單摘要…
        </div>
      )}

      {queryState.kind === 'error' && (
        <div className="tracker-query-state tracker-query-error" data-surface-id="order-tracker.query.error" role="alert">
          <strong>載入訂單摘要失敗</strong>
          <span>{queryState.message}</span>
        </div>
      )}

      {resolvedData && (
        <>
          <nav className="pipeline-stepper-nav" aria-label="訂單七階段槽位">
            {resolvedData.stageSlots.map((slot) => (
              <button
                type="button"
                key={slot.id}
                className="pipeline-step-pill"
                data-control-id={`order-tracker.stage-nav.${slot.id}`}
                onClick={() => scrollToStage(slot.id)}
              >
                <span>{slot.title}</span>
                <span
                  className="pipeline-step-badge"
                  data-surface-id={`order-tracker.stage-count.${slot.id}`}
                  aria-label={`${slot.title}案件數${stageProjectionState.kind === 'ready' ? visibleStageCount(slot.id) : '待重新載入'}`}
                >
                  {stageProjectionState.kind === 'ready' ? visibleStageCount(slot.id) : '—'}
                </span>
              </button>
            ))}
          </nav>

          <section className="pipeline-vertical-container" aria-label="七階段服務流程">
            {resolvedData.stageSlots.map((slot) => {
              const stageOrders = visibleTrackerOrders.filter(
                (order) =>
                  stageProjectionState.kind === 'ready' &&
                  stageProjectionState.byCaseNo.get(order.id)?.current_stage_code === slot.id
              );
              return (
                <article
                  key={slot.id}
                  id={`order-tracker-stage-${slot.id}`}
                  className="pipeline-stage-section"
                  data-surface-id={`order-tracker.stage-slot.${slot.id}`}
                >
                  <div className="pipeline-stage-header">
                    <div className="pipeline-stage-title-wrap">
                      <h2 className="pipeline-stage-title">{slot.title}</h2>
                      <span className="pipeline-stage-desc">{slot.description}</span>
                    </div>
                    <span className="pipeline-stage-count" style={{ backgroundColor: slot.badgeColor, color: slot.textColor }}>
                      {stageProjectionState.kind === 'ready' ? `案件數 ${visibleStageCount(slot.id)}` : '—'}
                    </span>
                  </div>
                  {stageProjectionState.kind === 'ready' ? (
                    <>
                      <span className="sr-only">階段案件已載入</span>
                      {stageOrders.length > 0 ? (
                        <div className="pipeline-cards-grid" data-surface-id={`order-tracker.stage-orders.${slot.id}`}>
                          {stageOrders.map(renderTrackerCard)}
                        </div>
                      ) : (
                        <div className="stage-empty-state" data-surface-id={`order-tracker.stage-empty.${slot.id}`}>
                          <span className="stage-empty-icon">☕</span>
                          <span className="stage-empty-text">目前無案件停留於此階段</span>
                          <span className="stage-empty-hint">當案件推進至「{slot.title}」時將自動在此呈現</span>
                          <span className="sr-only">0 筆案件</span>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="tracker-unavailable-panel" data-surface-id={`order-tracker.stage-unavailable.${slot.id}`} role="status">
                      <strong>階段資料載入失敗</strong>
                      <span>{stageProjectionState.kind === 'unavailable' ? stageProjectionState.message : slot.unavailableMessage}</span>
                    </div>
                  )}
                </article>
              );
            })}
          </section>

          <section className="tracker-unclassified" data-surface-id="order-tracker.unclassified-orders">
            <div className="tracker-section-heading">
              <div>
                <h2>{stageProjectionState.kind === 'ready' ? '歷史資料待補正' : '訂單摘要'}</h2>
                <p>{stageProjectionState.kind === 'ready'
                  ? '這不是業務階段；僅隔離缺少正式資料、無法安全推進的歷史案件。請開啟案件查看待補項目，系統不會猜測分類。'
                  : '階段資料恢復後會自動歸入對應欄位。'}</p>
              </div>
              <div>
                <span className="tracker-loaded-count">已載入 {resolvedData.loadedCount} 筆</span>
              </div>
            </div>

            {queryState.kind === 'empty' ? (
              <div className="tracker-query-state" data-surface-id="order-tracker.query.empty">
                目前沒有訂單摘要。
              </div>
            ) : (
              <div className="pipeline-cards-grid">
                {visibleTrackerOrders
                  .filter(
                    (order) =>
                      (stageProjectionState.kind !== 'ready' ||
                        !stageProjectionState.byCaseNo.get(order.id)?.current_stage_code)
                  )
                  .map(renderTrackerCard)}
              </div>
            )}
          </section>
        </>
      )}

      <Drawer
        isOpen={selectedOrder !== null}
        onClose={closeOrder}
        size="wide"
        title={`📋 訂單作業進度 - ${selectedOrder?.id ?? ''}`}
        footer={(
          <div className="drawer-footer-actions">
            <button
              type="button"
              className="tracker-close-button"
              data-control-id="order-tracker.drawer.close"
              onClick={closeOrder}
            >
              關閉
            </button>
            <button
              type="button"
              className="tracker-action-primary-btn"
              onClick={() => {
                window.location.hash = '#finance';
              }}
            >
              <span>💳</span> 查看帳務作業
            </button>
          </div>
        )}
      >
        {selectedOrder && (
          <div className="tracker-drawer" data-surface-id="order-tracker.drawer">
            {/* Header Status & Order Identity Row */}
            <div className="drawer-header-status-row">
              <div className="drawer-title-group">
                <div className="drawer-title-capsule">
                  <h3 className="drawer-main-title">訂單作業進度</h3>
                  <span className="drawer-order-status-badge">{selectedOrder.rawOrderStatus}</span>
                </div>
                <p className="drawer-order-id-label">{selectedOrder.id}</p>
              </div>
            </div>

            {/* 4-Column Summary Info Row (Stitch Exact Pattern) */}
            <div className="drawer-summary-strip">
              <div className="drawer-summary-item">
                <div className="drawer-summary-icon">👤</div>
                <div className="drawer-summary-text">
                  <span className="drawer-summary-label">客戶</span>
                  <strong className="drawer-summary-val">{selectedOrder.clientName}</strong>
                </div>
              </div>
              <div className="drawer-summary-divider" />
              <div className="drawer-summary-item">
                <div className="drawer-summary-icon">📍</div>
                <div className="drawer-summary-text">
                  <span className="drawer-summary-label">服務區域</span>
                  <strong className="drawer-summary-val">{cardProjectionContactValue(cardProjectionState, 'contact_address')}</strong>
                </div>
              </div>
              <div className="drawer-summary-divider" />
              <div className="drawer-summary-item">
                <div className="drawer-summary-icon">💳</div>
                <div className="drawer-summary-text">
                  <span className="drawer-summary-label">合約總額</span>
                  <strong className="drawer-summary-val drawer-val-amount">{selectedOrder.contractAmountFormatted}</strong>
                </div>
              </div>
              <div className="drawer-summary-divider" />
              <div className="drawer-summary-item">
                <div className="drawer-summary-icon">👩‍🍼</div>
                <div className="drawer-summary-text">
                  <span className="drawer-summary-label">派案月嫂</span>
                  <strong className="drawer-summary-val drawer-val-staff">{selectedOrder.assignedStaffDisplay}</strong>
                </div>
              </div>
            </div>

            {/* Basic Order Facts Panel (Placed on Top) */}
            <section className="orders-card-projection-container" style={{ marginBottom: '18px' }}>
              <div className="card-projection-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <h3 className="card-projection-title">📝 案件基本資料與條件</h3>
                  <span className="card-projection-badge">正式案件資料</span>
                </div>
                <span className="panel-status-tag">{selectedOrder.rawOrderStatus}</span>
              </div>
              
              <div className="panel-sub-header" style={{ borderTop: 'none', margin: '10px 0 6px', paddingTop: 0 }}>
                <h4 style={{ fontSize: '0.86rem', color: '#8b7169', fontWeight: 700 }}>📌 核心案件與聯絡資訊</h4>
              </div>
              <dl className="tracker-drawer-facts card-projection-grid" style={{ margin: 0 }}>
                <div className="card-projection-item">
                  <dt className="card-projection-item-label">案件編號</dt>
                  <dd className="card-projection-item-value">{selectedOrder.id}</dd>
                </div>
                <div className="card-projection-item">
                  <dt className="card-projection-item-label">目前訂單狀態</dt>
                  <dd className="card-projection-item-value">{selectedOrder.rawOrderStatus}</dd>
                </div>
                <div className="card-projection-item">
                  <dt className="card-projection-item-label">聯絡電話</dt>
                  <dd className="card-projection-item-value">{cardProjectionContactValue(cardProjectionState, 'contact_phone')}</dd>
                </div>
                <div className="card-projection-item">
                  <dt className="card-projection-item-label">服務地址</dt>
                  <dd className="card-projection-item-value">{cardProjectionContactValue(cardProjectionState, 'contact_address')}</dd>
                </div>
                <div className="card-projection-item">
                  <dt className="card-projection-item-label">身分資格</dt>
                  <dd className="card-projection-item-value">{selectedOrder.identityStatus}</dd>
                </div>
                <div className="card-projection-item">
                  <dt className="card-projection-item-label">服務縣市</dt>
                  <dd className="card-projection-item-value">{formContextState.kind === 'ready' ? formContextState.data.city ?? '待確認' : formContextState.kind === 'error' ? '載入失敗' : '載入中…'}</dd>
                </div>
                <div className="card-projection-item">
                  <dt className="card-projection-item-label">服務類型</dt>
                  <dd className="card-projection-item-value">{formContextState.kind === 'ready' ? formContextState.data.service_type ?? '待確認' : formContextState.kind === 'error' ? '載入失敗' : '載入中…'}</dd>
                </div>
                <div className="card-projection-item">
                  <dt className="card-projection-item-label">每日服務時段</dt>
                  <dd className="card-projection-item-value">{formContextState.kind === 'ready' ? formContextState.data.service_time ?? '待確認' : formContextState.kind === 'error' ? '載入失敗' : '載入中…'}</dd>
                </div>
                <div className="card-projection-item">
                  <dt className="card-projection-item-label">生產方式</dt>
                  <dd className="card-projection-item-value">{formContextState.kind === 'ready' ? formContextState.data.delivery_type ?? '待確認' : formContextState.kind === 'error' ? '載入失敗' : '載入中…'}</dd>
                </div>
                <div className="card-projection-item">
                  <dt className="card-projection-item-label">住宅類型</dt>
                  <dd className="card-projection-item-value">{formContextState.kind === 'ready' ? formContextState.data.residence_type ?? '待確認' : formContextState.kind === 'error' ? '載入失敗' : '載入中…'}</dd>
                </div>
                <div className="card-projection-item">
                  <dt className="card-projection-item-label">約定服務日期</dt>
                  <dd className="card-projection-item-value">{selectedOrder.plannedServiceRange}</dd>
                </div>
                <div className="card-projection-item">
                  <dt className="card-projection-item-label">實際服務日期</dt>
                  <dd className="card-projection-item-value">{selectedOrder.actualServiceRange}</dd>
                </div>
                <div className="card-projection-item">
                  <dt className="card-projection-item-label">正式指派月嫂</dt>
                  <dd className="card-projection-item-value highlight-staff">{selectedOrder.assignedStaffDisplay}</dd>
                </div>
                <div className="card-projection-item">
                  <dt className="card-projection-item-label">契約應付金額</dt>
                  <dd className="card-projection-item-value highlight-amount">{selectedOrder.contractAmountFormatted}</dd>
                </div>
              </dl>

              {cardProjectionState.kind === 'loading' && (
                <p className="drawer-loading-note" role="status" style={{ marginTop: '12px' }}>
                  ⏳ 正在載入案件聯絡、定金與正式指派資料…
                </p>
              )}
              {cardProjectionState.kind === 'error' && (
                <p className="drawer-error-note" role="alert" style={{ marginTop: '12px' }}>
                  {cardProjectionState.message}
                </p>
              )}
              {cardProjectionState.kind === 'ready' && (
                <>
                  <div className="panel-sub-header" style={{ marginTop: '16px', paddingTop: '12px', borderTop: '1px dashed #fed9b8' }}>
                    <h4 style={{ fontSize: '0.86rem', color: '#8b7169', fontWeight: 700 }}>🍳 履約條件、定金與指派</h4>
                  </div>
                  <dl className="tracker-drawer-facts card-projection-grid" data-surface-id="order-tracker.card-projection" style={{ margin: 0 }}>
                    <div className="card-projection-item">
                      <dt className="card-projection-item-label">下廚料理</dt>
                      <dd className="card-projection-item-value">{cardProjectionValue(cardProjectionState.data.requires_cooking, (value) => value ? '需要' : '不需要', '尚未登錄')}</dd>
                    </div>
                    <div className="card-projection-item">
                      <dt className="card-projection-item-label">樓層加給</dt>
                      <dd className="card-projection-item-value">{cardProjectionValue(cardProjectionState.data.floor_fee_ntd, (value) => `NT$ ${value.toLocaleString('en-US')}`, '尚未登錄')}</dd>
                    </div>
                    <div className="card-projection-item">
                      <dt className="card-projection-item-label">定金狀態</dt>
                      <dd className="card-projection-item-value">{cardProjectionValue(cardProjectionState.data.deposit_settlement_state, (value) => value === 'settled' ? '已核銷' : '尚未核銷', '尚未登錄')}</dd>
                    </div>
                    <div className="card-projection-item">
                      <dt className="card-projection-item-label">實際服務日期</dt>
                      <dd className="card-projection-item-value">{cardProjectionValue(cardProjectionState.data.actual_start_date, String, '待確認')} ～ {cardProjectionValue(cardProjectionState.data.actual_end_date, String, '待確認')}</dd>
                    </div>
                    <div className="card-projection-item">
                      <dt className="card-projection-item-label">正式指派分段</dt>
                      <dd className="card-projection-item-value">{cardProjectionValue(cardProjectionState.data.assignment_segments, (value) => `${value.length} 段`, '0 段')}</dd>
                    </div>
                  </dl>
                </>
              )}
            </section>

            {/* Tabs (Underline Navigation Style) */}
            <div className="tracker-tabs-stitch" role="tablist" aria-label="訂單作業歷程內容">
              <button
                type="button"
                role="tab"
                className={`tracker-tab-btn ${drawerTab === 'sop' ? 'active' : ''}`}
                aria-selected={drawerTab === 'sop'}
                data-control-id="order-tracker.drawer.tab.sop"
                onClick={() => setDrawerTab('sop')}
              >
                11 步 SOP 檢核
              </button>
              <button
                type="button"
                role="tab"
                className={`tracker-tab-btn ${drawerTab === 'notifications' ? 'active' : ''}`}
                aria-selected={drawerTab === 'notifications'}
                data-control-id="order-tracker.drawer.tab.notifications"
                onClick={() => setDrawerTab('notifications')}
              >
                LINE 通知紀錄與發送狀態
              </button>
            </div>

            {drawerTab === 'sop' ? (
              <div className="tracker-tab-content-sop" data-surface-id={selectedTimeline ? 'order-tracker.sop.typed' : 'order-tracker.sop.unavailable'}>
                {/* Hidden stage projection indicator for accessibility & tests */}
                {selectedTimeline && (
                  <div data-surface-id="order-tracker.typed-stage-projection" className="sr-only">
                    <span>七階段作業狀態</span>
                    <span>目前業務階段：{currentStageLabel(selectedTimeline)}</span>
                  </div>
                )}

                {/* 11 Steps Complete Detail SOP Timeline */}
                <section className="tracker-summary-panel">
                  <div className="panel-header-row">
                    <h3 className="panel-title">📋 工會因果鏈 11 步驟標準作業完整檢核</h3>
                  </div>
                  {selectedTimeline ? (
                    <div className="tracker-sop-timeline" role="list" aria-label="11 步 SOP 狀態">
                      {selectedTimeline.sop_steps.map((step) => {
                        const isCurrent = step.ordinal === selectedCurrentStepOrdinal;
                        const isCompleted = step.status === 'completed';
                        return (
                          <article
                            key={step.ordinal}
                            role="listitem"
                            className={`tracker-sop-step tracker-sop-step--${step.status} ${isCurrent ? 'tracker-sop-step--current' : ''}`}
                            data-surface-id={`order-tracker.sop.step.${step.ordinal}`}
                            data-status={step.status}
                            aria-current={isCurrent ? 'step' : undefined}
                          >
                            <div className="tracker-sop-node-track">
                              <div className="tracker-sop-node-line" />
                              <div className="tracker-sop-number">
                                {isCompleted ? (
                                  <>
                                    <input
                                      type="checkbox"
                                      checked
                                      disabled
                                      className="sr-only"
                                      aria-label={`步驟 ${step.ordinal} 已完成`}
                                    />
                                    <span className="sop-done-check">✓</span>
                                  </>
                                ) : (
                                  step.ordinal
                                )}
                              </div>
                            </div>
                            <div className="tracker-sop-card-body">
                              <div className="tracker-sop-header-row">
                                <div className="tracker-sop-title-wrap">
                                  <span className="tracker-sop-step-tag">步驟 {step.ordinal}</span>
                                  <h4 className="tracker-sop-title">{step.label}</h4>
                                </div>
                                <div className="tracker-sop-status-pill-wrap">
                                  {isCurrent && <span className="sop-current-pill">🎯 <span>目前執行</span></span>}
                                  <span className={`tracker-sop-status tracker-sop-status--${step.status}`}>
                                    {isCompleted && '🟢 '}
                                    {step.status === 'in_progress' && '🟠 '}
                                    {step.status === 'blocked' && '🔴 '}
                                    {(step.status === 'not_started' || step.status === 'unavailable') && '⚪ '}
                                    {stageStatusLabel(step.status)}
                                  </span>
                                </div>
                              </div>

                              <div className="tracker-sop-meta-row">
                                <span className="tracker-sop-owner">🏢 {businessOwnerLabel(step.owner)}</span>
                                <span className="tracker-sop-time">🕒 {formatFriendlyTimestamp(step.occurred_at)}</span>
                              </div>

                              {(step.blockers[0]?.message || step.warnings[0]?.message || stageAvailabilityLabel(step.availability_reason)) && (
                                <div className={`tracker-sop-callout ${step.status === 'blocked' ? 'callout--blocked' : 'callout--info'}`}>
                                  <span className="callout-icon">{step.status === 'blocked' ? '⚠️' : 'ℹ️'}</span>
                                  <p>
                                    {step.blockers[0]?.message
                                      ?? step.warnings[0]?.message
                                      ?? stageAvailabilityLabel(step.availability_reason)}
                                  </p>
                                </div>
                              )}

                              {/* Step 11 Embedded 3 Settlement Cards */}
                              {step.ordinal === 11 && (
                                <div className="step-11-settlement-wrap">
                                  <div className="step-info-callout">
                                    <span className="step-info-icon">ℹ️</span>
                                    <p className="step-info-text">三大獨立結算投影：服務履約、客戶款項與月嫂薪資獨立推進。</p>
                                  </div>
                                  <div className="tracker-settlement-grid" aria-label="三個獨立結清投影">
                                    {(stageByCode(selectedTimeline, 'settlement_payout')?.settlement ?? []).map((slot) => {
                                      const isSlotCompleted = slot.status === 'completed';
                                      const titleMap: Record<string, string> = {
                                        'service-completion': '服務履約：服務已完成',
                                        service_completion: '服務履約',
                                        'client-finance': '客戶款項：尾款待銀行核銷',
                                        client_settlement: '客戶款項',
                                        'staff-payroll': '月嫂薪資：薪資待出款核銷',
                                        staff_payout: '月嫂薪資',
                                      };
                                      const iconMap: Record<string, string> = {
                                        'service-completion': '✅',
                                        'client-finance': '📋',
                                        'staff-payroll': '⏳',
                                      };
                                      return (
                                        <article
                                          key={slot.code}
                                          className={`settlement-card ${isSlotCompleted ? 'settlement-card--completed' : 'settlement-card--pending'}`}
                                          data-surface-id={`order-tracker.settlement.${slot.code}`}
                                        >
                                          <div className="settlement-card-icon">
                                            {iconMap[slot.code] ?? '📄'}
                                          </div>
                                          <div className="settlement-card-main">
                                            <div className="settlement-card-top">
                                              <h4 className="settlement-card-title">{titleMap[slot.code] ?? slot.code}</h4>
                                              <span className="settlement-card-time">
                                                最後更新: {formatProjectionTimestamp(slot.occurred_at)}
                                              </span>
                                            </div>
                                            <p className="settlement-card-desc">
                                              {stageStatusLabel(slot.status)}
                                              {slot.availability_reason ? ` · ${stageAvailabilityLabel(slot.availability_reason)}` : ''}
                                              {slot.source.owner ? `（負責：${businessOwnerLabel(slot.source.owner)}）` : ''}
                                            </p>
                                          </div>
                                          <span className="settlement-card-link">查看明細 →</span>
                                        </article>
                                      );
                                    })}
                                  </div>
                                </div>
                              )}
                            </div>
                          </article>
                        );
                      })}
                    </div>
                  ) : (
                    <p role={stageProjectionState.kind === 'loading' ? 'status' : 'alert'}>
                      {stageProjectionState.kind === 'loading'
                        ? '正在載入 11 步 SOP…'
                        : stageProjectionState.kind === 'unavailable'
                          ? stageProjectionState.message
                          : '此案件缺少正式作業歷程資料，請重新載入摘要。'}
                    </p>
                  )}
                </section>
              </div>
            ) : (
              <section className="tracker-tab-panel" role="tabpanel" data-surface-id="order-tracker.notifications.timeline">
                <div className="panel-header-row">
                  <h3 className="panel-title">🔔 訂單生命週期通知紀錄</h3>
                  {notificationTimelineState.kind === 'ready' && notificationTimelineState.data.records.length > 0 && (
                    <span className="panel-status-tag">
                      共 {notificationTimelineState.data.records.length} 則通知
                    </span>
                  )}
                </div>
                {notificationTimelineState.kind === 'loading' && <p role="status">正在載入 LINE 通知歷程…</p>}
                {notificationTimelineState.kind === 'error' && <p role="alert">{notificationTimelineState.message}</p>}
                {notificationTimelineState.kind === 'ready' && notificationTimelineState.data.records.length === 0 && (
                  <p className="no-records-note">目前沒有 LINE 通知紀錄。</p>
                )}
                {notificationTimelineState.kind === 'ready' && notificationTimelineState.data.records.length > 0 && (
                  <div className="line-notification-list">
                    {notificationTimelineState.data.records.map((record) => {
                      const deliveryStatus = record.delivery_status ?? '未建立';
                      const isDelivered = deliveryStatus === 'delivered' || deliveryStatus === 'sent' || deliveryStatus === '發送成功' || deliveryStatus === '已送達';
                      const isRead = deliveryStatus === 'read' || deliveryStatus === '已讀';
                      const isFailed = deliveryStatus === 'failed' || deliveryStatus === '發送失敗';
                      return (
                        <article key={`${record.source_event_id}-${record.occurrence_number ?? 0}`} className="notification-card">
                          <div className="notification-card-header">
                            <div className="notification-event-group">
                              <span className="notification-icon">💬</span>
                              <span className="notification-badge-event">{record.event_code}</span>
                            </div>
                            <span className={`notification-badge-delivery ${isDelivered ? 'delivery--success' : isRead ? 'delivery--read' : isFailed ? 'delivery--failed' : 'delivery--neutral'}`}>
                              {isDelivered ? '🟢 發送成功' : isRead ? '🔵 已讀' : isFailed ? '🔴 發送失敗' : deliveryStatus}
                            </span>
                          </div>

                          <div className="notification-meta-row">
                            <span className="notification-recipient">
                              對象：{record.recipient_type === 'staff' ? '👩‍🍼 月嫂' : '👤 客戶'}（{record.recipient_masked ?? '未指定'}）
                            </span>
                            <span className="notification-time">
                              🕒 {record.occurred_at_utc ? formatFriendlyTimestamp(record.occurred_at_utc) : '未記錄'}
                            </span>
                          </div>

                          <div className="notification-bubble">
                            <p className="notification-bubble-text">
                              決策：{record.decision_status ?? '未產生'} ｜ 通知意圖：{record.intent_status ?? '未建立'}
                            </p>
                            {record.reason_code && (
                              <p className="notification-bubble-reason">原因代碼：{record.reason_code}</p>
                            )}
                          </div>
                        </article>
                      );
                    })}
                  </div>
                )}
              </section>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default OrderTrackerPage;

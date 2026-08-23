/**
 * File: OrderTrackerPage.tsx
 * Description: 顯示訂單七階段、案件卡片投影三態、SOP、結清與 LINE 通知唯讀歷程。
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { adaptOrderTrackerPage, type OrderTrackerPageViewModel, type TrackerOrderCardViewModel } from '../adapters/orders/order_tracker_adapter';
import {
  ORDER_STAGE_PROJECTION_UNAVAILABLE,
  formatProjectionTimestamp,
  indexOperationalTimelines,
  stageByCode,
  stageAvailabilityLabel,
  stageCount,
  stageStatusLabel,
} from '../adapters/orders/order_stage_projection_adapter';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { orderCardProjectionClient } from '../api/orders/order_card_projection_client';
import type { OrdersCardProjection } from '../api/orders/order_card_projection_schemas';
import { orderStageProjectionClient } from '../api/orders/order_stage_projection_client';
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

type TrackerNextPageState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'error'; message: string };

type CardProjectionState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ready'; data: OrdersCardProjection }
  | { kind: 'error'; message: string };

type NotificationTimelineState =
  | { kind: 'idle' | 'loading' }
  | { kind: 'ready'; data: LineNotificationTimeline }
  | { kind: 'error'; message: string };

function mergeSummaryPages(
  current: import('../api/orders/order_query_schemas').OrderSummaryPage,
  next: import('../api/orders/order_query_schemas').OrderSummaryPage,
): import('../api/orders/order_query_schemas').OrderSummaryPage {
  const itemsByCaseNo = new Map(current.items.map((item) => [item.case_no, item]));
  for (const item of next.items) itemsByCaseNo.set(item.case_no, item);
  return {
    items: [...itemsByCaseNo.values()],
    next_cursor: next.next_cursor,
    etag: next.etag,
  };
}

function mergeStageProjectionPages(
  current: OrderOperationalTimelinePage,
  next: OrderOperationalTimelinePage,
): OrderOperationalTimelinePage {
  const itemsByCaseNo = new Map(current.items.map((item) => [item.case_no, item]));
  for (const item of next.items) itemsByCaseNo.set(item.case_no, item);
  return {
    items: [...itemsByCaseNo.values()],
    stage_counts: {
      intake_terms: current.stage_counts.intake_terms + next.stage_counts.intake_terms,
      matching_willingness: current.stage_counts.matching_willingness + next.stage_counts.matching_willingness,
      client_review: current.stage_counts.client_review + next.stage_counts.client_review,
      contract_deposit: current.stage_counts.contract_deposit + next.stage_counts.contract_deposit,
      date_confirmation: current.stage_counts.date_confirmation + next.stage_counts.date_confirmation,
      active_service: current.stage_counts.active_service + next.stage_counts.active_service,
      settlement_payout: current.stage_counts.settlement_payout + next.stage_counts.settlement_payout,
    },
    next_cursor: next.next_cursor,
    etag: next.etag,
  };
}

function controlSafeCaseNo(caseNo: string): string {
  return encodeURIComponent(caseNo);
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
    const reason = stageAvailabilityLabel(field.availability_reason) ?? `${field.owner} 尚無可用投影`;
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

export const OrderTrackerPage: React.FC = () => {
  const [queryState, setQueryState] = useState<TrackerQueryState>({ kind: 'loading' });
  const [stageProjectionState, setStageProjectionState] = useState<StageProjectionQueryState>({ kind: 'loading' });
  const [nextPageState, setNextPageState] = useState<TrackerNextPageState>({ kind: 'idle' });
  const [selectedOrder, setSelectedOrder] = useState<TrackerOrderCardViewModel | null>(null);
  const [drawerTab, setDrawerTab] = useState<'sop' | 'notifications'>('sop');
  const [cardProjectionState, setCardProjectionState] = useState<CardProjectionState>({ kind: 'idle' });
  const [notificationTimelineState, setNotificationTimelineState] = useState<NotificationTimelineState>({ kind: 'idle' });
  const generationRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const nextPageAbortRef = useRef<AbortController | null>(null);
  const pendingCursorRef = useRef<string | null>(null);
  const summaryPageRef = useRef<import('../api/orders/order_query_schemas').OrderSummaryPage | null>(null);
  const drawerAbortRef = useRef<AbortController | null>(null);

  const fetchTrackerData = useCallback(async () => {
    abortRef.current?.abort();
    nextPageAbortRef.current?.abort();
    pendingCursorRef.current = null;
    const controller = new AbortController();
    abortRef.current = controller;
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    setSelectedOrder(null);
    setQueryState({ kind: 'loading' });
    setStageProjectionState({ kind: 'loading' });
    setNextPageState({ kind: 'idle' });

    try {
      const [summaryResult, stageResult] = await Promise.allSettled([
        ordersQueryClient.getOrderSummaries({}, { signal: controller.signal }),
        orderStageProjectionClient.getOperationalTimelines({ page_size: 50 }, { signal: controller.signal }),
      ]);
      if (controller.signal.aborted || generation !== generationRef.current) return;
      if (summaryResult.status === 'rejected') throw summaryResult.reason;
      const page = summaryResult.value;
      summaryPageRef.current = page;
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
        message: error instanceof Error ? error.message : '載入訂單摘要失敗',
      });
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  }, []);

  const fetchNextTrackerPage = useCallback(async () => {
    const cursor = summaryPageRef.current?.next_cursor;
    if (!cursor || pendingCursorRef.current === cursor) return;
    nextPageAbortRef.current?.abort();
    const controller = new AbortController();
    nextPageAbortRef.current = controller;
    pendingCursorRef.current = cursor;
    setNextPageState({ kind: 'loading' });

    try {
      const [summaryResult, stageResult] = await Promise.allSettled([
        ordersQueryClient.getOrderSummaries({ after_case_no: cursor }, { signal: controller.signal }),
        orderStageProjectionClient.getOperationalTimelines({ page_size: 50, after_case_no: cursor }, { signal: controller.signal }),
      ]);
      if (controller.signal.aborted || pendingCursorRef.current !== cursor) return;
      if (summaryResult.status === 'rejected') throw summaryResult.reason;

      const currentPage = summaryPageRef.current;
      if (!currentPage || currentPage.next_cursor !== cursor) return;
      const nextPage = summaryResult.value;
      const mergedPage = mergeSummaryPages(currentPage, nextPage);
      summaryPageRef.current = mergedPage;
      const data = adaptOrderTrackerPage(mergedPage);
      setQueryState(data.loadedCount === 0 ? { kind: 'empty', data } : { kind: 'ready', data });

      if (stageResult.status === 'fulfilled') {
        try {
          const nextIndex = indexOperationalTimelines(stageResult.value, nextPage);
          setStageProjectionState((current) => {
            const byCaseNo = current.kind === 'ready'
              ? new Map([...current.byCaseNo, ...nextIndex])
              : new Map(nextIndex);
            const page = current.kind === 'ready'
              ? mergeStageProjectionPages(current.page, stageResult.value)
              : stageResult.value;
            return { kind: 'ready', page, byCaseNo };
          });
        } catch (stageError) {
          setStageProjectionState({
            kind: 'unavailable',
            message: stageError instanceof Error ? stageError.message : ORDER_STAGE_PROJECTION_UNAVAILABLE,
          });
        }
      } else {
        setStageProjectionState({
          kind: 'unavailable',
          message: ORDER_STAGE_PROJECTION_UNAVAILABLE,
        });
      }
      setNextPageState({ kind: 'idle' });
    } catch (error) {
      if (!controller.signal.aborted && pendingCursorRef.current === cursor) {
        setNextPageState({ kind: 'error', message: error instanceof Error ? error.message : '載入下一頁訂單失敗' });
      }
    } finally {
      if (pendingCursorRef.current === cursor) {
        pendingCursorRef.current = null;
        nextPageAbortRef.current = null;
        setNextPageState((current) => current.kind === 'loading' ? { kind: 'idle' } : current);
      }
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
      nextPageAbortRef.current?.abort();
      drawerAbortRef.current?.abort();
      generationRef.current += 1;
      pendingCursorRef.current = null;
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

  const openOrder = (order: TrackerOrderCardViewModel) => {
    drawerAbortRef.current?.abort();
    const controller = new AbortController();
    drawerAbortRef.current = controller;
    setDrawerTab('sop');
    setSelectedOrder(order);
    setCardProjectionState({ kind: 'loading' });
    setNotificationTimelineState({ kind: 'loading' });
    void Promise.allSettled([
      orderCardProjectionClient.getCardProjection(order.id, { signal: controller.signal }),
      lineNotificationTimelineClient.query(order.id, { signal: controller.signal }),
    ]).then(([cardResult, notificationResult]) => {
      if (controller.signal.aborted || drawerAbortRef.current !== controller) return;
      setCardProjectionState(cardResult.status === 'fulfilled'
        ? { kind: 'ready', data: cardResult.value }
        : { kind: 'error', message: '案件聯絡與指派資料載入失敗，請重新開啟案件。' });
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
          <div><dt>原始訂單狀態</dt><dd>{order.rawOrderStatus}</dd></div>
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
        <button
          type="button"
          className="tracker-reload-button"
          data-control-id="order-tracker.query.retry"
          onClick={() => void fetchTrackerData()}
        >
          重新載入摘要
        </button>
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
                  aria-label={`${slot.title}案件數${stageProjectionState.kind === 'ready' ? stageCount(stageProjectionState.page, slot.id) : '待重新載入'}`}
                >
                  {stageProjectionState.kind === 'ready' ? stageCount(stageProjectionState.page, slot.id) : '—'}
                </span>
              </button>
            ))}
          </nav>

          <section className="pipeline-vertical-container" aria-label="七階段服務流程">
            {resolvedData.stageSlots.map((slot) => {
              const stageOrders = resolvedData.unclassifiedOrders.filter(
                (order) => stageProjectionState.kind === 'ready' && stageProjectionState.byCaseNo.get(order.id)?.current_stage_code === slot.id
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
                      {stageProjectionState.kind === 'ready' ? `案件數 ${stageCount(stageProjectionState.page, slot.id)}` : '—'}
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
                  ? '這不是業務階段；僅隔離缺少正式根事實、無法安全推進的歷史資料。請開啟案件查看缺失 owner，系統不會猜測分類。'
                  : '階段資料恢復後會自動歸入對應欄位。'}</p>
              </div>
              <div>
                <span className="tracker-loaded-count">已載入 {resolvedData.loadedCount} 筆</span>
                {resolvedData.nextCursor && (
                  <button
                    type="button"
                    className="tracker-reload-button"
                    data-control-id="order-tracker.query.next-page"
                    disabled={nextPageState.kind === 'loading'}
                    onClick={() => void fetchNextTrackerPage()}
                  >
                    {nextPageState.kind === 'loading' ? '正在載入下一頁…' : '載入下一頁'}
                  </button>
                )}
                {nextPageState.kind === 'error' && (
                  <div role="alert">
                    <span>載入下一頁失敗：{nextPageState.message}</span>
                    <button type="button" data-control-id="order-tracker.query.next-page.retry" onClick={() => void fetchNextTrackerPage()}>
                      重試下一頁
                    </button>
                  </div>
                )}
              </div>
            </div>

            {queryState.kind === 'empty' ? (
              <div className="tracker-query-state" data-surface-id="order-tracker.query.empty">
                目前沒有訂單摘要。
              </div>
            ) : (
              <div className="pipeline-cards-grid">
                {resolvedData.unclassifiedOrders
                  .filter((order) => stageProjectionState.kind !== 'ready' || !stageProjectionState.byCaseNo.get(order.id)?.current_stage_code)
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
        title={`📋 訂單關鍵 SOP 檢核抽屜 - ${selectedOrder?.id ?? ''}`}
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
                  <h3 className="drawer-main-title">訂單關鍵 SOP 檢核抽屜</h3>
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
                  <strong className="drawer-summary-val">{cardProjectionContactValue(cardProjectionState, 'contact_address') || '台北市'}</strong>
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
            <section className="tracker-summary-panel">
              <div className="panel-header-row">
                <h3 className="panel-title">📝 案件基本資料與條件</h3>
                <span className="panel-status-tag">{selectedOrder.rawOrderStatus}</span>
              </div>
              <dl className="tracker-drawer-facts">
                <div><dt>案件編號</dt><dd>{selectedOrder.id}</dd></div>
                <div><dt>原始訂單狀態</dt><dd>{selectedOrder.rawOrderStatus}</dd></div>
                <div><dt>聯絡電話</dt><dd>{cardProjectionContactValue(cardProjectionState, 'contact_phone')}</dd></div>
                <div><dt>服務地址</dt><dd>{cardProjectionContactValue(cardProjectionState, 'contact_address')}</dd></div>
                <div><dt>約定服務日期</dt><dd>{selectedOrder.plannedServiceRange}</dd></div>
                <div><dt>實際服務日期</dt><dd>{selectedOrder.actualServiceRange}</dd></div>
                <div><dt>正式指派月嫂</dt><dd className="highlight-staff">{selectedOrder.assignedStaffDisplay}</dd></div>
                <div><dt>契約應付金額</dt><dd className="highlight-amount">{selectedOrder.contractAmountFormatted}</dd></div>
              </dl>
              {cardProjectionState.kind === 'loading' && <p className="drawer-loading-note" role="status">正在載入案件聯絡、定金與正式指派資料…</p>}
              {cardProjectionState.kind === 'error' && <p className="drawer-error-note" role="alert">{cardProjectionState.message}</p>}
              {cardProjectionState.kind === 'ready' && (
                <>
                  <div className="panel-sub-header">
                    <h4>🍳 履約條件與加給</h4>
                  </div>
                  <dl className="tracker-drawer-facts" data-surface-id="order-tracker.card-projection">
                    <div><dt>下廚料理</dt><dd>{cardProjectionValue(cardProjectionState.data.requires_cooking, (value) => value ? '需要' : '不需要', '尚未登錄')}</dd></div>
                    <div><dt>樓層加給</dt><dd>{cardProjectionValue(cardProjectionState.data.floor_fee_ntd, (value) => `NT$ ${value.toLocaleString('en-US')}`, '尚未登錄')}</dd></div>
                    <div><dt>定金狀態</dt><dd>{cardProjectionValue(cardProjectionState.data.deposit_settlement_state, (value) => value === 'settled' ? '已核銷' : '尚未核銷', '尚未登錄')}</dd></div>
                    <div><dt>實際服務日期</dt><dd>{cardProjectionValue(cardProjectionState.data.actual_start_date, String, '待確認')} ～ {cardProjectionValue(cardProjectionState.data.actual_end_date, String, '待確認')}</dd></div>
                    <div><dt>正式指派分段</dt><dd>{cardProjectionValue(cardProjectionState.data.assignment_segments, (value) => `${value.length} 段`, '0 段')}</dd></div>
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
                    <span>目前階段：{selectedTimeline.current_stage_code ?? '待判定'}；資料版本：{selectedTimeline.base_revision}</span>
                  </div>
                )}

                {/* Horizontal Compact Steps Progress (Steps 1-10) */}
                <div className="steps-progress-indicator">
                  <div className="steps-progress-chain">
                    <div className="step-circle step-circle--done">✓</div>
                    <div className="step-chain-line step-chain-line--done" />
                    <div className="step-circle step-circle--done">✓</div>
                    <div className="step-chain-line step-chain-line--done" />
                    <div className="step-pill-middle">... (步驟 3-9)</div>
                    <div className="step-chain-line step-chain-line--done" />
                    <div className="step-circle step-circle--done">✓</div>
                  </div>
                  <div className="steps-progress-label">步驟 1-10 已完成</div>
                </div>

                {/* Step 11 Expanded Section */}
                <section className="step-expanded-section">
                  <div className="step-expanded-header">
                    <div className="step-expanded-badge">11</div>
                    <h3 className="step-expanded-title">完工後續處理</h3>
                  </div>

                  {/* Warning / Info Callout Box */}
                  <div className="step-info-callout">
                    <span className="step-info-icon">ℹ️</span>
                    <p className="step-info-text">此案服務已完成，但帳務尚未全部結清。</p>
                  </div>

                  {/* 3 Independent Settlement Cards */}
                  {selectedTimeline && (
                    <div className="tracker-settlement-grid" aria-label="三個獨立結清投影">
                      {(stageByCode(selectedTimeline, 'settlement_payout')?.settlement ?? []).map((slot) => {
                        const isCompleted = slot.status === 'completed';
                        const titleMap: Record<string, string> = {
                          'service-completion': '服務履約：服務已完成',
                          'client-finance': '客戶款項：尾款待銀行核銷',
                          'staff-payroll': '月嫂薪資：薪資待出款核銷',
                        };
                        const iconMap: Record<string, string> = {
                          'service-completion': '✅',
                          'client-finance': '📋',
                          'staff-payroll': '⏳',
                        };
                        return (
                          <article
                            key={slot.code}
                            className={`settlement-card ${isCompleted ? 'settlement-card--completed' : 'settlement-card--pending'}`}
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
                                {slot.source.owner ? ` (owner: ${slot.source.owner})` : ''}
                              </p>
                            </div>
                            <span className="settlement-card-link">查看明細 →</span>
                          </article>
                        );
                      })}
                    </div>
                  )}
                </section>

                {/* 11 Steps Complete Detail SOP List */}
                <section className="tracker-summary-panel">
                  <div className="panel-header-row">
                    <h3 className="panel-title">📋 工會因果鏈 11 步驟標準作業完整檢核</h3>
                  </div>
                  {selectedTimeline ? (
                    <div className="tracker-sop-list" role="list" aria-label="11 步 SOP 狀態">
                      {selectedTimeline.sop_steps.map((step) => (
                        <article
                          key={step.ordinal}
                          role="listitem"
                          className={`tracker-sop-step tracker-sop-step--${step.status}`}
                          data-surface-id={`order-tracker.sop.step.${step.ordinal}`}
                          data-status={step.status}
                          aria-current={step.ordinal === selectedCurrentStepOrdinal ? 'step' : undefined}
                        >
                          <span className="tracker-sop-number">
                            {step.status === 'completed' ? (
                              <input
                                type="checkbox"
                                checked
                                disabled
                                aria-label={`步驟 ${step.ordinal} 已完成`}
                              />
                            ) : step.ordinal}
                          </span>
                          <div className="tracker-sop-body">
                            <div className="tracker-sop-title-row">
                              <h4>{step.label}</h4>
                              {step.ordinal === selectedCurrentStepOrdinal && <strong>目前執行</strong>}
                            </div>
                            <p>
                              {step.blockers[0]?.message
                                ?? step.warnings[0]?.message
                                ?? stageAvailabilityLabel(step.availability_reason)
                                ?? `owner：${step.owner}`}
                            </p>
                            <span className={`tracker-sop-status tracker-sop-status--${step.status}`}>
                              {stageStatusLabel(step.status)}　{formatProjectionTimestamp(step.occurred_at)}
                            </span>
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <p role={stageProjectionState.kind === 'loading' ? 'status' : 'alert'}>
                      {stageProjectionState.kind === 'loading'
                        ? '正在載入 11 步 SOP…'
                        : stageProjectionState.kind === 'unavailable'
                          ? stageProjectionState.message
                          : '此案件缺少 typed 作業歷程 identity，請重新載入摘要。'}
                    </p>
                  )}
                </section>
              </div>
            ) : (
              <section className="tracker-tab-panel" role="tabpanel" data-surface-id="order-tracker.notifications.timeline">
                <div className="panel-header-row">
                  <h3 className="panel-title">🔔 訂單生命週期通知紀錄</h3>
                </div>
                {notificationTimelineState.kind === 'loading' && <p role="status">正在載入 LINE 通知歷程…</p>}
                {notificationTimelineState.kind === 'error' && <p role="alert">{notificationTimelineState.message}</p>}
                {notificationTimelineState.kind === 'ready' && notificationTimelineState.data.records.length === 0 && (
                  <p className="no-records-note">目前沒有 LINE 通知紀錄。</p>
                )}
                {notificationTimelineState.kind === 'ready' && (
                  <div className="line-notification-list">
                    {notificationTimelineState.data.records.map((record) => (
                      <article key={`${record.source_event_id}-${record.occurrence_number ?? 0}`} className="notification-card">
                        <div className="notification-card-header">
                          <span className="notification-badge-event">{record.event_code}</span>
                          <span className="notification-badge-delivery">{record.delivery_status ?? '未建立'}</span>
                        </div>
                        <div className="notification-card-body">
                          <p>決策：{record.decision_status ?? '未產生'} ｜ 通知意圖：{record.intent_status ?? '未建立'}</p>
                          <p>收件者：{record.recipient_masked ?? '未指定'} ｜ 時間：{record.occurred_at_utc ? formatProjectionTimestamp(record.occurred_at_utc) : '未記錄'}</p>
                        </div>
                      </article>
                    ))}
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

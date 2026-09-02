/**
 * File: order_tracker_real_data.test.tsx
 * Description: 驗證 Tracker 未完成／已完成案件、七階段、卡片投影、11 步 SOP、cursor 續頁與唯讀 LINE 歷程。
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { orderStageProjectionClient } from '../api/orders/order_stage_projection_client';
import { orderCardProjectionClient } from '../api/orders/order_card_projection_client';
import { lineNotificationTimelineClient } from '../api/line/notification_timeline_client';
import { ORDER_STAGE_PROJECTION_UNAVAILABLE } from '../adapters/orders/order_stage_projection_adapter';
import { OrderTrackerPage } from '../pages/OrderTrackerPage';
import { realisticFormManagementContext, realisticOrderSummaryPage } from './fixtures/orders_real_data_fixtures';
import { buildOrdersStageProjectionFixture } from './fixtures/orders_stage_projection_fixtures';

function surface(prefix: string): HTMLElement[] {
  return Array.from(document.querySelectorAll(`[data-surface-id^="${prefix}"]`));
}

describe('OrderTrackerPage query-only presentation', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue(realisticOrderSummaryPage);
    vi.spyOn(orderStageProjectionClient, 'getOperationalTimelines').mockRejectedValue(
      new Error(ORDER_STAGE_PROJECTION_UNAVAILABLE),
    );
    vi.spyOn(orderCardProjectionClient, 'getCardProjection').mockRejectedValue(new Error('card query fixture'));
    vi.spyOn(ordersQueryClient, 'getFormManagementContext').mockResolvedValue(realisticFormManagementContext);
    vi.spyOn(lineNotificationTimelineClient, 'query').mockResolvedValue({ case_no: 'ORD-2026-0801', records: [] });
  });

  it('renders seven stage slots and keeps summaries in a separate region when stage query fails', async () => {
    render(<OrderTrackerPage />);
    await waitFor(() => expect(screen.getByText('訂單摘要')).toBeInTheDocument());

    expect(surface('order-tracker.stage-slot.')).toHaveLength(7);
    expect(surface('order-tracker.stage-count.')).toHaveLength(7);
    expect(surface('order-tracker.stage-unavailable.')).toHaveLength(7);
    for (const panel of surface('order-tracker.stage-unavailable.')) {
      expect(panel).toHaveTextContent(ORDER_STAGE_PROJECTION_UNAVAILABLE);
    }
    expect(screen.queryByText(/目前無案件停留於此階段/)).not.toBeInTheDocument();
    expect(screen.queryByText(/1 筆案件/)).not.toBeInTheDocument();
    expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument();
    const cardStateTitles = document.querySelectorAll('.pipeline-order-card .card-waiting-alert strong');
    expect(cardStateTitles).toHaveLength(realisticOrderSummaryPage.items.length);
    for (const title of cardStateTitles) expect(title).toHaveTextContent('階段資料載入失敗');
    expect(screen.queryByText('資料完整性異常')).not.toBeInTheDocument();
    expect(screen.getAllByText('目前訂單狀態')).toHaveLength(
      realisticOrderSummaryPage.items.length
    );
  });

  it('loads completed orders only after the operator explicitly enables them', async () => {
    vi.mocked(orderStageProjectionClient.getOperationalTimelines).mockResolvedValue(
      buildOrdersStageProjectionFixture(realisticOrderSummaryPage),
    );

    render(<OrderTrackerPage />);
    await screen.findByText('ORD-2026-0801');
    expect(ordersQueryClient.getOrderSummaries).toHaveBeenLastCalledWith(
      { page_size: 200, lifecycle_scope: 'unfinished' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );

    fireEvent.click(screen.getByRole('checkbox', { name: '包含已完成案件' }));

    await waitFor(() => expect(ordersQueryClient.getOrderSummaries).toHaveBeenLastCalledWith(
      { page_size: 200, lifecycle_scope: 'all' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
    expect(orderStageProjectionClient.getOperationalTimelines).toHaveBeenLastCalledWith(
      { page_size: 200, lifecycle_scope: 'all' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it('does not disguise a failed typed projection as eleven empty business steps', async () => {
    render(<OrderTrackerPage />);
    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /查看訂單 ORD-2026-0801/ }));
    });

    expect(surface('order-tracker.sop.step.')).toHaveLength(0);
    expect(surface('order-tracker.settlement.')).toHaveLength(0);
    expect(screen.getAllByRole('alert')).not.toHaveLength(0);
    expect(screen.queryByText('尚無此步驟的作業紀錄。')).not.toBeInTheDocument();
    expect(screen.queryByText('狀態 — 時間 —')).not.toBeInTheDocument();
    expect(screen.getByText('聯絡電話').nextElementSibling).toHaveTextContent('載入失敗');
    expect(screen.getByText('服務地址').nextElementSibling).toHaveTextContent('載入失敗');
    expect(screen.queryByText('開啟案件卡片後載入')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: /LINE 通知紀錄與發送狀態/ }));
    await waitFor(() => expect(screen.getByText('目前沒有 LINE 通知紀錄。')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /手動重發/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/發送成功/)).not.toBeInTheDocument();
    expect(screen.queryByText(/2026-08-16/)).not.toBeInTheDocument();
  });

  it('shows card contact fields as loading until the typed projection is ready', async () => {
    vi.mocked(orderCardProjectionClient.getCardProjection).mockImplementation(
      () => new Promise(() => undefined),
    );

    render(<OrderTrackerPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getByRole('button', { name: /查看訂單 ORD-2026-0801/ }));

    expect(screen.getByText('聯絡電話').nextElementSibling).toHaveTextContent('載入中');
    expect(screen.getByText('服務地址').nextElementSibling).toHaveTextContent('載入中');
    expect(screen.queryByText('開啟案件卡片後載入')).not.toBeInTheDocument();
  });

  it('shows normalized client service facts without raw BeClass evidence or technical fingerprints', async () => {
    render(<OrderTrackerPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getByRole('button', { name: /查看訂單 ORD-2026-0801/ }));

    await waitFor(() => expect(screen.getByText('到府服務')).toBeInTheDocument());
    expect(screen.getByText('08:30-17:30')).toBeInTheDocument();
    expect(screen.getByText('公寓')).toBeInTheDocument();
    expect(screen.getByText('台北市')).toBeInTheDocument();
    expect(screen.getByText('生產方式').nextElementSibling).toHaveTextContent('待確認');
    expect(document.body).not.toHaveTextContent(/fingerprint|receipt|survey_details|query_no/i);
  });

  it('does not disguise unavailable card fields as empty business values', async () => {
    const unavailable = (owner: string) => ({
      value: null,
      owner,
      source_identity: `missing:${owner}`,
      source_version: null,
      availability: 'unavailable' as const,
      availability_reason: 'official_service_period_missing',
    });
    vi.mocked(orderStageProjectionClient.getOperationalTimelines).mockResolvedValue(
      buildOrdersStageProjectionFixture(realisticOrderSummaryPage),
    );
    vi.mocked(orderCardProjectionClient.getCardProjection).mockResolvedValue({
      case_no: 'ORD-2026-0801',
      contact_phone: unavailable('Client'),
      contact_address: unavailable('Client'),
      requires_cooking: unavailable('Orders'),
      floor_fee_ntd: unavailable('Orders'),
      deposit_amount_ntd: unavailable('Client Finance'),
      deposit_settlement_state: unavailable('Client Finance'),
      deposit_settled_on: unavailable('Client Finance'),
      actual_start_date: unavailable('Orders'),
      actual_end_date: unavailable('Orders'),
      assignment_segments: unavailable('Scheduling'),
    });

    render(<OrderTrackerPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getByRole('button', { name: /查看訂單 ORD-2026-0801/ }));

    const projection = await waitFor(() => {
      const element = document.querySelector('[data-surface-id="order-tracker.card-projection"]');
      expect(element).not.toBeNull();
      return element as HTMLElement;
    });
    expect(screen.getByText('聯絡電話').nextElementSibling).toHaveTextContent('資料待補正');
    expect(screen.getByText('服務地址').nextElementSibling).toHaveTextContent('資料待補正');
    expect(projection).toHaveTextContent('資料待補正：正式服務日或服務時段尚未完整');
    expect(projection).not.toHaveTextContent('尚未登錄');
    expect(projection).not.toHaveTextContent('待確認');
    expect(projection).not.toHaveTextContent('0 段');
  });

  it('renders completed, current, blocked and unavailable SOP states with distinct semantics', async () => {
    const stagePage = buildOrdersStageProjectionFixture(realisticOrderSummaryPage);
    stagePage.items[0].sop_steps[0].status = 'completed';
    stagePage.items[0].sop_steps[1].status = 'in_progress';
    stagePage.items[0].current_sop_step = 2;
    stagePage.items[0].sop_steps[2].status = 'blocked';
    stagePage.items[0].sop_steps[2].blockers = [{ code: 'deposit_pending', message: '定金尚未完成核銷。' }];
    stagePage.items[0].sop_steps[3].status = 'not_started';
    stagePage.items[0].sop_steps[4].status = 'unavailable';
    stagePage.items[0].sop_steps[4].availability_reason = 'test_data_unavailable';
    vi.mocked(orderStageProjectionClient.getOperationalTimelines).mockResolvedValue(stagePage);

    render(<OrderTrackerPage />);
    await screen.findByText('ORD-2026-0801');
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /查看訂單 ORD-2026-0801/ }));
    });

    const completed = document.querySelector('[data-surface-id="order-tracker.sop.step.1"]');
    const current = document.querySelector('[data-surface-id="order-tracker.sop.step.2"]');
    expect(completed).toHaveAttribute('data-status', 'completed');
    expect(screen.getByRole('checkbox', { name: '步驟 1 已完成' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: '步驟 1 已完成' })).toBeDisabled();
    expect(current).toHaveAttribute('data-status', 'in_progress');
    expect(current).toHaveAttribute('aria-current', 'step');
    expect(screen.getByText('目前執行')).toBeInTheDocument();
    expect(screen.getByText('定金尚未完成核銷。')).toBeInTheDocument();
    expect(document.querySelector('[data-surface-id="order-tracker.sop.step.3"]')).toHaveAttribute('data-status', 'blocked');
    expect(document.querySelector('[data-surface-id="order-tracker.sop.step.5"]')).toHaveAttribute('data-status', 'unavailable');
  });

  it('uses the server current SOP step when the current work is blocked', async () => {
    const stagePage = buildOrdersStageProjectionFixture(realisticOrderSummaryPage);
    const timeline = stagePage.items[0];
    timeline.current_sop_step = 3;
    timeline.sop_steps = timeline.sop_steps.map((step) => ({
      ...step,
      status: step.ordinal < 3 ? 'completed' as const : step.ordinal === 3 ? 'blocked' as const : 'not_started' as const,
      blockers: step.ordinal === 3 ? [{ code: 'current_blocker', message: '目前作業受阻。' }] : [],
    }));
    vi.mocked(orderStageProjectionClient.getOperationalTimelines).mockResolvedValue(stagePage);

    render(<OrderTrackerPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getByRole('button', { name: /查看訂單 ORD-2026-0801/ }));

    const current = document.querySelector('[data-surface-id="order-tracker.sop.step.3"]');
    expect(current).toHaveAttribute('data-status', 'blocked');
    expect(current).toHaveAttribute('aria-current', 'step');
    expect(screen.getByText('目前作業受阻。')).toBeInTheDocument();
  });

  it('renders cancelled orders outside both the seven stages and data-correction region', async () => {
    const stagePage = buildOrdersStageProjectionFixture(realisticOrderSummaryPage);
    const cancelled = stagePage.items[0];
    cancelled.current_stage_code = null;
    cancelled.current_sop_step = null;
    cancelled.terminal_state = 'cancelled';
    cancelled.stages = cancelled.stages.map((stage) => ({
      ...stage,
      status: 'unavailable' as const,
      warnings: [{ code: 'order_cancelled', message: '訂單已取消。' }],
      availability_reason: 'order_cancelled',
    }));
    cancelled.sop_steps = cancelled.sop_steps.map((step) => ({
      ...step,
      status: 'unavailable' as const,
      warnings: [{ code: 'order_cancelled', message: '訂單已取消。' }],
      availability_reason: 'order_cancelled',
    }));
    stagePage.stage_counts.intake_terms = 0;
    vi.mocked(orderStageProjectionClient.getOperationalTimelines).mockResolvedValue(stagePage);

    render(<OrderTrackerPage />);

    await screen.findByText('已取消訂單');
    const cancelledRegion = document.querySelector('[data-surface-id="order-tracker.cancelled-orders"]');
    const correctionRegion = document.querySelector('[data-surface-id="order-tracker.unclassified-orders"]');
    expect(cancelledRegion).toHaveTextContent('ORD-2026-0801');
    expect(cancelledRegion).toHaveTextContent('訂單已取消');
    expect(correctionRegion).not.toHaveTextContent('ORD-2026-0801');
    expect(screen.getByText(/已取消是終止狀態/)).toBeInTheDocument();
  });

  it('uses the server current SOP step when the current work is blocked', async () => {
    const stagePage = buildOrdersStageProjectionFixture(realisticOrderSummaryPage);
    const timeline = stagePage.items[0];
    timeline.current_sop_step = 3;
    timeline.sop_steps = timeline.sop_steps.map((step) => ({
      ...step,
      status: step.ordinal < 3 ? 'completed' as const : step.ordinal === 3 ? 'blocked' as const : 'not_started' as const,
      blockers: step.ordinal === 3 ? [{ code: 'current_blocker', message: '目前作業受阻。' }] : [],
    }));
    vi.mocked(orderStageProjectionClient.getOperationalTimelines).mockResolvedValue(stagePage);

    render(<OrderTrackerPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getByRole('button', { name: /查看訂單 ORD-2026-0801/ }));

    const current = document.querySelector('[data-surface-id="order-tracker.sop.step.3"]');
    expect(current).toHaveAttribute('data-status', 'blocked');
    expect(current).toHaveAttribute('aria-current', 'step');
    expect(screen.getByText('目前作業受阻。')).toBeInTheDocument();
  });

  it('renders cancelled orders outside both the seven stages and data-correction region', async () => {
    const stagePage = buildOrdersStageProjectionFixture(realisticOrderSummaryPage);
    const cancelled = stagePage.items[0];
    cancelled.current_stage_code = null;
    cancelled.current_sop_step = null;
    cancelled.terminal_state = 'cancelled';
    cancelled.stages = cancelled.stages.map((stage) => ({
      ...stage,
      status: 'unavailable' as const,
      warnings: [{ code: 'order_cancelled', message: '訂單已取消。' }],
      availability_reason: 'order_cancelled',
    }));
    cancelled.sop_steps = cancelled.sop_steps.map((step) => ({
      ...step,
      status: 'unavailable' as const,
      warnings: [{ code: 'order_cancelled', message: '訂單已取消。' }],
      availability_reason: 'order_cancelled',
    }));
    stagePage.stage_counts.intake_terms = 0;
    vi.mocked(orderStageProjectionClient.getOperationalTimelines).mockResolvedValue(stagePage);

    render(<OrderTrackerPage />);

    await screen.findByText('已取消訂單');
    const cancelledRegion = document.querySelector('[data-surface-id="order-tracker.cancelled-orders"]');
    const correctionRegion = document.querySelector('[data-surface-id="order-tracker.unclassified-orders"]');
    expect(cancelledRegion).toHaveTextContent('ORD-2026-0801');
    expect(cancelledRegion).toHaveTextContent('訂單已取消');
    expect(correctionRegion).not.toHaveTextContent('ORD-2026-0801');
    expect(screen.getByText(/已取消是終止狀態/)).toBeInTheDocument();
  });

  it('isolates incomplete historical imports as data correction instead of a business stage', async () => {
    const stagePage = buildOrdersStageProjectionFixture(realisticOrderSummaryPage);
    const incomplete = stagePage.items[0];
    incomplete.current_stage_code = null;
    incomplete.current_sop_step = null;
    incomplete.stages = incomplete.stages.map((stage, index) => ({
      ...stage,
      status: 'unavailable' as const,
      availability_reason: index === 0
        ? 'case_import_and_terms_lineage_missing'
        : index === 5
          ? 'official_service_period_missing'
          : 'test_data_unavailable',
    }));
    stagePage.stage_counts.intake_terms = 0;
    vi.mocked(orderStageProjectionClient.getOperationalTimelines).mockResolvedValue(stagePage);

    render(<OrderTrackerPage />);

    await screen.findByText('歷史資料待補正');
    expect(screen.queryByText('尚待分類的訂單')).not.toBeInTheDocument();
    expect(screen.getByText(/這不是業務階段/)).toBeInTheDocument();
    expect(screen.getByText('資料完整性異常')).toBeInTheDocument();
    expect(screen.getByText(/資料待補正：請先完成進件匯入與訂單條款/)).toBeInTheDocument();
  });

  it('shows an honest loaded-scope empty state without turning stage slots into zero counts', async () => {
    vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValue({
      items: [],
      next_cursor: null,
      etag: 'b'.repeat(64),
    });
    render(<OrderTrackerPage />);

    await waitFor(() => expect(screen.getByText('目前沒有訂單摘要。')).toBeInTheDocument());
    expect(surface('order-tracker.stage-count.')).toHaveLength(7);
    expect(screen.queryByText(/0 筆案件/)).not.toBeInTheDocument();
  });

  it('automatically continues to terminal and does not duplicate the first summary', async () => {
    const firstPage = {
      ...realisticOrderSummaryPage,
      items: [realisticOrderSummaryPage.items[0]],
      next_cursor: realisticOrderSummaryPage.items[0].case_no,
    };
    const secondPage = {
      ...realisticOrderSummaryPage,
      items: [realisticOrderSummaryPage.items[1]],
      next_cursor: null,
    };
    vi.mocked(ordersQueryClient.getOrderSummaries)
      .mockResolvedValueOnce(firstPage)
      .mockResolvedValueOnce(secondPage);
    const firstStagePage = { ...buildOrdersStageProjectionFixture(firstPage), next_cursor: firstPage.next_cursor };
    const secondStagePage = buildOrdersStageProjectionFixture(secondPage);
    secondStagePage.items[0].current_stage_code = 'matching_willingness';
    secondStagePage.items[0].current_sop_step = 2;
    secondStagePage.stage_counts.intake_terms = 0;
    secondStagePage.stage_counts.matching_willingness = 1;
    vi.mocked(orderStageProjectionClient.getOperationalTimelines)
      .mockResolvedValueOnce(firstStagePage)
      .mockResolvedValueOnce(secondStagePage);

    render(<OrderTrackerPage />);
    await screen.findByText('ORD-2026-0801');
    await screen.findByText('ORD-2026-0802');
    expect(screen.getAllByText('ORD-2026-0801')).toHaveLength(1);
    expect(document.querySelector('[data-surface-id="order-tracker.stage-count.intake_terms"]')).toHaveTextContent('1');
    expect(document.querySelector('[data-surface-id="order-tracker.stage-count.matching_willingness"]')).toHaveTextContent('1');
    expect(ordersQueryClient.getOrderSummaries).toHaveBeenNthCalledWith(
      2,
      { page_size: 200, lifecycle_scope: 'unfinished', after_case_no: 'ORD-2026-0801' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(orderStageProjectionClient.getOperationalTimelines).toHaveBeenNthCalledWith(
      2,
      { page_size: 200, lifecycle_scope: 'unfinished', after_case_no: 'ORD-2026-0801' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(screen.queryByRole('button', { name: '載入下一頁' })).not.toBeInTheDocument();
  });

  it('keeps the active search filter and de-duplicates cross-page stage projections', async () => {
    const firstItem = realisticOrderSummaryPage.items[0];
    const secondItem = realisticOrderSummaryPage.items[1];
    const firstPage = {
      ...realisticOrderSummaryPage,
      items: [firstItem],
      next_cursor: firstItem.case_no,
    };
    const secondPage = {
      ...realisticOrderSummaryPage,
      items: [firstItem, secondItem],
      next_cursor: null,
    };
    vi.mocked(ordersQueryClient.getOrderSummaries)
      .mockResolvedValueOnce(firstPage)
      .mockResolvedValueOnce(secondPage);
    const firstStagePage = { ...buildOrdersStageProjectionFixture(firstPage), next_cursor: firstPage.next_cursor };
    const secondStagePage = buildOrdersStageProjectionFixture(secondPage);
    secondStagePage.items[0].current_stage_code = 'intake_terms';
    secondStagePage.items[1].current_stage_code = 'matching_willingness';
    vi.mocked(orderStageProjectionClient.getOperationalTimelines)
      .mockResolvedValueOnce(firstStagePage)
      .mockResolvedValueOnce(secondStagePage);

    render(<OrderTrackerPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.change(screen.getByRole('textbox', { name: '搜尋案件' }), { target: { value: 'ORD-2026-0802' } });
    expect(screen.queryByText('ORD-2026-0801')).not.toBeInTheDocument();
    await screen.findByText('ORD-2026-0802');
    expect(screen.queryByText('ORD-2026-0801')).not.toBeInTheDocument();
    expect(document.querySelector('[data-surface-id="order-tracker.stage-count.intake_terms"]')).toHaveTextContent('0');
    expect(document.querySelector('[data-surface-id="order-tracker.stage-count.matching_willingness"]')).toHaveTextContent('1');
    expect(screen.getAllByText('ORD-2026-0802')).toHaveLength(1);
  });

  it('preserves every server-scoped item when a later page contains a cancelled order', async () => {
    const firstPage = {
      ...realisticOrderSummaryPage,
      items: [realisticOrderSummaryPage.items[0]],
      next_cursor: realisticOrderSummaryPage.items[0].case_no,
    };
    const cancelled = {
      ...realisticOrderSummaryPage.items[2],
      case_no: 'ORD-2026-CANCELLED',
      order_status: '訂單取消',
    };
    const secondPage = {
      ...realisticOrderSummaryPage,
      items: [realisticOrderSummaryPage.items[1], cancelled],
      next_cursor: null,
    };
    vi.mocked(ordersQueryClient.getOrderSummaries)
      .mockResolvedValueOnce(firstPage)
      .mockResolvedValueOnce(secondPage);
    const firstStagePage = { ...buildOrdersStageProjectionFixture(firstPage), next_cursor: firstPage.next_cursor };
    const secondStagePage = buildOrdersStageProjectionFixture(secondPage);
    secondStagePage.items[0].current_stage_code = 'matching_willingness';
    secondStagePage.items[1].current_stage_code = 'settlement_payout';
    secondStagePage.stage_counts.intake_terms = 0;
    secondStagePage.stage_counts.active_service = 0;
    secondStagePage.stage_counts.matching_willingness = 1;
    secondStagePage.stage_counts.settlement_payout = 1;
    vi.mocked(orderStageProjectionClient.getOperationalTimelines)
      .mockResolvedValueOnce(firstStagePage)
      .mockResolvedValueOnce(secondStagePage);

    render(<OrderTrackerPage />);
    await screen.findByText('ORD-2026-0801');
    await screen.findByText('ORD-2026-0802');
    expect(screen.getByText('ORD-2026-CANCELLED')).toBeInTheDocument();
    expect(document.querySelector('[data-surface-id="order-tracker.stage-count.matching_willingness"]')).toHaveTextContent('1');
    expect(document.querySelector('[data-surface-id="order-tracker.stage-count.settlement_payout"]')).toHaveTextContent('1');
  });

  it('marks typed projection unavailable when the next summary page succeeds but its stage page fails', async () => {
    const firstPage = {
      ...realisticOrderSummaryPage,
      items: [realisticOrderSummaryPage.items[0]],
      next_cursor: realisticOrderSummaryPage.items[0].case_no,
    };
    const secondPage = {
      ...realisticOrderSummaryPage,
      items: [realisticOrderSummaryPage.items[1]],
      next_cursor: null,
    };
    vi.mocked(ordersQueryClient.getOrderSummaries)
      .mockResolvedValueOnce(firstPage)
      .mockResolvedValueOnce(secondPage);
    vi.mocked(orderStageProjectionClient.getOperationalTimelines)
      .mockResolvedValueOnce({ ...buildOrdersStageProjectionFixture(firstPage), next_cursor: firstPage.next_cursor })
      .mockRejectedValueOnce(new Error('stage page failed'));

    render(<OrderTrackerPage />);
    await screen.findByText('ORD-2026-0801');
    await screen.findByText('ORD-2026-0802');
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /查看訂單 ORD-2026-0802/ }));
    });

    expect(screen.getAllByRole('alert')).not.toHaveLength(0);
    expect(surface('order-tracker.sop.step.')).toHaveLength(0);
  });
});

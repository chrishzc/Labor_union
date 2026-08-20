/**
 * File: order_tracker_adapter.test.ts
 * Description: 驗證 Tracker 不從原始狀態推導七階、SOP、LINE或結清，並保留所有 unavailable 槽位。
 */
import { describe, expect, it } from 'vitest';
import { adaptOrderTrackerPage, adaptTrackerOrderCard } from '../adapters/orders/order_tracker_adapter';
import { realisticOrderSummaryPage } from './fixtures/orders_real_data_fixtures';

describe('Order Tracker adapter', () => {
  it('keeps seven stage slots unavailable and leaves every summary unclassified', () => {
    const view = adaptOrderTrackerPage(realisticOrderSummaryPage);

    expect(view.stageSlots).toHaveLength(7);
    expect(view.stageSlots.every((slot) => slot.count === null)).toBe(true);
    expect(view.stageSlots.every((slot) => slot.availability === 'unavailable')).toBe(true);
    expect(view.unclassifiedOrders).toHaveLength(realisticOrderSummaryPage.items.length);
    expect(view.unclassifiedOrders.map((order) => order.id)).toEqual(
      realisticOrderSummaryPage.items.map((item) => item.case_no)
    );
    expect('stageCounts' in view).toBe(false);
    expect('ordersByStage' in view).toBe(false);
  });

  it('raw order status changes only the raw label, never SOP or settlement projections', () => {
    const item = realisticOrderSummaryPage.items[0];
    const first = adaptTrackerOrderCard({ ...item, order_status: '洽談中' });
    const second = adaptTrackerOrderCard({ ...item, order_status: '已結案' });

    expect(first.rawOrderStatus).toBe('洽談中');
    expect(second.rawOrderStatus).toBe('已結案');
    expect(first.stepsChecklist).toEqual(second.stepsChecklist);
    expect(first.settlementSlots).toEqual(second.settlementSlots);
    expect(first.notificationTimelineMessage).toBe(second.notificationTimelineMessage);
    expect(first.waitingText).toBe(second.waitingText);
  });

  it('retains eleven label-only SOP slots and three independent settlement owners', () => {
    const card = adaptTrackerOrderCard(realisticOrderSummaryPage.items[0]);

    expect(card.stepsChecklist).toHaveLength(11);
    expect(card.stepsChecklist.every((step) => step.status === null && step.timestamp === null)).toBe(true);
    expect(card.stepsChecklist.every((step) => step.availability === 'unavailable')).toBe(true);
    expect(card.settlementSlots.map((slot) => slot.id)).toEqual([
      'service-completion',
      'client-finance',
      'staff-payroll',
    ]);
    expect(card.settlementSlots.every((slot) => slot.availability === 'unavailable')).toBe(true);
  });
});


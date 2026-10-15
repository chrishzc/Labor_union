/**
 * File: orders_adapter.test.ts
 * Description: 驗證 Orders adapters 只顯示 typed facts，且缺投影時不生成業務結論。
 */
import { describe, expect, it } from 'vitest';
import { adaptOrdersCardProjection } from '../../../../../../../adapters/orders/order_card_projection_adapter';
import type { OrdersCardProjection, OrdersCardProjectionField } from '../../../../../../../api/orders/order_card_projection_schemas';
import {
  adaptMatchingWorkbenchDrawer,
  adaptOrderCancellationDrawer,
  adaptOrderTermsContractDrawer,
  adaptServiceDateConfirmationDrawer,
} from '../../../../../../../adapters/orders/order_detail_adapter';
import {
  ORDERS_TYPED_PROJECTION_UNAVAILABLE,
  adaptOrderSummaryItem,
  adaptOrderSummaryPage,
} from '../../../../../../../adapters/orders/order_summary_adapter';
import {
  mockSummaryItems,
  realisticActualStart,
  realisticAssignmentPlan,
  realisticContractCompletion,
  realisticOrderCalendarDetail,
  realisticOrderDetail,
  realisticOrderSummaryPage,
  realisticOrderTerms,
} from '../../../../../../fixtures/orders_real_data_fixtures';

function cardField<T>(value: T | null, reason: string | null = null): OrdersCardProjectionField<T> {
  return {
    value, owner: 'test-owner', source_identity: 'test-source', source_version: '1',
    availability: reason ? 'unavailable' : 'available', availability_reason: reason,
  };
}

function cardProjection(): OrdersCardProjection {
  return {
    case_no: 'CARD-100',
    contact_phone: cardField('0912000000'),
    contact_address: cardField('測試地址'),
    requires_cooking: cardField<boolean>(null, 'orders_requires_cooking_unknown'),
    floor_fee_ntd: cardField(0),
    deposit_amount_ntd: cardField(12000),
    deposit_settlement_state: cardField<'settled' | 'unsettled'>(null, 'deposit_settlement_projection_missing'),
    deposit_settled_on: cardField<string>(null, 'deposit_settlement_projection_missing'),
    actual_start_date: cardField('2027-01-04'),
    actual_end_date: cardField<string>(null, 'actual_end_not_recorded'),
    assignment_segments: cardField<[]>(null, 'formal_assignment_segments_missing'),
  };
}

describe('Orders card status text', () => {
  it('shows the known deposit amount and describes unknown or unrecorded facts separately', () => {
    const view = adaptOrdersCardProjection(cardProjection());
    const text = Object.fromEntries(view.rows.map((row) => [row.key, row.valueText]));
    expect(text).toMatchObject({
      requires_cooking: '需求尚待確認', floor_fee_ntd: 'NT$ 0',
      deposit_amount_ntd: 'NT$ 12,000', deposit_settlement_state: '尚無結清紀錄',
      deposit_settled_on: '尚無結清紀錄', actual_start_date: '2027-01-04',
      actual_end_date: '尚未登錄實際結束日',
    });
    expect(view.depositSettlementState).toBeNull();
    expect(view.assignmentSegmentsMessage).toBe('目前尚無正式指派分段。');
    expect(view.rows.some((row) => row.valueText.includes('資料待補正'))).toBe(false);
  });

  it.each([
    ['unsettled', null, 'deposit_not_settled', '尚未結清', '尚未結清'],
    ['settled', '2026-10-15', null, '已結清', '2026-10-15'],
    ['settled', null, 'deposit_settlement_date_missing', '已結清', '已結清，日期待確認'],
  ] as const)('renders %s without inferring a date', (state, date, reason, stateText, dateText) => {
    const projection = cardProjection();
    projection.deposit_settlement_state = cardField(state);
    projection.deposit_settled_on = cardField<string>(date, reason);
    const view = adaptOrdersCardProjection(projection);
    const text = Object.fromEntries(view.rows.map((row) => [row.key, row.valueText]));
    expect(text.deposit_settlement_state).toBe(stateText);
    expect(text.deposit_settled_on).toBe(dateText);
    expect(view.depositSettlementState).toBe(state);
  });

  it('preserves explicit no-cooking and zero-amount facts and does not invent missing amounts', () => {
    const projection = cardProjection();
    projection.requires_cooking = cardField(false);
    projection.deposit_amount_ntd = cardField(0);
    let view = adaptOrdersCardProjection(projection);
    expect(view.rows.find((row) => row.key === 'requires_cooking')?.valueText).toBe('否');
    expect(view.rows.find((row) => row.key === 'deposit_amount_ntd')?.valueText).toBe('NT$ 0');
    projection.deposit_amount_ntd = cardField<number>(null, 'deposit_obligation_missing');
    view = adaptOrdersCardProjection(projection);
    expect(view.rows.find((row) => row.key === 'deposit_amount_ntd')?.valueText).toBe('尚未建立訂金應收');
  });

  it('keeps blocked facts distinct and uses neutral text for unrecognized reasons', () => {
    const projection = cardProjection();
    projection.deposit_amount_ntd = { ...cardField<number>(null, 'deposit_obligation_ambiguous'), availability: 'blocked' };
    projection.actual_end_date = cardField<string>(null, 'future_unknown_reason');
    const view = adaptOrdersCardProjection(projection);
    expect(view.rows.find((row) => row.key === 'deposit_amount_ntd')).toMatchObject({
      valueText: '資料受阻（定金金額）', availability: 'blocked',
    });
    expect(view.rows.find((row) => row.key === 'actual_end_date')?.valueText).toBe('尚無可用資料（已發生實際結束日）');
  });
});

describe('Orders summary adapter', () => {
  it('keeps the raw server status and does not create a workflow stage', () => {
    const card = adaptOrderSummaryItem(mockSummaryItems[6]);
    expect(card.orderStatus).toBe('已結案');
    expect(card.identityStatus).toBe('regular');
    expect('stage' in card).toBe(false);
    expect(card.depositSettled).toBeNull();
    expect(card.depositSettledText).toContain(ORDERS_TYPED_PROJECTION_UNAVAILABLE);
  });

  it('keeps missing identity status explicit for the client card', () => {
    const card = adaptOrderSummaryItem({ ...mockSummaryItems[0], identity_status: null });
    expect(card.identityStatus).toBe('待確認');
  });

  it('keeps typed service dates alongside the display range', () => {
    const card = adaptOrderSummaryItem({
      ...mockSummaryItems[0],
      start_date: '2026-09-03',
      end_date: '2026-10-02',
    });
    expect(card.startDate).toBe('2026-09-03');
    expect(card.endDate).toBe('2026-10-02');
    expect(card.serviceRange).toBe('2026-09-03 ~ 2026-10-02');
  });

  it('does not invent zero when nullable money or service days are absent', () => {
    const card = adaptOrderSummaryItem({
      ...mockSummaryItems[0],
      service_days: null,
      total_employer_self_pay_payable: null,
    });
    expect(card.serviceDays).toBeNull();
    expect(card.contractAmount).toBeNull();
    expect(card.contractAmountFormatted).toContain(ORDERS_TYPED_PROJECTION_UNAVAILABLE);
  });

  it('reports only the loaded-scope count', () => {
    const page = adaptOrderSummaryPage(realisticOrderSummaryPage);
    expect(page.loadedCount).toBe(7);
    expect('stageCounts' in page).toBe(false);
    expect(page.nextCursor).toBeNull();
  });
});

describe('Orders Drawer adapters', () => {
  it('uses actual-start and calendar facts without date arithmetic', () => {
    const view = adaptServiceDateConfirmationDrawer({
      caseNo: realisticOrderDetail.case_no,
      actualStart: { ...realisticActualStart, current_actual_start_date: '2026-09-03' },
      calendarDetail: realisticOrderCalendarDetail,
      orderDetail: realisticOrderDetail,
      precision: {
        actual_start_date: '2026-09-03', actual_end_date: '2026-10-07',
        target_service_days: 30, total_calendar_days: 35,
        actual_work_days_count: 30, rest_days_count: 5,
        national_holidays_found: [], total_estimated_salary: null,
        weekly_stats: [], day_by_day: [],
      },
    });
    expect(view.actualStartDate).toBe('2026-09-03');
    expect(view.serviceMode).toBe('休周日');
    expect(view.serviceRangeText).toBe('2026-09-03 ~ 2026-10-07');
    expect(view.calculatedServiceDaysText).toBe('30 天（目標 30 天）');
    expect(view.restDaysCountText).toBe('5 天');
    expect(view.bufferDateRange).toContain(ORDERS_TYPED_PROJECTION_UNAVAILABLE);
    expect(view.customerConfirmed).toBeNull();
    expect(view.staffConfirmed).toBeNull();
  });

  it('renders assignment-owned segments and an explicit empty candidate pool', () => {
    const view = adaptMatchingWorkbenchDrawer({
      caseNo: realisticAssignmentPlan.case_no,
      assignmentPlan: realisticAssignmentPlan,
    });
    expect(view.assignmentSegments).toHaveLength(1);
    expect(view.assignmentSegments[0]).toMatchObject({ staffId: 88, sequence: 1 });
    expect(view.candidatePool).toEqual([]);
    expect(view.status).toBe('無進行中方案');
    expect(view.waitingLockAcquired).toBe(false);
    expect(view.serviceTimeText).toBe('資料待補正（服務時段三欄）');
  });

  it('uses the matching communication readback instead of stale active-plan status', () => {
    const view = adaptMatchingWorkbenchDrawer({
      caseNo: 'CASE-COMMUNICATION-1',
      activePlan: { planId: 26, status: 'proposed', activeLockId: null, planVersion: 2 },
      customerDecision: 'accepted',
    });

    expect(view.status).toBe('已接受');
    expect(view.waitingLockAcquired).toBe(false);
  });

  it('does not expose replacement-question-mark corruption as a candidate reason', () => {
    const view = adaptMatchingWorkbenchDrawer({
      caseNo: '115000015',
      candidateContactPool: {
        pool_id: 1,
        case_no: '115000015',
        candidates: [{
          id: 2,
          staff_id: 531,
          staff_name: '驗收月嫂',
          service_start_date: '2026-09-01',
          service_end_date: '2026-09-30',
          status: 'active',
          information: {},
          willingness: 'willing',
          reason: '??????',
        }],
      } as never,
    });
    expect(view.candidatePool[0].reason).toBe('原因文字無法辨識');
  });

  it('uses typed terms and completion while no signing record is present', () => {
    const summary = adaptOrderSummaryItem(mockSummaryItems[0]);
    const view = adaptOrderTermsContractDrawer({
      caseNo: summary.id,
      terms: realisticOrderTerms,
      completion: realisticContractCompletion,
      summary,
      orderDetail: realisticOrderDetail,
    });
    expect(view.serviceTimeText).toBe('08:30:00 ~ 17:30:00（同日）');
    expect(view.requiresCookingText).toBe('是');
    expect(view.depositSettled).toBe(false);
    expect(view.depositSettledText).toBe('⏳ 待核銷');
    expect(view.staffContractSigned).toBe(false);
    expect(view.clientContractSigned).toBe(false);
    expect(view.staffContractSignedText).toBe('尚無月嫂契約分段');
    expect(view.clientContractSignedText).toBe('尚未寄送客戶契約');
  });

  it('keeps the cancellation Drawer visible without calculating a refund', () => {
    const view = adaptOrderCancellationDrawer({
      caseNo: 'ORD-2026-0801',
      summary: adaptOrderSummaryItem(mockSummaryItems[0]),
    });
    expect(view.isPurePreview).toBe(false);
    expect(view.contractAmount).toBeNull();
    expect(view.penaltyFee).toBeNull();
    expect(view.refundAmount).toBeNull();
    expect(view.refundAmountText).toContain(ORDERS_TYPED_PROJECTION_UNAVAILABLE);
  });
});

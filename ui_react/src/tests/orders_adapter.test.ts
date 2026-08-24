/**
 * File: orders_adapter.test.ts
 * Description: 驗證 Orders adapters 只顯示 typed facts，且缺投影時不生成業務結論。
 */
import { describe, expect, it } from 'vitest';
import {
  adaptMatchingWorkbenchDrawer,
  adaptOrderCancellationDrawer,
  adaptOrderTermsContractDrawer,
  adaptServiceDateConfirmationDrawer,
} from '../adapters/orders/order_detail_adapter';
import {
  ORDERS_TYPED_PROJECTION_UNAVAILABLE,
  adaptOrderSummaryItem,
  adaptOrderSummaryPage,
} from '../adapters/orders/order_summary_adapter';
import {
  mockSummaryItems,
  realisticActualStart,
  realisticAssignmentPlan,
  realisticContractCompletion,
  realisticOrderCalendarDetail,
  realisticOrderDetail,
  realisticOrderSummaryPage,
  realisticOrderTerms,
} from './fixtures/orders_real_data_fixtures';

describe('Orders summary adapter', () => {
  it('keeps the raw server status and does not create a workflow stage', () => {
    const card = adaptOrderSummaryItem(mockSummaryItems[6]);
    expect(card.orderStatus).toBe('已結案');
    expect('stage' in card).toBe(false);
    expect(card.depositSettled).toBeNull();
    expect(card.depositSettledText).toContain(ORDERS_TYPED_PROJECTION_UNAVAILABLE);
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
    expect(view.serviceMode).toBe('週休1日');
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
      activePlan: { planId: 26, status: 'proposed', activeLockId: null, communicationVersion: 2 },
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

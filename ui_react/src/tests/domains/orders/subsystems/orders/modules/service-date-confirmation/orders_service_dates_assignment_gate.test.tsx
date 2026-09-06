/**
 * File: orders_service_dates_assignment_gate.test.tsx
 * Description: 驗證 Service Dates 只依同案件正式 assignment projection 決定是否需要 Actual Start。
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { orderMutationFlowStore } from '../../../../../../../adapters/orders/order_mutation_flow_store';
import { orderCardProjectionClient } from '../../../../../../../api/orders/order_card_projection_client';
import type { OrdersCardProjection } from '../../../../../../../api/orders/order_card_projection_schemas';
import { ordersMutationClient } from '../../../../../../../api/orders/order_mutation_client';
import { ordersQueryClient } from '../../../../../../../api/orders/order_query_client';
import { contractSigningClient } from '../../../../../../../api/orders/contract_signing_client';
import { orderStageProjectionClient } from '../../../../../../../api/orders/order_stage_projection_client';
import { schedulePrecisionClient } from '../../../../../../../api/scheduling/schedule_precision_client';
import { OrdersPage } from '../../../../../../../pages/OrdersPage';
import { realisticServiceDateQueryView } from '../../../../../../fixtures/orders/order_mutation_contract_fixtures';
import { realisticOrderDetail } from '../../../../../../fixtures/orders_real_data_fixtures';
import { buildOrdersStageProjectionFixture } from '../../../../../../fixtures/orders_stage_projection_fixtures';

const CASE_NO = 'ORD-2026-0801';
const ALERT_TEXT = '正式服務日精算所需的開始日、合約天數或排休類型尚未載入，請關閉後重試。';

const field = <T,>(value: T) => ({
  value,
  availability: 'available' as const,
  source_identity: 'test',
  availability_reason: null,
  owner: 'test',
  source_version: '1',
});

const unavailableField = <T,>() => ({
  value: null as T | null,
  availability: 'unavailable' as const,
  source_identity: 'test',
  availability_reason: 'not ready',
  owner: 'test',
  source_version: '1',
});

function projection(caseNo = CASE_NO): OrdersCardProjection {
  return {
    case_no: caseNo,
    contact_phone: field('0912-345-678'),
    contact_address: field('台北市大安區新生南路一段'),
    requires_cooking: field(true),
    floor_fee_ntd: field(0),
    deposit_amount_ntd: field(18000),
    deposit_settlement_state: field<'settled' | 'unsettled'>('settled'),
    deposit_settled_on: field('2026-08-05'),
    actual_start_date: field<string | null>(null),
    actual_end_date: field<string | null>(null),
    assignment_segments: field([]),
  };
}

function assignedProjection(caseNo = CASE_NO): OrdersCardProjection {
  return {
    ...projection(caseNo),
    assignment_segments: field([{
      assignment_id: field(101),
      staff_id: field(7),
      staff_name: field('正式指派員'),
      sequence: field(1),
      assigned_start_date: field('2026-09-10'),
      assigned_end_date: field('2026-09-12'),
      status: field('planned'),
    }]),
  };
}

describe('Service Dates formal assignment gate', () => {
  const originalFetch = globalThis.fetch;
  const summaryPage = {
    items: [{
      case_no: CASE_NO,
      client_name: '陳雅婷',
      order_status: '確認實際服務日期',
      staff_name: '',
      identity_status: null,
      start_date: '2026-09-01',
      end_date: '2026-09-30',
      actual_start_date: null,
      actual_end_date: null,
      service_days: 30,
      total_employer_self_pay_payable: 90000,
    }],
    next_cursor: null,
    etag: 'a'.repeat(64),
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    orderMutationFlowStore.clearAll();
    globalThis.fetch = vi.fn();
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue(summaryPage);
    vi.spyOn(orderStageProjectionClient, 'getOperationalTimelines').mockResolvedValue(
      buildOrdersStageProjectionFixture(summaryPage),
    );
    vi.spyOn(orderCardProjectionClient, 'getCardProjection').mockResolvedValue(assignedProjection());
    vi.spyOn(ordersQueryClient, 'getActualStart').mockResolvedValue({
      case_no: CASE_NO,
      planned_start_date: '2026-09-10',
      current_actual_start_date: null,
      service_data_locked: false,
      order_version: 1,
      scheduling_version: 1,
      scheduling_generation: 1,
      client_finance_version: 1,
      payroll_version: 1,
    });
    vi.spyOn(ordersQueryClient, 'getOrderCalendarDetail').mockResolvedValue({
      case_no: CASE_NO,
      service_mode: '週休2日',
    });
    vi.spyOn(ordersQueryClient, 'getOrderDetail').mockResolvedValue({
      ...realisticOrderDetail,
      case_no: CASE_NO,
    });
    vi.spyOn(contractSigningClient, 'query').mockResolvedValue({
      case_no: CASE_NO,
      staff_segments: [],
      commitment_id: null,
      client_document_sent: true,
      client_signed_received: true,
      contract_identity: 'CT-2026-0801',
      documents: [],
    });
    vi.spyOn(ordersMutationClient, 'getServiceDates').mockResolvedValue({
      ...realisticServiceDateQueryView,
      case_no: CASE_NO,
      contracted_service_days: 3,
      selectable_dates: ['2026-09-01', '2026-09-02', '2026-09-03'],
    });
    vi.spyOn(schedulePrecisionClient, 'calculate').mockResolvedValue({
      actual_start_date: '2026-09-10',
      actual_end_date: '2026-09-12',
      target_service_days: 3,
      total_calendar_days: 3,
      actual_work_days_count: 3,
      rest_days_count: 0,
      national_holidays_found: [],
      total_estimated_salary: null,
      weekly_stats: [],
      day_by_day: ['2026-09-10', '2026-09-11', '2026-09-12'].map((date, index) => ({
        date,
        day_num: index + 1,
        is_work_day: true,
        is_rest_day: false,
        holiday_name: null,
      })),
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    orderMutationFlowStore.clearAll();
    globalThis.fetch = originalFetch;
  });

  async function openCalendar(): Promise<void> {
    render(React.createElement(OrdersPage));
    await screen.findByText(CASE_NO);
    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);
    const calendarTab = await screen.findByRole('button', { name: /實質服務日曆/ });
    await act(async () => {
      fireEvent.click(calendarTab);
    });
  }

  it('正式 assignment 存在時不依摘要 staff_name，仍以同案件 Actual Start 作為精算起點且不寫入排班', async () => {
    const calculateSpy = vi.mocked(schedulePrecisionClient.calculate);
    const previewSpy = vi.spyOn(ordersMutationClient, 'previewServiceDates');
    const applySpy = vi.spyOn(ordersMutationClient, 'applyServiceDates');

    await openCalendar();

    await waitFor(() => expect(calculateSpy).toHaveBeenCalledTimes(1));
    expect(calculateSpy).toHaveBeenCalledWith({
      actual_start_date: '2026-09-10',
      target_service_days: 3,
      service_mode: '週休2日',
      custom_leave_dates: [],
    });
    expect(previewSpy).not.toHaveBeenCalled();
    expect(applySpy).not.toHaveBeenCalled();
  });

  it('正式 assignment 存在但 Actual Start unavailable 時 fail closed，不退回 Service Dates 起點', async () => {
    vi.mocked(ordersQueryClient.getActualStart).mockRejectedValue(new Error('query unavailable'));
    const calculateSpy = vi.mocked(schedulePrecisionClient.calculate);

    await openCalendar();

    expect(await screen.findByText(ALERT_TEXT)).toHaveAttribute('role', 'alert');
    expect(calculateSpy).not.toHaveBeenCalled();
  });

  it('assignment facts unavailable 時 fail closed，不把未知狀態當成未指派', async () => {
    vi.mocked(orderCardProjectionClient.getCardProjection).mockResolvedValue({
      ...projection(),
      assignment_segments: unavailableField(),
    });
    const calculateSpy = vi.mocked(schedulePrecisionClient.calculate);

    await openCalendar();

    expect(await screen.findByText(ALERT_TEXT)).toHaveAttribute('role', 'alert');
    expect(calculateSpy).not.toHaveBeenCalled();
  });

  it('跨案件 stale assignment projection 會被拒絕，不得驅動目前案件精算', async () => {
    vi.mocked(orderCardProjectionClient.getCardProjection).mockResolvedValue(assignedProjection('ORD-STALE-0001'));
    const calculateSpy = vi.mocked(schedulePrecisionClient.calculate);

    await openCalendar();

    expect(await screen.findByText(ALERT_TEXT)).toHaveAttribute('role', 'alert');
    expect(calculateSpy).not.toHaveBeenCalled();
  });
});

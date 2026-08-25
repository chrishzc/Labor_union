/**
 * File: orders_service_dates_flow.test.tsx
 * Description: 驗證 OrdersPage 依工會規則精算服務日，並以日曆人工排休後自動補足約定天數。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';
import { OrdersPage } from '../pages/OrdersPage';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { ordersMutationClient } from '../api/orders/order_mutation_client';
import { contractSigningClient } from '../api/orders/contract_signing_client';
import { orderCardProjectionClient } from '../api/orders/order_card_projection_client';
import { orderStageProjectionClient } from '../api/orders/order_stage_projection_client';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';
import {
  realisticServiceDateQueryView,
  realisticServiceDatePreviewView,
  realisticServiceDateReceiptView,
} from './fixtures/orders/order_mutation_contract_fixtures';
import {
  OrderMutationConflictError,
  ApiTimeoutError,
} from '../api/orders/order_mutation_errors';
import { realisticOrderDetail } from './fixtures/orders_real_data_fixtures';
import { buildOrdersStageProjectionFixture } from './fixtures/orders_stage_projection_fixtures';
import { schedulePrecisionClient } from '../api/scheduling/schedule_precision_client';

describe('Confirmed Service Dates Component Flow Suite', () => {
  const originalFetch = globalThis.fetch;

  const precisionResult = (dates: string[]) => ({
    actual_start_date: dates[0],
    actual_end_date: dates.at(-1)!,
    target_service_days: dates.length,
    total_calendar_days: dates.length,
    actual_work_days_count: dates.length,
    rest_days_count: 0,
    national_holidays_found: [],
    total_estimated_salary: null,
    weekly_stats: [],
    day_by_day: dates.map((date, index) => ({
      date,
      day_num: index + 1,
      is_work_day: true,
      is_rest_day: false,
      holiday_name: null,
    })),
  });

  const openServiceCalendarTab = async (expectedDays = 3) => {
    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);
    const tabBtn = await screen.findByRole('button', { name: /實質服務日曆/ });
    await act(async () => {
      fireEvent.click(tabBtn);
    });
    await waitFor(() => {
      expect(screen.getByText('合約目標天數').parentElement).toHaveTextContent(`${expectedDays} 天`);
    });
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    orderMutationFlowStore.clearAll();
    globalThis.fetch = vi.fn();

    const summaryPage = {
      items: [
        {
          case_no: 'ORD-2026-0801',
          client_name: '陳雅婷',
          order_status: '確認實際服務日期',
          staff_name: '林月嬌',
          identity_status: null,
          start_date: '2026-09-01',
          end_date: '2026-09-30',
          actual_start_date: null,
          actual_end_date: null,
          service_days: 30,
          total_employer_self_pay_payable: 90000,
        },
      ],
      next_cursor: null,
      etag: 'a'.repeat(64),
    };
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockReset().mockResolvedValue(summaryPage);
    vi.spyOn(orderStageProjectionClient, 'getOperationalTimelines').mockResolvedValue(
      buildOrdersStageProjectionFixture(summaryPage)
    );

    vi.spyOn(orderCardProjectionClient, 'getCardProjection').mockResolvedValue({
      case_no: 'ORD-2026-0801',
      contact_phone: { value: '0912-345-678', availability: 'available', source_identity: 'mock', availability_reason: null, owner: 'mock', source_version: '1' },
      contact_address: { value: '台北市大安區新生南路一段', availability: 'available', source_identity: 'mock', availability_reason: null, owner: 'mock', source_version: '1' },
      requires_cooking: { value: true, availability: 'available', source_identity: 'mock', availability_reason: null, owner: 'mock', source_version: '1' },
      floor_fee_ntd: { value: 0, availability: 'available', source_identity: 'mock', availability_reason: null, owner: 'mock', source_version: '1' },
      deposit_amount_ntd: { value: 18000, availability: 'available', source_identity: 'mock', availability_reason: null, owner: 'mock', source_version: '1' },
      deposit_settlement_state: { value: 'settled', availability: 'available', source_identity: 'mock', availability_reason: null, owner: 'mock', source_version: '1' },
      deposit_settled_on: { value: '2026-08-05', availability: 'available', source_identity: 'mock', availability_reason: null, owner: 'mock', source_version: '1' },
      actual_start_date: { value: null, availability: 'available', source_identity: 'mock', availability_reason: null, owner: 'mock', source_version: '1' },
      actual_end_date: { value: null, availability: 'available', source_identity: 'mock', availability_reason: null, owner: 'mock', source_version: '1' },
      assignment_segments: { value: [], availability: 'available', source_identity: 'mock', availability_reason: null, owner: 'mock', source_version: '1' },
    });

    vi.spyOn(ordersQueryClient, 'getActualStart').mockReset().mockResolvedValue({
      case_no: 'ORD-2026-0801',
      planned_start_date: '2026-09-01',
      current_actual_start_date: null,
      service_data_locked: false,
      order_version: 1,
      scheduling_version: 1,
      scheduling_generation: 1,
      client_finance_version: 1,
      payroll_version: 1,
    });

    vi.spyOn(ordersQueryClient, 'getOrderCalendarDetail').mockReset().mockResolvedValue({
      case_no: 'ORD-2026-0801',
      service_mode: '週休2日',
    });

    vi.spyOn(ordersQueryClient, 'getOrderDetail').mockReset().mockResolvedValue(
      realisticOrderDetail
    );

    vi.spyOn(contractSigningClient, 'query').mockReset().mockResolvedValue({
      case_no: 'ORD-2026-0801',
      staff_segments: [],
      commitment_id: null,
      client_document_sent: true,
      client_signed_received: true,
      contract_identity: 'CT-2026-0801',
      documents: [],
    });

    vi.spyOn(ordersMutationClient, 'getServiceDates').mockReset().mockResolvedValue(
      realisticServiceDateQueryView
    );
    vi.spyOn(schedulePrecisionClient, 'calculate').mockReset().mockResolvedValue(
      precisionResult(['2026-09-01', '2026-09-02', '2026-09-03'])
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    globalThis.fetch = originalFetch;
  });

  it('1. 雙哨兵 (Sentinel) 驗證：不同伺服器回傳值驅動相異 DOM 渲染（非 hardcode）', async () => {
    // Sentinel A
    vi.spyOn(ordersMutationClient, 'getServiceDates').mockResolvedValue({
      ...realisticServiceDateQueryView,
      case_no: 'ORD-2026-0801',
      contracted_service_days: 3,
      current_dates: ['2026-09-01'],
      current_version: 1,
    });

    const { unmount } = render(React.createElement(OrdersPage));
    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());

    await openServiceCalendarTab();

    await waitFor(() => {
      const metaRow = document.querySelector('.service-dates-meta-row')!;
      expect(metaRow).not.toBeNull();
      expect(metaRow).toHaveTextContent('合約服務天數：3 天');
      expect(metaRow).toHaveTextContent('日期確認狀態：已確認');
      expect(metaRow).toHaveTextContent('已確認日期：2026-09-01');
    });

    unmount();
    orderMutationFlowStore.clearAll();

    // Sentinel B (different days and version)
    vi.spyOn(ordersMutationClient, 'getServiceDates').mockResolvedValue({
      ...realisticServiceDateQueryView,
      case_no: 'ORD-2026-0801',
      contracted_service_days: 5,
      current_dates: ['2026-09-10', '2026-09-11'],
      current_version: 2,
    });
    vi.spyOn(schedulePrecisionClient, 'calculate').mockResolvedValue(
      precisionResult(['2026-09-01', '2026-09-02', '2026-09-03', '2026-09-04', '2026-09-05'])
    );

    render(React.createElement(OrdersPage));
    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());

    await openServiceCalendarTab(5);

    await waitFor(() => {
      const metaRow = document.querySelector('.service-dates-meta-row')!;
      expect(metaRow).not.toBeNull();
      expect(metaRow).toHaveTextContent('合約服務天數：5 天');
      expect(metaRow).toHaveTextContent('日期確認狀態：已確認');
      expect(metaRow).toHaveTextContent('已確認日期：2026-09-10, 2026-09-11');
    });
  });

  it('2. 完整服務日期變更流程：查詢 -> 選取 -> 預覽 -> 填寫原因 -> 套用 -> 重新查詢觀察', async () => {
    vi.spyOn(ordersMutationClient, 'getServiceDates').mockResolvedValue(realisticServiceDateQueryView);

    const previewSpy = vi
      .spyOn(ordersMutationClient, 'previewServiceDates')
      .mockResolvedValue(realisticServiceDatePreviewView);

    const applySpy = vi
      .spyOn(ordersMutationClient, 'applyServiceDates')
      .mockResolvedValue(realisticServiceDateReceiptView);

    render(React.createElement(OrdersPage));
    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());

    await openServiceCalendarTab();

    await waitFor(() => {
      expect(screen.getByText(/正式服務日期確認/)).toBeInTheDocument();
    });

    // 預覽按鈕應為可點擊
    const previewBtn = await screen.findByRole('button', { name: /檢查服務週次影響/ });
    expect(previewBtn).not.toBeDisabled();

    // 點擊預覽
    await act(async () => {
      fireEvent.click(previewBtn);
    });

    await waitFor(() => {
      expect(screen.getByText(/服務週次精算預覽/)).toBeInTheDocument();
      expect(screen.getByText(/第 1 週/)).toBeInTheDocument();
    });
    expect(previewSpy).toHaveBeenCalledTimes(1);

    // 填寫原因
    const reasonInput = document.querySelector('.mutation-reason-input') as HTMLInputElement;
    fireEvent.change(reasonInput, { target: { value: '客戶確認服務日期無誤' } });

    // 點擊確認套用
    const applyBtn = await screen.findByRole('button', { name: /確認套用服務日期/ });
    expect(applyBtn).not.toBeDisabled();

    await act(async () => {
      fireEvent.click(applyBtn);
    });

    await waitFor(() => {
      expect(screen.getByText(/服務日期已確認成功/)).toBeInTheDocument();
    });

    expect(applySpy).toHaveBeenCalledTimes(1);
    const applyCallArgs = applySpy.mock.calls[0];
    expect(applyCallArgs[0]).toBe('ORD-2026-0801');
    expect(applyCallArgs[1].reason).toBe('客戶確認服務日期無誤');
    expect(applyCallArgs[2].idempotencyKey).toBeTruthy();
  });

  it('3. 草稿失效機制：產生預覽後若使用者更改日期，舊預覽立即失效且無法直接 Apply', async () => {
    vi.spyOn(ordersMutationClient, 'previewServiceDates').mockResolvedValue(
      realisticServiceDatePreviewView
    );

    render(React.createElement(OrdersPage));
    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());

    await openServiceCalendarTab();
    await waitFor(() => expect(screen.getByText(/正式服務日期確認/)).toBeInTheDocument());

    const previewBtn = document.querySelector(
      '[data-control-id="orders.date.service-date-preview"]'
    ) as HTMLButtonElement;
    fireEvent.click(previewBtn);

    await waitFor(() => {
      expect(screen.getByText(/服務週次精算預覽/)).toBeInTheDocument();
    });

    const rerunSpy = vi.spyOn(schedulePrecisionClient, 'calculate').mockResolvedValue({
      ...precisionResult(['2026-09-01', '2026-09-02', '2026-09-04']),
      actual_end_date: '2026-09-04',
      total_calendar_days: 4,
      rest_days_count: 1,
      day_by_day: [
        { date: '2026-09-01', day_num: 1, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-02', day_num: 2, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-03', day_num: 3, is_work_day: false, is_rest_day: true, holiday_name: null },
        { date: '2026-09-04', day_num: 4, is_work_day: true, is_rest_day: false, holiday_name: null },
      ],
    });
    fireEvent.change(screen.getByLabelText('事前請假日期'), { target: { value: '2026-09-03' } });
    fireEvent.click(screen.getByRole('button', { name: '新增事前請假' }));
    await waitFor(() => expect(rerunSpy).toHaveBeenCalledTimes(1));

    // 預覽結果卡片與 Apply 按鈕應消失或不可見
    expect(screen.queryByText(/服務週次精算預覽/)).toBeNull();
    expect(document.querySelector('[data-control-id="orders.date.service-date-apply"]')).toBeNull();
  });

  it('固定排休可覆寫為正式服務日，僅以 custom_work_dates 重跑後端精算', async () => {
    const initialPrecision = {
      ...precisionResult(['2026-09-01', '2026-09-03', '2026-09-04']),
      actual_end_date: '2026-09-04',
      total_calendar_days: 4,
      rest_days_count: 1,
      day_by_day: [
        { date: '2026-09-01', day_num: 1, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-02', day_num: 2, is_work_day: false, is_rest_day: true, holiday_name: null },
        { date: '2026-09-03', day_num: 3, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-04', day_num: 4, is_work_day: true, is_rest_day: false, holiday_name: null },
      ],
    };
    const overriddenPrecision = {
      ...precisionResult(['2026-09-01', '2026-09-02', '2026-09-03']),
      actual_end_date: '2026-09-03',
      total_calendar_days: 3,
    };
    const calculateSpy = vi.spyOn(schedulePrecisionClient, 'calculate')
      .mockResolvedValueOnce(initialPrecision)
      .mockResolvedValueOnce(overriddenPrecision);

    render(React.createElement(OrdersPage));
    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());
    await openServiceCalendarTab();

    fireEvent.click(screen.getByRole('button', { name: '2026-09-02 固定排休，點擊改為正式服務日' }));

    await waitFor(() => {
      expect(calculateSpy).toHaveBeenCalledTimes(2);
      expect(calculateSpy.mock.calls[1][0]).toMatchObject({
        custom_leave_dates: [],
        custom_work_dates: ['2026-09-02'],
      });
      expect(screen.getByRole('button', { name: '2026-09-02 人工覆寫服務日，點擊恢復固定排休' })).toBeInTheDocument();
    });
  });

  it('4. 409 Conflict Stale 處理：伺服器版本衝突時顯示過期提示並要求重新查詢', async () => {
    vi.spyOn(ordersMutationClient, 'previewServiceDates').mockResolvedValue(
      realisticServiceDatePreviewView
    );
    vi.spyOn(ordersMutationClient, 'applyServiceDates').mockRejectedValue(
      new OrderMutationConflictError({
        code: 'service_date_confirmation_stale_version',
        message: '排程版本已過期，請重新查詢',
        status: 409,
      })
    );

    render(React.createElement(OrdersPage));
    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());

    await openServiceCalendarTab();
    await waitFor(() => expect(screen.getByText(/正式服務日期確認/)).toBeInTheDocument());

    fireEvent.click(
      document.querySelector('[data-control-id="orders.date.service-date-preview"]')!
    );

    await waitFor(() => expect(screen.getByText(/服務週次精算預覽/)).toBeInTheDocument());

    const reasonInput = document.querySelector('.mutation-reason-input') as HTMLInputElement;
    fireEvent.change(reasonInput, { target: { value: '原因說明' } });

    fireEvent.click(
      document.querySelector('[data-control-id="orders.date.service-date-apply"]')!
    );

    await waitFor(() => {
      expect(screen.getByText(/排程版本已過期，請重新查詢/)).toBeInTheDocument();
    });
  });

  it('5. Outcome Unknown 恢復：逾時時進入 outcome_unknown 並允許原 Key 原 Payload 重試', async () => {
    vi.spyOn(ordersMutationClient, 'getServiceDates')
      .mockResolvedValueOnce(realisticServiceDateQueryView)
      .mockResolvedValueOnce({
        ...realisticServiceDateQueryView,
        current_version: 1,
        current_dates: ['2026-09-01', '2026-09-02', '2026-09-03'],
      });

    vi.spyOn(ordersMutationClient, 'previewServiceDates').mockResolvedValue(
      realisticServiceDatePreviewView
    );

    const applySpy = vi
      .spyOn(ordersMutationClient, 'applyServiceDates')
      .mockRejectedValueOnce(new ApiTimeoutError(5000))
      .mockResolvedValueOnce(realisticServiceDateReceiptView);

    render(React.createElement(OrdersPage));
    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());

    await openServiceCalendarTab();
    await waitFor(() => expect(screen.getByText(/正式服務日期確認/)).toBeInTheDocument());

    fireEvent.click(
      document.querySelector('[data-control-id="orders.date.service-date-preview"]')!
    );

    await waitFor(() => expect(screen.getByText(/服務週次精算預覽/)).toBeInTheDocument());

    const reasonInput = document.querySelector('.mutation-reason-input') as HTMLInputElement;
    fireEvent.change(reasonInput, { target: { value: '原因說明' } });

    fireEvent.click(
      document.querySelector('[data-control-id="orders.date.service-date-apply"]')!
    );

    // 出現 outcome_unknown 提示
    await waitFor(() => {
      expect(screen.getByText(/服務日期確認回應逾時或未明/)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /重試提交/ })).toBeInTheDocument();
    });

    expect(reasonInput).toBeDisabled();
    expect(
      document.querySelector('[data-control-id="orders.date.service-date-apply"]')
    ).toBeDisabled();
    expect(screen.getByLabelText('事前請假日期')).toBeDisabled();

    const firstKey = applySpy.mock.calls[0][2].idempotencyKey;

    // 點擊重試
    fireEvent.click(screen.getByRole('button', { name: /重試提交/ }));

    await waitFor(() => {
      expect(screen.getByText(/服務日期已確認成功/)).toBeInTheDocument();
    });

    expect(applySpy).toHaveBeenCalledTimes(2);
    const secondKey = applySpy.mock.calls[1][2].idempotencyKey;
    expect(secondKey).toBe(firstKey);
  });

  it('6. 抽屜關閉後重開：Draft 與 Idempotency Key 保留在記憶體 Store 中不遺失', async () => {
    render(React.createElement(OrdersPage));
    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());

    // 開啟抽屜並選取日期
    await openServiceCalendarTab();
    await waitFor(() => expect(screen.getByText(/正式服務日期確認/)).toBeInTheDocument());

    const draftBefore = orderMutationFlowStore.getServiceDatesDraft('ORD-2026-0801');
    const keyBefore = draftBefore?.idempotencyKey;

    // 關閉抽屜
    fireEvent.click(screen.getByRole('button', { name: '關閉' }));

    // 再次開啟抽屜
    await openServiceCalendarTab();
    await waitFor(() => expect(screen.getByText(/正式服務日期確認/)).toBeInTheDocument());

    const draftAfter = orderMutationFlowStore.getServiceDatesDraft('ORD-2026-0801');
    expect(draftAfter?.selectedDates).toEqual(['2026-09-01', '2026-09-02', '2026-09-03']);
    expect(draftAfter?.idempotencyKey).toBe(keyBefore);
  });

  it('7. 出勤精算使用同案件 service-date 與 actual-start query，不回退成 30 天', async () => {
    vi.spyOn(ordersMutationClient, 'getServiceDates').mockResolvedValue({
      ...realisticServiceDateQueryView,
      contracted_service_days: 5,
    });
    const calculateSpy = vi.spyOn(schedulePrecisionClient, 'calculate').mockResolvedValue(
      precisionResult(['2026-09-01', '2026-09-02', '2026-09-03', '2026-09-04', '2026-09-05'])
    );

    render(React.createElement(OrdersPage));
    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());
    await openServiceCalendarTab(5);

    await waitFor(() => expect(calculateSpy).toHaveBeenCalledTimes(1));
    expect(calculateSpy).toHaveBeenCalledWith({
      actual_start_date: '2026-09-01',
      target_service_days: 5,
      service_mode: '週休2日',
      custom_leave_dates: [],
    });
    expect((await screen.findByText('合約目標天數')).parentElement).toHaveTextContent('5 天');
    expect(screen.getByText('實質出勤天數').parentElement).toHaveTextContent('5 天');
  });

  it('8. actual-start query 缺失時 fail closed 且不呼叫精算 API', async () => {
    vi.spyOn(ordersQueryClient, 'getActualStart').mockRejectedValue(new Error('query unavailable'));
    const calculateSpy = vi.spyOn(schedulePrecisionClient, 'calculate');

    render(React.createElement(OrdersPage));
    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);
    const tabBtn = await screen.findByRole('button', { name: /實質服務日曆/ });
    fireEvent.click(tabBtn);

    expect(await screen.findByText('正式服務日精算所需的開始日、合約天數或排休類型尚未載入，請關閉後重試。')).toHaveAttribute('role', 'alert');
    expect(calculateSpy).not.toHaveBeenCalled();
  });

  it('9. 國定假日與事前請假每次都由 server 重算並自動替代，服務日維持 5 天', async () => {
    vi.spyOn(ordersMutationClient, 'getServiceDates').mockResolvedValue({
      ...realisticServiceDateQueryView,
      contracted_service_days: 5,
      selectable_dates: [
        '2026-09-01', '2026-09-02', '2026-09-03', '2026-09-04',
        '2026-09-05', '2026-09-06', '2026-09-07', '2026-09-08',
      ],
    });
    const resultWithHolidayRest = {
      ...precisionResult(['2026-09-01', '2026-09-02', '2026-09-04', '2026-09-05', '2026-09-07']),
      actual_end_date: '2026-09-07',
      total_calendar_days: 7,
      rest_days_count: 2,
      national_holidays_found: [
        { date: '2026-09-03', name: '工會測試假日', is_worked: false },
      ],
      day_by_day: [
        { date: '2026-09-01', day_num: 1, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-02', day_num: 2, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-03', day_num: 3, is_work_day: false, is_rest_day: true, holiday_name: '工會測試假日' },
        { date: '2026-09-04', day_num: 4, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-05', day_num: 5, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-06', day_num: 6, is_work_day: false, is_rest_day: true, holiday_name: null },
        { date: '2026-09-07', day_num: 7, is_work_day: true, is_rest_day: false, holiday_name: null },
      ],
    };
    const resultHolidayWorked = {
      ...precisionResult(['2026-09-01', '2026-09-02', '2026-09-03', '2026-09-04', '2026-09-05']),
      national_holidays_found: [
        { date: '2026-09-03', name: '工會測試假日', is_worked: true },
      ],
      day_by_day: [
        { date: '2026-09-01', day_num: 1, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-02', day_num: 2, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-03', day_num: 3, is_work_day: true, is_rest_day: false, holiday_name: '工會測試假日' },
        { date: '2026-09-04', day_num: 4, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-05', day_num: 5, is_work_day: true, is_rest_day: false, holiday_name: null },
      ],
    };
    const resultWithLeave = {
      ...resultWithHolidayRest,
      national_holidays_found: [
        { date: '2026-09-03', name: '工會測試假日', is_worked: true },
      ],
      day_by_day: [
        { date: '2026-09-01', day_num: 1, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-02', day_num: 2, is_work_day: false, is_rest_day: true, holiday_name: null },
        { date: '2026-09-03', day_num: 3, is_work_day: true, is_rest_day: false, holiday_name: '工會測試假日' },
        { date: '2026-09-04', day_num: 4, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-05', day_num: 5, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-06', day_num: 6, is_work_day: false, is_rest_day: true, holiday_name: null },
        { date: '2026-09-07', day_num: 7, is_work_day: true, is_rest_day: false, holiday_name: null },
      ],
    };
    const calculateSpy = vi.spyOn(schedulePrecisionClient, 'calculate')
      .mockResolvedValueOnce(resultWithHolidayRest)
      .mockResolvedValueOnce(resultHolidayWorked)
      .mockResolvedValueOnce(resultWithLeave);

    render(React.createElement(OrdersPage));
    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());
    await openServiceCalendarTab(5);
    const holidayCheckbox = screen.getByRole('checkbox');
    expect(holidayCheckbox).toBeChecked();
    fireEvent.click(holidayCheckbox);
    await waitFor(() => expect(calculateSpy).toHaveBeenCalledTimes(2));

    fireEvent.change(screen.getByLabelText('事前請假日期'), { target: { value: '2026-09-02' } });
    fireEvent.click(screen.getByRole('button', { name: '新增事前請假' }));
    await waitFor(() => expect(calculateSpy).toHaveBeenCalledTimes(3));
    expect(calculateSpy.mock.calls[2][0]).toMatchObject({
      target_service_days: 5,
      custom_holiday_rest_dates: [],
      custom_leave_dates: ['2026-09-02'],
    });
    expect(orderMutationFlowStore.getServiceDatesDraft('ORD-2026-0801')?.selectedDates)
      .toEqual(['2026-09-01', '2026-09-03', '2026-09-04', '2026-09-05', '2026-09-07']);
    expect(screen.queryByRole('button', { name: '帶入建議日期' })).not.toBeInTheDocument();
    expect(screen.queryByText('已選服務日期清單')).not.toBeInTheDocument();
    expect(screen.queryByText('最新根事實版本')).not.toBeInTheDocument();
  });

  it('10. 點擊服務日可人工排休並由 server 補足；再次點擊可取消，固定排休另可覆寫', async () => {
    vi.spyOn(ordersMutationClient, 'getServiceDates').mockResolvedValue({
      ...realisticServiceDateQueryView,
      contracted_service_days: 3,
      selectable_dates: [
        '2026-09-01', '2026-09-02', '2026-09-03', '2026-09-04', '2026-09-05',
      ],
    });
    const initialResult = precisionResult(['2026-09-01', '2026-09-02', '2026-09-03']);
    const adjustedResult = {
      ...precisionResult(['2026-09-01', '2026-09-03', '2026-09-04']),
      actual_end_date: '2026-09-05',
      total_calendar_days: 5,
      rest_days_count: 2,
      day_by_day: [
        { date: '2026-09-01', day_num: 1, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-02', day_num: 2, is_work_day: false, is_rest_day: true, holiday_name: null },
        { date: '2026-09-03', day_num: 3, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-04', day_num: 4, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-05', day_num: 5, is_work_day: false, is_rest_day: true, holiday_name: null },
      ],
    };
    const calculateSpy = vi.spyOn(schedulePrecisionClient, 'calculate')
      .mockResolvedValueOnce(initialResult)
      .mockResolvedValueOnce(adjustedResult)
      .mockResolvedValueOnce(initialResult);

    render(React.createElement(OrdersPage));
    await screen.findByText('ORD-2026-0801');
    await openServiceCalendarTab(3);

    fireEvent.click(screen.getByRole('button', {
      name: '2026-09-02 服務日，點擊改為人工排休',
    }));
    await waitFor(() => expect(calculateSpy).toHaveBeenCalledTimes(2));
    expect(calculateSpy.mock.calls[1][0]).toMatchObject({
      target_service_days: 3,
      custom_leave_dates: ['2026-09-02'],
    });
    expect(orderMutationFlowStore.getServiceDatesDraft('ORD-2026-0801')?.selectedDates)
      .toEqual(['2026-09-01', '2026-09-03', '2026-09-04']);
    expect(screen.getByLabelText('2026-09-05 固定排休，點擊改為正式服務日').tagName).toBe('BUTTON');

    fireEvent.click(await screen.findByRole('button', {
      name: '2026-09-02 人工調整休假，點擊取消',
    }));
    await waitFor(() => expect(calculateSpy).toHaveBeenCalledTimes(3));
    expect(calculateSpy.mock.calls[2][0]).toMatchObject({
      target_service_days: 3,
      custom_leave_dates: [],
    });
    expect(orderMutationFlowStore.getServiceDatesDraft('ORD-2026-0801')?.selectedDates)
      .toEqual(['2026-09-01', '2026-09-02', '2026-09-03']);

    fireEvent.click(screen.getByRole('button', { name: '前往請假／代班工作台' }));
    expect(window.location.hash).toBe('#scheduling?tab=leave_sub&case_no=ORD-2026-0801');
    window.location.hash = '';
  });

  it('11. Sunday-first 日曆欄位正確呈現週休 1／2 日，不把開始日誤塞星期日欄', async () => {
    vi.spyOn(ordersQueryClient, 'getActualStart').mockResolvedValue({
      case_no: 'ORD-2026-0801',
      planned_start_date: '2026-09-10',
      current_actual_start_date: null,
      service_data_locked: false,
      order_version: 1,
      scheduling_version: 1,
      scheduling_generation: 1,
      client_finance_version: 1,
      payroll_version: 1,
    });
    vi.spyOn(ordersMutationClient, 'getServiceDates').mockResolvedValue({
      ...realisticServiceDateQueryView,
      contracted_service_days: 5,
      selectable_dates: [
        '2026-09-10', '2026-09-11', '2026-09-12', '2026-09-13',
        '2026-09-14', '2026-09-15', '2026-09-16',
      ],
    });
    const weeklyTwoResult = {
      ...precisionResult(['2026-09-10', '2026-09-11', '2026-09-14', '2026-09-15', '2026-09-16']),
      actual_start_date: '2026-09-10',
      actual_end_date: '2026-09-16',
      total_calendar_days: 7,
      rest_days_count: 2,
      day_by_day: [
        { date: '2026-09-10', day_num: 1, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-11', day_num: 2, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-12', day_num: 3, is_work_day: false, is_rest_day: true, holiday_name: null },
        { date: '2026-09-13', day_num: 4, is_work_day: false, is_rest_day: true, holiday_name: null },
        { date: '2026-09-14', day_num: 5, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-15', day_num: 6, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-16', day_num: 7, is_work_day: true, is_rest_day: false, holiday_name: null },
      ],
    };
    vi.spyOn(schedulePrecisionClient, 'calculate').mockResolvedValue(weeklyTwoResult);

    const { unmount } = render(React.createElement(OrdersPage));
    await screen.findByText('ORD-2026-0801');
    await openServiceCalendarTab(5);
    const weeklyTwoGrid = document.querySelector('[data-surface-id="orders.date.service-date-selection"]')!;
    const columnOf = (grid: Element, label: string) => (
      Array.from(grid.children).indexOf(screen.getByLabelText(label)) % 7
    );
    expect(columnOf(weeklyTwoGrid, '2026-09-12 固定排休，點擊改為正式服務日')).toBe(6);
    expect(columnOf(weeklyTwoGrid, '2026-09-13 固定排休，點擊改為正式服務日')).toBe(0);
    expect(columnOf(weeklyTwoGrid, '2026-09-14 服務日，點擊改為人工排休')).toBe(1);
    expect(columnOf(weeklyTwoGrid, '2026-09-15 服務日，點擊改為人工排休')).toBe(2);

    unmount();
    orderMutationFlowStore.clearAll();
    vi.spyOn(ordersQueryClient, 'getOrderCalendarDetail').mockResolvedValue({
      case_no: 'ORD-2026-0801',
      service_mode: '週休1日',
    });
    vi.spyOn(schedulePrecisionClient, 'calculate').mockResolvedValue({
      ...weeklyTwoResult,
      actual_end_date: '2026-09-15',
      total_calendar_days: 6,
      rest_days_count: 1,
      day_by_day: [
        { date: '2026-09-10', day_num: 1, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-11', day_num: 2, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-12', day_num: 3, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-13', day_num: 4, is_work_day: false, is_rest_day: true, holiday_name: null },
        { date: '2026-09-14', day_num: 5, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-15', day_num: 6, is_work_day: true, is_rest_day: false, holiday_name: null },
      ],
    });

    render(React.createElement(OrdersPage));
    await screen.findByText('ORD-2026-0801');
    await openServiceCalendarTab(5);
    const weeklyOneGrid = document.querySelector('[data-surface-id="orders.date.service-date-selection"]')!;
    expect(columnOf(weeklyOneGrid, '2026-09-12 服務日，點擊改為人工排休')).toBe(6);
    expect(columnOf(weeklyOneGrid, '2026-09-13 固定排休，點擊改為正式服務日')).toBe(0);
  });
});

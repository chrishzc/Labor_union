import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderServiceDatesPanel } from '../components/OrderServiceDatesPanel';

const mocks = vi.hoisted(() => ({
  getActualStart: vi.fn(),
  getOrderCalendarDetail: vi.fn(),
  calculate: vi.fn(),
  fetchServiceDatesQuery: vi.fn(),
  selectServiceDates: vi.fn(),
  updateServiceDatesReason: vi.fn(),
  previewServiceDatesFlow: vi.fn(),
  applyServiceDatesFlow: vi.fn(),
  getServiceDatesDraft: vi.fn(),
}));

vi.mock('../api/orders/order_query_client', () => ({
  ordersQueryClient: {
    getActualStart: mocks.getActualStart,
    getOrderCalendarDetail: mocks.getOrderCalendarDetail,
  },
}));

vi.mock('../api/scheduling/schedule_precision_client', () => ({
  schedulePrecisionClient: {
    calculate: mocks.calculate,
  },
}));

vi.mock('../adapters/orders/order_mutation_adapter', () => ({
  fetchServiceDatesQuery: mocks.fetchServiceDatesQuery,
  selectServiceDates: mocks.selectServiceDates,
  updateServiceDatesReason: mocks.updateServiceDatesReason,
  previewServiceDatesFlow: mocks.previewServiceDatesFlow,
  applyServiceDatesFlow: mocks.applyServiceDatesFlow,
}));

vi.mock('../adapters/orders/order_mutation_flow_store', () => ({
  orderMutationFlowStore: {
    getServiceDatesDraft: mocks.getServiceDatesDraft,
  },
}));

const initialQuery = {
  case_no: 'CASE-SERVICE-DATES',
  order_version: 11,
  scheduling_version: 7,
  contracted_service_days: 3,
  suggested_dates: ['2026-10-01', '2026-10-02', '2026-10-04'],
  selectable_dates: ['2026-10-01', '2026-10-02', '2026-10-03', '2026-10-04'],
  current_version: null,
  current_dates: [],
};

const observedQuery = {
  ...initialQuery,
  order_version: 12,
  scheduling_version: 8,
  current_version: 1,
  current_dates: ['2026-10-01', '2026-10-03', '2026-10-04'],
};

const preview = {
  case_no: 'CASE-SERVICE-DATES',
  order_version: 11,
  scheduling_version: 7,
  current_version: null,
  service_dates: ['2026-10-01', '2026-10-03', '2026-10-04'],
  weeks: [{
    week_number: 1,
    period_start: '2026-09-28',
    period_end: '2026-10-04',
    service_dates: ['2026-10-01', '2026-10-03', '2026-10-04'],
    service_day_count: 3,
  }],
  preview_fingerprint: 'a'.repeat(64),
};

const receipt = {
  case_no: 'CASE-SERVICE-DATES',
  confirmed_version: 1,
  order_version: 12,
  scheduling_version: 8,
  service_dates: preview.service_dates,
  preview_fingerprint: preview.preview_fingerprint,
};

describe('待辦看板 Beta 第 9 階服務日期精算', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
    mocks.getActualStart.mockResolvedValue({
      case_no: 'CASE-SERVICE-DATES',
      current_actual_start_date: null,
      planned_start_date: '2026-10-01',
      service_data_locked: false,
      order_version: 11,
      scheduling_version: 7,
      scheduling_generation: 1,
      client_finance_version: 3,
      payroll_version: 2,
    });
    mocks.getOrderCalendarDetail.mockResolvedValue({
      case_no: 'CASE-SERVICE-DATES',
      service_mode: '週休1日',
    });
    mocks.fetchServiceDatesQuery.mockResolvedValue(initialQuery);
    mocks.calculate.mockResolvedValue({
      actual_start_date: '2026-10-01',
      actual_end_date: '2026-10-04',
      target_service_days: 3,
      total_calendar_days: 4,
      actual_work_days_count: 3,
      rest_days_count: 1,
      national_holidays_found: [],
      total_estimated_salary: null,
      weekly_stats: [],
      day_by_day: [
        { date: '2026-10-01', day_num: 1, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-10-02', day_num: 2, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-10-03', day_num: 3, is_work_day: false, is_rest_day: true, holiday_name: null },
        { date: '2026-10-04', day_num: 4, is_work_day: true, is_rest_day: false, holiday_name: null },
      ],
    });
    mocks.previewServiceDatesFlow.mockResolvedValue(preview);
    mocks.applyServiceDatesFlow.mockResolvedValue(receipt);
    mocks.getServiceDatesDraft.mockReturnValue({
      status: 'observed',
      queryView: observedQuery,
    });
  });

  it('沿用正式精算與服務日期 mutation flow，允許調整後 Preview、Apply 並回讀', async () => {
    const onObserved = vi.fn();
    render(<OrderServiceDatesPanel caseNo="CASE-SERVICE-DATES" onObserved={onObserved} />);

    fireEvent.click(screen.getByRole('button', { name: '讀取並精算服務日期' }));

    await waitFor(() => expect(mocks.calculate).toHaveBeenCalledWith({
      actual_start_date: '2026-10-01',
      target_service_days: 3,
      service_mode: '週休1日',
    }));
    expect(mocks.selectServiceDates).toHaveBeenLastCalledWith(
      'CASE-SERVICE-DATES',
      ['2026-10-01', '2026-10-02', '2026-10-04'],
    );

    fireEvent.click(screen.getByRole('checkbox', { name: '服務日期 2026-10-02' }));
    fireEvent.click(screen.getByRole('checkbox', { name: '服務日期 2026-10-03' }));
    expect(mocks.selectServiceDates).toHaveBeenLastCalledWith(
      'CASE-SERVICE-DATES',
      ['2026-10-01', '2026-10-03', '2026-10-04'],
    );

    fireEvent.click(screen.getByRole('button', { name: '預覽服務日期' }));
    await waitFor(() => expect(mocks.previewServiceDatesFlow).toHaveBeenCalledWith('CASE-SERVICE-DATES'));
    expect(await screen.findByText('服務日期預覽已取得。')).toBeInTheDocument();

    fireEvent.change(screen.getByRole('textbox', { name: '服務日期確認原因' }), {
      target: { value: '依客戶確認調整服務日期' },
    });
    expect(mocks.updateServiceDatesReason).toHaveBeenCalledWith(
      'CASE-SERVICE-DATES',
      '依客戶確認調整服務日期',
    );

    fireEvent.click(screen.getByRole('button', { name: '套用並回讀服務日期' }));
    await waitFor(() => expect(mocks.applyServiceDatesFlow).toHaveBeenCalledWith('CASE-SERVICE-DATES'));
    expect(await screen.findByText('服務日期已套用並回讀版本 #1。')).toBeInTheDocument();
    expect(onObserved).toHaveBeenCalledTimes(1);

    const readback = screen.getByLabelText('正式服務日期回讀');
    expect(within(readback).getByText('#1')).toBeInTheDocument();
    expect(within(readback).getByText('2026-10-01、2026-10-03、2026-10-04')).toBeInTheDocument();
  });
});

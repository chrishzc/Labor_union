import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderServiceDatesPanel } from '../../../../../../../components/OrderServiceDatesPanel';

const mocks = vi.hoisted(() => ({
  getActualStart: vi.fn(),
  getOrderCalendarDetail: vi.fn(),
  calculate: vi.fn(),
  getServiceDates: vi.fn(),
  selectServiceDates: vi.fn(),
  updateServiceDatesReason: vi.fn(),
  previewServiceDatesFlow: vi.fn(),
  applyServiceDatesFlow: vi.fn(),
  retryServiceDatesApplyFlow: vi.fn(),
  retryServiceDatesObservationFlow: vi.fn(),
  getServiceDatesDraft: vi.fn(),
  resetServiceDatesDraft: vi.fn(),
  setServiceDatesQueryReady: vi.fn(),
  subscribe: vi.fn(),
  getActualStartFlow: vi.fn(),
  setServiceDatesCalculation: vi.fn(),
}));

vi.mock('../../../../../../../api/orders/order_query_client', () => ({
  ordersQueryClient: {
    getActualStart: mocks.getActualStart,
    getOrderCalendarDetail: mocks.getOrderCalendarDetail,
  },
}));

vi.mock('../../../../../../../api/orders/order_mutation_client', () => ({
  ordersMutationClient: {
    getServiceDates: mocks.getServiceDates,
  },
}));

vi.mock('../../../../../../../api/scheduling/schedule_precision_client', () => ({
  schedulePrecisionClient: {
    calculate: mocks.calculate,
  },
}));

vi.mock('../../../../../../../adapters/orders/order_mutation_adapter', () => ({
  selectServiceDates: mocks.selectServiceDates,
  updateServiceDatesReason: mocks.updateServiceDatesReason,
  previewServiceDatesFlow: mocks.previewServiceDatesFlow,
  applyServiceDatesFlow: mocks.applyServiceDatesFlow,
  retryServiceDatesApplyFlow: mocks.retryServiceDatesApplyFlow,
  retryServiceDatesObservationFlow: mocks.retryServiceDatesObservationFlow,
}));

vi.mock('../../../../../../../adapters/orders/order_mutation_flow_store', () => ({
  orderMutationFlowStore: {
    getServiceDatesDraft: mocks.getServiceDatesDraft,
    resetServiceDatesDraft: mocks.resetServiceDatesDraft,
    setServiceDatesQueryReady: mocks.setServiceDatesQueryReady,
    subscribe: mocks.subscribe,
    getActualStart: mocks.getActualStartFlow,
    setServiceDatesCalculation: mocks.setServiceDatesCalculation,
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
  bound_staff: [],
  arrangement_pending: false,
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

describe('待辦看板 Beta 第 9 階服務日期', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
    mocks.getActualStart.mockResolvedValue({
      case_no: 'CASE-SERVICE-DATES',
      current_actual_start_date: '2026-10-01',
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
      service_mode: '休周六',
    });
    mocks.getServiceDates.mockResolvedValue(initialQuery);
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
    mocks.getServiceDatesDraft.mockImplementation(() => (
      mocks.applyServiceDatesFlow.mock.calls.length > 0
        ? { status: 'observed', queryView: observedQuery }
        : { status: 'observed', queryView: initialQuery }
    ));
    mocks.subscribe.mockReturnValue(() => undefined);
  });

  it('以查看與調整服務日期、確認、完成確認的主流程沿用既有 Preview/Apply 並回讀', async () => {
    const onObserved = vi.fn();
    const onOpenActualStart = vi.fn();
    render(<OrderServiceDatesPanel caseNo="CASE-SERVICE-DATES" onObserved={onObserved} onOpenActualStart={onOpenActualStart} />);

    fireEvent.click(await screen.findByRole('button', { name: '精算天數並設定服務日期' }));

    await waitFor(() => expect(mocks.calculate).toHaveBeenCalledWith({
      case_no: 'CASE-SERVICE-DATES',
      actual_start_date: '2026-10-01',
      target_service_days: 3,
      service_mode: '休周六',
    }));
    expect(mocks.selectServiceDates).toHaveBeenLastCalledWith(
      'CASE-SERVICE-DATES',
      ['2026-10-01', '2026-10-02', '2026-10-04'],
    );
    expect(mocks.updateServiceDatesReason).toHaveBeenCalledWith(
      'CASE-SERVICE-DATES',
      '確認正式服務日期',
    );
    expect(screen.getByLabelText('建議服務日期摘要')).toBeInTheDocument();
    expect(screen.getByLabelText('服務日期計算基準')).toHaveTextContent('正式實際開始日：2026-10-01');
    fireEvent.click(screen.getByRole('button', { name: '確認／更正實際開始日' }));
    expect(onOpenActualStart).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('heading', { name: '📅 正式服務日期確認（日曆排盤）' })).toBeInTheDocument();
    expect(screen.getByText('請逐日核對服務安排；選取國定假日即代表已確認該日安排服務，不需另行登錄協調結果。')).toBeInTheDocument();
    const calendar = screen.getByRole('group', { name: '服務日期月曆' });
    expect(within(calendar).getByRole('button', { name: '服務日期 2026-10-02' })).toHaveAttribute('aria-pressed', 'true');
    expect(within(calendar).getByRole('button', { name: '服務日期 2026-10-03' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.queryByRole('button', { name: '預覽服務日期' })).not.toBeInTheDocument();

    fireEvent.click(within(calendar).getByRole('button', { name: '服務日期 2026-10-02' }));
    fireEvent.click(within(calendar).getByRole('button', { name: '服務日期 2026-10-03' }));
    expect(mocks.selectServiceDates).toHaveBeenLastCalledWith(
      'CASE-SERVICE-DATES',
      ['2026-10-01', '2026-10-03', '2026-10-04'],
    );

    fireEvent.click(screen.getByRole('button', { name: '確認服務日期' }));
    await waitFor(() => expect(mocks.previewServiceDatesFlow).toHaveBeenCalledWith(
      'CASE-SERVICE-DATES',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
    expect(await screen.findByText('服務日期確認內容已準備。')).toBeInTheDocument();
    expect(screen.getByLabelText('服務日期確認內容')).toBeInTheDocument();

    expect(screen.queryByRole('textbox', { name: '服務日期確認原因' })).not.toBeInTheDocument();
    expect(screen.getByText('系統會自動記錄「確認正式服務日期」，不需另外填寫原因。')).toBeInTheDocument();

    expect(screen.queryByRole('button', { name: '套用並回讀服務日期' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '完成服務日期確認' }));
    await waitFor(() => expect(mocks.applyServiceDatesFlow).toHaveBeenCalledWith('CASE-SERVICE-DATES'));
    expect(await screen.findByText('服務日期已確認並回讀版本 #1。')).toBeInTheDocument();
    expect(onObserved).toHaveBeenCalledTimes(1);

    const readback = screen.getByLabelText('正式服務日期回讀');
    expect(within(readback).getByText('#1')).toBeInTheDocument();
    expect(within(readback).getByText('2026-10-01、2026-10-03、2026-10-04')).toBeInTheDocument();
  });

  it('實際開始日重排後區分先前確認日期與目前有效排班', async () => {
    mocks.getActualStart.mockResolvedValue({
      case_no: 'CASE-SERVICE-DATES',
      current_actual_start_date: '2026-10-05',
      planned_start_date: '2026-10-01',
      service_data_locked: false,
      order_version: 13,
      scheduling_version: 9,
    });
    mocks.getServiceDates.mockResolvedValue({
      ...observedQuery,
      order_version: 13,
      scheduling_version: 9,
      current_version: 2,
      current_dates: ['2026-10-01', '2026-10-02', '2026-10-04'],
    });
    render(<OrderServiceDatesPanel caseNo="CASE-SERVICE-DATES" currentAssignmentPlan={{
      case_no: 'CASE-SERVICE-DATES',
      order_version: 13,
      scheduling_version: 9,
      scheduling_generation: 3,
      client_finance_version: 3,
      payroll_version: 2,
      contracted_service_days: 3,
      service_hours_per_day: 8,
      service_started: true,
      assignments: [
        {
          assignment_id: 101, candidate_key: null, staff_id: 1, sequence: 1,
          assigned_start_date: '2026-10-05', assigned_end_date: '2026-10-06',
          official_service_dates: ['2026-10-05', '2026-10-06'], actual_hours: 16,
          lineage_source_assignment_ids: [91],
        },
        {
          assignment_id: 102, candidate_key: null, staff_id: 2, sequence: 2,
          assigned_start_date: '2026-10-07', assigned_end_date: '2026-10-07',
          official_service_dates: ['2026-10-07'], actual_hours: 8,
          lineage_source_assignment_ids: [92],
        },
      ],
    }} />);

    expect(await screen.findByText('先前確認的日期與目前正式排班不同；下方日曆保留事前確認紀錄，不代表目前服務安排。')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '📅 先前確認日期（日曆紀錄）' })).toBeInTheDocument();
    expect(screen.getByText('此日曆為先前確認日期紀錄；目前服務日期請以正式排班為準。')).toBeInTheDocument();
    const readback = screen.getByLabelText('先前確認日期與目前正式排班回讀');
    expect(within(readback).getByText('先前確認日期')).toBeInTheDocument();
    expect(within(readback).getByText('2026-10-01、2026-10-02、2026-10-04')).toBeInTheDocument();
    expect(within(readback).getByText('目前正式排班服務日')).toBeInTheDocument();
    expect(within(readback).getByText('2026-10-05、2026-10-06、2026-10-07')).toBeInTheDocument();
  });

  it('任一 owner 回讀案件編號不一致時 fail closed，不執行精算或 Preview', async () => {
    mocks.getActualStart.mockResolvedValue({
      case_no: 'OTHER-CASE',
      current_actual_start_date: null,
      planned_start_date: '2026-10-01',
      service_data_locked: false,
      order_version: 11,
      scheduling_version: 7,
      scheduling_generation: 1,
      client_finance_version: 3,
      payroll_version: 2,
    });

    render(<OrderServiceDatesPanel caseNo="CASE-SERVICE-DATES" />);
    fireEvent.click(await screen.findByRole('button', { name: '精算天數並設定服務日期' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('服務日期精算回讀案件編號不一致。');
    expect(mocks.calculate).not.toHaveBeenCalled();
    expect(mocks.previewServiceDatesFlow).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: '確認服務日期' })).not.toBeInTheDocument();
  });

  it('owner Query 或精算失敗時不保留上一輪可操作狀態', async () => {
    mocks.calculate.mockRejectedValueOnce(new Error('正式精算暫時無法使用'));

    render(<OrderServiceDatesPanel caseNo="CASE-SERVICE-DATES" />);
    fireEvent.click(await screen.findByRole('button', { name: '精算天數並設定服務日期' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('正式精算暫時無法使用');
    expect(screen.queryByLabelText('建議服務日期摘要')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '確認服務日期' })).not.toBeInTheDocument();
  });

  it('使用者改動日期後會使既有 Preview 失效，必須重新 Preview', async () => {
    render(<OrderServiceDatesPanel caseNo="CASE-SERVICE-DATES" />);
    fireEvent.click(await screen.findByRole('button', { name: '精算天數並設定服務日期' }));
    await screen.findByLabelText('建議服務日期摘要');

    fireEvent.click(screen.getByRole('button', { name: '確認服務日期' }));
    await screen.findByLabelText('服務日期確認內容');
    fireEvent.click(screen.getByRole('button', { name: '服務日期 2026-10-02' }));

    expect(screen.queryByLabelText('服務日期確認內容')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '完成服務日期確認' })).not.toBeInTheDocument();
  });

  it('歷史重啟後顯示既定服務人員且不要求重新挑選候選', async () => {
    mocks.getServiceDates.mockResolvedValue({
      ...initialQuery,
      bound_staff: [{ staff_id: 12, staff_name: '王月嫂' }],
    });

    render(<OrderServiceDatesPanel caseNo="CASE-SERVICE-DATES" />);

    expect(await screen.findByText(/既定服務人員：/)).toBeInTheDocument();
    expect(screen.getByText(/王月嫂/)).toBeInTheDocument();
    expect(screen.getByText(/不需重新挑選候選或再次推薦/)).toBeInTheDocument();
  });

  it('歷史日期已確認但未排班時顯示獨立建立正式安排入口', async () => {
    mocks.getServiceDates.mockResolvedValue({
      ...initialQuery,
      current_version: 2,
      current_dates: ['2026-10-01', '2026-10-02', '2026-10-04'],
      bound_staff: [{ staff_id: 12, staff_name: '王月嫂' }],
      arrangement_pending: true,
    });

    render(<OrderServiceDatesPanel caseNo="CASE-SERVICE-DATES" />);

    expect(await screen.findByRole('region', { name: '歷史訂單建立正式安排' })).toBeInTheDocument();
    expect(screen.getByText(/排班與費率快照尚未建立/)).toBeInTheDocument();
  });

  it('正式實際開始日變更後自動重算，舊預覽失效且人工選日須明確採用新建議', async () => {
    const { rerender } = render(
      <OrderServiceDatesPanel caseNo="CASE-SERVICE-DATES" calculationRevision={0} />,
    );
    fireEvent.click(await screen.findByRole('button', { name: '精算天數並設定服務日期' }));
    await screen.findByLabelText('建議服務日期摘要');
    fireEvent.click(screen.getByRole('button', { name: '服務日期 2026-10-02' }));
    fireEvent.click(screen.getByRole('button', { name: '服務日期 2026-10-03' }));
    fireEvent.click(screen.getByRole('button', { name: '確認服務日期' }));
    await screen.findByLabelText('服務日期確認內容');

    mocks.getActualStart.mockResolvedValue({
      case_no: 'CASE-SERVICE-DATES',
      current_actual_start_date: '2026-09-28',
      planned_start_date: '2026-10-01',
      service_data_locked: false,
      order_version: 12,
      scheduling_version: 8,
      scheduling_generation: 2,
      client_finance_version: 4,
      payroll_version: 3,
    });
    mocks.getServiceDates.mockResolvedValue({
      ...initialQuery,
      order_version: 12,
      scheduling_version: 8,
      selectable_dates: ['2026-09-28', '2026-09-29', '2026-09-30'],
    });
    mocks.calculate.mockResolvedValue({
      actual_start_date: '2026-09-28',
      actual_end_date: '2026-09-30',
      target_service_days: 3,
      total_calendar_days: 3,
      actual_work_days_count: 3,
      rest_days_count: 0,
      national_holidays_found: [],
      total_estimated_salary: null,
      weekly_stats: [],
      day_by_day: [
        { date: '2026-09-28', day_num: 1, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-29', day_num: 2, is_work_day: true, is_rest_day: false, holiday_name: null },
        { date: '2026-09-30', day_num: 3, is_work_day: true, is_rest_day: false, holiday_name: null },
      ],
    });

    rerender(<OrderServiceDatesPanel caseNo="CASE-SERVICE-DATES" calculationRevision={1} />);

    expect(await screen.findByText(/已依正式實際開始日更新服務日期，請核對後再確認。/)).toBeInTheDocument();
    expect(screen.queryByLabelText('服務日期確認內容')).not.toBeInTheDocument();
    expect(screen.getByLabelText('建議服務日期摘要')).toHaveTextContent('2026-09-28');
    expect(screen.getByRole('button', { name: '確認服務日期' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '採用新建議' }));
    expect(mocks.calculate).toHaveBeenLastCalledWith({
      case_no: 'CASE-SERVICE-DATES',
      actual_start_date: '2026-09-28',
      target_service_days: 3,
      service_mode: '休周六',
    });
    expect(mocks.selectServiceDates).toHaveBeenLastCalledWith(
      'CASE-SERVICE-DATES',
      ['2026-09-28', '2026-09-29', '2026-09-30'],
    );
  });

  it('正式實際開始日變更後忽略較晚回來的舊 Preview', async () => {
    let resolveLatePreview!: (value: typeof preview) => void;
    mocks.previewServiceDatesFlow.mockReturnValue(new Promise((resolve) => {
      resolveLatePreview = resolve;
    }));
    const { rerender } = render(
      <OrderServiceDatesPanel caseNo="CASE-SERVICE-DATES" calculationRevision={0} />,
    );
    fireEvent.click(await screen.findByRole('button', { name: '精算天數並設定服務日期' }));
    await screen.findByLabelText('建議服務日期摘要');
    fireEvent.click(screen.getByRole('button', { name: '確認服務日期' }));
    await waitFor(() => expect(mocks.previewServiceDatesFlow).toHaveBeenCalledTimes(1));

    mocks.getActualStart.mockResolvedValue({
      case_no: 'CASE-SERVICE-DATES',
      current_actual_start_date: '2026-09-28',
      planned_start_date: '2026-10-01',
      service_data_locked: false,
      order_version: 12,
      scheduling_version: 8,
      scheduling_generation: 2,
      client_finance_version: 4,
      payroll_version: 3,
    });
    mocks.getServiceDates.mockResolvedValue({
      ...initialQuery,
      order_version: 12,
      scheduling_version: 8,
    });
    const previousCalculation = await mocks.calculate.mock.results[0].value;
    mocks.calculate.mockResolvedValue({ ...previousCalculation, actual_start_date: '2026-09-28', actual_end_date: '2026-09-30',
      day_by_day: ['2026-09-28', '2026-09-29', '2026-09-30'].map((date, index) => ({ date, day_num: index + 1, is_work_day: true, is_rest_day: false, holiday_name: null })),
    });
    rerender(<OrderServiceDatesPanel caseNo="CASE-SERVICE-DATES" calculationRevision={1} />);
    expect(await screen.findByText('日期基準已變更；待目前操作結果確認後，會接續更新。')).toBeInTheDocument();
    await act(async () => resolveLatePreview(preview));
    await screen.findByText(/已依正式實際開始日更新服務日期，請核對後再確認。/);

    expect(screen.queryByLabelText('服務日期確認內容')).not.toBeInTheDocument();
    expect(screen.queryByText('服務日期確認內容已準備。')).not.toBeInTheDocument();
  });

  it('Apply 後缺少正式 owner readback 時顯示失敗且不通知外層成功', async () => {
    const onObserved = vi.fn();
    mocks.getServiceDatesDraft.mockImplementation(() => (
      mocks.applyServiceDatesFlow.mock.calls.length > 0
        ? { status: 'outcome_unknown', queryView: null }
        : { status: 'observed', queryView: initialQuery }
    ));

    render(<OrderServiceDatesPanel caseNo="CASE-SERVICE-DATES" onObserved={onObserved} />);
    fireEvent.click(await screen.findByRole('button', { name: '精算天數並設定服務日期' }));
    await screen.findByLabelText('建議服務日期摘要');
    fireEvent.click(screen.getByRole('button', { name: '確認服務日期' }));
    await screen.findByLabelText('服務日期確認內容');
    fireEvent.click(screen.getByRole('button', { name: '完成服務日期確認' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('服務日期已套用，但未取得正式回讀狀態。');
    expect(onObserved).not.toHaveBeenCalled();
    expect(screen.queryByText(/服務日期已確認並回讀版本/)).not.toBeInTheDocument();
  });
});
